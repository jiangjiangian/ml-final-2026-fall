"""N1 影子跑（使用者 2026-11-23）：JS_ONLINE 每天早上補更新、預測 t，再和 c2v2d 的三個成員組成 N1。只記不交。

N1 = k_t·comb4 + 2(2p − 1)·β̃（UB 01 的公式）：comb4 是 c2v2d 的 ridge、kernel ridge、LightGBM 加 JS_ONLINE 四個
當天名次 − 0.5 的平均，k_t = SD(comb3) ÷ SD(comb4) 把尺度對齊回三個成員，p、β̃、γ = 2 照 c2v2d。前一半猜漲。
JS_ONLINE 是 Kaggle KD 05 凍結的 MLP（54 個輸入 → 256 → 128 → 3，5 個種子），每天用前一個交易日的答案更新一步。

怎麼跑：run_daily.py 收尾時用 n1 自己的環境（.venv-n1，requirements-n1.txt）以子程序執行，失敗只記 WARNING：
    .venv-n1/bin/python -m src.models.m7_n1_js_online --date 2026-11-24
不在 src/models/__init__.py 的 MODEL_KINDS（不能填在 kind、fallback、shadow），不 import src.pipeline，不讀 config：
設定都由命令列傳進來。只 import 標準函式庫、numpy、pandas、scipy、torch。

逐位元重現 Kaggle UB 04（bt/src/ub04.txt，第 5 版）：讀檔、面板、特徵、網路、更新、N1 的函式照原樣搬，
只把全域的股票清單改成參數。要照做的幾件事：
    - 套件版本鎖在 PINNED（和 KD 05、UB 04 一樣），4 個執行緒（interop 2）。版本不同就不算。
    - 載入順序：先建 5 個 Net（建的時候會用掉亂數），再載權重，最後設 rng.pt。存檔前這個程序沒有別的程式用 torch 的亂數。
    - 特徵從老師檔第一天（2020-01-02）整段重算，yfinance 用整個原始檔（爬蟲每天從 data.start 重抓）。滾動統計從序列
      開頭累積，截短會讓最後幾位不同。
    - 每天先補更新（狀態的最後更新日之後、t 之前的每個交易日，照日期各更新一步），再預測 t。預測在 eval 模式，不用亂數。

每天早上的步驟（run_day）：
    1. 拿 .cache/n1/n1.lock。n1_<t>.csv 已經算過現在這份 shadow_<t>.csv，或已經 max_runs 批，就不做（回傳 0）。
    2. 套件版本、起始資料夾的 sha256.json、meta.json 的常數都要對；狀態檔的 sha256 和內容雜湊要對（回傳碼 3）。
    3. 資料是 t 的（回傳碼 2，下一個時段再試）：data/raw/manifest.json 的 run.target_date 是 t、狀態 ok 或 stale、
       teacher_live.prev_day_never_filled 是 false；老師檔的日曆（50 檔以上有開收盤）在 t 之前的最後一天等於 run.prev_day。
    4. 美股四個輸入照 D06 規則（last_bar_ret）：丟複製K棒，還原收盤對前一根，取日期早於 t 的最後一根，早於 t 超過 16 天
       就空白（模型裡補 0）。用到的K棒比 dji 在 t 之前最後一根舊、值是空白，或 manifest 記這次沒抓成（status 不是 ok），
       stale_us_n1 記 1，照樣預測。
    5. 補更新。d 是 i（t 的前一個交易日）而且 i 有「新缺」的股票（manifest 的 prev_day_missing_stocks 裡、i 的前一個
       交易日有資料）時，這次先不更新 i，用舊狀態預測，stale_n1 記 1；下一個交易日再照有的列更新（最多延一次）。
       有更新就把新狀態寫到暫存資料夾、核對、改名，最後才改 current.json。
    6. 預測 t：Top50 裡 61 根以上K棒的列，5 個種子主目標的平均。
    7. N1：讀 shadow_<t>.csv 的 ridge_c2v2d、kridge_c2v2d、lgbm_c2v2d、beta_rank_c2v2d、p_up_c2v2d。沒有或有空白時
       N1 空白，JS 照記。
    8. 寫 data/submission/n1/n1_<t>.csv（一批 50 列，第 2 批加在後面）和 inputs_<t>.npz（這次每個更新日和 t 的 54 個
       輸入、目標、K棒數、更新前後的內容雜湊），都先寫暫存檔再改名。

檔案：
    models/n1/ub04_v5/        起始狀態（人 commit，只讀）：meta.json、norm.npz、sha256.json、state_<日期>/
    .cache/n1/<起始資料夾名>/ 會變的狀態（Git 不追蹤、不推）：current.json、state_<最後更新日>/（seed0～4.pt、rng.pt、
                              meta.json、sha256.json）。不見了就從起始狀態重來：先照日期用 data/submission/n1/ 的
                              inputs_<t>.npz 重播以前的每次更新（核對每次更新前後的內容雜湊），再照日期補更新
    data/submission/n1/       每天的核對檔，排程和其他資料一起 commit

回傳碼：0 寫好或不用做；2 資料還不是 t 的；3 狀態檔、常數或套件版本對不上；4 上一次還在跑；1 其他錯誤
（原因寫在 stderr 的最後一行，完整的 traceback 在 .cache/n1/last_error.txt）。
"""

import argparse
import copy
import fcntl
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import scipy
import torch
from scipy import stats
from torch import nn

ROOT = Path(__file__).resolve().parents[2]   # repo 根目錄（這個檔在 src/models/）
TAIPEI = ZoneInfo("Asia/Taipei")
PINNED = {"torch": "2.11.0+cpu", "numpy": "2.1.3", "pandas": "2.3.3", "scipy": "1.16.3"}   # 和 KD 05、UB 04 一樣
THREADS, INTEROP_THREADS = 4, 2
UB04_SOURCE = "Kaggle modelnovice/ub-04-n1-js-online-replay-for-shadow-run v5（bt/src/ub04.txt sha256 " \
              "9ee1b6f529c5a0c0bda02bd3671629d36961b1511a8db5bb252e2526986b6c39）"
CODE_DATA, CODE_STATE, CODE_BUSY = 2, 3, 4

# KD 05 凍結的設定（meta.json 的 constants 要一樣，不然不算）
MIN_BARS, H5, MAX_GAP, GAMMA = 61, 5, 16, 2.0
CALENDAR_MIN_STOCKS, CLIP = 50, 10
TARGET_EDGES, TARGET_VALUES = [0.05, 0.25, 0.75, 0.95], [0.0, 0.25, 0.5, 0.75, 1.0]
MLP_HIDDEN, MLP_DROP, MLP_WD, ONLINE_LR, GRAD_CLIP = (256, 128), 0.1, 0.01, 3e-4, 1.0
SEEDS = [0, 1, 2, 3, 4]
FEATURES = ["cc_1", "cc_5", "cc_20", "cc_60", "cc_120", "mom_20_120", "oc_1", "oc_2", "oc_m5", "oc_m20", "oc_m60",
            "gap_1", "gap_m5", "gap_m20", "tug_20", "vol_20", "vol_60", "ocvol_20", "rng_1", "rng_20", "clv_1",
            "ushadow_1", "lshadow_1", "hi20", "lo20", "hi120", "ma20", "ma60", "vr_1", "vr_5_60", "size_rel",
            "illiq_rel", "beta_60", "corr_60", "resvol_60", "ocbeta_60", "max_20", "min_20", "skew_60", "updown_14",
            "spx_x", "sox_x", "tsm_x", "mkt_oc_1", "mkt_cc_1", "mkt_cc_5", "mkt_cc_20", "mkt_vol_20", "mkt_disp_1",
            "mkt_breadth_1", "gspc", "sox", "tsm", "vix"]
PRICE_COLS = {"etl:adj_close": "close", "etl:adj_open": "open", "etl:adj_high": "high", "etl:adj_low": "low",
              "price:成交股數": "volume", "price:成交金額": "amount"}
US_FILES = {"gspc": "gspc", "sox": "sox", "tsm": "tsm_adr", "vix": "vix"}   # 輸入 → data/raw/yfinance/<檔名>.csv
US_CALENDAR = "dji"   # 美股交易日：這個序列有K棒的日子（和 features.fear_greed.us_calendar 一樣）
C2V2D_COLUMNS = {"ridge": "ridge_c2v2d", "kridge": "kridge_c2v2d", "lgbm": "lgbm_c2v2d",
                 "beta_rank": "beta_rank_c2v2d", "p": "p_up_c2v2d"}   # n1_frame 的欄 → shadow_<t>.csv 的欄
