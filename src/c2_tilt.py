"""C2、C2v2d：排名集成加上「看大盤方向，換高 β 或低 β 股票」的傾斜（組員的 c2_tilt_backtest.ipynb）。

config 的 daily_model.kind 是 c2v2d 或 c2 時 run_daily_test.py 用它（使用者 2026-11-15 決定換成 c2v2d，備援 c2）。
猜漲檔數不變（每天一半猜 1），只換「哪幾檔」。算式照組員那本和 Kaggle notebook 44：

    1. combined：rank_ensemble.predict 的三個模型（ridge、kridge、lgbm）各自換成當天要預測的股票裡的名次 − 0.5，
       取平均，不再排名。p = 0.5 時選出來的和 rank_ensemble 一模一樣。
    2. β̃：每檔過去 120 個有答案的交易日，盤中報酬對「100 檔平均盤中報酬」的斜率（兩邊都退一天，至少 60 天），
       換成當天要預測的股票裡的名次 − 0.5，缺值給 0。
    3. p：方向模型估「今天要預測的股票平均盤中報酬 > 0」的機率。L2 邏輯迴歸（C = 1），樣本權重 |m|，
       狀態用訓練期的 1%、99% 截尾再標準化，缺值補 0（等於訓練期平均）。
       每個月重訓一次：重訓日是當月第一個「要預測的股票都有答案」的交易日；t 之前當月還沒有這種日子時就是 t。
       訓練資料是 2020-03-01 到重訓日前一天。C2 用 14 個狀態，C2v2d 用 20 個（見 STATES）。
    4. 分數 = combined + γ·(2p − 1)·β̃（γ = 2）。p > 0.5 時高 β 加分，p < 0.5 時低 β 加分。當天前一半猜 1。

狀態都是台北 07:10 前知道的：老師 global 表的美股（t 那列 = 前一夜美股收盤）、台股和韓股和台指期未平倉
（只用 t 以前的列）、要預測的股票前幾天的盤中報酬和跳空、長表 t 那列的 9 個市場欄（*_ret_lag1）。

回測（notebook 44，2025-01-02～2026-10-08，排名用每月重訓的版本）：C2v2d 每天比原版多 +0.000324（t 2.54），
C2 +0.000285。MT 24 拆解：押大盤那塊和 Decider P4 的調檔規則是同一件事；另外約 +0.00018 是跟著 p 走的個股效應。

資料不對就丟 TiltError（rank_ensemble 的 EnsembleError 照樣往上丟），讓 run_daily_test.py 換備援：
    - 老師 global 表沒有 t 那列的美股（排程 07:10 時通常已經有；美國或韓國休市時可能沒有，那天就用備援）。
    - t 的狀態缺超過 max_missing_states 個（例如長表的市場欄沒更新）。
    - 要預測的股票在 t 之前的交易日不夠訓練方向模型（少於 min_train_days）。
"""

from pathlib import Path

import numpy as np
import pandas as pd

from src import rank_ensemble, utils

STATES_14 = ["us_gspc", "us_ixic", "vix", "vix_chg", "twii_prev", "ks11_prev", "oi_chg1", "oi_chg5",
             "mkt_1", "mkt_3", "mkt_5", "gap_prev", "disp_prev", "us_gspc_5"]
REPO_VARS = ["tx_night_ret_lag1", "sox_ret_lag1", "tsm_adr_ret_lag1", "nvda_ret_lag1", "dji_ret_lag1",
             "usd_twd_am_ret_lag1", "us10y_ret_lag1", "wti_ret_lag1", "gold_ret_lag1"]
STATES = {"c2": STATES_14,   # C2v2d 去共線：S&P、Nasdaq 和道瓊相關 0.89～0.95 只留道瓊；費半和 NVDA 0.88 只留費半
          "c2v2d": [c for c in STATES_14 + REPO_VARS if c not in ("us_gspc", "us_ixic", "nvda_ret_lag1")]}
_CACHE = {}   # 同一次執行裡 c2v2d 失敗換 c2 時，不重算 rank_ensemble 和讀資料


class TiltError(RuntimeError):
    """資料不夠或沒更新，不能用 C2、C2v2d。"""


def read_global(teacher_dir: Path) -> pd.DataFrame:
    """老師 global 表 Training 接上 Live，同一天留 Live 的。-1（還沒填）當成空值。"""
    parts = [pd.read_csv(teacher_dir / part / "global" / "global_data.csv", parse_dates=["date"]) for part in ("training", "live")]
    world = pd.concat(parts).drop_duplicates("date", keep="last").sort_values("date").replace(-1, np.nan)
    world["date"] = world["date"].astype("datetime64[ns]")
    return world.reset_index(drop=True)


