"""法人組排名集成：只給影子跑的模型（使用者 2026-11-20）。config 的 daily_model.shadow 有 rank_inst 時才算。

不能填在 daily_model.kind 或 fallback（src/models/__init__.py 的 SHADOW_ONLY），所以不會被交出去。
做法是 Kaggle notebook 33 的 X_inst：rank_ensemble 的 41 個價量欄，加法人 23 欄（config 的 rank_inst.columns），
模型、參數、訓練天數、25 檔猜漲 25 檔猜跌都和 rank_ensemble 一樣（直接呼叫 m3_rank_ensemble.predict）。
回測：另外 50 檔每天比 X_price 多 0.00019（過了多重檢定），2021 的確認沒過（p 0.078），所以先影子跑累積紀錄
（memory/projects/04-raw-feature-experiments.md 的 33、42）。

法人 23 欄都從老師個股檔的外資、投信、自營商買賣超股數和外資持股比率算，每一格是「前一個有價格的日子收盤後」的值：
    c_foreign_pct、c_trust_pct、c_dealer_pct   外資、投信、自營商當天買賣超 ÷ 當天成交股數（m3_rank_ensemble 已經算好）
    c_foreign_pct5、c_foreign_hold_chg5        外資 5 天累計買賣超 ÷ 5 天成交股數；外資持股比率 5 天的變化（已經算好）
    f_foreign_pct20、f_trust_pct5、f_trust_pct20  外資 20 天、投信 5 天和 20 天累計買賣超 ÷ 同期成交股數
    f_inst_pct                                 三大法人合計當天買賣超 ÷ 當天成交股數，截在 ±1
    f_foreign_streak、f_trust_streak           連續買超（正）或賣超（負）的天數，截在 ±20；買賣超是 0 或空白時歸零
    f_foreign_z60                              外資當天買賣超占比和自己前 60 天比的 z 分數（至少 30 天）
    f_foreign_hold、f_foreign_hold_chg20       外資持股比率；20 天的變化
    f_<foreign、trust、inst>_ema<5、10、20>_gap  當天買賣超 − 買賣超的 EMA，再 ÷ 20 天平均成交股數
算式和 notebook 25 的 institution_features 一樣。t 那列只用 t 之前的資料，t 當天的價格、成交量、法人、答案都不會用到。

什麼時候算（使用者 2026-11-20）：
    早上：第一次交件後的影子跑照常算。老師 Live 還沒填前一個交易日（爬蟲記在 data/raw/manifest.json），或要預測的
          股票裡前一個交易日的法人欄有值的不到 min_filled_share，就丟 InstError，影子檔那幾欄先空白。
    傍晚：step6_evening_score 下載老師 Live 以後補算（predict 的 late=True，不看爬蟲早上的紀錄），寫回同一個影子檔。
          這時用的還是前一個交易日的法人資料，只是比早上晚拿到。
輸出多兩欄：inst_filled（要預測的股票裡前一個交易日的法人欄有值的檔數）、late（0 是早上算的，1 是傍晚補算）。
late 是 1 的日子代表「資料到齊時模型會怎麼猜」，不代表早上 07 點多交得出來，評估能不能上線時要分開看。

和 notebook 33 不一樣的地方：33 的法人欄在訓練期空白 30% 以內都用，這裡沿用 rank_ensemble 的 max_missing（10%）。
"""

from pathlib import Path

import numpy as np
import pandas as pd

from src.models import m3_rank_ensemble as rank_ensemble
from src.pipeline import step2_features as features, utils

FILLED_COLUMNS = ["f_inst_pct", "f_foreign_hold"]   # 這兩欄都有值，才算這檔前一個交易日的法人資料到了


class InstError(RuntimeError):
    """t 的法人組排名集成算不出來。"""


def streak(sign: pd.Series) -> pd.Series:
    """連續同一個方向的天數乘上方向（買超是正的），截在 ±20；方向是 0 的日子是 0。"""
    groups = (sign != sign.shift()).cumsum()
    run = sign.groupby(groups).cumcount() + 1
    return (run * sign).where(sign != 0, 0.0).clip(-20, 20)


def institution_features(stock: pd.DataFrame) -> pd.DataFrame:
    """一檔股票第 d 天收盤後算得出的 f_ 欄，還沒退一天。stock 是 m3_rank_ensemble.read_teacher_stock 的表，依日期排。"""
    volume = stock["volume"].where(stock["volume"] > 0)
    foreign, trust = stock["foreign_net"], stock["trust_net"]
    dealer = stock["dealer_self_net"] + stock["dealer_hedge_net"]
    foreign_pct = (foreign / volume).clip(-1, 1)
    out = pd.DataFrame(index=stock.index)
    out["f_foreign_pct20"] = foreign.rolling(20).sum() / volume.rolling(20).sum()
    out["f_trust_pct5"] = trust.rolling(5).sum() / volume.rolling(5).sum()
    out["f_trust_pct20"] = trust.rolling(20).sum() / volume.rolling(20).sum()
    out["f_inst_pct"] = ((foreign + trust + dealer) / volume).clip(-1, 1)
    out["f_foreign_streak"] = streak(np.sign(foreign).fillna(0.0))
    out["f_trust_streak"] = streak(np.sign(trust).fillna(0.0))
    rolling = foreign_pct.rolling(60, min_periods=30)
    out["f_foreign_z60"] = (foreign_pct - rolling.mean()) / rolling.std()
    out["f_foreign_hold"] = stock["foreign_hold"] / 100
    out["f_foreign_hold_chg20"] = stock["foreign_hold"].diff(20)
    scale = volume.rolling(20, min_periods=10).mean()
    for name, net in [("foreign", foreign), ("trust", trust), ("inst", foreign + trust + dealer)]:
        for span in (5, 10, 20):
            out[f"f_{name}_ema{span}_gap"] = (net - net.ewm(span=span, adjust=False).mean()) / scale
    return out


