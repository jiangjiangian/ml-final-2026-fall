"""端到端 pipeline 和 CLI：資料 → 股票池 → 協變量 → 樣本 → 切分 → 模型 → 微調 → 預測 → 回測報告。

用法（在 repo 根目錄）：

    python -m src.twfm.pipeline --synthetic --backbone patch
    python -m src.twfm.pipeline --data-dir /kaggle/input/twfm-data --backbone kronos \
        --kronos-src /kaggle/working/Kronos --out /kaggle/working/twfm_out

套件複製成頂層的 `twfm/`（例如 Kaggle 的 `/kaggle/working/twfm`）時，改用 `python -m twfm.pipeline`。
一定要用 `-m` 跑：套件內都是相對 import，直接 `python pipeline.py` 會找不到套件。

`run_pipeline` 的輸出（都在 `cfg.out_dir`）：
- `config.json`：這次用的完整設定（`PipelineConfig.from_dict` 讀得回來）。
- `history.csv`：每個 epoch 一列（`Trainer.fit` 的紀錄）。
- `predictions_val.csv`、`predictions_test.csv`：`date, stock_id, score`（和 `q_*`），加上標籤欄。
  `final_fit=True` 時沒有 `predictions_val.csv`；`score_test=False` 時測試期的檔沒有標籤欄。
- `report.json`：驗證期、測試期的 `backtest_report`，股票池摘要，切分，樣本數，每段樣本實際的起訖日（`date_range`）。
- `checkpoints/`：`last.pt`、`best.pt`，Kaggle 一次 12 小時跑不完時從這裡接續。
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import re
import shutil
import time
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import PipelineConfig, SplitConfig, StageConfig, default_stages
from .data.align import build_covariates
from .data.dataset import PanelStore, PanelWindowDataset, SampleIndex, build_samples, make_loader
from .data.schema import (
    common_stock_mask,
    validate_calendar,
    validate_inst,
    validate_margin,
    validate_panel,
    validate_us,
)
from .data.synthetic import SyntheticMarket, make_synthetic_market
from .data.universe import build_universe, universe_audit
from .eval.backtest import backtest_report
from .eval.costs import TaiwanCostModel
from .models.model import TWFMModel, build_model
from .train.finetune import (
    Trainer,
    TrainingInterrupted,
    extract_embeddings,
    fit_ridge_probe,
    resolve_device,
    set_seed,
)
from .train.losses import CompositeLoss
from .train.walkforward import fixed_split

# 假資料的預設：每月換名單、短視窗，才有足夠的天數切成 60/20/20。
SYNTHETIC_LOOKBACK: int = 32
SYNTHETIC_UNIVERSE_LOOKBACK_DAYS: int = 40
SYNTHETIC_FRACTIONS: tuple[float, float, float] = (0.6, 0.2, 0.2)

# Kronos 在 CUDA 上訓練主幹時，每個訓練 batch 的 token 數（序列數 × lookback）上限。
# 預設 8 天 × 約 450 檔 × 128 根，lora 那階在 T4 16 GB 上一定爆記憶體（每個 block 的輸入是 fp32，
# gradient checkpointing 也要留 8 個 block 的輸入，再加重算那個 block 的中間值）。
# 1024 個 128 根的視窗約 5～6 GB，留了餘裕。沒開 gradient checkpointing 時每個 block 的中間值都要留，上限小很多。
KRONOS_CUDA_TRAIN_TOKENS: int = 1024 * 128
KRONOS_CUDA_TRAIN_TOKENS_NO_CKPT: int = 192 * 128

STATUS_DONE: str = "done"
STATUS_INTERRUPTED: str = "interrupted"
EXIT_INTERRUPTED: int = 3

_LABEL_COLS: tuple[str, ...] = ("label_r", "target_z", "exec_long_ok", "exec_short_ok")


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _log(msg: str, verbose: bool) -> None:
    if verbose:
        print(f"[twfm.pipeline] {msg}", flush=True)


def _json_default(obj: Any) -> Any:
    """`json.dump` 不認得的型別：numpy 純量和陣列、日期、路徑。"""
    if isinstance(obj, np.datetime64):
        return None if np.isnat(obj) else str(pd.Timestamp(obj))
    if isinstance(obj, pd.Timestamp):
        return None if pd.isna(obj) else str(obj)
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"{type(obj).__name__} 不能寫進 JSON")


def _write_json(obj: Any, path: Path) -> None:
    """寫 JSON。NaN 照 `json.dump` 的預設寫成 `NaN`（Python 的 `json.load` 讀得回來）。"""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=_json_default)
    tmp.replace(path)


def _n_days(samples: SampleIndex) -> int:
    return int(len(np.unique(samples.dates))) if len(samples) else 0


def _date_range(samples: SampleIndex) -> list[str | None]:
    if len(samples) == 0:
        return [None, None]
    d = np.unique(samples.dates)
    return [str(pd.Timestamp(d[0]).date()), str(pd.Timestamp(d[-1]).date())]


def _empty_samples() -> SampleIndex:
    z = np.zeros(0)
    return SampleIndex(
        dates=np.zeros(0, dtype="datetime64[ns]"),
        stock_ids=np.zeros(0, dtype=str),
        day_ids=np.zeros(0, dtype=np.int64),
        target_z=z.astype(np.float32),
        label_r=z.astype(np.float32),
        exec_long_ok=np.zeros(0, dtype=bool),
        exec_short_ok=np.zeros(0, dtype=bool),
    )


def _select(samples: SampleIndex, dates: pd.DatetimeIndex) -> SampleIndex:
    return samples.select_dates(dates) if len(dates) else _empty_samples()


# ---------------------------------------------------------------------------
# 資料
# ---------------------------------------------------------------------------


@dataclass
class MarketInputs:
    """`run_pipeline` 要的五份輸入。`us_daily`、`inst_daily`、`margin_daily` 可以是 None。"""

    panel: pd.DataFrame
    us_daily: pd.DataFrame | None
    inst_daily: pd.DataFrame | None
    margin_daily: pd.DataFrame | None
    calendar: pd.DatetimeIndex


def _read_table(data_dir: Path, name: str, required: bool) -> pd.DataFrame | None:
    """讀 `<name>.parquet`，沒有就讀 `<name>.csv`（`stock_id`、`symbol` 當字串讀，保留前面的 0）。"""
    parquet = data_dir / f"{name}.parquet"
    if parquet.exists():
        return pd.read_parquet(parquet)
    csv = data_dir / f"{name}.csv"
    if csv.exists():
        header = pd.read_csv(csv, nrows=0).columns
        dtype = {c: str for c in ("stock_id", "symbol") if c in header}
        return pd.read_csv(csv, dtype=dtype)
    if required:
        raise FileNotFoundError(f"{data_dir} 底下找不到 {name}.parquet 或 {name}.csv")
    warnings.warn(f"{data_dir} 沒有 {name}，這部分的協變量全部當成缺值", stacklevel=3)
    return None


def _read_calendar(data_dir: Path, panel: pd.DataFrame) -> pd.DatetimeIndex:
    """讀 `calendar.csv`（有 `date` 欄就用它，否則用第一欄）。沒有這個檔就用 panel 的日期。"""
    path = data_dir / "calendar.csv"
    if not path.exists():
        warnings.warn(f"{data_dir} 沒有 calendar.csv，改用 panel 出現過的日期當交易日曆", stacklevel=3)
        return pd.DatetimeIndex(np.unique(pd.to_datetime(panel["date"]).to_numpy()))
    df = pd.read_csv(path)
    col = "date" if "date" in df.columns else df.columns[0]
    return pd.DatetimeIndex(pd.to_datetime(df[col]))


def load_data_dir(data_dir: str | Path) -> MarketInputs:
    """讀 `data_dir` 底下的 `panel`、`us_daily`、`inst_daily`、`margin_daily`（parquet 或 csv）和 `calendar.csv`。

    `panel` 一定要有；其他三份沒有就當成 None（那些協變量全 0，`_isna = 1`）。
    格式見 `twfm.data.schema`。這裡只讀檔，檢查在 `run_pipeline` 裡做。
    """
    root = Path(data_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"找不到資料夾 {root}")
    panel = _read_table(root, "panel", required=True)
    assert panel is not None
    return MarketInputs(
        panel=panel,
        us_daily=_read_table(root, "us_daily", required=False),
        inst_daily=_read_table(root, "inst_daily", required=False),
        margin_daily=_read_table(root, "margin_daily", required=False),
        calendar=_read_calendar(root, panel),
    )


def _inputs_from(data: SyntheticMarket | MarketInputs) -> MarketInputs:
    return MarketInputs(
        panel=data.panel,
        us_daily=data.us_daily,
        inst_daily=data.inst_daily,
        margin_daily=data.margin_daily,
        calendar=pd.DatetimeIndex(data.calendar),
    )


def _validate(inputs: MarketInputs) -> MarketInputs:
    """全部過一次 `validate_*`，回傳整理好的新表（型別、排序、`ref_price` 補值）。"""
    return MarketInputs(
        panel=validate_panel(inputs.panel),
        us_daily=None if inputs.us_daily is None else validate_us(inputs.us_daily),
        inst_daily=None if inputs.inst_daily is None else validate_inst(inputs.inst_daily),
        margin_daily=None if inputs.margin_daily is None else validate_margin(inputs.margin_daily),
        calendar=validate_calendar(inputs.calendar),
    )


# ---------------------------------------------------------------------------
# 設定的小工具（CLI 和測試共用）
# ---------------------------------------------------------------------------


def stage_presets() -> dict[str, StageConfig]:
    """`--stages` 可以用的名字。`head`、`last_k`、`lora` 就是 `default_stages()` 那三階，另外加 `all`。"""
    presets = {s.name: s for s in default_stages()}
    presets.setdefault("all", StageConfig(name="all", trainable="all"))
    return presets


def parse_stages(spec: str, epochs: int | None = None) -> tuple[StageConfig, ...]:
    """把 `"head,last_k,lora"` 變成 `StageConfig` 的 tuple。`epochs` 有給時每一階都改成這個 epoch 數。"""
    presets = stage_presets()
    names = [s.strip() for s in str(spec).split(",") if s.strip()]
    if not names:
        raise ValueError("--stages 不能是空的")
    unknown = [n for n in names if n not in presets]
    if unknown:
        raise ValueError(f"不認得的階段 {unknown}，可以用 {sorted(presets)}")
    if len(set(names)) != len(names):
        raise ValueError(f"--stages 有重複的名字：{names}")
    stages = tuple(presets[n] for n in names)
    if epochs is not None:
        stages = tuple(dataclasses.replace(s, epochs=int(epochs)) for s in stages)
    return stages


def split_by_fraction(
    dates: Sequence[Any] | np.ndarray | pd.DatetimeIndex,
    fractions: tuple[float, float, float] = SYNTHETIC_FRACTIONS,
    embargo_days: int = 0,
) -> SplitConfig:
    """把有樣本的交易日按順序切成訓練、驗證、測試（預設 60%、20%、20%），回傳 `SplitConfig`。

    只按日期切，同一天的股票一定在同一邊。`horizon` > 1 的 embargo 由 `fixed_split` 處理。
    """
    d = pd.DatetimeIndex(np.unique(pd.to_datetime(np.asarray(dates)).to_numpy()))
    n = len(d)
    if n < 10:
        raise ValueError(f"有樣本的交易日只有 {n} 天，至少要 10 天才能切三段")
    f_train, f_val, _ = (float(x) for x in fractions)
    if not (0.0 < f_train < 1.0 and 0.0 < f_val < 1.0 and f_train + f_val < 1.0):
        raise ValueError(f"fractions 不合理：{fractions}")
    n_train = max(1, int(round(n * f_train)))
    n_val = max(1, int(round(n * f_val)))
    if n_train + n_val >= n:
        raise ValueError(f"{n} 天切 {fractions} 之後測試期是空的")

    def _s(ts: pd.Timestamp) -> str:
        return str(pd.Timestamp(ts).date())

    return SplitConfig(
        train_start=_s(d[0]),
        train_end=_s(d[n_train - 1]),
        val_start=_s(d[n_train]),
        val_end=_s(d[n_train + n_val - 1]),
        test_start=_s(d[n_train + n_val]),
        test_end=None,
        embargo_days=int(embargo_days),
    )


def synthetic_pipeline_config(
    cfg: PipelineConfig,
    market: SyntheticMarket,
    lookback: int | None = None,
    fractions: tuple[float, float, float] = SYNTHETIC_FRACTIONS,
) -> PipelineConfig:
    """假資料用的設定：每月換名單、短視窗，切分改成「有股票池的交易日」的 60/20/20。

    預設的 `yearly` 名單在 calendar 第一年沒有錨點，`lookback` 128 又再吃掉半年，
    假資料只有一年多，照原本的設定幾乎沒有訓練樣本；預設的 `SplitConfig` 日期（2004～2025）也和假資料對不上。
    所以這裡改成：
    - `universe_refresh="monthly"`、`universe_lookback_days` 最多 40、`universe_size` 不超過普通股檔數。
    - `lookback`：有給就用；沒給就是 `min(cfg.data.lookback, 32)`。
    - 切分：先用調整後的設定建一次股票池，對它的日期做 60/20/20（`split_by_fraction`）。
    其他設定（模型、微調、成本、輸出資料夾）不變。
    """
    panel = validate_panel(market.panel)
    calendar = validate_calendar(market.calendar)
    n_common = int(len(np.unique(panel["stock_id"].to_numpy()[common_stock_mask(panel["stock_id"])])))
    data_cfg = dataclasses.replace(
        cfg.data,
        universe_refresh="monthly",
        universe_lookback_days=min(int(cfg.data.universe_lookback_days), SYNTHETIC_UNIVERSE_LOOKBACK_DAYS),
        universe_size=max(1, min(int(cfg.data.universe_size), n_common)),
        lookback=int(lookback) if lookback is not None else min(int(cfg.data.lookback), SYNTHETIC_LOOKBACK),
    )
    universe = build_universe(panel, calendar, data_cfg)
    if len(universe) == 0:
        raise ValueError("假資料建不出股票池（天數太少或 lookback 太長）")
    split = split_by_fraction(universe["date"].to_numpy(), fractions, embargo_days=int(cfg.split.embargo_days))
    return dataclasses.replace(cfg, data=data_cfg, split=split)


def limit_kronos_train_batch(
    cfg: PipelineConfig, device_type: str, gradient_checkpointing: bool
) -> tuple[PipelineConfig, dict[str, Any]]:
    """Kronos 在 CUDA 上訓練主幹時，自動限制訓練 batch 的大小，避免 T4 爆記憶體。

    只在這些條件都成立時才動手：主幹是 `kronos`、裝置是 CUDA、有階段要訓練主幹（不是只有 `head`）、
    `max_stocks_per_day` 是 None（沒設過）。這時把 `max_stocks_per_day` 設成
    `max(2, token 上限 // (batch_days × lookback))`，預設 8 天、lookback 128 是每天 128 檔。
    `batch_days` 不改，所以每個 epoch 的 batch 數不變，接續訓練對得上。每天抽哪幾檔每個 epoch 重抽，
    排序損失照樣整天一起算。驗證和預測的 loader 不受影響（在 `no_grad` 裡跑，整天全部的股票）。
    `max_stocks_per_day` 已經有值時不改；超過上限只發警告。

    回傳 `(新的設定, 說明)`，說明寫進報告的 `train_batch`。
    """
    ft = cfg.finetune
    lookback = int(cfg.data.lookback)
    budget = KRONOS_CUDA_TRAIN_TOKENS if gradient_checkpointing else KRONOS_CUDA_TRAIN_TOKENS_NO_CKPT
    info: dict[str, Any] = {
        "batch_days": int(ft.batch_days),
        "max_stocks_per_day": None if ft.max_stocks_per_day is None else int(ft.max_stocks_per_day),
        "auto_limited": False,
        "token_budget": None,
    }
    trains_backbone = any(s.trainable != "head" for s in ft.stages)
    if cfg.model.backbone != "kronos" or device_type != "cuda" or not trains_backbone:
        return cfg, info
    info["token_budget"] = int(budget)
    if ft.max_stocks_per_day is not None:
        tokens = int(ft.batch_days) * int(ft.max_stocks_per_day) * lookback
        if tokens > budget:
            warnings.warn(
                f"訓練 batch 最多 {ft.batch_days} 天 × {ft.max_stocks_per_day} 檔 × {lookback} 根 = {tokens:,} 個 token，"
                f"超過建議的 {budget:,}，Kronos 在 T4 上可能爆記憶體",
                stacklevel=2,
            )
        return cfg, info
    cap = max(2, budget // (int(ft.batch_days) * lookback))
    info["max_stocks_per_day"] = int(cap)
    info["auto_limited"] = True
    new_ft = dataclasses.replace(ft, max_stocks_per_day=int(cap))
    return dataclasses.replace(cfg, finetune=new_ft), info


def parse_stock_list(spec: str) -> tuple[str, ...]:
    """`--competition-stocks` 的值變成股票代號的 tuple（去重、保留順序）。

    可以是逗號分隔的代號（`2330,2317,2454`），或一個檔案的路徑：`.csv` 有 `stock_id` 欄就用它，
    否則用第一欄；其他副檔名是空白、換行或逗號分隔的代號。代號一律當字串，保留前面的 0。
    """
    text = str(spec).strip()
    path = Path(text)
    items: list[str]
    # 很長的逗號清單當成路徑時，`is_file` 可能丟「檔名太長」的 OSError，那就不是檔案。
    try:
        is_file = bool(text) and path.is_file()
    except OSError:
        is_file = False
    if is_file:
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path, dtype=str)
            if df.shape[1] == 0:
                raise ValueError(f"{path} 沒有任何欄")
            col = "stock_id" if "stock_id" in df.columns else df.columns[0]
            items = df[col].dropna().astype(str).tolist()
        else:
            items = re.split(r"[\s,]+", path.read_text(encoding="utf-8"))
    else:
        items = text.split(",")
    ids = tuple(dict.fromkeys(x.strip() for x in items if x.strip()))
    if not ids:
        raise ValueError(f"--competition-stocks 讀不到任何股票代號：{spec!r}")
    return ids


# ---------------------------------------------------------------------------
# 輸出
# ---------------------------------------------------------------------------


def _with_labels(pred: pd.DataFrame, samples: SampleIndex) -> pd.DataFrame:
    """預測接上標籤欄（`label_r, target_z, exec_long_ok, exec_short_ok`），用 `(date, stock_id)` 對。"""
    labels = samples.to_frame()
    cols = ["date", "stock_id", *[c for c in _LABEL_COLS if c in labels.columns]]
    out = pred.merge(labels[cols], on=["date", "stock_id"], how="left", validate="one_to_one")
    return out


def _write_predictions(pred: pd.DataFrame, samples: SampleIndex, path: Path) -> None:
    frame = _with_labels(pred, samples)
    frame.to_csv(path, index=False, date_format="%Y-%m-%d")


def _copy_checkpoints(src: Path, dst: Path, verbose: bool) -> None:
    """把上一次的 `last.pt`、`best.pt` 複製到可寫的 `dst`（Kaggle 的 input 是唯讀的）。

    `src` 可以是放 checkpoint 的資料夾，或上一次的 `out_dir`（底下有 `checkpoints/`）。
    """
    src = Path(src)
    if (src / "checkpoints" / "last.pt").exists():
        src = src / "checkpoints"
    if not (src / "last.pt").exists():
        raise FileNotFoundError(f"{src} 底下沒有 last.pt，沒辦法接續")
    dst.mkdir(parents=True, exist_ok=True)
    if src.resolve() == dst.resolve():
        return
    for name in ("last.pt", "best.pt"):
        if (src / name).exists():
            shutil.copy2(src / name, dst / name)
            _log(f"複製 {src / name} → {dst / name}", verbose)


# ---------------------------------------------------------------------------
# linear probe
# ---------------------------------------------------------------------------


def _probe_frame(samples: SampleIndex, idx: np.ndarray, score: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"date": samples.dates[idx], "stock_id": samples.stock_ids[idx], "score": score})


def _run_probe(
    model: TWFMModel,
    loaders: dict[str, Any],
    samples: dict[str, SampleIndex],
    device: Any,
    cost_model: TaiwanCostModel,
    out_dir: Path,
    verbose: bool,
    report_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """凍結主幹算 embedding，用 ridge 閉式解當 linear probe（只用主幹的表示，不含協變量）。

    訓練用 `target_z`，alpha 用驗證期每天 RankIC 選。報告格式和主模型一樣（`backtest_report`）。
    """
    t0 = time.time()
    rk: dict[str, Any] = dict(report_kwargs or {})
    x_tr, i_tr = extract_embeddings(model, loaders["train_full"], device)
    x_va, i_va = extract_embeddings(model, loaders["val"], device)
    s_tr, s_va = samples["train"], samples["val"]
    probe = fit_ridge_probe(
        x_tr,
        s_tr.target_z[i_tr],
        X_val=x_va,
        y_val=s_va.label_r[i_va],
        day_val=s_va.day_ids[i_va],
    )
    del x_tr
    out: dict[str, Any] = {
        "alpha": float(probe.alpha),
        "val_rank_ic_by_alpha": {f"{a:g}": float(v) for a, v in probe.val_rank_ic.items()},
        "n_train": int(probe.n_train),
    }
    pred_va = _probe_frame(s_va, i_va, probe.predict(x_va))
    _write_predictions(pred_va, s_va, out_dir / "probe_predictions_val.csv")
    out["val"] = backtest_report(pred_va, s_va.to_frame(), cost_model, **rk)
    if loaders.get("test") is not None:
        s_te = samples["test"]
        x_te, i_te = extract_embeddings(model, loaders["test"], device)
        pred_te = _probe_frame(s_te, i_te, probe.predict(x_te))
        _write_predictions(pred_te, s_te, out_dir / "probe_predictions_test.csv")
        out["test"] = backtest_report(pred_te, s_te.to_frame(), cost_model, **rk)
    else:
        out["test"] = None
    out["seconds"] = time.time() - t0
    _log(f"linear probe：alpha {probe.alpha:g}，驗證 RankIC {out['val']['rank_ic']['mean']:.5f}", verbose)
    return out


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def run_pipeline(
    cfg: PipelineConfig,
    data: SyntheticMarket | MarketInputs | None = None,
    data_dir: str | None = None,
    max_train_days: int | None = None,
    *,
    resume: bool = False,
    resume_from: str | None = None,
    max_seconds: float | None = None,
    probe: bool = False,
    gradient_checkpointing: bool | None = None,
    competition_stocks: Sequence[str] | None = None,
    final_fit: bool = False,
    score_test: bool = True,
    stop_after: tuple[int, int] | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """端到端跑一次，回傳報告（也寫進 `cfg.out_dir/report.json`）。

    資料二選一：`data`（`SyntheticMarket` 或 `MarketInputs`）或 `data_dir`（見 `load_data_dir`）。

    步驟：`validate_*` → `build_universe` → `build_samples`（只建一次）→ `fixed_split` → 每段 `select_dates`
    → `build_covariates`（只算用得到的日期）→ `PanelStore`、Dataset、loader → `build_model` → `Trainer.fit`
    → `predict` 驗證和測試 → `backtest_report`。

    參數：
    - `max_train_days`：只留訓練期最後這麼多個交易日（smoke 和快速試跑用）。
    - `resume`：從 `out_dir/checkpoints/last.pt` 接續。`resume_from`：先把別處的 `last.pt`、`best.pt`
      複製到 `out_dir/checkpoints/` 再接續（Kaggle 上一次的輸出是唯讀的）。
    - `max_seconds`：整個 pipeline 的時間預算（秒，從進入這個函式算）。扣掉資料準備的時間後交給 `Trainer`，
      訓練超過就存 `last.pt` 停下，報告的 `status` 是 `"interrupted"`，沒有預測。預測本身也要時間，預算要留餘裕。
    - `probe`：訓練前先用凍結主幹的 embedding 做 ridge linear probe，結果在報告的 `probe`。
    - `gradient_checkpointing`：None 時 Kronos 在 CUDA 上自動打開（省記憶體），其他情況關掉。
    - Kronos 在 CUDA 上訓練主幹、又沒設 `max_stocks_per_day` 時，會自動設一個上限（見
      `limit_kronos_train_batch`）。`config.json` 寫的是調整後的設定，報告的 `train_batch` 有說明。
    - `competition_stocks`：比賽的股票代號（例如 50 檔）。有給時報告的 `competition` 只用這些股票算，
      才能和 c2v2d 的每天分數直接比；沒給時是整個股票池。
    - `cfg.data.horizon` > 1 時，報告改用每 h 天調整一次的 `hold_h` 回測，沒有比賽分數（見 `backtest_report`）。
    - `final_fit`：最後重訓。驗證期併進訓練期，`Trainer` 不拿驗證集挑 epoch（每階跑滿設定的 epoch 數，
      最後一個 epoch 的權重就是結果），也不寫驗證期的預測（那是樣本內）。不能和 `probe` 一起用。
    - `score_test`：False 時測試期只寫 `date, stock_id, score`（和 `q_*`），不接標籤、不算 `backtest_report`，
      報告的 `test` 是 `{"hidden": True, ...}`。給「測試期只開一次」的研究：分數先存好，之後另一本一次算。
    - `stop_after`：`(階段, epoch)`，跑完那個 epoch 就停（見 `Trainer.fit`）。最後重訓照驗證期挑到的點停，
      學習率排程仍照設定的 epoch 數排，和驗證期那次走的路一樣（每個 epoch 的步數因為多了驗證期而變多）。
      這要一個條件：驗證期那次，停點之前的每一階都跑滿設定的 epoch 數（沒有被 early stop 截掉），
      而且那一階的最後一個 epoch 就是當時最好的（`history.csv` 的 `is_best`）。驗證期每一階從當時最好的權重開始；
      最後重訓沒有驗證集，每一階從上一階的最後一個 epoch 開始。條件不成立時兩條路不同，呼叫的人要先檢查。
    - 報告的 `date_range`：訓練、驗證、測試三段樣本實際的第一天和最後一天（股票池和 lookback 會讓它晚於切分的日期）。
    """
    if final_fit and probe:
        raise ValueError("final_fit 不能和 probe 一起用（probe 要拿驗證集挑 ridge 的 alpha）")
    t_start = time.time()
    out_dir = Path(cfg.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    device = resolve_device(cfg.device)
    if gradient_checkpointing is None:
        gradient_checkpointing = cfg.model.backbone == "kronos" and device.type == "cuda"
    cfg, train_batch = limit_kronos_train_batch(cfg, device.type, bool(gradient_checkpointing))
    if train_batch["auto_limited"]:
        _log(
            f"Kronos 在 CUDA 上訓練主幹：訓練時每天最多抽 {train_batch['max_stocks_per_day']} 檔"
            f"（{cfg.finetune.batch_days} 天一個 batch，token 上限 {train_batch['token_budget']:,}），"
            "要改就給 --max-stocks-per-day",
            verbose,
        )
    _write_json(cfg.to_dict(), out_dir / "config.json")
    ft = cfg.finetune
    comp_ids = None if competition_stocks is None else [str(x) for x in competition_stocks]
    report_kwargs: dict[str, Any] = {"horizon": int(cfg.data.horizon), "competition_stocks": comp_ids}

    # 1. 資料
    if (data is None) == (data_dir is None):
        raise ValueError("data 和 data_dir 要剛好給一個")
    raw = _inputs_from(data) if data is not None else load_data_dir(str(data_dir))
    inputs = _validate(raw)
    del raw
    panel = inputs.panel
    cal = inputs.calendar
    _log(f"資料：panel {len(panel):,} 列、{panel['stock_id'].nunique():,} 檔、交易日 {len(cal):,} 天", verbose)

    # 2. 股票池和樣本（樣本只建一次，之後按日期切）
    universe = build_universe(panel, cal, cfg.data)
    if len(universe) == 0:
        raise ValueError("股票池是空的：檢查 calendar 是否涵蓋 panel、lookback 和 universe_* 設定")
    samples = build_samples(panel, universe, cal, cfg.data)
    _log(f"股票池 {len(universe):,} 組 (t, 股票)，有標籤的樣本 {len(samples):,} 個", verbose)

    # 3. 切分
    split = fixed_split(cal, cfg.split, horizon=int(cfg.data.horizon))
    train_dates = split.train_dates.union(split.val_dates) if final_fit else split.train_dates
    train_s = _select(samples, train_dates)
    val_s = _select(samples, split.val_dates)
    test_s = _select(samples, split.test_dates)
    if max_train_days is not None:
        if int(max_train_days) < 1:
            raise ValueError(f"max_train_days 至少 1，拿到 {max_train_days}")
        days = np.unique(train_s.dates)
        if len(days) > int(max_train_days):
            train_s = train_s.select_dates(days[-int(max_train_days) :])
    if len(train_s) == 0:
        raise ValueError(f"訓練期沒有樣本：{split.summary()}")
    if len(val_s) == 0:
        raise ValueError(f"驗證期沒有樣本：{split.summary()}")
    if len(test_s) == 0:
        warnings.warn("測試期沒有樣本，只做驗證期的預測和報告", stacklevel=2)
    del samples
    for name, s in (("訓練", train_s), ("驗證", val_s), ("測試", test_s)):
        rng = _date_range(s)
        _log(f"{name}：{_n_days(s)} 天、{len(s):,} 個樣本（{rng[0]} ～ {rng[1]}）", verbose)

    # 4. 協變量（只算三段用得到的日期）
    parts = [s for s in (train_s, val_s, test_s) if len(s)]
    target_dates = pd.DatetimeIndex(np.unique(np.concatenate([s.dates for s in parts])))
    t0 = time.time()
    stock_cov, market_cov = build_covariates(
        panel,
        inputs.us_daily,
        inputs.inst_daily,
        inputs.margin_daily,
        target_dates,
        cal,
        cfg.data,
        universe=universe,
    )
    _log(
        f"協變量：個股 {stock_cov.shape[1]} 欄、市場 {market_cov.shape[1]} 欄，{time.time() - t0:.0f} 秒",
        verbose,
    )

    # 5. Dataset 和 loader
    stock_ids = np.unique(np.concatenate([s.stock_ids for s in parts]))
    store = PanelStore(panel, stock_ids=stock_ids.tolist())
    audit = universe_audit(universe, panel)
    # 長表之後用不到，先放掉（DataLoader 的 worker 會 fork 這個行程）。
    del panel, universe, inputs
    lookback = int(cfg.data.lookback)
    ds_train = PanelWindowDataset(store, train_s, stock_cov, market_cov, lookback)
    ds_val = PanelWindowDataset(store, val_s, stock_cov, market_cov, lookback)
    ds_test = PanelWindowDataset(store, test_s, stock_cov, market_cov, lookback) if len(test_s) else None
    n_stock_cov = len(ds_train.stock_cov_cols)
    n_market_cov = len(ds_train.market_cov_cols)
    del stock_cov, market_cov
    seed = int(ft.seed)
    workers = int(ft.num_workers)
    train_loader = make_loader(
        ds_train, train_s.day_ids, ft.batch_days, True, seed, workers, ft.max_stocks_per_day
    )
    val_loader = make_loader(ds_val, val_s.day_ids, ft.batch_days, False, seed, workers, None)
    test_loader = (
        make_loader(ds_test, test_s.day_ids, ft.batch_days, False, seed, workers, None) if ds_test is not None else None
    )

    # 6. 模型
    set_seed(seed)
    model = build_model(cfg, n_stock_cov, n_market_cov, gradient_checkpointing=bool(gradient_checkpointing))
    cost_model = TaiwanCostModel(cfg.cost)
    _log(
        f"模型：{cfg.model.backbone}（d_model {model.backbone.d_model}），裝置 {device}，"
        f"gradient checkpointing {'開' if gradient_checkpointing else '關'}",
        verbose,
    )

    report: dict[str, Any] = {
        "status": STATUS_DONE,
        "backbone": cfg.model.backbone,
        "device": str(device),
        "split": split.summary(),
        "n_samples": {"train": len(train_s), "val": len(val_s), "test": len(test_s)},
        "n_days": {"train": _n_days(train_s), "val": _n_days(val_s), "test": _n_days(test_s)},
        "date_range": {"train": _date_range(train_s), "val": _date_range(val_s), "test": _date_range(test_s)},
        "n_stock_cov": n_stock_cov,
        "n_market_cov": n_market_cov,
        "stock_cov_cols": list(ds_train.stock_cov_cols),
        "market_cov_cols": list(ds_train.market_cov_cols),
        "universe_audit": audit.to_dict(orient="records"),
        "train_batch": train_batch,
        "horizon": int(cfg.data.horizon),
        "competition_stocks": comp_ids,
        "final_fit": bool(final_fit),
        "score_test": bool(score_test),
        "stop_after": None if stop_after is None else [int(x) for x in stop_after],
        "probe": None,
        "best": None,
        "val": None,
        "test": None,
    }

    # 7. linear probe（選用）
    if probe:
        probe_loaders = {
            "train_full": make_loader(ds_train, train_s.day_ids, ft.batch_days, False, seed, workers, None),
            "val": val_loader,
            "test": test_loader,
        }
        report["probe"] = _run_probe(
            model,
            probe_loaders,
            {"train": train_s, "val": val_s, "test": test_s},
            device,
            cost_model,
            out_dir,
            verbose,
            report_kwargs=report_kwargs,
        )

    # 8. 微調
    loss_fn = CompositeLoss(ft.loss_weights, ft.huber_delta, ft.listnet_temperature, cfg.model.quantiles)
    ckpt_dir = out_dir / "checkpoints"
    if resume_from is not None:
        _copy_checkpoints(Path(resume_from), ckpt_dir, verbose)
        resume = True
    # max_seconds 是整個 pipeline 的時間預算，扣掉資料準備（和 probe）已經用掉的時間才給 Trainer。
    fit_budget = None if max_seconds is None else max(60.0, float(max_seconds) - (time.time() - t_start))
    trainer = Trainer(
        model,
        loss_fn,
        ft,
        device,
        checkpoint_dir=ckpt_dir,
        max_seconds=fit_budget,
        verbose=verbose,
    )
    try:
        if final_fit:
            history = trainer.fit(train_loader, None, None, resume=resume, stop_after=stop_after)
        else:
            history = trainer.fit(train_loader, val_loader, val_s, resume=resume, stop_after=stop_after)
    except TrainingInterrupted as exc:
        _log(str(exc), verbose)
        history = list(trainer.history)
        report["status"] = STATUS_INTERRUPTED
    pd.DataFrame(history).to_csv(out_dir / "history.csv", index=False)
    if trainer.has_best:
        report["best"] = {
            "stage_idx": int(trainer.best_stage),
            "stage": cfg.finetune.stages[trainer.best_stage].name if trainer.best_stage >= 0 else None,
            "epoch": int(trainer.best_epoch),
            "val_rank_ic": float(trainer.best_score) if math.isfinite(trainer.best_score) else float("nan"),
        }

    # 9. 預測和報告
    if report["status"] == STATUS_DONE:
        if not final_fit:
            pred_val = trainer.predict(val_loader, val_s)
            _write_predictions(pred_val, val_s, out_dir / "predictions_val.csv")
            report["val"] = backtest_report(pred_val, val_s.to_frame(), cost_model, **report_kwargs)
        if test_loader is not None:
            pred_test = trainer.predict(test_loader, test_s)
            if score_test:
                _write_predictions(pred_test, test_s, out_dir / "predictions_test.csv")
                report["test"] = backtest_report(pred_test, test_s.to_frame(), cost_model, **report_kwargs)
            else:
                hidden = pred_test.drop(columns=[c for c in _LABEL_COLS if c in pred_test.columns])
                hidden.to_csv(out_dir / "predictions_test.csv", index=False, date_format="%Y-%m-%d")
                report["test"] = {"hidden": True, "n_rows": int(len(hidden)), "n_days": _n_days(test_s)}
    report["seconds"] = time.time() - t_start
    _write_json(report, out_dir / "report.json")
    _log(f"完成（{report['status']}），{report['seconds']:.0f} 秒，輸出在 {out_dir}", verbose)
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=f"python -m {__package__ or 'twfm'}.pipeline",
        description="台股時序基礎模型的微調 pipeline（研究用）。資料用 --synthetic 或 --data-dir 二選一。",
    )
    p.add_argument("--config", help="PipelineConfig 的 JSON 檔（可以只寫要改的欄）")
    p.add_argument("--synthetic", action="store_true", help="用假資料（自動每月換名單、60/20/20 切分）")
    p.add_argument("--data-dir", help="放 panel.parquet、us_daily.parquet、inst_daily.parquet、margin_daily.parquet、calendar.csv 的資料夾")
    p.add_argument("--backbone", choices=["kronos", "patch"], help="主幹")
    p.add_argument("--kronos-src", help="clone 下來的 shiyu-coder/Kronos 根目錄（也可以設環境變數 KRONOS_SRC）")
    p.add_argument("--stages", help="微調的階段，逗號分隔，例如 head,last_k,lora（可用 head、last_k、lora、all）")
    p.add_argument("--epochs", type=int, help="每一階的 epoch 數")
    p.add_argument("--batch-days", type=int, help="每個 batch 幾個交易日")
    p.add_argument("--lookback", type=int, help="視窗長度（列數）")
    p.add_argument("--device", help="auto、cuda、cpu")
    p.add_argument("--out", help="輸出資料夾（PipelineConfig.out_dir）")
    p.add_argument("--max-train-days", type=int, help="只用訓練期最後這麼多個交易日")
    p.add_argument("--num-workers", type=int, help="DataLoader 的 worker 數")
    p.add_argument("--max-stocks-per-day", type=int, help="訓練時每天最多抽幾檔（省 GPU 記憶體）")
    p.add_argument("--seed", type=int, help="亂數種子（FinetuneConfig.seed）")
    p.add_argument("--amp-dtype", choices=["auto", "fp16", "bf16"], help="CUDA 混合精度（auto：A100 用 bf16，T4 用 fp16）")
    p.add_argument("--probe", action="store_true", help="訓練前先做凍結主幹的 ridge linear probe")
    p.add_argument("--final-fit", action="store_true", help="最後重訓：驗證期併進訓練期，不挑 epoch，不寫驗證期預測")
    p.add_argument("--hide-test-labels", action="store_true", help="測試期只寫分數，不接標籤、不算報告")
    p.add_argument(
        "--competition-stocks",
        help="比賽的股票代號：逗號分隔（2330,2317,...）或檔案路徑（csv 用 stock_id 欄，其他一行一檔）；"
        "有給時報告的 competition 只用這些股票算",
    )
    p.add_argument("--grad-ckpt", action=argparse.BooleanOptionalAction, default=None, help="gradient checkpointing（預設 Kronos 在 CUDA 上打開）")
    p.add_argument("--resume", action="store_true", help="從 <out>/checkpoints/last.pt 接續")
    p.add_argument("--resume-from", help="先把這個資料夾的 last.pt、best.pt 複製到 <out>/checkpoints/ 再接續")
    p.add_argument("--max-hours", type=float, help="訓練超過幾小時就存檔停下（Kaggle 一次 12 小時，建議 11）")
    p.add_argument("--synthetic-stocks", type=int, default=60, help="假資料的普通股檔數")
    p.add_argument("--synthetic-days", type=int, default=420, help="假資料的交易日數")
    p.add_argument("--synthetic-seed", type=int, default=0, help="假資料的亂數種子")
    p.add_argument("--quiet", action="store_true", help="不印進度")
    return p


def apply_cli_overrides(cfg: PipelineConfig, args: argparse.Namespace) -> PipelineConfig:
    """把命令列參數蓋到設定上。沒給的參數不動（保留 `--config` 或預設值）。"""
    model = cfg.model
    if args.backbone is not None:
        model = dataclasses.replace(model, backbone=args.backbone)
    if args.kronos_src is not None:
        model = dataclasses.replace(model, kronos_src_dir=args.kronos_src)
    data = cfg.data
    if args.lookback is not None:
        data = dataclasses.replace(data, lookback=int(args.lookback))
    ft = cfg.finetune
    stages = parse_stages(args.stages) if args.stages else ft.stages
    if args.epochs is not None:
        stages = tuple(dataclasses.replace(s, epochs=int(args.epochs)) for s in stages)
    ft_kwargs: dict[str, Any] = {"stages": stages}
    if args.batch_days is not None:
        ft_kwargs["batch_days"] = int(args.batch_days)
    if args.num_workers is not None:
        ft_kwargs["num_workers"] = int(args.num_workers)
    if args.max_stocks_per_day is not None:
        ft_kwargs["max_stocks_per_day"] = int(args.max_stocks_per_day)
    if args.seed is not None:
        ft_kwargs["seed"] = int(args.seed)
    if getattr(args, "amp_dtype", None) is not None:
        ft_kwargs["amp_dtype"] = str(args.amp_dtype)
    ft = dataclasses.replace(ft, **ft_kwargs)
    top: dict[str, Any] = {}
    if args.device is not None:
        top["device"] = str(args.device)
    if args.out is not None:
        top["out_dir"] = str(args.out)
    return dataclasses.replace(cfg, data=data, model=model, finetune=ft, **top)


def _fmt(x: Any) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "NaN"
    return f"{v:.5f}" if math.isfinite(v) else "NaN"


def _print_summary(report: dict[str, Any]) -> None:
    for part in ("val", "test"):
        r = report.get(part)
        if not r:
            continue
        hh = (r.get("modes") or {}).get("half_half", {})
        net = hh.get("net_mean_by_discount", {})
        comp = r.get("competition")
        comp_txt = _fmt(comp["mean"]) if comp else "不算（horizon > 1）"
        scope = "比賽股票" if r.get("competition_scope") == "stock_ids" else "整個股票池"
        per = "每天" if int(r.get("horizon", 1)) == 1 else f"每 {int(r['horizon'])} 天"
        print(
            f"[twfm.pipeline] {part}：RankIC {_fmt(r['rank_ic']['mean'])}（t_nw {_fmt(r['rank_ic']['t_nw'])}），"
            f"比賽分數（{scope}）{comp_txt}，half_half {per}淨報酬 "
            + "、".join(f"折扣 {k} {_fmt(v)}" for k, v in net.items()),
            flush=True,
        )


def main(argv: list[str] | None = None) -> int:
    """命令列入口。完成回傳 0；超過 `--max-hours` 存檔停下回傳 3（用 `--resume` 接續）。"""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.synthetic == (args.data_dir is not None):
        parser.error("--synthetic 和 --data-dir 要剛好給一個")
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            cfg = PipelineConfig.from_dict(json.load(f))
    else:
        cfg = PipelineConfig()
    try:
        cfg = apply_cli_overrides(cfg, args)
    except ValueError as exc:
        parser.error(str(exc))

    competition_stocks: tuple[str, ...] | None = None
    if args.competition_stocks:
        try:
            competition_stocks = parse_stock_list(args.competition_stocks)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))

    data: SyntheticMarket | None = None
    if args.synthetic:
        data = make_synthetic_market(
            n_stocks=int(args.synthetic_stocks), n_days=int(args.synthetic_days), seed=int(args.synthetic_seed)
        )
        cfg = synthetic_pipeline_config(cfg, data, lookback=args.lookback)

    report = run_pipeline(
        cfg,
        data=data,
        data_dir=args.data_dir,
        max_train_days=args.max_train_days,
        resume=bool(args.resume),
        resume_from=args.resume_from,
        max_seconds=None if args.max_hours is None else float(args.max_hours) * 3600.0,
        probe=bool(args.probe),
        gradient_checkpointing=args.grad_ckpt,
        competition_stocks=competition_stocks,
        final_fit=bool(args.final_fit),
        score_test=not bool(args.hide_test_labels),
        verbose=not args.quiet,
    )
    _print_summary(report)
    if report["status"] != STATUS_DONE:
        print(f"[twfm.pipeline] 訓練中斷，已存 {Path(cfg.out_dir) / 'checkpoints' / 'last.pt'}，加 --resume 接續", flush=True)
        return EXIT_INTERRUPTED
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
