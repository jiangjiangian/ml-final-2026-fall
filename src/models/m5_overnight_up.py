"""隔夜大跌全猜漲：只給影子跑用的規則（使用者 2026-11-20）。config 的 daily_model.shadow 有 overnight_up 時才算。

不能填在 daily_model.kind 或 fallback（src/models/__init__.py 的 SHADOW_ONLY），所以不會被交出去。
目的是累積沒人看過的新日子：這條規則在回測只有一點跡象（Kaggle BT 05、07、09，memory/projects/11-breakthrough-research.md），
測試期 37 個觸發日裡 39% 的分數來自一天，要靠之後每天的紀錄才分得出真假。

規則（BT 05 的「前 10% 規則」，少一個成分）：
    1. 三個美股序列各算「從上一個台股交易日開盤前到 t 開盤前」的漲跌：台積電 ADR、費城半導體指數（yfinance）、
       S&P 500（老師 global 表）。台股連休時這段會包含好幾場美股。
    2. 每個漲跌除以自己前 std_days 個台股交易日（不含 t）的標準差，有值的平均，得到隔夜訊號 O。
       至少要 min_parts 個（2 個）有值。老師 global 在美國或韓國休市的台股交易日沒有那一列（約 13% 的日子），
       那天和隔天的 S&P 500 是空白，O 只用台積電 ADR 和費半兩個；o_parts 記用了幾個。
    3. |O| 在前 rank_days 個台股交易日（不含 t）裡的分位 o_absq = 那段日子 |O| ≤ 今天 |O| 的比例。
    4. O < 0 而且 o_absq ≥ quantile（0.90）：t 的每一檔都猜漲。其他日子照 rank_ensemble 的 25 漲 25 跌。
研究用的是四個成分（多一個美國掛牌的台灣 ETF「EWT」），每天的爬蟲沒有抓 EWT，使用者 2026-11-20 選先用三個；
四個成分的版本每週在 Kaggle 補算對照。

只用 t 開盤前就有的資料：yfinance 只用日期早於 t 的K棒（美股 t−1 那場在台北 t 清晨收盤；日期是 t 的那根
要到 t 晚上才開盤）；老師 global 第 t 列的 ^GSPC 是 t 開盤前最後一次美股收盤（和 m4_c2_tilt 的用法一樣）。
t 當天的台股價格、成交量、答案都不會用到。不用訓練；rank_ensemble 的猜法從 m4_c2_tilt 的快取拿，不重算。

算不出來（兩個 yfinance 序列的最後一根不是同一天、有值的成分不到 min_parts 個、歷史不夠）就丟 OvernightError，
影子跑那幾欄留空白，原因記在 log；不拿不完整的訊號湊數。
"""

import numpy as np
import pandas as pd

from src.models import m4_c2_tilt as c2_tilt
from src.pipeline import utils

YF_PARTS = ("tsm_adr", "sox")   # data/raw/yfinance/<名字>.csv，用 adj_close（指數的 adj_close 和 close 一樣）
PARTS = YF_PARTS + ("gspc",)    # gspc 來自老師 global 的 ^GSPC


class OvernightError(RuntimeError):
    """t 的隔夜訊號算不出來。"""


def trading_days(frame: pd.DataFrame, t: pd.Timestamp) -> pd.DatetimeIndex:
    """有答案的台股交易日加上 t，照日期排（和 m4_c2_tilt.market_states 同一個日曆）。"""
    return pd.DatetimeIndex(sorted(set(frame.loc[frame["r"].notna(), "date"]) | {t})).astype("datetime64[ns]")


def read_bars(name: str, cfg: dict) -> pd.DataFrame:
    """yfinance 的日K：date、adj_close，照日期排，空值拿掉。"""
    path = utils.ROOT / cfg["data"]["raw_dir"] / "yfinance" / f"{name}.csv"
    bars = pd.read_csv(path, usecols=["date", "adj_close"], parse_dates=["date"]).dropna()
    bars["date"] = bars["date"].astype("datetime64[ns]")
    return bars.sort_values("date").reset_index(drop=True)


def last_before(days: pd.DatetimeIndex, bars: pd.DataFrame) -> pd.DataFrame:
    """每個交易日 d：日期早於 d 的最後一根K棒（index 是 days；欄 bar_date、adj_close）。日期等於 d 的那根不用。"""
    calendar = pd.DataFrame({"date": days.astype("datetime64[ns]")})          # merge_asof 兩邊的時間單位要一樣
    stamps = bars["date"].astype("datetime64[ns]").to_numpy()
    rows = pd.DataFrame({"date": stamps, "bar_date": stamps, "adj_close": bars["adj_close"].to_numpy()})
    got = pd.merge_asof(calendar, rows, on="date", allow_exact_matches=False)[["bar_date", "adj_close"]]
    return got.set_index(days)