def beta120(frame: pd.DataFrame, days: int) -> pd.Series:
    """每一列 = 這檔股票前 days 個有答案的交易日，盤中報酬對 100 檔平均盤中報酬的斜率（至少 days // 2 天）。"""
    stock = frame["stock_id"]

    def trailing(values):
        return values.groupby(stock, sort=False).transform(lambda v: v.rolling(days, min_periods=days // 2).mean())

    market_100 = frame.groupby("date")["r"].transform("mean")
    prev_r = frame.groupby("stock_id", sort=False)["r"].shift(1)
    prev_m = market_100.groupby(stock, sort=False).shift(1)
    cov = trailing(prev_r * prev_m) - trailing(prev_r) * trailing(prev_m)
    var = trailing(prev_m ** 2) - trailing(prev_m) ** 2
    return cov / var


def market_states(frame: pd.DataFrame, world: pd.DataFrame, stocks: list, t: pd.Timestamp) -> pd.DataFrame:
    """每個有答案的交易日加上 t 一列：23 個狀態和 m（要預測的股票當天平均盤中報酬，t 是空的）。"""
    days = pd.DatetimeIndex(sorted(set(frame.loc[frame["r"].notna(), "date"]) | {t})).astype("datetime64[ns]")
    calendar = pd.DataFrame({"date": days})
    us = pd.merge_asof(calendar, world[["date", "^GSPC", "^IXIC", "^VIX"]].dropna(), on="date",
                       allow_exact_matches=True)                         # 美股：第 t 列 = 前一夜美股收盤
    tw = pd.merge_asof(calendar, world[["date", "^TWII", "^KS11", "TX_OI"]].dropna(), on="date",
                       allow_exact_matches=False)                        # 台股、韓股、台指期：只用 t 以前的列
    states = pd.DataFrame(index=days)
    states["us_gspc"] = us["^GSPC"].pct_change().to_numpy()
    states["us_ixic"] = us["^IXIC"].pct_change().to_numpy()
    states["vix"] = us["^VIX"].to_numpy()
    states["vix_chg"] = np.log(us["^VIX"]).diff().to_numpy()
    states["twii_prev"] = tw["^TWII"].pct_change().to_numpy()
    states["ks11_prev"] = tw["^KS11"].pct_change().to_numpy()
    open_interest = tw["TX_OI"]
    states["oi_chg1"] = (open_interest.diff() / open_interest.shift(5).abs()).to_numpy()   # 照組員：分母是 5 天前
    states["oi_chg5"] = (open_interest.diff(5) / open_interest.shift(5).abs()).to_numpy()
    top = frame[frame["stock_id"].isin(stocks)]
    m = top.groupby("date")["r"].mean().reindex(days)
    states["mkt_1"] = m.shift(1)
    states["mkt_3"] = m.rolling(3).sum().shift(1)
    states["mkt_5"] = m.rolling(5).sum().shift(1)
    states["gap_prev"] = top.groupby("date")["a_gap"].mean().reindex(days)    # a_gap 已經退一天 = 前一天的跳空
    states["disp_prev"] = top.groupby("date")["r"].std().reindex(days).shift(1)
    states["us_gspc_5"] = states["us_gspc"].rolling(5).sum()
    states = states.join(frame.groupby("date")[REPO_VARS].first().reindex(days))  # 長表的市場欄每檔都一樣
    states["m"] = m
    us_rows = world[["date", "^GSPC", "^IXIC", "^VIX"]].dropna()["date"]
    states.attrs["us_has_t"] = bool((us_rows == t).any())
    states.attrs["us_last_row"] = f"{us_rows[us_rows <= t].max():%Y-%m-%d}" if (us_rows <= t).any() else "沒有"
    return states


def standardize(train: pd.DataFrame, test: pd.DataFrame) -> tuple:
    """用訓練期的 1%、99% 截尾，再用訓練期的平均和標準差標準化；缺值補 0。"""
    low, high = train.quantile(0.01), train.quantile(0.99)
    train, test = train.clip(low, high, axis=1), test.clip(low, high, axis=1)
    mean, sd = train.mean(), train.std().replace(0, 1)
    return ((train - mean) / sd).fillna(0), ((test - mean) / sd).fillna(0)


def fit_day_of(t: pd.Timestamp, frame: pd.DataFrame, stocks: list) -> pd.Timestamp:
    """當月第一個「要預測的股票都有答案」的交易日；t 之前當月還沒有這種日子就是 t。"""
    counts = frame[frame["stock_id"].isin(stocks) & frame["r"].notna()].groupby("date").size()
    complete = counts.index[(counts.to_numpy() == len(stocks)) & (counts.index < t)]
    same_month = complete[pd.DatetimeIndex(complete).to_period("M") == t.to_period("M")]
    return pd.Timestamp(same_month.min()) if len(same_month) else t


def direction(states: pd.DataFrame, columns: list, fit_day: pd.Timestamp, days: list, c: dict) -> dict:
    """在 fit_day 之前的日子訓練方向模型，回傳 days 每天的 p 和這次重訓的資訊。sklearn 用到才載入。"""
    from sklearn.linear_model import LogisticRegression

    train = states[(states.index >= pd.Timestamp(c["direction_start"])) & (states.index < fit_day)].dropna(subset=["m"])
    if len(train) < c["min_train_days"]:
        raise TiltError(f"{fit_day:%Y-%m-%d} 之前只有 {len(train)} 天可以訓練方向模型")
    x_train, x_days = standardize(train[columns], states.loc[days, columns])
    weight = train["m"].abs() / train["m"].abs().mean()
    model = LogisticRegression(C=1.0, max_iter=2000).fit(x_train, (train["m"] > 0).astype(int), sample_weight=weight)
    return {"p": pd.Series(model.predict_proba(x_days)[:, 1], index=days), "n_train": len(train),
            "coef": pd.Series(model.coef_[0], index=columns), "intercept": float(model.intercept_[0])}


def load_inputs(data, cfg: dict, dates: list, stocks: list) -> dict:
    """rank_ensemble 的三個模型、特徵表和老師 global 表。同一次執行裡算過就直接拿（c2v2d 換 c2 時不重算）。"""
    key = (tuple(dates), tuple(stocks))
    if key not in _CACHE:
        base = rank_ensemble.predict(data, cfg, dates, stocks)        # 爬蟲紀錄、空白比例等檢查都在這裡
        t = max(pd.to_datetime(dates))
        frame = rank_ensemble.load_frame(cfg, t)
        world = read_global(utils.ROOT / cfg["data"]["raw_dir"] / "teacher")
        _CACHE.clear()
        _CACHE[key] = {"base": base, "frame": frame, "world": world}
    return _CACHE[key]


def predict(data, cfg: dict, dates: list, stocks: list, variant: str = "c2v2d", *, inputs=None) -> pd.DataFrame:
    """回傳 dates × stocks 的表：rank_ensemble 的欄，加上 combined、beta120、beta_rank、p_up、tilt、score、prob、pred。

    data 不用（和其他模型同一個呼叫方式）。inputs 只給重播用：{"base", "frame", "world"}，不給就自己讀。
    prob 是分數在當天的名次換成 0～1（不是機率）；p_up 才是方向模型的機率。
    """
    c = cfg["c2_tilt"]
    stocks = sorted(str(s) for s in stocks)
    days = sorted(pd.to_datetime(dates))
    inputs = inputs or load_inputs(data, cfg, [f"{d:%Y-%m-%d}" for d in days], stocks)
    frame, world = inputs["frame"], inputs["world"]
    result = inputs["base"][["date", "stock_id", "ridge", "kridge", "lgbm", "prob", "pred"]].copy()
    result = result.rename(columns={"prob": "base_prob", "pred": "base_pred"})
    result["date"] = pd.to_datetime(result["date"])
    by_day = result.groupby("date")
    result["combined"] = sum((by_day[name].rank(pct=True) - 0.5).fillna(0.0) for name in rank_ensemble.MODELS) / 3
    betas = frame.assign(beta120=beta120(frame, c["beta_days"]))[["date", "stock_id", "beta120"]]
    result = result.merge(betas, on=["date", "stock_id"], how="left", validate="one_to_one")
    result["beta_rank"] = (result.groupby("date")["beta120"].rank(pct=True) - 0.5).fillna(0.0)
    for t in days:
        states = market_states(frame, world, stocks, t)
        if not states.attrs["us_has_t"]:
            raise TiltError(f"老師 global 表沒有 {t:%Y-%m-%d} 那列的美股（t 以前最後一列是 {states.attrs['us_last_row']}）")
        missing = [s for s in STATES[variant] if pd.isna(states.at[t, s])]
        if len(missing) > c["max_missing_states"]:
            raise TiltError(f"{t:%Y-%m-%d} 的狀態缺 {len(missing)} 個：{', '.join(missing)}")
        fit_day = fit_day_of(t, frame, stocks)
        fitted = direction(states, STATES[variant], fit_day, [t], c)
        today = result["date"] == t
        result.loc[today, "p_up"] = float(fitted["p"].iloc[0])
        result.loc[today, "fit_day"] = f"{fit_day:%Y-%m-%d}"
        result.loc[today, "n_train"] = fitted["n_train"]
        result.loc[today, "missing_states"] = len(missing)
    result["tilt"] = c["gamma"] * (2 * result["p_up"] - 1)              # 正 = 今天偏好高 β，負 = 偏好低 β
    result["score"] = result["combined"] + result["tilt"] * result["beta_rank"]
    by_day = result.groupby("date")
    order = by_day["score"].rank(method="first")                       # 同分時照代號，代號大的名次高（和 rank_ensemble 一樣）
    result["prob"] = (order - 0.5) / by_day["stock_id"].transform("size")
    result["pred"] = (order > by_day["stock_id"].transform("size") / 2).astype(int)
    result["variant"] = variant
    result["date"] = result["date"].dt.strftime("%Y-%m-%d")
    return result.sort_values(["date", "stock_id"], ignore_index=True)


def predict_c2v2d(data, cfg: dict, dates: list, stocks: list) -> pd.DataFrame:
    """C2v2d：20 個狀態。"""
    return predict(data, cfg, dates, stocks, "c2v2d")


def predict_c2(data, cfg: dict, dates: list, stocks: list) -> pd.DataFrame:
    """C2：14 個狀態（組員原版）。"""
    return predict(data, cfg, dates, stocks, "c2")
