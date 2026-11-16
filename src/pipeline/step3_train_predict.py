"""第 3 步：訓練和預測。照 config 的 daily_model 選模型，用 t 之前的答案訓練，預測 t 的每一檔。

    load_model_input(cfg)                          → 所有模型共用的輸入表
    train_and_predict(cfg, data, dates, stocks, log) → （用了哪個模型, 預測表）
    save_scores(cfg, pred, t, model_name, log)     → data/submission/scores_<t>.csv（只給研究用）
    log_direction(pred, model_name, log)           → c2、c2v2d 當天押的大盤方向寫進 log

模型在 src/models/，名字和檔案的對照是 src/models/__init__.py 的 MODEL_KINDS。每個模型都在 predict 裡從頭訓練，
不讀也不寫 repo 根目錄的 models/。
模型開關（使用者 2026-11-12）：config 的 daily_model.kind 是主模型，fallback 是它丟錯時照順序換的備援。
"""

import importlib
from pathlib import Path

from src.models import MODEL_KINDS
from src.models import m1_online_lr as online_lr
from src.pipeline import step1_crawler as crawler, utils


class ModelChoiceError(RuntimeError):
    """config 的 daily_model.kind 不能用。"""


def load_model_input(cfg: dict):
    """特徵表（data/processed/）接上個股特徵（盤中報酬的 lag 等），date 是 Timestamp。

    每個模型的 predict 都吃這張表；讀法是 m1_online_lr.load_data（最早的模型留下來的，所有模型共用）。
    這一步失敗整次就停下，因為沒有模型能用。
    """
    return online_lr.load_data(cfg)


def phase1_score(pred, data) -> float:
    """Phase 1（84 天回測）的本機官方分數，只寫進 log。"""
    return online_lr.official_score(pred, data)


def model_order(cfg: dict, log) -> list:
    """主模型加上備援，照要試的順序。主模型不認得或填 none 就丟 ModelChoiceError（不默默換備援）；
    fallback 可以是一個名字或一串名字，none 代表沒有備援，不認得或重複的名字記一行 ERROR 後跳過。
    沒有 daily_model 這個設定時用 online_lr。"""
    choice = cfg.get("daily_model") or {}
    kind = choice.get("kind", "online_lr")
    if kind not in MODEL_KINDS:
        raise ModelChoiceError(f"daily_model.kind 只能填 {list(MODEL_KINDS)}：{kind}")
    fallback = choice.get("fallback") or []
    order = [kind]
    for name in [fallback] if isinstance(fallback, str) else list(fallback):
        if str(name).lower() == "none":
            continue
        if name not in MODEL_KINDS or name in order:
            log.error("daily_model.fallback 的 %s 不認得或重複，跳過（可以填 %s）", name, list(MODEL_KINDS))
            continue
        order.append(name)
    return order


def load_model(kind: str):
    """MODEL_KINDS 的「模組:函式」→ 那個 predict 函式。用到才 import：檔案壞掉也只影響這個模型。"""
    module, _, function = MODEL_KINDS[kind].partition(":")
    return getattr(importlib.import_module(module), function or "predict")


def train_and_predict(cfg: dict, data, dates: list, stocks: list, log) -> tuple:
    """照 model_order 一個一個試，回傳第一個算得出來的（模型名稱, 預測表）。

    輸入：data 是 load_model_input 的表；dates 是要預測的日子；stocks 是網站範本的股票代號。
    輸出：模型名稱（用了備援時寫成「online_lr（rank_ensemble 的備援）」）和預測表（date、stock_id、pred，
          通常還有 prob 和各模型自己的欄）。
    模型丟錯時記一行 ERROR、換下一個，當天照樣交件；最後一個也丟錯就把那個錯往上丟。
    """
    order = model_order(cfg, log)
    for position, kind in enumerate(order):
        try:
            pred = load_model(kind)(data, cfg, dates, stocks)
            return (kind if position == 0 else f"{kind}（{order[0]} 的備援）"), pred
        except Exception as e:
            if position == len(order) - 1:
                raise
            log.error("%s 算不出來（%s），改用 %s", kind, public_reason(e), order[position + 1])


def public_reason(e: BaseException) -> str:
    """模型的錯誤訊息（模型不連網站，不會帶伺服器內容）。路徑換成相對的：log 會推上 GitHub，不寫出主機的家目錄。"""
    message = str(e).replace(str(utils.ROOT), ".").replace(str(Path.home()), "~")
    return f"{type(e).__name__}: {message[:300]}"


def save_scores(cfg: dict, pred, t: str, model_name: str, log) -> None:
    """另存當天每檔的分數（使用者 2026-11-15），給每週重算成本和組員核對用。失敗只記警告，不影響上傳。

    檔名 scores_<t>.csv，放在 config 的 data.submission_dir。欄是模型輸出的全部欄（rank_ensemble 是 ridge、
    kridge、lgbm、prob、pred；c2、c2v2d 多 combined、beta_rank、p_up、tilt、score、variant 等），
    加上 model（用了哪個模型）和 rank（1～50，照 prob 排，同分時代號大的名次高）。
    """
    try:
        keep = pred.sort_values(["date", "stock_id"]).copy()
        if "prob" in keep:
            keep["rank"] = keep.groupby("date")["prob"].rank(method="first").astype(int)
        keep.insert(2, "model", model_name)
        path = utils.ROOT / cfg["data"]["submission_dir"] / f"scores_{t}.csv"
        crawler.write_atomic(path, keep.to_csv(index=False).encode("utf-8"))
        log.info("另存 %s（每檔的分數，只給研究用）", path.relative_to(utils.ROOT))
    except Exception as e:
        log.warning("每檔分數沒存成（%s），不影響上傳", short_reason(e))


def log_direction(pred, model_name: str, log) -> None:
    """c2、c2v2d 的預測表有 p_up：把當天押的大盤方向寫進 log（每檔的分數在 scores_<t>.csv）。只是記錄，不丟錯。"""
    if "p_up" not in pred:
        return
    try:
        log.info("模型 %s：大盤方向 p = %.3f，傾斜 %+.3f，和 rank_ensemble 換了 %d 組，狀態缺 %d 個，重訓日 %s",
                 model_name, pred["p_up"].iloc[0], pred["tilt"].iloc[0],
                 int((pred["pred"] != pred["base_pred"]).sum() // 2), int(pred["missing_states"].iloc[0]),
                 pred["fit_day"].iloc[0])
    except Exception as e:
        log.warning("方向的紀錄沒寫成（%s）", short_reason(e))


def short_reason(e: BaseException) -> str:
    """和 run_daily.describe 一樣：自己寫的錯誤（RuntimeError、ValueError）印出訊息，其他只寫類別。"""
    return f"{type(e).__name__}: {str(e)[:300]}" if isinstance(e, (RuntimeError, ValueError)) else type(e).__name__
