"""組員的邏輯迴歸，run_daily_test.py 用（使用者 2026-11-06：先用組員的方法和模型跑自動化）。

方法照 notebooks/feature_switch.ipynb 第 6 節：
    1. 預測日所在的那一週 W，fit_end = W 往前 online_lr.online_weeks 週的週一。
    2. 用 fit_end 之前 train_months 個月有答案的列（100 檔都用）fit：中位數補空值、標準化、截在 ±clip_z，
       LogisticRegression(C)。前處理只在這段資料上 fit。
    3. 從 fit_end 開始逐日往前走：當天要預測的就先預測（只看過前一天以前的答案），再用當天有答案的列做
       steps 步 GD（L2 的 λ = 1 / (C × fit 的列數)）。
    4. 機率 > threshold 猜 1。
每天早上都重新 fit，不讀 models/：每週重訓、每天微調本來就是這個方法的一部分（和 predict.py「只載入
models/ 的模型」不同，見 memory/context/pipeline.md）。

特徵：組員 notebooks/build_model.ipynb 的 26 個個股特徵 + 特徵表的 model_columns（features.model_columns）。
個股特徵用老師個股檔「填好的列」算（crawler.row_filled），滾動視窗只往回看；(日期 d, 股票) 那列拿的是那檔股票
日期早於 d 的最後一個填好的列算出的值，所以 t 當天的價格、成交量、法人都不會用到。
Live（Training 最後一天之後）的列裡外資持股和法人欄的 -1 當成空值；Training 的 -1 是真的（買賣超 1 股），保留。
外資持股比率待定時沿用這檔股票前一個有值的比率（使用者 2026-11-07）：t 早上 i 那列常常還沒有這個值。
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src import crawler, features, utils

RENAME = {
    "etl:adj_close": "close", "etl:adj_open": "open", "etl:adj_high": "high", "etl:adj_low": "low",
    "price:成交筆數": "n_trades", "price:成交金額": "value", "price:成交股數": "shares",
    "foreign_investors_shareholding:全體外資及陸資持股比率": "foreign_hold_pct",
    "institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)": "foreign_net",
    "institutional_investors_trading_summary:投信買賣超股數": "trust_net",
    "institutional_investors_trading_summary:自營商買賣超股數(自行買賣)": "dealer_net",
    "institutional_investors_trading_summary:自營商買賣超股數(避險)": "dealer_hedge_net",
}
NETS = ["foreign_net", "trust_net", "dealer_net", "dealer_hedge_net"]
LIVE_PENDING = ["foreign_hold_pct"] + NETS   # Live 列裡這幾欄的 -1 是「還沒有資料」
TECH = ["hl_range", "atr_pct", "boll_mid_dist", "boll_width", "boll_pctb", "volume", "MACD_sma5", "MACD_osc", "RSI"]
ORIG = (["orig_ret_1d", "orig_intraday_ret", "orig_gap_ret", "orig_sma_gap", "orig_macd_pct", "orig_bb_pos",
         "orig_foreign_hold", "orig_foreign_hold_chg"]
        + [f"orig_{c}{s}" for c in NETS for s in ("_pct", "_institution_hold_chg")] + ["orig_log_value"])
STOCK_FEATURES = TECH + ORIG   # 26 個


class ModelError(RuntimeError):
    """資料不夠或對不起來，不能預測。"""


def sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


# ---------------------------------------------------------------- 個股特徵


def teacher_table(teacher_dir: Path, live_dir: Path | None) -> pd.DataFrame:
    """老師個股檔填好的列 → DataFrame（date 是 Timestamp、stock_id、RENAME 後的欄、RSI、SMA…）。

    Training 全部的列，接上 Live 在 Training 最後一天之後的列（和 features.load_teacher 一樣），再只留 row_filled。
    """
    stocks, _, _ = features.load_teacher(teacher_dir, None)
    boundary = max(d for rows in stocks.values() for d in rows)
    live = set()
    if live_dir is not None and Path(live_dir).exists():
        for path in sorted((Path(live_dir) / "market").glob("*.csv")):
            if path.stem not in stocks:
                raise ModelError(f"Live 有 Training 沒有的代號 {path.stem}")
            for r in features.read_csv_rows(path, crawler.STOCK_COLUMNS):
                if features.check_date(r[0], path.name) > boundary:
                    stocks[path.stem][r[0]] = r
                    live.add((path.stem, r[0]))
    records, is_live = [], []
    for code in sorted(stocks):
        for d in sorted(stocks[code]):
            row = stocks[code][d]
            if crawler.row_filled(row):
                records.append([code] + row)
                is_live.append((code, d) in live)
    df = pd.DataFrame(records, columns=["stock_id"] + list(crawler.STOCK_COLUMNS)).rename(columns=RENAME)
    for c in df.columns[2:]:
        df[c] = pd.to_numeric(df[c].replace("", np.nan), errors="raise")
    live_mask = np.array(is_live, dtype=bool)
    pending_hold = live_mask & (df["foreign_hold_pct"] == -1)
    for c in LIVE_PENDING:
        df.loc[live_mask & (df[c] == -1), c] = np.nan
    # 使用者 2026-11-07：Live 的外資持股比率常常隔天才公布，待定時沿用這檔股票前一個有值的比率（變化就成了 0）
    df["foreign_hold_pct"] = df["foreign_hold_pct"].where(
        ~pending_hold, df.groupby("stock_id", sort=False)["foreign_hold_pct"].ffill())
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["stock_id", "date"], ignore_index=True)


def stock_features(raw: pd.DataFrame) -> pd.DataFrame:
    """組員 build_stock_features：每列用到那一天收盤為止的資料（滾動視窗只往回看）。回傳 date、stock_id、26 欄。"""
    g = raw.groupby("stock_id", sort=False)
    C, O, H, L = raw["close"], raw["open"], raw["high"], raw["low"]
    prev_close = g["close"].shift(1)

    def roll(col, n, how):
        return g[col].transform(lambda s: getattr(s.rolling(n), how)(**({"ddof": 0} if how == "std" else {})))

    f = raw[["date", "stock_id"]].copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        f["orig_ret_1d"] = C / prev_close - 1
        f["orig_intraday_ret"] = C / O - 1
        f["orig_gap_ret"] = O / prev_close - 1
        f["orig_sma_gap"] = C / raw["SMA"] - 1
        f["orig_macd_pct"] = raw["MACD"] / C
        f["orig_bb_pos"] = (C - raw["BBANDS_lower"]) / (raw["BBANDS_upper"] - raw["BBANDS_lower"])
        f["orig_foreign_hold"] = raw["foreign_hold_pct"]
        f["orig_foreign_hold_chg"] = g["foreign_hold_pct"].diff()
        for col in NETS:
            f[f"orig_{col}_pct"] = np.log1p(raw[col] / raw["shares"])
            f[f"orig_{col}_institution_hold_chg"] = f[f"orig_{col}_pct"].groupby(raw["stock_id"]).diff()
        f["orig_log_value"] = np.log1p(raw["value"])

        M, sd = roll("close", 20, "mean"), roll("close", 20, "std")
        U, Lo = M + 2 * sd, M - 2 * sd
        width = (U - Lo).where((U - Lo) > 1e-6 * M)
        vol_sma5 = roll("shares", 5, "mean")
        macd_sma5 = roll("MACD", 5, "mean")
        f["hl_range"] = (H - L) / C
        f["atr_pct"] = raw["ATR"] / C
        f["boll_mid_dist"] = (C - M) / M
        f["boll_width"] = (U - Lo) / M
        f["boll_pctb"] = (C - Lo) / width
        f["volume"] = (raw["shares"] - vol_sma5) / raw["shares"]
        f["MACD_sma5"] = macd_sma5 / C
        f["MACD_osc"] = (raw["MACD"] - macd_sma5) / C
        f["RSI"] = raw["RSI"]
    return f.replace([np.inf, -np.inf], np.nan)


def attach(table: pd.DataFrame, sf: pd.DataFrame) -> pd.DataFrame:
    """table 的每一列 (date, stock_id) 接上那檔股票日期早於 date 的最後一列個股特徵。feat_date 是那一列的日期。"""
    left = table.assign(date=pd.to_datetime(table["date"])).sort_values("date", kind="stable")
    right = sf.rename(columns={"date": "feat_date"}).assign(date=lambda x: x["feat_date"]).sort_values("date")
    out = pd.merge_asof(left, right, on="date", by="stock_id", allow_exact_matches=False)
    return out.sort_values(["date", "stock_id"], ignore_index=True)


def load_data(cfg: dict, *, table=None, teacher_dir=None, live_dir=None) -> pd.DataFrame:
    """特徵表（features.load_features）接上個股特徵。date 是 Timestamp。"""
    raw_dir = utils.ROOT / cfg["data"]["raw_dir"]
    table = features.load_features() if table is None else table
    raw = teacher_table(Path(teacher_dir) if teacher_dir else raw_dir / "teacher" / "training",
                        Path(live_dir) if live_dir else raw_dir / "teacher" / "live")
    keep = ["date", "stock_id", "label_y", "label_intraday_return"] + features.model_columns(cfg)
    missing = set(keep) - set(table.columns)
    if missing:
        raise ModelError(f"特徵表少了 {sorted(missing)}；model_series 改過的話要先跑 features --rebuild")
    return attach(table[keep], stock_features(raw))


def feature_columns(cfg: dict) -> list:
    return STOCK_FEATURES + features.model_columns(cfg)


# ---------------------------------------------------------------- 模型


def predict(data: pd.DataFrame, cfg: dict, dates: list, stocks: list) -> pd.DataFrame:
    """回傳 dates × stocks 的 DataFrame：date（YYYY-MM-DD）、stock_id、prob、pred。

    data 是 load_data 的結果。預測日那天的答案就算 data 裡有也不會用到：先預測再更新，fit 只用 fit_end 之前的列。
    """
    m = cfg["online_lr"]
    cols = feature_columns(cfg)
    target = sorted(pd.to_datetime(dates))
    if not target:
        raise ModelError("沒有要預測的日子")
    stocks = [str(s) for s in stocks]
    data = data.sort_values(["date", "stock_id"], ignore_index=True)
    labeled = data[data["label_y"].notna()]
    out = []
    for wk in sorted({d.to_period("W") for d in target}):
        fit_end = (wk - m["online_weeks"]).start_time
        fit = labeled[(labeled["date"] >= fit_end - pd.DateOffset(months=m["train_months"]))
                      & (labeled["date"] < fit_end)]
        y_fit = fit["label_y"].astype(int).to_numpy()
        if len(fit) == 0 or len(set(y_fit)) < 2:
            raise ModelError(f"{wk} 的訓練資料不夠（{len(fit)} 列）")
        med = fit[cols].median()
        scaler = StandardScaler().fit(fit[cols].fillna(med))

        def X(frame):
            z = np.clip(scaler.transform(frame[cols].fillna(med)), -m["clip_z"], m["clip_z"])
            return np.nan_to_num(z, nan=0.0)   # 整欄沒資料時中位數也是空的，標準化後當 0

        lr = LogisticRegression(C=m["C"], max_iter=m["max_iter"]).fit(X(fit), y_fit)
        w, b, lam = lr.coef_.ravel().copy(), float(lr.intercept_[0]), 1 / (m["C"] * len(fit))
        seg = data[(data["date"] >= fit_end) & (data["date"] <= wk.end_time)]
        for d, day in seg.groupby("date", sort=True):
            if d.to_period("W") == wk and d in target:
                rows = day.set_index("stock_id").reindex(stocks)
                if rows["date"].isna().any():
                    raise ModelError(f"{d:%Y-%m-%d} 特徵表少了 {rows.index[rows['date'].isna()].tolist()[:5]}…")
                prob = sigmoid(X(rows) @ w + b)
                out.append(pd.DataFrame({"date": d.strftime("%Y-%m-%d"), "stock_id": stocks, "prob": prob}))
            lab = day[day["label_y"].notna()]
            if len(lab):
                Xd, yd = X(lab), lab["label_y"].astype(float).to_numpy()
                for _ in range(m["steps"]):
                    grad = sigmoid(Xd @ w + b) - yd
                    w = w - m["learning_rate"] * (Xd.T @ grad / len(yd) + lam * w)
                    b = b - m["learning_rate"] * grad.mean()
    result = pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["date", "stock_id", "prob"])
    got = set(result["date"])
    lost = [d.strftime("%Y-%m-%d") for d in target if d.strftime("%Y-%m-%d") not in got]
    if lost:
        raise ModelError(f"特徵表沒有這些日子的列：{lost[:5]}")
    result["pred"] = (result["prob"] > m["threshold"]).astype(int)
    return result


def official_score(pred: pd.DataFrame, data: pd.DataFrame) -> dict:
    """官方分數：每格 (2 × pred − 1) × 當天盤中報酬，取平均。也算全猜 0、全猜 1 和正確率。"""
    truth = data.assign(date=data["date"].dt.strftime("%Y-%m-%d"))[["date", "stock_id", "label_y",
                                                                    "label_intraday_return"]]
    j = pred.merge(truth, on=["date", "stock_id"], how="left")
    if j["label_intraday_return"].isna().any():
        return {"cells": len(j), "missing_truth": int(j["label_intraday_return"].isna().sum())}
    r = j["label_intraday_return"].to_numpy()
    p = j["pred"].to_numpy()
    return {"cells": len(j), "score": float(((2 * p - 1) * r).mean()), "all_0": float(-r.mean()),
            "all_1": float(r.mean()), "accuracy": float((p == j["label_y"].astype(int).to_numpy()).mean()),
            "pred_up": float(p.mean())}