N1_COLUMNS = ["run", "date", "stock_id", "pred_n1", "prob_n1", "pred_js_n1", "js_n1", "k_t_n1", "c2v2d_same_n1",
              "note_n1", "state_n1", "state_sha_n1", "updated_n1", "stale_n1", "stale_us_n1", "gspc_n1", "sox_n1",
              "tsm_n1", "vix_n1", "us_bar_n1", "shadow_sha_n1", "inputs_sha_n1", "files_sha_n1", "code_commit",
              "made_at"]
REPLAY_FIXTURES = Path("tests") / "fixtures" / "n1"   # 重現測試的參考檔（Kaggle UB 04 的輸出）


class N1Error(RuntimeError):
    """這次不算。code 是 main 的回傳碼，訊息是自己寫的短句。"""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


# ================================================================ 小工具（標準函式庫）


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_atomic(path: Path, data: bytes) -> None:
    """先寫同一個資料夾的暫存檔（點開頭）再改名，中途出錯不會留下寫一半的檔。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_json(path: Path, value) -> None:
    write_atomic(path, (json.dumps(value, ensure_ascii=False, indent=1, default=str) + "\n").encode("utf-8"))


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def taipei_now() -> datetime:
    return datetime.now(TAIPEI)


def day_text(day) -> str:
    return pd.Timestamp(day).strftime("%Y-%m-%d")


def git_commit(root: Path) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def cpu_model() -> str:
    try:
        lines = Path("/proc/cpuinfo").read_text().splitlines()
    except OSError:
        return platform.processor() or "unknown"
    return next((line.split(":", 1)[1].strip() for line in lines if line.startswith("model name")), "unknown")


def environment() -> dict:
    return {"torch": torch.__version__, "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__,
            "python": sys.version.split()[0], "threads": torch.get_num_threads(),
            "interop_threads": torch.get_num_interop_threads(), "cpu": cpu_model(), "platform": platform.platform()}


def files_digest(base: Path, rels: list) -> str:
    """一組檔的指紋：照路徑排，「路徑<TAB>sha256」逐行接起來再算 sha256（和爬蟲的 files_digest 同一個算法）。"""
    lines = "".join(f"{rel}\t{sha256_file(base / rel)}\n" for rel in sorted(rels))
    return hashlib.sha256(lines.encode()).hexdigest()


# ================================================================ 讀老師檔和 yfinance（UB 04 原樣，網址換成本機檔）


def read_part(raw_dir: Path, part: str, stock_id: str) -> pd.DataFrame:
    return pd.read_csv(raw_dir / "teacher" / part / "market" / f"{stock_id}.csv", parse_dates=["date"],
                       usecols=["date"] + list(PRICE_COLS)).rename(columns=PRICE_COLS)


def combine(stock_id, training, live):
    """Training 接 Live 在 Training 最後一天之後、開收盤不是 -1 的列，其他 -1 當空值（KD 05 的 read_teacher_stock）。"""
    live = live[(live["date"] > training["date"].max()) & (live["close"] != -1) & (live["open"] != -1)]
    stock = pd.concat([training, live]).replace(-1, np.nan)
    stock["stock_id"] = stock_id
    return stock


def load_teacher(raw_dir: Path, all100: list) -> pd.DataFrame:
    """100 檔的老師檔接起來（UB 04 的 assemble，不截日期；面板只用日期早於 t 的列）。"""
    try:
        teacher = pd.concat([combine(s, read_part(raw_dir, "training", s), read_part(raw_dir, "live", s))
                             for s in all100], ignore_index=True)
    except FileNotFoundError as e:
        raise N1Error(f"老師檔少了 {Path(e.filename).name if e.filename else '某一檔'}", CODE_DATA) from None
    if teacher.duplicated(["date", "stock_id"]).any():
        raise N1Error("老師檔有重複的 (日期, 代號)", CODE_DATA)
    return teacher


def read_bars(path: Path) -> pd.DataFrame:
    bars = pd.read_csv(path, parse_dates=["date"])
    return bars.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)


def is_copy(bars):
    columns = ["open", "high", "low", "close", "adj_close"]
    return (bars[columns] == bars[columns].shift(1)).all(axis=1) & (bars["high"] != bars["low"])


def last_bar_ret(bars, days, price="adj_close"):
    """D06 的規則：丟複製K棒和還原收盤空的；報酬是還原收盤對前一根，兩根隔超過 16 天空白；第 d 天取日期早於 d 的
    最後一根，那根早於 d 超過 16 天也空白。"""
    kept = bars[~is_copy(bars)]
    kept = kept[kept[price].notna()]
    close, previous = kept[price], kept[price].shift(1)
    change = (close / previous - 1).where((close > 0) & (previous > 0)).where(kept["date"].diff().dt.days <= MAX_GAP)
    table = pd.DataFrame({"date": kept["date"].to_numpy(), "change": change.to_numpy()})
    last = pd.merge_asof(pd.DataFrame({"date": days}), table, on="date", allow_exact_matches=False,
                         tolerance=pd.Timedelta(days=MAX_GAP))
    return pd.Series(last["change"].to_numpy(), index=days)


def last_bar_date(bars, t, price="adj_close"):
    """last_bar_ret 在 t 用到的那根K棒的日期（日期早於 t 的最後一根）；沒有回傳 None。"""
    kept = bars[~is_copy(bars)]
    kept = kept[kept[price].notna()]
    before = kept.loc[kept["date"] < t, "date"]
    return pd.Timestamp(before.max()) if len(before) else None


def load_us_bars(raw_dir: Path, t) -> dict:
    """四個美股輸入和 dji 的原始檔，只留日期早於 t 的K棒。檔不在就丟 N1Error（爬蟲沒抓到時會留舊檔，所以只有
    第一次抓 gspc 之前會這樣）。gspc.csv 不在時不用空白照算：補更新會把空白的 gspc 寫進狀態，之後改不回來
    （n1 實作審查 m4）。那天回傳碼 2，隔天爬蟲再抓。"""
    out = {}
    for name, file in {**US_FILES, US_CALENDAR: US_CALENDAR}.items():
        path = raw_dir / "yfinance" / f"{file}.csv"
        if not path.exists():
            hint = "（爬蟲還沒抓到過 ^GSPC，看 data/raw/manifest.json 的 yfinance_extra）" if name == "gspc" else ""
            raise N1Error(f"沒有 yfinance/{file}.csv{hint}", CODE_DATA)
        bars = read_bars(path)
        out[name] = bars[bars["date"] < t].reset_index(drop=True)
    return out


def us_table(us_bars: dict, calendar, override: dict | None = None) -> pd.DataFrame:
    """日曆上每天的四個美股輸入（欄 gspc、sox、tsm、vix）。override 只給重現測試：{輸入: 照日期的 Series}。"""
    us = pd.DataFrame({name: last_bar_ret(us_bars[name], calendar) for name in US_FILES}, index=calendar)
    for name, series in (override or {}).items():
        us[name] = series.reindex(calendar)
    return us


# ================================================================ 特徵（KD 05 原樣）


def rmean(frame, n):
    return frame.rolling(n, min_periods=n).mean()


def rstd(frame, n):
    return frame.rolling(n, min_periods=n).std()


def broadcast(series, like):
    return pd.DataFrame(np.repeat(series.to_numpy(dtype=float)[:, None], like.shape[1], axis=1),
                        index=like.index, columns=like.columns)


def roll_reg(y, x, n, minp):
    both = y.notna() & x.notna()
    y, x = y.where(both), x.where(both)
    cnt = both.astype(float).rolling(n, min_periods=1).sum()

    def avg(z):
        return z.rolling(n, min_periods=1).sum() / cnt
    mx, my = avg(x), avg(y)
    vx, vy, cxy = avg(x * x) - mx * mx, avg(y * y) - my * my, avg(x * y) - mx * my
    ok = (cnt >= minp) & (vx > 1e-12) & (vy > 1e-12)
    slope = (cxy / vx).where(ok)
    return slope, (cxy / np.sqrt(vx * vy)).where(ok), (vy - slope * cxy).clip(lower=0).where(ok)


def cs_demedian(frame):
    return frame.sub(frame.median(axis=1), axis=0)


def finalize(values):
    values = np.asarray(values, dtype=np.float64)
    return np.where(np.isfinite(values), values, np.nan).astype(np.float32)


def base_features(w):
    c, o, h, l = w["close"], w["open"], w["high"], w["low"]  # noqa: E741（照 KD 05 的名字）
    v, a = w["volume"].where(w["volume"] > 0), w["amount"].where(w["amount"] > 0)
    c1 = c.shift(1)
    cc, oc, gap = c / c1 - 1, c / o - 1, o / c1 - 1
    rng, span = (h - l) / c, (h - l).where(h > l)
    f = {"cc_1": cc, "cc_5": c / c.shift(5) - 1, "cc_20": c / c.shift(20) - 1, "cc_60": c / c.shift(60) - 1,
         "cc_120": c / c.shift(120) - 1, "mom_20_120": c.shift(20) / c.shift(120) - 1,
         "oc_1": oc, "oc_2": oc.shift(1), "oc_m5": rmean(oc, 5), "oc_m20": rmean(oc, 20), "oc_m60": rmean(oc, 60),
         "gap_1": gap, "gap_m5": rmean(gap, 5), "gap_m20": rmean(gap, 20),
         "tug_20": gap.rolling(20, min_periods=20).sum() - oc.rolling(20, min_periods=20).sum(),
         "vol_20": rstd(cc, 20), "vol_60": rstd(cc, 60), "ocvol_20": rstd(oc, 20), "rng_1": rng, "rng_20": rmean(rng, 20),
         "clv_1": (2 * c - h - l) / span, "ushadow_1": (h - np.maximum(o, c)) / c, "lshadow_1": (np.minimum(o, c) - l) / c,
         "hi20": c / h.rolling(20, min_periods=20).max() - 1, "lo20": c / l.rolling(20, min_periods=20).min() - 1,
         "hi120": c / h.rolling(120, min_periods=120).max() - 1, "ma20": c / rmean(c, 20) - 1, "ma60": c / rmean(c, 60) - 1,
         "vr_1": v / rmean(v, 20), "vr_5_60": rmean(v, 5) / rmean(v, 60),
         "size_rel": cs_demedian(np.log(rmean(a, 20))),
         "illiq_rel": cs_demedian(np.log(rmean(cc.abs() / a, 20)))}
    return f, cc, oc, c - c1


def build_features(w, us):
    f, cc, oc, dc = base_features(w)
    mkt_cc, mkt_oc = cc.mean(axis=1), oc.mean(axis=1)
    beta, corr, resvar = roll_reg(cc, broadcast(mkt_cc, cc), 60, 60)
    f.update({"beta_60": beta, "corr_60": corr, "resvol_60": np.sqrt(resvar),
              "ocbeta_60": roll_reg(oc, broadcast(mkt_oc, oc), 60, 60)[0],
              "max_20": cc.rolling(20, min_periods=20).max(), "min_20": cc.rolling(20, min_periods=20).min(),
              "skew_60": cc.rolling(60, min_periods=60).skew(),
              "updown_14": dc.clip(lower=0).rolling(14, min_periods=14).sum() / dc.abs().rolling(14, min_periods=14).sum()})
    feats = {name: frame.shift(1) for name, frame in f.items()}  # t 那列只用到 t − 1 收盤
    for name, col in (("spx_x", "gspc"), ("sox_x", "sox"), ("tsm_x", "tsm")):
        u = broadcast(us[col], oc)
        feats[name] = roll_reg(oc, u, 120, 60)[0].shift(1) * u  # 斜率算到 t − 1，乘 t 那天 07:10 的數字
    market = {"mkt_oc_1": mkt_oc, "mkt_cc_1": mkt_cc, "mkt_cc_5": f["cc_5"].mean(axis=1),
              "mkt_cc_20": f["cc_20"].mean(axis=1), "mkt_vol_20": mkt_cc.rolling(20, min_periods=20).std(),
              "mkt_disp_1": oc.std(axis=1), "mkt_breadth_1": (cc > 0).astype(float).where(cc.notna()).mean(axis=1)}
    market = {name: series.shift(1) for name, series in market.items()}
    market.update({col: us[col] for col in ("gspc", "sox", "tsm", "vix")})
    return feats, market


# ================================================================ 面板（KD 05 原樣，股票清單改成參數）


def day_pct(frame):
    return (frame.rank(axis=1) - 0.5).div(frame.notna().sum(axis=1), axis=0)


def to_bins(pct):
    values = np.select([pct.to_numpy() < e for e in TARGET_EDGES], TARGET_VALUES[:4], TARGET_VALUES[4])
    return np.where(pct.notna().to_numpy(), values, np.nan).ravel()


def calendar_of(teacher):
    good = teacher["close"].notna() & teacher["open"].notna()
    per_day = teacher[good].groupby("date")["stock_id"].nunique()
    return pd.DatetimeIndex(per_day.index[per_day >= CALENDAR_MIN_STOCKS]).sort_values()


def panel_on(teacher, calendar, us, all100, top_idx):
    """寬表、54 欄、三個目標（當天盤中報酬的名次、扣掉 β 的名次、五天的名次，換成常態分數）。"""
    S = len(all100)
    w = {field: teacher.pivot(index="date", columns="stock_id", values=field).reindex(index=calendar, columns=all100)
         for field in ("close", "open", "high", "low", "volume", "amount")}
    bars_wide = w["close"].notna().cumsum().shift(1).fillna(0)
    r_wide = w["close"] / w["open"] - 1
    us_cal = us.reindex(calendar)
    feat, market = build_features(w, us_cal)
    names, n_days = list(feat) + list(market), len(calendar)
    raw = np.empty((n_days * S, len(names)), dtype=np.float32)
    for j, name in enumerate(feat):
        raw[:, j] = finalize(feat[name].to_numpy().ravel())
    for j, name in enumerate(market):
        raw[:, len(feat) + j] = finalize(np.repeat(market[name].to_numpy(dtype=float), S))
    ok_wide = r_wide.notna() & (bars_wide >= MIN_BARS)
    r_ok = r_wide.where(ok_wide)
    res_ok = (r_ok - feat["ocbeta_60"].mul(r_ok.mean(axis=1), axis=0)).where(feat["ocbeta_60"].notna())
    h5_ok = sum(r_wide.shift(-k) for k in range(H5)).where(ok_wide)
    pct = {"main": day_pct(r_ok), "res": day_pct(res_ok), "h5": day_pct(h5_ok)}
    yg = np.column_stack([stats.norm.ppf(pct[k].to_numpy().ravel()) for k in ("main", "res", "h5")]).astype(np.float32)
    return {"calendar": calendar, "names": names, "raw": raw, "bars": bars_wide.to_numpy().ravel(), "r_wide": r_wide,
            "yg": yg, "trainable": ~np.isnan(to_bins(pct["main"])), "day": np.repeat(np.arange(n_days), S),
            "is_top": np.tile(np.isin(np.arange(S), top_idx), n_days), "us": us_cal, "S": S, "all100": list(all100)}


def build_panel(teacher, t, us_bars, all100, top_idx, override=None):
    """t 早上的面板（UB 04 的 panel_0710）：只用日期早於 t 的老師檔列，日曆最後接一天空的 t。"""
    rows = teacher[teacher["date"] < t]
    calendar = calendar_of(rows).append(pd.DatetimeIndex([t]))
    panel = panel_on(rows, calendar, us_table(us_bars, calendar, override), all100, top_idx)
    if panel["names"] != FEATURES:
        raise N1Error("面板的欄和 KD 05 不一樣", CODE_STATE)
    return panel


# ================================================================ 網路（KD 05 原樣）


class Net(nn.Module):
    def __init__(self, n_in):
        super().__init__()
        layers, width = [], n_in
        for hidden in MLP_HIDDEN:
            layers += [nn.Linear(width, hidden), nn.SiLU(), nn.Dropout(MLP_DROP)]
            width = hidden
        self.body, self.head = nn.Sequential(*layers), nn.Linear(width, 3)

    def forward(self, x):
        return self.head(self.body(x))


def inputs(raw, rows, norm):
    return torch.from_numpy(np.nan_to_num(np.clip((raw[rows] - norm[0]) / norm[1], -CLIP, CLIP), nan=0.0)
                            .astype(np.float32))


def day_rows(d, mask, S):
    return np.flatnonzero(mask[d * S:(d + 1) * S]) + d * S


def predict_day(models, raw, rows, norm):
    with torch.no_grad():
        return np.mean([mdl.eval()(inputs(raw, rows, norm))[:, 0].numpy() for mdl in models], axis=0)


def update_day(models, panel, d, norm):
    rows_u = day_rows(d, panel["trainable"], panel["S"])
    if len(rows_u):
        x, y = inputs(panel["raw"], rows_u, norm), torch.from_numpy(panel["yg"][rows_u, 0])
        for mdl in models:
            mdl.train()
            opt = torch.optim.AdamW(mdl.parameters(), lr=ONLINE_LR, weight_decay=MLP_WD)
            opt.zero_grad()
            ((mdl(x)[:, 0] - y) ** 2).mean().backward()
            nn.utils.clip_grad_norm_(mdl.parameters(), max_norm=GRAD_CLIP)
            opt.step()
    return len(rows_u)


def snapshot(models):
    return {"state": [copy.deepcopy(mdl.state_dict()) for mdl in models], "rng": torch.get_rng_state().clone()}


def restore(snap):
    """先建 5 個 Net（建的時候會用掉亂數），再載權重，最後設亂數狀態。順序不能換。"""
    models = [Net(len(FEATURES)) for _ in SEEDS]
    for mdl, state in zip(models, snap["state"]):
        mdl.load_state_dict(state)
    torch.set_rng_state(snap["rng"])
    return models


def content_sha(snap):
    """權重和亂數狀態的位元組雜湊，和存檔格式無關，用來確認兩台機器載入的是同一份。"""
    digest = hashlib.sha256()
    for state in snap["state"]:
        for name, tensor in state.items():
            digest.update(name.encode())
            digest.update(tensor.detach().contiguous().numpy().tobytes())
    digest.update(snap["rng"].numpy().tobytes())
    return digest.hexdigest()


def save_state(snap, folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    for seed, state in zip(SEEDS, snap["state"]):
        torch.save(state, folder / f"seed{seed}.pt")
    torch.save(snap["rng"], folder / "rng.pt")


def load_state(folder: Path):
    return {"state": [torch.load(folder / f"seed{seed}.pt", weights_only=True) for seed in SEEDS],
            "rng": torch.load(folder / "rng.pt", weights_only=True)}


STATE_FILES = [f"seed{seed}.pt" for seed in SEEDS] + ["rng.pt"]


# ================================================================ 每天：補更新、預測（重現測試走同樣的函式）


def catch_up(models, panel, last_update, norm, hold=None) -> tuple:
    """最後更新日之後、t 之前的每個交易日照日期各更新一步（先更新再預測，同一天不會更新兩次）。hold 是這次先不更新
    的那一天（i 有新缺的股票時）。回傳（每次更新的紀錄, 新的最後更新日）。"""
    calendar, S = panel["calendar"], panel["S"]
    todo = [d for d in range(len(calendar) - 1) if calendar[d] > last_update and (hold is None or calendar[d] != hold)]
    if hold is not None and todo and calendar[todo[-1]] > hold:
        raise N1Error("先不更新的日子後面還有要更新的日子", CODE_STATE)
    records = []
    for d in todo:
        before = content_sha(snapshot(models))
        rows = update_day(models, panel, d, norm)
        block = slice(d * S, (d + 1) * S)
        records.append({"date": calendar[d], "rows": rows, "before": before, "after": content_sha(snapshot(models)),
                        "x": panel["raw"][block].copy(), "target": panel["yg"][block, 0].copy(),
                        "trainable": panel["trainable"][block].copy(), "bars": panel["bars"][block].copy()})
    return records, (calendar[todo[-1]] if todo else last_update)


def predict_t(models, panel, norm) -> pd.DataFrame:
    """t（面板最後一天）Top50 裡 61 根以上K棒的列：date、stock_id、js（5 個種子主目標的平均，float32）。"""
    S, d = panel["S"], len(panel["calendar"]) - 1
    rows = day_rows(d, panel["is_top"] & (panel["bars"] >= MIN_BARS), S)
    js = predict_day(models, panel["raw"], rows, norm) if len(rows) else np.empty(0, dtype=np.float32)
    return pd.DataFrame({"date": panel["calendar"][d], "stock_id": np.array(panel["all100"])[rows % S], "js": js})


def replay(models, teacher, us_bars, days, norm, all100, top_idx, last_update, override=None) -> tuple:
    """照每天早上的做法逐日走：每個 t 建 t 早上的面板、補更新、預測 t。給重現測試和 --replay-check 用。
    回傳（{t: 預測表}, {t: t 那天 100 列的輸入和K棒數}, 所有更新的紀錄, 最後更新日）。"""
    preds, day_inputs, updates = {}, {}, []
    for t in days:
        panel = build_panel(teacher, pd.Timestamp(t), us_bars, all100, top_idx, override)
        records, last_update = catch_up(models, panel, last_update, norm)
        updates += records
        preds[pd.Timestamp(t)] = predict_t(models, panel, norm)
        d, S = len(panel["calendar"]) - 1, panel["S"]
        day_inputs[pd.Timestamp(t)] = {"x": panel["raw"][d * S:(d + 1) * S].copy(),
                                       "bars": panel["bars"][d * S:(d + 1) * S].copy()}
    return preds, day_inputs, updates, last_update


# ================================================================ N1（UB 01 的公式）


def day_rank(values, days):
    return (values.groupby(days).rank(pct=True) - 0.5).fillna(0.0)


def side_of(rank_score, days):
    order = rank_score.groupby(days).rank(method="first")
    return pd.Series(np.where(order > rank_score.groupby(days).transform("size") / 2, 1.0, -1.0), index=rank_score.index)


def n1_frame(frame):
    """frame 要照日期、代號排（同分時代號大的猜漲）：欄 date、stock_id、ridge、kridge、lgbm、js、beta_rank、p。"""
    days, out = frame["date"], frame.copy()
    rank = {name: day_rank(frame[name], days) for name in ("ridge", "kridge", "lgbm", "js")}
    out["comb3"] = (rank["ridge"] + rank["kridge"] + rank["lgbm"]) / 3
    out["comb4"] = (rank["ridge"] + rank["kridge"] + rank["lgbm"] + rank["js"]) / 4
    out["k_t"] = out["comb3"].groupby(days).transform("std") / out["comb4"].groupby(days).transform("std")
    out["tilt"] = GAMMA * (2 * out["p"] - 1)
    out["score_c2v2d"] = out["comb3"] + out["tilt"] * out["beta_rank"]
    out["score_n1"] = out["k_t"] * out["comb4"] + out["tilt"] * out["beta_rank"]
    out["pred_c2v2d"] = (side_of(out["score_c2v2d"], days) > 0).astype(int)
    out["pred_n1"] = (side_of(out["score_n1"], days) > 0).astype(int)
    return out


def n1_today(js: pd.DataFrame, top50: list, t, shadow_path: Path) -> tuple:
    """t 那天 50 檔的表（照代號排）：pred_js_n1，有 c2v2d 的四個分數和 p 時再加 pred_n1、prob_n1、k_t_n1、
    c2v2d_same_n1（重算的 c2v2d 0／1 和 shadow 的 pred_c2v2d 一樣是 1）。回傳（表, 空白時的原因）。"""
    table = pd.DataFrame({"date": pd.Timestamp(t), "stock_id": sorted(str(s) for s in top50)})
    table = table.merge(js[["stock_id", "js"]].astype({"stock_id": str}), on="stock_id", how="left")
    table["js"] = table["js"].astype(np.float64)
    table["pred_js_n1"] = (side_of(day_rank(table["js"], table["date"]), table["date"]) > 0).astype(int)
    for column in ("pred_n1", "prob_n1", "k_t_n1", "c2v2d_same_n1"):
        table[column] = np.nan
    if not shadow_path.exists():
        return table, "沒有 shadow 檔"
    shadow = pd.read_csv(shadow_path, dtype={"date": str, "stock_id": str}, float_precision="round_trip")
    missing = [c for c in C2V2D_COLUMNS.values() if c not in shadow.columns]
    if missing:
        return table, f"shadow 沒有 {missing[0]}"
    shadow = shadow.set_index("stock_id").reindex(table["stock_id"])
    member = shadow[list(C2V2D_COLUMNS.values())]
    if member.isna().any().any():
        return table, "c2v2d 有空白"
    frame = table[["date", "stock_id", "js"]].copy()
    for name, column in C2V2D_COLUMNS.items():
        frame[name] = member[column].to_numpy(dtype=np.float64)
    out = n1_frame(frame)
    order = out.groupby("date")["score_n1"].rank(method="first")
    table["pred_n1"] = out["pred_n1"].to_numpy()
    table["prob_n1"] = ((order - 0.5) / len(out)).to_numpy()
    table["k_t_n1"] = out["k_t"].to_numpy()
    if "pred_c2v2d" in shadow.columns and shadow["pred_c2v2d"].notna().all():
        table["c2v2d_same_n1"] = int((out["pred_c2v2d"].to_numpy() == shadow["pred_c2v2d"].to_numpy()).all())
    return table, ""


# ================================================================ 狀態檔


class Paths:
    """這次用到的路徑。root 是 repo 根目錄，其他都從命令列來（相對於 root）。"""

    def __init__(self, root: Path, args):
        self.root = root
        self.raw = root / args.raw_dir
        self.submission = root / args.submission_dir
        self.out = self.submission / "n1"
        self.initial = root / args.initial_dir
        self.cache = root / args.cache_dir
        self.line = self.cache / self.initial.name   # 換起點時開新的一條，不覆蓋舊的
        self.start_state = args.start_state

    def n1_csv(self, t: str) -> Path:
        return self.out / f"n1_{t}.csv"

    def inputs_npz(self, t: str, run: int) -> Path:
        return self.out / (f"inputs_{t}.npz" if run == 1 else f"inputs_{t}_run{run}.npz")


def check_versions(meta: dict) -> None:
    """套件版本要等於 PINNED，meta.json 記的 Kaggle 環境也要一樣（54 欄的對照只在這組版本驗過）。"""
    env = meta.get("env") or {}
    have = {"torch": torch.__version__, "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__}
    for name, version in PINNED.items():
        if have[name] != version or env.get(name) != version:
            raise N1Error(f"{name} 是 {have[name]}（起始狀態 {env.get(name)}），要 {version}", CODE_STATE)


def check_initial(paths: Paths) -> tuple:
    """起始資料夾：meta.json、norm.npz 的 sha256 對 sha256.json，常數和欄的順序和這支程式一樣。回傳（meta, norm）。"""
    try:
        shas = read_json(paths.initial / "sha256.json")
        meta = read_json(paths.initial / "meta.json")
    except (OSError, ValueError):
        raise N1Error(f"{paths.initial.name} 沒有 sha256.json 或 meta.json", CODE_STATE) from None
    for name in ("meta.json", "norm.npz"):
        if not (paths.initial / name).exists() or sha256_file(paths.initial / name) != shas.get(name):
            raise N1Error(f"{paths.initial.name}/{name} 的 sha256 對不上", CODE_STATE)
    check_versions(meta)
    want = {"min_bars": MIN_BARS, "calendar_min_stocks": CALENDAR_MIN_STOCKS, "clip": CLIP, "online_lr": ONLINE_LR,
            "weight_decay": MLP_WD, "grad_clip": GRAD_CLIP, "hidden": list(MLP_HIDDEN), "dropout": MLP_DROP,
            "seeds": SEEDS, "max_gap_days_us": MAX_GAP, "gamma": GAMMA}
    constants = meta.get("constants") or {}
    wrong = [key for key, value in want.items() if constants.get(key) != value]
    if wrong or meta.get("features") != FEATURES:
        raise N1Error(f"meta.json 的設定和程式不一樣：{wrong or ['features']}", CODE_STATE)
    with np.load(paths.initial / "norm.npz") as norm_file:
        norm = (norm_file["mean"], norm_file["sd"])
        if list(norm_file["features"]) != FEATURES:
            raise N1Error("norm.npz 的欄和程式不一樣", CODE_STATE)
    return meta, norm


def verify_folder(folder: Path, shas: dict, prefix: str = "") -> None:
    for name in STATE_FILES:
        path = folder / name
        if not path.exists() or sha256_file(path) != shas.get(prefix + name):
            raise N1Error(f"{folder.name}/{name} 的 sha256 對不上", CODE_STATE)


def clean_leftovers(paths: Paths) -> None:
    """上一次被砍時留下的暫存：狀態的暫存資料夾（.tmp_ 開頭）、data/submission/n1/ 的暫存檔（.*.tmp，不然會被
    排程 commit）。"""
    for leftover in paths.line.glob(".tmp_*") if paths.line.exists() else []:
        shutil.rmtree(leftover, ignore_errors=True)
    for leftover in paths.out.glob(".*.tmp") if paths.out.exists() else []:
        leftover.unlink(missing_ok=True)


def commit_state(paths: Paths, snap, meta: dict) -> str:
    """狀態寫到暫存資料夾，核對 sha256 和內容雜湊，改名成 state_<最後更新日>，最後改 current.json。回傳資料夾名。
    同名的資料夾已經在（上次改名後、改 current.json 前停下）：內容一樣就直接用，不一樣就加 _2、_3，不覆蓋。"""
    paths.line.mkdir(parents=True, exist_ok=True)
    name = f"state_{meta['last_update_date']}"
    tmp = Path(tempfile.mkdtemp(prefix=f".tmp_{name}_", dir=paths.line))
    try:
        save_state(snap, tmp)
        shas = {file: sha256_file(tmp / file) for file in STATE_FILES}
        write_json(tmp / "sha256.json", shas)
        write_json(tmp / "meta.json", meta)
        verify_folder(tmp, shas)
        if content_sha(load_state(tmp)) != meta["content_sha256"]:
            raise N1Error("新狀態寫完讀回來，內容雜湊對不上", CODE_STATE)
        final, k = paths.line / name, 2
        while final.exists():
            try:
                same = read_json(final / "meta.json").get("content_sha256") == meta["content_sha256"]
                verify_folder(final, read_json(final / "sha256.json"))
            except (OSError, ValueError, N1Error):
                same = False
            if same:
                shutil.rmtree(tmp)
                break
            final, k = paths.line / f"{name}_{k}", k + 1
        else:
            os.rename(tmp, final)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    write_json(paths.line / "current.json", {"state": final.name, "last_update_date": meta["last_update_date"],
                                             "content_sha256": meta["content_sha256"],
                                             "switched_at": taipei_now().isoformat(timespec="seconds")})
    return final.name


def adopt_initial(paths: Paths, meta: dict, root: Path) -> None:
    """.cache/n1/<起始資料夾名>/ 還沒有 current.json：從起始資料夾複製 start_state（逐檔核對 sha256），當成第一份狀態。"""
    info = (meta.get("states") or {}).get(paths.start_state)
    source = paths.initial / paths.start_state
    if not info or not source.is_dir():
        raise N1Error(f"{paths.initial.name} 沒有 {paths.start_state}", CODE_STATE)
    verify_folder(source, read_json(paths.initial / "sha256.json"), prefix=f"{paths.start_state}/")
    snap = load_state(source)
    if content_sha(snap) != info.get("content_sha256"):
        raise N1Error(f"{paths.start_state} 載入後的內容雜湊和 meta.json 不一樣", CODE_STATE)
    commit_state(paths, snap, {**info, "name": paths.start_state, "copied_from": f"{paths.initial.name}/{paths.start_state}",
                               "origin": UB04_SOURCE, "environment": environment(), "code_commit": git_commit(root),
                               "features_from": {"teacher": "老師檔第一天（2020-01-02）", "yfinance": "整個原始檔（data.start 起）"},
                               "next_step": "下一個交易日早上：補更新最後更新日之後、t 之前的交易日，再預測 t"})


def load_current(paths: Paths) -> tuple:
    """current.json 指的狀態：核對 sha256 和內容雜湊，回傳（資料夾名, snapshot, 最後更新日, 內容雜湊）。"""
    current = read_json(paths.line / "current.json")
    folder = paths.line / current["state"]
    try:
        state_meta = read_json(folder / "meta.json")
        verify_folder(folder, read_json(folder / "sha256.json"))
    except (OSError, ValueError):
        raise N1Error(f"{current['state']} 的 meta.json 或 sha256.json 讀不了", CODE_STATE) from None
    snap = load_state(folder)
    sha = content_sha(snap)
    if sha != state_meta.get("content_sha256") or sha != current.get("content_sha256"):
        raise N1Error(f"{current['state']} 的內容雜湊對不上", CODE_STATE)
    return current["state"], snap, pd.Timestamp(state_meta["last_update_date"]), sha


def update_from_inputs(models, x_block, target_block, trainable_block, norm) -> int:
    """用 inputs_<t>.npz 存的一天 100 列做一次更新，和 update_day 同樣的運算（列、順序、dtype 都一樣）。"""
    rows_u = np.flatnonzero(trainable_block)
    if len(rows_u):
        x, y = inputs(x_block, rows_u, norm), torch.from_numpy(np.ascontiguousarray(target_block[rows_u]))
        for mdl in models:
            mdl.train()
            opt = torch.optim.AdamW(mdl.parameters(), lr=ONLINE_LR, weight_decay=MLP_WD)
            opt.zero_grad()
            ((mdl(x)[:, 0] - y) ** 2).mean().backward()
            nn.utils.clip_grad_norm_(mdl.parameters(), max_norm=GRAD_CLIP)
            opt.step()
    return len(rows_u)


def recover_from_inputs(paths: Paths, norm, t: str) -> list:
    """讀 data/submission/n1/ 的 inputs_<日期>.npz（日期不晚於 t），記下的更新裡比現在狀態的最後更新日晚的，
    照日期用原本的輸入重播一遍。同一天記了不只一次（上一次寫完 npz、存狀態前被砍，下一次又更新一次）時取檔名
    最後的那份（第 2 批排在第 1 批後面），那份才是存進狀態的。平常（狀態已經包含所有記下的更新）什麼都不做；
    .cache/n1/ 不見、從起始狀態重來時才會重播。每次更新前後的內容雜湊都要和檔裡記的一樣，不一樣就丟 N1Error
    （回傳碼 3），current.json 不換。有重播就存成新狀態。回傳重播的日子。"""
    state_name, snap, last_update, sha = load_current(paths)
    files = sorted(p for p in paths.out.glob("inputs_*.npz") if p.name[len("inputs_"):len("inputs_") + 10] <= t) \
        if paths.out.exists() else []
    todo = {}
    for path in files:
        with np.load(path) as saved:
            dates = [str(d) for d in saved["update_dates"]]
            if str(saved["line"][0]) != paths.initial.name or not any(pd.Timestamp(day) > last_update for day in dates):
                continue   # 別條（換過起點）的紀錄，或已經在狀態裡的更新
            S = len(saved["pred_stock"])
            for k, day in enumerate(dates):
                if pd.Timestamp(day) > last_update:
                    block = slice(k * S, (k + 1) * S)
                    todo[day] = {"file": path.name, "before": str(saved["state_before"][k]),
                                 "after": str(saved["state_after"][k]), "x": saved["upd_x"][block],
                                 "target": saved["upd_target"][block], "trainable": saved["upd_trainable"][block]}
    models, done = None, []
    for day in sorted(todo):
        record = todo[day]
        if models is None:
            models = restore(snap)
        if content_sha(snapshot(models)) != record["before"]:
            raise N1Error(f"{record['file']} 記的 {day} 更新前狀態和重播的不一樣", CODE_STATE)
        update_from_inputs(models, record["x"], record["target"], record["trainable"], norm)
        sha = content_sha(snapshot(models))
        if sha != record["after"]:
            raise N1Error(f"{record['file']} 記的 {day} 更新後狀態和重播的不一樣", CODE_STATE)
        last_update = pd.Timestamp(day)
        done.append(day)
    if done:
        commit_state(paths, snapshot(models), {
            "last_update_date": day_text(last_update), "content_sha256": sha, "parent": state_name,
            "recovered_from": sorted({todo[d]["file"] for d in done}), "updates": [{"date": d} for d in done],
            "origin": UB04_SOURCE, "line": paths.initial.name, "environment": environment(),
            "code_commit": git_commit(paths.root),
            "next_step": "下一個交易日早上：補更新最後更新日之後、t 之前的交易日，再預測 t",
            "written_at": taipei_now().isoformat(timespec="seconds")})
    return done


# ================================================================ 每天早上


def check_data(paths: Paths, t: str) -> dict:
    """爬蟲紀錄是 t 的：run.target_date 是 t、狀態 ok 或 stale、前一天老師有填。回傳 manifest（不成立丟 N1Error）。"""
    try:
        manifest = read_json(paths.raw / "manifest.json")
    except (OSError, ValueError):
        raise N1Error("data/raw/manifest.json 讀不了", CODE_DATA) from None
    run = manifest.get("run") or {}
    live = manifest.get("teacher_live") or {}
    if run.get("target_date") != t:
        raise N1Error(f"爬蟲紀錄的 t 是 {run.get('target_date')}，不是 {t}", CODE_DATA)
    if run.get("status") not in ("ok", "stale"):
        raise N1Error(f"爬蟲這次的狀態是 {run.get('status')}", CODE_DATA)
    if live.get("prev_day_never_filled") is not False:
        raise N1Error("前一個交易日老師還沒填（prev_day_never_filled 不是 false）", CODE_DATA)
    if not run.get("prev_day"):
        raise N1Error("爬蟲紀錄沒有 prev_day", CODE_DATA)
    return manifest


def check_universe(paths: Paths, meta: dict) -> None:
    try:
        info = read_json(paths.raw / "teacher" / "training" / "info.json")
    except (OSError, ValueError):
        raise N1Error("老師的 info.json 讀不了", CODE_DATA) from None
    if sorted(map(str, info.get("Top50@Y", []))) != meta["top50"] or sorted(map(str, info.get("Top100@Y", []))) != meta["all100"]:
        raise N1Error("老師的 Top50、Top100 和起始狀態的清單不一樣", CODE_STATE)


def newly_missing(teacher, calendar, prev_day, missing: list) -> list:
    """i 那天沒資料、i 的前一個交易日有資料的股票（manifest 的 prev_day_missing_stocks 裡新缺的）。"""
    if not missing or len(calendar) < 3:
        return []
    before = calendar[-3]
    good = teacher[(teacher["date"] == before) & teacher["close"].notna() & teacher["open"].notna()]
    have_before = set(good["stock_id"])
    have_i = set(teacher.loc[(teacher["date"] == prev_day) & teacher["close"].notna() & teacher["open"].notna(),
                             "stock_id"])
    return sorted(s for s in map(str, missing) if s in have_before and s not in have_i)


def us_check(us_bars: dict, us_row: pd.Series, t, manifest: dict) -> tuple:
    """每個美股輸入用到的K棒日期，和要不要記 stale_us_n1：比 dji 在 t 之前最後一根舊、值是空白，或爬蟲這次沒抓成
    四個輸入或 dji 其中一個（第二輪審查）。Yahoo 整個抓不到時每個檔都留著舊檔，dji 也一樣舊，只比日期看不出來，
    所以也看 manifest：yfinance（sox、tsm_adr、vix、dji）或 yfinance_extra（gspc）裡那個檔的 status 不是 ok
    （沒有紀錄也算）就記 1。同一個 t 重爬失敗、但上一次已經抓到新的K棒時也會記 1，寧可多標。"""
    last_us = last_bar_date(us_bars[US_CALENDAR], t)
    used = {name: last_bar_date(us_bars[name], t) for name in US_FILES}
    yf, extra = manifest.get("yfinance") or {}, manifest.get("yfinance_extra") or {}
    failed = any((yf.get(file) or extra.get(file) or {}).get("status") != "ok"
                 for file in [*US_FILES.values(), US_CALENDAR])
    stale = failed or any(day is None or last_us is None or day < last_us for day in used.values()) \
        or bool(us_row.isna().any())
    return used, int(stale)


def existing_batches(path: Path) -> tuple:
    """n1_<t>.csv 已經有幾批、最後一批記的 shadow sha256、最大的批號。"""
    if not path.exists():
        return 0, None, 0
    table = pd.read_csv(path, dtype=str, keep_default_na=False)
    if table.empty:
        return 0, None, 0
    runs = table["run"].astype(int)
    return int(runs.nunique()), table.loc[runs == runs.max(), "shadow_sha_n1"].iloc[0], int(runs.max())


def next_run(paths: Paths, t: str, top_run: int) -> int:
    """這一批的批號：n1_<t>.csv 和 inputs_<t>*.npz 裡最大的批號加 1。上一次寫完 npz、還沒寫 csv 就被砍時，
    那份 npz 可能記了已經存進狀態的更新，不能蓋掉，所以也要看 npz。"""
    done = [top_run]
    for path in paths.out.glob(f"inputs_{t}*.npz") if paths.out.exists() else []:
        rest = path.name[len(f"inputs_{t}"):-len(".npz")]
        if rest == "":
            done.append(1)
        elif rest.startswith("_run") and rest[4:].isdigit():
            done.append(int(rest[4:]))
    return max(done) + 1


def write_inputs(path: Path, records: list, panel, us_row, used: dict, held: list, missing: list, line: str,
                 state_sha: str) -> str:
    """inputs_<t>.npz：這次每個更新日（100 列）和 t（100 列）的 54 個原始輸入（float32）、目標、能不能更新、K棒數，
    每次更新前後的內容雜湊，美股四個值和K棒日期，i 那天缺的代號（held_missing 是先不更新的新缺，prev_day_missing
    是爬蟲記的全部，含連續停牌），預測 t 用的狀態的內容雜湊（state_sha）。.cache/n1/ 不見時 recover_from_inputs
    用它重播。回傳檔案的 sha256。"""
    S, d = panel["S"], len(panel["calendar"]) - 1
    stocks = np.array(panel["all100"])
    block = slice(d * S, (d + 1) * S)
    arrays = {
        "features": np.array(FEATURES),
        "update_dates": np.array([day_text(r["date"]) for r in records], dtype="U10"),
        "update_rows": np.array([r["rows"] for r in records], dtype=np.int64),
        "state_before": np.array([r["before"] for r in records], dtype="U64"),
        "state_after": np.array([r["after"] for r in records], dtype="U64"),
        "upd_date": np.repeat(np.array([day_text(r["date"]) for r in records], dtype="U10"), S),
        "upd_stock": np.tile(stocks, len(records)),
        "upd_x": np.concatenate([r["x"] for r in records]) if records else np.zeros((0, len(FEATURES)), np.float32),
        "upd_target": np.concatenate([r["target"] for r in records]) if records else np.zeros(0, np.float32),
        "upd_trainable": np.concatenate([r["trainable"] for r in records]) if records else np.zeros(0, bool),
        "upd_bars": np.concatenate([r["bars"] for r in records]) if records else np.zeros(0, np.float64),
        "pred_date": np.repeat(np.array([day_text(panel["calendar"][d])], dtype="U10"), S),
        "pred_stock": stocks,
        "pred_x": panel["raw"][block].copy(),
        "pred_bars": panel["bars"][block].copy(),
        "pred_mask": (panel["is_top"] & (panel["bars"] >= MIN_BARS))[block].copy(),
        "us_inputs": np.array(list(US_FILES)),
        "us_values": us_row[list(US_FILES)].to_numpy(dtype=np.float64),
        "us_bars": np.array([day_text(used[name]) if used[name] is not None else "" for name in US_FILES], dtype="U10"),
        "held_missing": np.array(held, dtype="U10"),
        "prev_day_missing": np.array(missing, dtype="U10"),
        "line": np.array([line]),
        "state_sha": np.array([state_sha], dtype="U64"),
    }
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **arrays)
    data = buffer.getvalue()
    write_atomic(path, data)
    return hashlib.sha256(data).hexdigest()


def append_batch(path: Path, batch: pd.DataFrame) -> None:
    """第 1 批寫表頭；之後的批照原本的表頭接在後面，前面的位元組不動。"""
    if path.exists():
        old = path.read_bytes()
        header = old.decode("utf-8").splitlines()[0].split(",")
        data = old + batch.reindex(columns=header).to_csv(index=False, header=False).encode("utf-8")
    else:
        data = batch[N1_COLUMNS].to_csv(index=False).encode("utf-8")
    write_atomic(path, data)


def run_day(paths: Paths, t: str, max_runs: int) -> str:
    """每天早上的步驟（見檔頭）。回傳給 log 的一行摘要；不算的時候丟 N1Error。"""
    shadow_path = paths.submission / f"shadow_{t}.csv"
    shadow_sha = sha256_file(shadow_path) if shadow_path.exists() else ""
    runs, last_shadow, top_run = existing_batches(paths.n1_csv(t))
    if runs and last_shadow == shadow_sha:
        return f"n1 {t}：這份 shadow_{t}.csv 已經算過（第 {runs} 批），不重算"
    if runs >= max_runs:
        return f"n1 {t}：已經算了 {runs} 批，不再算"
    torch.set_num_threads(THREADS)
    try:
        torch.set_num_interop_threads(INTEROP_THREADS)
    except RuntimeError:   # 同一個程序設過一次就不能再設（測試裡會這樣），執行緒數照舊
        pass
    meta, norm = check_initial(paths)
    manifest = check_data(paths, t)
    check_universe(paths, meta)
    clean_leftovers(paths)
    adopted = not (paths.line / "current.json").exists()
    if adopted:
        adopt_initial(paths, meta, paths.root)
    try:
        recovered = recover_from_inputs(paths, norm, t)   # 平常什麼都不做；.cache/n1/ 重來時照記下的輸入補回來
    except BaseException:
        if adopted:   # 剛接上的起始狀態重播對不上：current.json 拿掉，下次再從頭試，不悄悄從起始狀態接著更新
            (paths.line / "current.json").unlink(missing_ok=True)
        raise
    state_name, snap, last_update, state_sha = load_current(paths)
    t_day = pd.Timestamp(t)
    if last_update >= t_day:
        raise N1Error(f"狀態的最後更新日 {day_text(last_update)} 不早於 {t}", CODE_STATE)

    all100, top50 = meta["all100"], meta["top50"]
    top_idx = np.array([all100.index(s) for s in top50])
    teacher = load_teacher(paths.raw, all100)
    us_bars = load_us_bars(paths.raw, t_day)
    panel = build_panel(teacher, t_day, us_bars, all100, top_idx)
    calendar = panel["calendar"]
    prev_day = pd.Timestamp(manifest["run"]["prev_day"])
    if len(calendar) < 2 or calendar[-2] != prev_day:
        raise N1Error(f"老師檔的日曆在 {t} 之前的最後一天是 {day_text(calendar[-2]) if len(calendar) > 1 else '沒有'}，"
                      f"爬蟲記的前一個交易日是 {day_text(prev_day)}", CODE_DATA)
    held = newly_missing(teacher, calendar, prev_day, (manifest.get("teacher_live") or {}).get("prev_day_missing_stocks"))
    hold = prev_day if held and last_update < prev_day else None

    rels = ([f"yfinance/{f}.csv" for f in [*US_FILES.values(), US_CALENDAR]] + ["teacher/training/info.json"]
            + [f"teacher/{part}/market/{s}.csv" for part in ("training", "live") for s in all100])
    files_sha = files_digest(paths.raw, rels)   # 這次讀的原始檔的指紋，寫進狀態的 meta.json 和 n1_<t>.csv

    models = restore(snap)
    records, new_last = catch_up(models, panel, last_update, norm, hold)
    js = predict_t(models, panel, norm)   # 預測不用亂數、不改權重，在存狀態之前做也一樣

    us_row = panel["us"].iloc[-1]
    used, stale_us = us_check(us_bars, us_row, t_day, manifest)
    table, note = n1_today(js, top50, t_day, shadow_path)
    run = next_run(paths, t, top_run)
    missing = [str(s) for s in (manifest.get("teacher_live") or {}).get("prev_day_missing_stocks") or []]
    new_sha = content_sha(snapshot(models)) if records else state_sha
    # 先寫 inputs_<t>.npz 再存狀態：中途被砍時，記下的更新不會比狀態少（recover_from_inputs 同一天取最後一筆）
    inputs_sha = write_inputs(paths.inputs_npz(t, run), records, panel, us_row, used, held if hold is not None else [],
                              missing, paths.initial.name, new_sha)
    if records:
        new_snap = snapshot(models)
        state_meta = {"last_update_date": day_text(new_last), "content_sha256": new_sha, "parent": state_name,
                      "parent_content_sha256": state_sha,
                      "updates": [{"date": day_text(r["date"]), "rows": r["rows"], "before": r["before"],
                                   "after": r["after"]} for r in records],
                      "held": {"date": day_text(hold), "stocks": held} if hold is not None else None,
                      "environment": environment(), "code_commit": git_commit(paths.root), "files_sha256": files_sha,
                      "features_from": {"teacher": day_text(calendar[0]),
                                        "yfinance": {n: day_text(b["date"].min()) for n, b in us_bars.items() if len(b)}},
                      "origin": UB04_SOURCE, "line": paths.initial.name, "made_for": t,
                      "next_step": "下一個交易日早上：補更新最後更新日之後、t 之前的交易日，再預測 t",
                      "written_at": taipei_now().isoformat(timespec="seconds")}
        state_name, state_sha = commit_state(paths, new_snap, state_meta), new_sha
        last_update = new_last
    batch = table.assign(
        run=run, date=t, js_n1=table["js"], note_n1=note, state_n1=day_text(last_update), state_sha_n1=state_sha,
        updated_n1=" ".join(day_text(r["date"]) for r in records), stale_n1=int(hold is not None),
        stale_us_n1=stale_us, **{f"{name}_n1": float(us_row[name]) for name in US_FILES},
        us_bar_n1=" ".join(f"{name}:{day_text(used[name]) if used[name] is not None else '沒有'}" for name in US_FILES),
        shadow_sha_n1=shadow_sha, inputs_sha_n1=inputs_sha, files_sha_n1=files_sha,
        code_commit=git_commit(paths.root), made_at=taipei_now().isoformat(timespec="seconds"))
    for column in ("pred_n1", "c2v2d_same_n1"):
        batch[column] = batch[column].astype("Int64")
    append_batch(paths.n1_csv(t), batch)

    if note:
        n1_text = f"N1 空白（{note}）"
    else:
        shadow = pd.read_csv(shadow_path, dtype={"stock_id": str}).set_index("stock_id").reindex(table["stock_id"])
        swaps = int((table["pred_n1"].to_numpy() != shadow["pred_c2v2d"].to_numpy()).sum() // 2) \
            if "pred_c2v2d" in shadow.columns else -1
        n1_text = f"N1 猜漲 {int(table['pred_n1'].sum())} 檔、和 c2v2d 換 {swaps} 組"
    flags = [f"stale_n1（{day_text(hold)} 有新缺的 {'、'.join(held)}，先不更新）"] if hold is not None else []
    flags += ["stale_us_n1"] if stale_us else []
    flags += [f".cache/n1 從起始狀態重來，用 inputs_*.npz 重播了 {len(recovered)} 次更新"] if recovered else []
    return (f"n1 {t} 第 {run} 批：補更新 {' '.join(day_text(r['date']) for r in records) or '沒有'}，"
            f"狀態 {state_name}；JS {len(js)} 檔；{n1_text}{'；' + '、'.join(flags) if flags else ''}；"
            f"寫 {os.path.relpath(paths.n1_csv(t), paths.root)}")


# ================================================================ 重現檢查（oop 第一次跑之前，tests/test_n1_model.py 也用）


def replay_inputs(root: Path, commit: str, workdir: Path) -> Path:
    """git archive 拿 commit 的老師檔和 yfinance 原始檔，解到 workdir，回傳 workdir 裡的 data/raw。"""
    out = subprocess.run(["git", "archive", "--format=tar", commit, "data/raw/teacher", "data/raw/yfinance"], cwd=root,
                         capture_output=True, timeout=300)
    if out.returncode != 0:
        raise N1Error(f"git archive {commit[:7]} 失敗：{out.stderr.decode(errors='replace')[-200:]}", CODE_DATA)
    with tarfile.open(fileobj=io.BytesIO(out.stdout)) as archive:
        archive.extractall(workdir, filter="data")
    return workdir / "data" / "raw"


def replay_check(root: Path, initial_dir: str, workdir: Path, adopt_into: Paths | None = None) -> dict:
    """只換平台的重現檢查（UB 04 報告第 8 節「第一次在 oop 跑之前」第 1 步）：老師檔和 sox、tsm_adr、vix 用 meta.json
    記的正式流程 commit（f02b89d），gspc 用 tests/fixtures/n1/gspc_yahoo_d06.csv，從 kd05 那份狀態逐日走 11-13～11-20，
    再補更新 11-20。比 tests/fixtures/n1/js_preds_cont.csv 的 js_yahoo_gspc 和 Yahoo 那份 11-20 狀態的內容雜湊。
    adopt_into 有給、而且那條還沒有 current.json 時，把走出來的狀態當成起點（Kaggle 的狀態在這台對不上時用）。"""
    initial = root / initial_dir
    meta = read_json(initial / "meta.json")
    check_versions(meta)
    states = meta["states"]
    kd05 = next(name for name, info in states.items() if info.get("kd05_exact"))
    target = next(name for name, info in states.items() if info.get("parent") == kd05 and "yahoo" in name)
    with np.load(initial / "norm.npz") as norm_file:
        norm = (norm_file["mean"], norm_file["sd"])
    torch.set_num_threads(THREADS)
    try:
        torch.set_num_interop_threads(INTEROP_THREADS)
    except RuntimeError:
        pass
    raw = replay_inputs(root, meta["commits"]["production"], workdir)
    all100, top50 = meta["all100"], meta["top50"]
    top_idx = np.array([all100.index(s) for s in top50])
    teacher = load_teacher(raw, all100)
    last_day = pd.Timestamp(states[target]["last_update_date"])
    start = pd.Timestamp(states[kd05]["last_update_date"])
    calendar = calendar_of(teacher[teacher["date"] <= last_day])
    days = list(calendar[(calendar > start) & (calendar <= last_day)]) + [last_day + pd.Timedelta(days=1)]
    us_bars = {name: read_bars(raw / "yfinance" / f"{file}.csv") for name, file in US_FILES.items() if name != "gspc"}
    gspc = pd.read_csv(root / REPLAY_FIXTURES / "gspc_yahoo_d06.csv", parse_dates=["date"], float_precision="round_trip")
    gspc = gspc.set_index("date").iloc[:, 0]
    us_bars["gspc"] = us_bars["sox"]   # 佔位：gspc 由 override 整欄換掉
    verify_folder(initial / kd05, read_json(initial / "sha256.json"), prefix=f"{kd05}/")
    snap = load_state(initial / kd05)
    if content_sha(snap) != states[kd05]["content_sha256"]:
        raise N1Error(f"{kd05} 載入後的內容雜湊和 meta.json 不一樣", CODE_STATE)
    models = restore(snap)
    preds, day_inputs, updates, last = replay(models, teacher, us_bars, days, norm, all100, top_idx, start,
                                              override={"gspc": gspc})
    ref = pd.read_csv(root / REPLAY_FIXTURES / "js_preds_cont.csv", parse_dates=["date"], dtype={"stock_id": str},
                      float_precision="round_trip")
    mine = pd.concat([p for day, p in preds.items() if day <= last_day], ignore_index=True)
    both = ref.merge(mine.astype({"stock_id": str}), on=["date", "stock_id"], how="outer", indicator=True)
    diff = (both["js"].astype(np.float64) - both["js_yahoo_gspc"]).abs()
    final = snapshot(models)
    result = {"days": [day_text(d) for d in days[:-1]], "cells": int((both["_merge"] == "both").sum()),
              "unmatched": int((both["_merge"] != "both").sum()), "max_abs_diff": float(diff.max()),
              "updates": [{"date": day_text(r["date"]), "rows": r["rows"]} for r in updates],
              "last_update": day_text(last), "content_sha256": content_sha(final),
              "expected_sha256": states[target]["content_sha256"], "environment": environment(),
              "preds": preds, "day_inputs": day_inputs, "updates_raw": updates}
    result["state_identical"] = result["content_sha256"] == result["expected_sha256"]
    if adopt_into is not None and not (adopt_into.line / "current.json").exists():
        commit_state(adopt_into, final, {"last_update_date": day_text(last), "content_sha256": result["content_sha256"],
                                         "parent": kd05, "inputs": "replay on this host: teacher and US from "
                                         f"{meta['commits']['production'][:7]}, gspc from {REPLAY_FIXTURES}",
                                         "replay_max_abs_diff": result["max_abs_diff"],
                                         "kaggle_state_identical": result["state_identical"], "origin": UB04_SOURCE,
                                         "environment": environment(), "code_commit": git_commit(root),
                                         "next_step": "下一個交易日早上：補更新最後更新日之後、t 之前的交易日，再預測 t"})
        result["adopted"] = True
    return result


# ================================================================ 命令列


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="N1 影子跑：JS_ONLINE 補更新、預測 t、和 c2v2d 組成 N1（只記不交）")
    parser.add_argument("--date", help="預測日 t（YYYY-MM-DD）")
    parser.add_argument("--root", help="repo 根目錄（測試用；不給就是這支程式所在的 repo）")
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--submission-dir", default="data/submission")
    parser.add_argument("--initial-dir", default="models/n1/ub04_v5")
    parser.add_argument("--start-state", default="state_2026-11-20_yahoo_gspc")
    parser.add_argument("--cache-dir", default=".cache/n1")
    parser.add_argument("--max-runs", type=int, default=2)
    parser.add_argument("--replay-check", action="store_true",
                        help="只換平台的重現檢查（用 meta.json 記的 commit 和 tests/fixtures/n1），不寫 data/")
    parser.add_argument("--adopt", action="store_true",
                        help="和 --replay-check 一起用：.cache/n1 還沒有狀態時，把這台走出來的 11-20 狀態當起點")
    args = parser.parse_args(argv)
    if not args.replay_check:
        if not args.date:
            parser.error("要給 --date")
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            parser.error("--date 要是 YYYY-MM-DD")
    return args


def public(text: str, root: Path) -> str:
    """寫出去的訊息：路徑換成相對的（log 會推上 GitHub，不寫出主機的家目錄）。"""
    return text.replace(str(root), ".").replace(str(Path.home()), "~")


def main(argv=None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve() if args.root else ROOT
    paths = Paths(root, args)
    paths.cache.mkdir(parents=True, exist_ok=True)
    with open(paths.cache / "n1.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("上一次的 n1 還在跑，這次不跑", file=sys.stderr)
            return CODE_BUSY
        try:
            if args.replay_check:
                with tempfile.TemporaryDirectory(dir=paths.cache) as workdir:
                    result = replay_check(root, args.initial_dir, Path(workdir), paths if args.adopt else None)
                print(json.dumps({k: v for k, v in result.items() if k not in ("preds", "day_inputs", "updates_raw")},
                                 ensure_ascii=False, indent=1))
                passed = result["max_abs_diff"] <= 1e-12 and result["unmatched"] == 0 and result["state_identical"]
                return 0 if passed else 1
            print(public(run_day(paths, args.date, args.max_runs), root))
            return 0
        except N1Error as e:
            print(f"n1 停下：{public(str(e), root)}", file=sys.stderr)
            return e.code
        except Exception as e:
            (paths.cache / "last_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            print(f"n1 出錯：{type(e).__name__}: {public(str(e), root)[:300]}（traceback 在 .cache/n1/last_error.txt）",
                  file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