def since_close(days: pd.DatetimeIndex, world: pd.DataFrame, cfg: dict, bars: dict | None = None) -> pd.DataFrame:
    """每個交易日三個成分的漲跌（index 是 days，欄是 PARTS）。attrs["last_bar"] 是每個 yfinance 序列在最後一天用的K棒日期。

    bars 只給測試用：{名字: read_bars 那樣的表}，不給就讀 data/raw/yfinance。
    """
    out, last_bar = pd.DataFrame(index=days), {}
    for name in YF_PARTS:
        level = last_before(days, bars[name] if bars else read_bars(name, cfg))
        out[name] = (level["adj_close"] / level["adj_close"].shift(1) - 1).to_numpy()
        last_bar[name] = level["bar_date"].iloc[-1]
    rows = world.dropna(subset=["^GSPC"])
    gspc = pd.Series(rows["^GSPC"].to_numpy(), index=pd.DatetimeIndex(rows["date"]).astype("datetime64[ns]"))
    gspc = gspc.reindex(days.astype("datetime64[ns]"))                       # 沒有那列就空白，不往前找舊的
    out["gspc"] = (gspc / gspc.shift(1) - 1).to_numpy()
    out.attrs["last_bar"] = last_bar
    return out


def trailing_share(values: pd.Series, window: int, min_share: float) -> pd.Series:
    """每一列：前 window 列（不含自己）裡 ≤ 自己的比例。前面有值的列不到 window × min_share 就空白。"""
    array, out = values.to_numpy(dtype=float), np.full(len(values), np.nan)
    for i in range(window, len(array)):
        past = array[i - window:i]
        past = past[~np.isnan(past)]
        if not np.isnan(array[i]) and len(past) >= min_share * window:
            out[i] = (past <= array[i]).mean()
    return pd.Series(out, index=values.index)


def signal(parts: pd.DataFrame, c: dict) -> pd.DataFrame:
    """隔夜訊號：o（標準化漲跌的平均，有值的不到 min_parts 個就空白）、o_parts（用了幾個成分）、
    o_absq（|o| 在前 rank_days 天的分位）。"""
    z = parts[list(PARTS)] / parts[list(PARTS)].rolling(c["std_days"], min_periods=c["min_std_days"]).std().shift(1)
    count = z.notna().sum(axis=1)
    o = z.mean(axis=1).where(count >= c["min_parts"])
    return pd.DataFrame({"o": o, "o_parts": count, "o_absq": trailing_share(o.abs(), c["rank_days"], c["min_rank_share"])})


def overnight(frame: pd.DataFrame, world: pd.DataFrame, cfg: dict, t: pd.Timestamp, bars: dict | None = None) -> dict:
    """t 的訊號：{"o", "o_absq", "o_parts", "us_last_bar"}。算不出來丟 OvernightError。"""
    days = trading_days(frame, t)
    parts = since_close(days, world, cfg, bars)
    last_bar = parts.attrs["last_bar"]
    if len(set(last_bar.values())) != 1 or any(pd.isna(day) for day in last_bar.values()):
        shown = "、".join(f"{name} {day:%Y-%m-%d}" if pd.notna(day) else f"{name} 沒有" for name, day in last_bar.items())
        raise OvernightError(f"{t:%Y-%m-%d} 開盤前 yfinance 兩個序列的最後一根不是同一天（{shown}），可能有一個沒更新")
    today = signal(parts, cfg["overnight_up"]).loc[t]
    if pd.isna(today["o"]) or pd.isna(today["o_absq"]):
        raise OvernightError(f"{t:%Y-%m-%d} 的隔夜訊號是空的（有值的成分只有 {int(today['o_parts'])} 個，或歷史不夠）")
    return {"o": float(today["o"]), "o_absq": float(today["o_absq"]), "o_parts": int(today["o_parts"]),
            "us_last_bar": f"{last_bar[YF_PARTS[0]]:%Y-%m-%d}"}


def predict(data, cfg: dict, dates: list, stocks: list, *, inputs=None, bars=None) -> pd.DataFrame:
    """回傳 dates × stocks 的表：date、stock_id、prob、pred、base_pred、o、o_absq、o_parts、us_last_bar、all_up。

    pred：觸發的日子全部是 1，其他日子是 rank_ensemble 的猜法（base_pred）。prob 是 rank_ensemble 的名次（0～1）。
    o、o_absq、o_parts 同一天每檔都一樣。all_up 是 1 代表那天觸發。
    data 不用（和其他模型同一個呼叫方式）。inputs、bars 只給測試用，不給就從 m4_c2_tilt 的快取和 data/raw 讀。
    """
    c = cfg["overnight_up"]
    stocks = sorted(str(s) for s in stocks)
    days = sorted(pd.to_datetime(dates))
    inputs = inputs or c2_tilt.load_inputs(data, cfg, [f"{d:%Y-%m-%d}" for d in days], stocks)
    result = inputs["base"][["date", "stock_id", "prob", "pred"]].rename(columns={"pred": "base_pred"}).copy()
    result["date"] = pd.to_datetime(result["date"])
    for t in days:
        got = overnight(inputs["frame"], inputs["world"], cfg, t, bars)
        today = result["date"] == t
        for name, value in got.items():
            result.loc[today, name] = value
    hit = (result["o"] < 0) & (result["o_absq"] >= c["quantile"])
    result["all_up"] = hit.astype(int)
    result["pred"] = np.where(hit, 1, result["base_pred"]).astype(int)
    result["date"] = result["date"].dt.strftime("%Y-%m-%d")
    return result.sort_values(["date", "stock_id"], ignore_index=True)
