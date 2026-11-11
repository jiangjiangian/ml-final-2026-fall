"""持續性規則：每天交件暫時用的模型（使用者 2026-11-12）。config 的 daily_model.kind 是 persist 時 run_daily_test.py 用它。

規則照 Kaggle notebook 14 的 persist120（回測和驗證在 README「每天交件的模型」、memory/context/pipeline.md）：
    1. 只看要預測的那幾檔（網站範本的 50 檔）。每個有答案的交易日，e = 這檔的盤中報酬 − 當天這幾檔的平均，
       也就是這檔股票那天比同伴強多少。
    2. 預測日 d 的分數 = 這檔股票在 d 之前 days 個有答案的交易日的 e 的平均。有值的日子不到 min_days 就沒有分數。
    3. 當天照分數排名，前一半猜 1、後一半猜 0。沒有分數的排在中間；名次一樣時代號大的排前面。
每天猜漲和猜跌各一半，所以官方分數只來自「哪幾檔比較強」，和大盤當天漲或跌無關。
只用日期早於 d 的答案，d 當天的價格、成交量、答案都不會用到。不用訓練，也不讀其他特徵欄。

回測（notebook 14，2024-01-02～2026-10-08 共 670 天，官方分數）：每天平均 +0.00069，95% 區間 +0.00040～+0.00101，
11 季都是正的。同一段期間全猜 0 是 +0.00046，但每季正負不定。
"""

import pandas as pd


class RuleError(RuntimeError):
    """答案太舊或有分數的股票太少，不能用這條規則。"""


def relative_returns(data: pd.DataFrame, stocks: list) -> pd.DataFrame:
    """日期 × 股票的 e：這檔的盤中報酬 − 當天 stocks 這幾檔的平均。只有有答案的日子，照日期排。"""
    rows = data[data["stock_id"].isin(stocks) & data["label_intraday_return"].notna()]
    if rows.empty:
        raise RuleError("特徵表沒有這幾檔股票的答案")
    e = rows["label_intraday_return"] - rows.groupby("date")["label_intraday_return"].transform("mean")
    return rows.assign(e=e).pivot(index="date", columns="stock_id", values="e").sort_index()


def predict(data: pd.DataFrame, cfg: dict, dates: list, stocks: list) -> pd.DataFrame:
    """回傳 dates × stocks 的 DataFrame：date（YYYY-MM-DD）、stock_id、score、prob、pred。

    data 要有 date、stock_id、label_intraday_return（online_lr.load_data 或 features.load_features 的結果都可以）。
    score 是第 2 步的平均；prob 是當天名次換成 0～1（不是機率，欄名和 online_lr.predict 一樣方便換模型）；pred 是 0／1。
    """
    m = cfg["persist_rule"]
    stocks = sorted(str(s) for s in stocks)
    target = sorted(pd.to_datetime(dates))
    if not target or not stocks:
        raise RuleError("沒有要預測的日子或股票")
    data = data.assign(date=pd.to_datetime(data["date"]), stock_id=data["stock_id"].astype(str))
    relative = relative_returns(data, stocks)
    trailing = relative.rolling(m["days"], min_periods=m["min_days"]).mean()   # 第 k 列：到第 k 個有答案的日子為止
    labeled = relative.index
    table_days = pd.DatetimeIndex(sorted(data["date"].unique()))
    out = []
    for d in target:
        k = labeled.searchsorted(d, side="left")   # d 之前有幾個有答案的日子
        if k == 0:
            raise RuleError(f"{d:%Y-%m-%d} 之前沒有答案")
        last = labeled[k - 1]
        stale = int(((table_days > last) & (table_days < d)).sum())
        if stale > m["max_stale_days"]:
            raise RuleError(f"{d:%Y-%m-%d} 之前最新的答案是 {last:%Y-%m-%d}，中間隔了 {stale} 個交易日")
        score = trailing.iloc[k - 1].reindex(stocks)
        if score.notna().sum() < m["min_scored_share"] * len(stocks):
            raise RuleError(f"{d:%Y-%m-%d} 只有 {int(score.notna().sum())} 檔有分數（共 {len(stocks)} 檔）")
        rank = (score.rank(pct=True) - 0.5).fillna(0.0)   # −0.5～0.5；沒有分數的排在中間
        order = rank.rank(method="first")                 # 名次一樣時照代號，代號大的名次高
        out.append(pd.DataFrame({"date": d.strftime("%Y-%m-%d"), "stock_id": stocks, "score": score.to_numpy(),
                                 "prob": rank.to_numpy() + 0.5,
                                 "pred": (order > len(stocks) / 2).astype(int).to_numpy()}))
    return pd.concat(out, ignore_index=True)