def lagged_institution(teacher: pd.DataFrame, t: pd.Timestamp | None) -> pd.DataFrame:
    """每檔股票每一列 = 前一個有價格的日子收盤後的 f_ 欄（和 m3_rank_ensemble.lagged_teacher_features 同一個退法）。
    t 還沒有價格時先補一個空列，退一天後 t 那列就有值。"""
    parts = []
    for stock_id, stock in teacher.groupby("stock_id", sort=False):
        if t is not None and stock["date"].max() < t:
            stock = pd.concat([stock, pd.DataFrame({"date": [t], "stock_id": [stock_id]})], ignore_index=True)
        lagged = institution_features(stock).shift(1)
        lagged[["date", "stock_id"]] = stock[["date", "stock_id"]]
        parts.append(lagged)
    return pd.concat(parts, ignore_index=True).replace([np.inf, -np.inf], np.nan)


def build_frame(table: pd.DataFrame, teacher: pd.DataFrame, cfg: dict, t=None) -> pd.DataFrame:
    """m3_rank_ensemble.build_frame 的表再接上 f_ 欄。table、teacher、t 和它的一樣。"""
    t = None if t is None else pd.Timestamp(t)
    base = rank_ensemble.build_frame(table, teacher, cfg, t)
    frame = base.merge(lagged_institution(teacher, t), on=["date", "stock_id"], how="left", validate="one_to_one")
    frame.attrs = dict(base.attrs)   # stale_days 要留著給 m3_rank_ensemble.predict 檢查
    missing = [c for c in cfg["rank_inst"]["columns"] if c not in frame.columns]
    if missing:
        raise InstError(f"rank_inst.columns 有不存在的欄：{missing[:5]}")
    return frame


def load_frame(cfg: dict, t=None, *, table=None, teacher_dir=None) -> pd.DataFrame:
    """讀長表和老師檔，回傳 build_frame 的結果。"""
    table = features.load_features() if table is None else table
    teacher_dir = Path(teacher_dir) if teacher_dir else utils.ROOT / cfg["data"]["raw_dir"] / "teacher"
    codes = sorted(table["stock_id"].astype(str).unique())
    teacher = pd.concat([rank_ensemble.read_teacher_stock(teacher_dir, code) for code in codes], ignore_index=True)
    return build_frame(table, teacher.sort_values(["stock_id", "date"]).reset_index(drop=True), cfg, t)


def predict(data, cfg: dict, dates: list, stocks: list, *, late: bool = False, frame=None, fit_dates=None,
            allow_missing: bool = False, manifest_path=None) -> pd.DataFrame:
    """回傳 dates × stocks 的表：m3_rank_ensemble.predict 的欄（date、stock_id、ridge、kridge、lgbm、prob、pred），
    加上 inst_filled、late。

    data 不用（和其他模型同一個呼叫方式）。late=True 是傍晚補算：不看爬蟲早上的紀錄，用現在 data/raw 的老師檔。
    frame、fit_dates、allow_missing 只給重播和測試用（和 m3_rank_ensemble.predict 的一樣）；給了 frame 就不做
    早上的資料檢查，inst_filled 是空白。算不出來丟 InstError。
    """
    c = cfg["rank_inst"]
    stocks = sorted(str(s) for s in stocks)
    days = sorted(pd.to_datetime(dates))
    if not days or not stocks:
        raise InstError("沒有要預測的日子或股票")
    t = days[-1]
    columns = list(cfg["rank_ensemble"]["columns"]) + list(c["columns"])
    filled = None
    if frame is None:
        manifest_path = manifest_path or utils.ROOT / cfg["data"]["raw_dir"] / "manifest.json"
        if not late and rank_ensemble.previous_day_unfilled(t, manifest_path):
            raise InstError(f"{t:%Y-%m-%d} 的前一個交易日在老師 Live 裡還沒填，等傍晚補算")
        frame = load_frame(cfg, t)
        missed = set() if late else rank_ensemble.previous_day_missing(t, manifest_path)
        if missed:   # 這幾檔自己前一個交易日沒填：t 那列當成空白，不用更早一天的值（和 m3_rank_ensemble 一樣）
            attrs, frame = dict(frame.attrs), frame.copy()
            frame.attrs = attrs
            frame.loc[(frame["date"] == t) & frame["stock_id"].isin(missed), columns] = np.nan
        today = frame[(frame["date"] == t) & frame["stock_id"].isin(stocks)]
        filled = int(today[FILLED_COLUMNS].notna().all(axis=1).sum())
        if filled < c["min_filled_share"] * len(stocks):
            raise InstError(f"{t:%Y-%m-%d} 要預測的 {len(stocks)} 檔裡，前一個交易日的法人欄只有 {filled} 檔有值"
                            f"{'' if late else '，等傍晚補算'}")
    settings = {**cfg, "rank_ensemble": {**cfg["rank_ensemble"], "columns": columns}}
    try:
        result = rank_ensemble.predict(None, settings, dates, stocks, frame=frame, fit_dates=fit_dates,
                                       allow_missing=allow_missing)
    except rank_ensemble.EnsembleError as e:
        raise InstError(str(e)) from e
    result["inst_filled"] = filled
    result["late"] = int(late)
    return result
