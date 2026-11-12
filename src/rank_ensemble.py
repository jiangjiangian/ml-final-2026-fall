"""排名集成：三個模型學「同一天哪幾檔比較強」（Kaggle notebook 15、16 的 X 系列）。

config 的 daily_model.kind 是 rank_ensemble 時 run_daily_test.py 用它。算式和 notebook 16 一樣，在 oop 逐格比對過。

    1. 個股欄：老師個股檔每天收盤後算得出的欄（a_、c_、o_ 開頭），退一天變成隔天開盤前的值；加上長表的
       stock_ret_lag1、lag2，和 4 個持續性欄（p_ 開頭：這檔股票過去相對同伴的盤中報酬和跳空）。
       用哪些欄寫在 config 的 rank_ensemble.columns，順序不能動（LightGBM 抽欄和順序有關）。
    2. 每一欄換成當天在全部股票（100 檔）裡的排名，範圍 −1～1，沒有值的格子給 0。
    3. 目標：(這檔的盤中報酬 − 當天平均) ÷ 當天標準差，截在 ±target_clip。
    4. 用重訓日之前 train_days 個有答案的交易日訓練 ridge、Nyström kernel ridge、LightGBM 迴歸；後兩個各用
       3 個種子取平均。每天交件時重訓日就是預測日 t，所以每天早上重新訓練，不讀 models/。
    5. 三個模型的預測各自換成當天要預測的 50 檔裡的排名，取平均，前一半猜 1、後一半猜 0。
每天猜漲和猜跌各一半，分數只來自個股排序。預測日 t 那列只用 t 之前的資料：老師檔的欄取 t 之前最後一個有
價格的日子，持續性欄只用 t 之前的答案。

回測（notebook 16 的 X_price，就是這裡的 41 欄；官方分數，每月重訓一次）：2024-01～2026-10 每天平均 +0.00101
（t 6.0），11 季都是正的；2022～2023 八季每天 +0.00080（t 4.9）。正式流程每天重訓，沒有單獨回測過；notebook 18
每 5 個交易日重訓的版本和每月重訓最多差 0.0001。oop 用這份程式重播 1,175 天，0／1 有 99.45% 的格子和 notebook 一樣。

資料不對就丟 EnsembleError，讓 run_daily_test.py 換備援模型：
    - 爬蟲記下「前一個交易日在老師 Live 裡還沒填」（data/raw/manifest.json）。這時短期的欄會落後一天。
      只有幾檔自己那天沒填時，不丟錯，那幾檔 t 那列當成空白，算進下一條的空白比例。
    - 要預測的股票少了，或它們的欄空白太多（超過 max_missing，或有一欄全部空白）。
    - 有答案的交易日不到 min_train_days，或模型的預測值不是有限的數。
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src import features, utils

TEACHER_RENAME = {
    "etl:adj_close": "close", "etl:adj_open": "open", "etl:adj_high": "high", "etl:adj_low": "low",
    "price:成交股數": "volume", "price:成交金額": "amount",
    "foreign_investors_shareholding:全體外資及陸資持股比率": "foreign_hold",
    "institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)": "foreign_net",
    "institutional_investors_trading_summary:投信買賣超股數": "trust_net",
    "institutional_investors_trading_summary:自營商買賣超股數(自行買賣)": "dealer_self_net",
    "institutional_investors_trading_summary:自營商買賣超股數(避險)": "dealer_hedge_net",
    "RSI": "rsi", "SMA": "sma", "MACD": "macd", "ATR": "atr",
    "BBANDS_upper": "bb_upper", "BBANDS_mid": "bb_mid", "BBANDS_lower": "bb_lower", "y": "y_teacher",
}
PERSIST_COLUMNS = ["p_e_mean20", "p_e_mean120", "p_e_up60", "p_gap_rel20"]
MODELS = ("ridge", "kridge", "lgbm")


class EnsembleError(RuntimeError):
    """資料不夠或對不起來，不能用排名集成。"""


def crawler_record(t, manifest_path: Path) -> dict:
    """爬蟲在同一個 t 的那次執行記下的老師 Live 狀況（manifest 的 teacher_live）。

    長表只放填好的交易日，沒填的那天整天不在表裡，從表看不出來，所以要讀爬蟲的紀錄。
    manifest 讀不到、或它是別的 t 的（手動指定日期重跑、爬蟲沒跑），回傳 {}，不擋。
    """
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(manifest, dict) or (manifest.get("run") or {}).get("target_date") != f"{pd.Timestamp(t):%Y-%m-%d}":
        return {}
    record = manifest.get("teacher_live")
    return record if isinstance(record, dict) else {}


def previous_day_unfilled(t, manifest_path: Path) -> bool:
    """爬蟲有沒有記下「前一個交易日整天在老師 Live 裡還沒填」。"""
    return bool(crawler_record(t, manifest_path).get("prev_day_never_filled"))


def previous_day_missing(t, manifest_path: Path) -> set:
    """前一個交易日算填好了，但這幾檔自己那天沒填（多半是停牌）。它們 t 那列的老師檔欄會是更早一天的值。"""
    return {str(s) for s in crawler_record(t, manifest_path).get("prev_day_missing_stocks") or []}


# ---------------------------------------------------------------- 老師檔算的個股欄（和 notebook 的程式一樣）


def read_teacher_stock(teacher_dir: Path, stock_id: str) -> pd.DataFrame:
    """一檔股票的老師 Training 接上 Live，依日期排。Live 還沒有價格的列（-1）丟掉，其他 -1 當成空值。"""
    training = pd.read_csv(teacher_dir / "training" / "market" / f"{stock_id}.csv", parse_dates=["date"],
                           encoding="utf-8-sig")
    live_path = teacher_dir / "live" / "market" / f"{stock_id}.csv"
    if live_path.exists():
        live = pd.read_csv(live_path, parse_dates=["date"], encoding="utf-8-sig")
        live = live[live["date"] > training["date"].max()]
        live = live[(live["etl:adj_close"] != -1) & (live["etl:adj_open"] != -1)].replace(-1, np.nan)
        training = pd.concat([training, live])
    stock = training.rename(columns=TEACHER_RENAME)
    stock["stock_id"] = stock_id
    return stock[["date", "stock_id"] + list(TEACHER_RENAME.values())].sort_values("date")


def teacher_day_features(stock: pd.DataFrame) -> pd.DataFrame:
    """第 d 天收盤後算得出的 a_ 欄，還沒退一天。stock 要依日期排。"""
    close = stock["close"]
    out = pd.DataFrame(index=stock.index)
    out["a_ret1"] = close / close.shift(1) - 1
    out["a_intraday"] = close / stock["open"] - 1
    out["a_gap"] = stock["open"] / close.shift(1) - 1
    out["a_high"] = stock["high"] / close - 1
    out["a_low"] = stock["low"] / close - 1
    volume = stock["volume"].where(stock["volume"] > 0)
    out["a_volume_ratio"] = np.log(volume / volume.rolling(20, min_periods=5).mean())
    out["a_rsi"] = stock["rsi"] / 100
    band = stock["bb_upper"] - stock["bb_lower"]
    out["a_bb_pos"] = (close - stock["bb_lower"]) / band.where(band > 0)
    out["a_bb_width"] = band / stock["bb_mid"]
    out["a_macd"] = stock["macd"] / close
    ema = {span: close.ewm(span=span, adjust=False).mean() for span in (5, 20, 60)}
    for span in (5, 20, 60):
        out[f"a_ema{span}_dev"] = close / ema[span] - 1
    out["a_ema5_20"] = ema[5] / ema[20] - 1
    out["a_ema20_60"] = ema[20] / ema[60] - 1
    return out


def teacher_extra_features(stock: pd.DataFrame) -> pd.DataFrame:
    """第 d 天收盤後算得出的 c_ 欄（法人、多日報酬、ATR、成交金額），還沒退一天。"""
    close = stock["close"]
    volume = stock["volume"].where(stock["volume"] > 0)
    intraday = close / stock["open"] - 1
    log_amount = np.log(stock["amount"].where(stock["amount"] > 0))
    out = pd.DataFrame(index=stock.index)
    out["c_foreign_pct"] = (stock["foreign_net"] / volume).clip(-1, 1)
    out["c_trust_pct"] = (stock["trust_net"] / volume).clip(-1, 1)
    out["c_dealer_pct"] = ((stock["dealer_self_net"] + stock["dealer_hedge_net"]) / volume).clip(-1, 1)
    out["c_foreign_pct5"] = stock["foreign_net"].rolling(5).sum() / volume.rolling(5).sum()
    out["c_foreign_hold_chg5"] = stock["foreign_hold"].diff(5)
    out["c_intraday_mean5"] = intraday.rolling(5).mean()
    out["c_intraday_mean20"] = intraday.rolling(20).mean()
    out["c_ret5"] = close / close.shift(5) - 1
    out["c_ret20"] = close / close.shift(20) - 1
    out["c_atr_pct"] = stock["atr"] / close
    out["c_sma_dev"] = close / stock["sma"] - 1
    out["c_amount_z60"] = (log_amount - log_amount.rolling(60).mean()) / log_amount.rolling(60).std()
    return out


def open_close_features(stock: pd.DataFrame) -> pd.DataFrame:
    """第 d 天收盤後算得出的 o_ 欄（跳空、盤中報酬的統計、波動），還沒退一天。"""
    close, open_price, high, low = stock["close"], stock["open"], stock["high"], stock["low"]
    intraday = close / open_price - 1
    gap = open_price / close.shift(1) - 1
    log_high_low = np.log(high / low)
    log_close_open = np.log(close / open_price)
    out = pd.DataFrame(index=stock.index)
    out["o_gap_mean5"] = gap.rolling(5).mean()
    out["o_gap_mean20"] = gap.rolling(20).mean()
    out["o_gap_std20"] = gap.rolling(20).std()
    out["o_intraday_std20"] = intraday.rolling(20).std()
    out["o_gap_intraday_corr60"] = gap.rolling(60).corr(intraday)
    out["o_intraday_minus_gap5"] = (intraday - gap).rolling(5).mean()
    out["o_parkinson20"] = np.sqrt((log_high_low ** 2).rolling(20).mean() / (4 * np.log(2)))
    garman_klass = 0.5 * log_high_low ** 2 - (2 * np.log(2) - 1) * log_close_open ** 2
    out["o_garman_klass20"] = np.sqrt(garman_klass.rolling(20).mean().clip(lower=0))
    out["o_close_location"] = (close - low) / (high - low).where(high > low)
    out["o_intraday_up_frac20"] = (intraday > 0).astype(float).rolling(20).mean()
    return out


def lagged_teacher_features(teacher: pd.DataFrame, t: pd.Timestamp | None) -> pd.DataFrame:
    """每檔股票每一列 = 前一個有價格的日子收盤後的值。t 還沒有價格，先補一個空列，退一天後 t 那列就有值。"""
    parts = []
    for stock_id, stock in teacher.groupby("stock_id", sort=False):
        if t is not None and stock["date"].max() < t:
            stock = pd.concat([stock, pd.DataFrame({"date": [t], "stock_id": [stock_id]})], ignore_index=True)
        day_values = pd.concat([teacher_day_features(stock), teacher_extra_features(stock),
                                open_close_features(stock)], axis=1)
        lagged = day_values.shift(1)
        lagged[["date", "stock_id"]] = stock[["date", "stock_id"]]
        parts.append(lagged)
    return pd.concat(parts, ignore_index=True).replace([np.inf, -np.inf], np.nan)


# ---------------------------------------------------------------- 長表、目標、持續性欄、當天排名


def build_frame(table: pd.DataFrame, teacher: pd.DataFrame, cfg: dict, t=None) -> pd.DataFrame:
    """長表接上老師檔算的欄，再算目標和持續性欄。只留有答案的列和 t 那天的列，依股票、日期排。

    table 是 features.load_features() 的結果；teacher 是每檔 read_teacher_stock 接起來的表。
    """
    m = cfg["rank_ensemble"]
    t = None if t is None else pd.Timestamp(t)
    df = table.rename(columns={"label_intraday_return": "r", "label_y": "y"})
    df = df.assign(date=pd.to_datetime(df["date"]), stock_id=df["stock_id"].astype(str))
    df = df.sort_values(["stock_id", "date"]).reset_index(drop=True)
    df = df.merge(lagged_teacher_features(teacher, t), on=["date", "stock_id"], how="left", validate="one_to_one")
    if not (df["a_ret1"] - df["stock_ret_lag1"]).abs().max() < 1e-9:
        raise EnsembleError("老師檔算的報酬和長表的 stock_ret_lag1 對不起來")
    by_day = df.groupby("date")
    two_ranks = pd.DataFrame({"o_intraday_rank": by_day["a_intraday"].rank(pct=True) - 0.5,
                              "o_gap_rank": by_day["a_gap"].rank(pct=True) - 0.5})
    df = pd.concat([df, two_ranks], axis=1)   # 一次接上去；一欄一欄加，pandas 會警告表太零碎

    keep = df["r"].notna() if t is None else df["r"].notna() | (df["date"] == t)
    frame = df[keep].sort_values(["stock_id", "date"]).reset_index(drop=True).copy()   # copy：欄很多，先整理記憶體再加欄
    same_day = frame.groupby("date")["r"]
    frame["e"] = frame["r"] - same_day.transform("mean")
    frame["target"] = (frame["e"] / same_day.transform("std")).clip(-m["target_clip"], m["target_clip"])
    frame["gap_rel"] = frame["a_gap"] - frame.groupby("date")["a_gap"].transform("mean")
    previous_e = frame.groupby("stock_id", sort=False)["e"].shift(1)

    def trailing_mean(values, days):
        rolled = values.groupby(frame["stock_id"], sort=False).rolling(days, min_periods=days // 2).mean()
        return rolled.reset_index(level=0, drop=True)

    frame["p_e_mean20"] = trailing_mean(previous_e, 20)
    frame["p_e_mean120"] = trailing_mean(previous_e, 120)
    frame["p_e_up60"] = trailing_mean((previous_e > 0).astype(float).where(previous_e.notna()), 60)
    frame["p_gap_rel20"] = trailing_mean(frame["gap_rel"], 20)
    missing = [c for c in m["columns"] if c not in frame.columns]
    if missing:
        raise EnsembleError(f"rank_ensemble.columns 有不存在的欄：{missing[:5]}")
    if t is not None:   # 表裡 t 之前還沒有答案的日子數。features.py 產生的長表一定是 0（沒填的日子不進表），
        # 這一層只擋別的來源做的表；老師 Live 沒更新由 predict 讀爬蟲的紀錄來擋（previous_day_unfilled）
        table_days, last = df["date"].unique(), df.loc[df["r"].notna(), "date"].max()
        frame.attrs["stale_days"] = int(((table_days > last) & (table_days < t)).sum())
    return frame


def load_frame(cfg: dict, t=None, *, table=None, teacher_dir=None) -> pd.DataFrame:
    """讀長表和老師檔，回傳 build_frame 的結果。"""
    table = features.load_features() if table is None else table
    teacher_dir = Path(teacher_dir) if teacher_dir else utils.ROOT / cfg["data"]["raw_dir"] / "teacher"
    codes = sorted(table["stock_id"].astype(str).unique())
    teacher = pd.concat([read_teacher_stock(teacher_dir, code) for code in codes], ignore_index=True)
    return build_frame(table, teacher.sort_values(["stock_id", "date"]).reset_index(drop=True), cfg, t)


def day_ranks(frame: pd.DataFrame, columns: list) -> np.ndarray:
    """每一欄換成當天在全部股票裡的排名（−1～1），沒有值的給 0。"""
    return (2 * frame.groupby("date")[columns].rank(pct=True) - 1).fillna(0.0).to_numpy(dtype=np.float32)


# ---------------------------------------------------------------- 三個模型


def fit_predict(train_x, target, predict_x, days: int, m: dict) -> dict:
    """訓練三個模型，回傳每個模型對 predict_x 的預測（越大越看好）。sklearn、lightgbm 用到才載入。"""
    import lightgbm as lgb
    from sklearn.kernel_approximation import Nystroem
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline

    out = {"ridge": Ridge(alpha=m["ridge_alpha"] * days / 125).fit(train_x, target).predict(predict_x)}
    total = 0.0
    for seed in m["seeds"]:
        kernel_map = Nystroem(kernel="rbf", gamma=m["kernel_gamma_scale"] / train_x.shape[1],
                              n_components=m["kernel_components"], random_state=seed)
        model = make_pipeline(kernel_map, Ridge(alpha=m["kernel_alpha"])).fit(train_x, target)
        total = total + model.predict(predict_x) / len(m["seeds"])
    out["kridge"] = total
    total = 0.0
    for seed in m["seeds"]:
        model = lgb.LGBMRegressor(random_state=seed, **m["lgbm"]).fit(train_x, target)
        total = total + model.predict(predict_x) / len(m["seeds"])
    out["lgbm"] = total
    return out


def predict(data, cfg: dict, dates: list, stocks: list, *, frame=None, fit_dates=None,
            allow_missing: bool = False, manifest_path=None) -> pd.DataFrame:
    """回傳 dates × stocks 的 DataFrame：date（YYYY-MM-DD）、stock_id、三個模型的預測、prob、pred。

    data 不用（和 online_lr.predict、persist_rule.predict 同一個呼叫方式）；資料自己讀，或用 frame 傳進來。
    fit_dates 是 {預測日: 重訓日}，不給就每個預測日自己重訓（每天交件的做法）；重播回測時傳每月的重訓日。
    prob 是集成的當天名次換成 0～1（不是機率）。allow_missing 只給重播用：過去有幾天某檔股票沒有答案，那天就少一檔，
    也不檢查空白比例。manifest_path 是爬蟲的紀錄，不給就用 data/raw/manifest.json；只有自己讀資料時（frame 沒給）才看。
    """
    m = cfg["rank_ensemble"]
    stocks = sorted(str(s) for s in stocks)
    target_days = sorted(pd.to_datetime(dates))
    if not target_days or not stocks:
        raise EnsembleError("沒有要預測的日子或股票")
    if frame is None:
        manifest_path = manifest_path or utils.ROOT / cfg["data"]["raw_dir"] / "manifest.json"
        if previous_day_unfilled(target_days[-1], manifest_path):
            raise EnsembleError(f"{target_days[-1]:%Y-%m-%d} 的前一個交易日在老師 Live 裡還沒填，短期的欄會落後一天")
        frame = load_frame(cfg, target_days[-1])
        late = previous_day_missing(target_days[-1], manifest_path)
        if late:   # 這幾檔 t 那列整列當成空白（排名後是 0），不用更早一天的值；太多檔就會被下面的空白檢查擋下
            attrs, frame = dict(frame.attrs), frame.copy()
            frame.attrs = attrs
            frame.loc[(frame["date"] == target_days[-1]) & frame["stock_id"].isin(late), list(m["columns"])] = np.nan
    if frame.attrs.get("stale_days", 0) > m["max_stale_days"]:
        raise EnsembleError(f"{target_days[-1]:%Y-%m-%d} 之前有 {frame.attrs['stale_days']} 個交易日還沒有答案，資料沒更新")
    columns = list(m["columns"])
    x_all, is_missing = day_ranks(frame, columns), frame[columns].isna().to_numpy()
    has_target = frame["target"].notna().to_numpy()
    labeled_days = pd.DatetimeIndex(sorted(frame.loc[frame["r"].notna(), "date"].unique()))
    fit_of = {d: pd.Timestamp((fit_dates or {}).get(d, d)) for d in target_days}
    out = []
    for fit_day in sorted(set(fit_of.values())):
        position = labeled_days.searchsorted(fit_day, side="left")   # 重訓日之前有幾個有答案的日子
        window = labeled_days[max(0, position - m["train_days"]):position]
        if len(window) < min(m["train_days"], m["min_train_days"]):
            raise EnsembleError(f"{fit_day:%Y-%m-%d} 之前只有 {len(window)} 個有答案的交易日")
        rows = np.flatnonzero(frame["date"].isin(window).to_numpy() & has_target)
        usable = np.flatnonzero(is_missing[rows].mean(axis=0) <= m["max_missing"])
        days = [d for d in target_days if fit_of[d] == fit_day]
        picked = frame[frame["date"].isin(days) & frame["stock_id"].isin(stocks)]
        for d in days if not allow_missing else []:
            day_rows = picked.index[picked["date"] == d].to_numpy()
            if set(picked.loc[day_rows, "stock_id"]) != set(stocks):
                raise EnsembleError(f"{d:%Y-%m-%d} 的特徵表沒有全部要預測的股票")
            blank = is_missing[day_rows][:, usable]   # 空白的格子排名後是 0，太多就等於沒有資訊
            if blank.mean() > m["max_missing"] or blank.all(axis=0).any():
                empty = [columns[usable[j]] for j in np.flatnonzero(blank.all(axis=0))]
                raise EnsembleError(f"{d:%Y-%m-%d} 要預測的列有 {blank.mean():.1%} 的格子是空的，"
                                    f"{len(empty)} 欄全部空白{'：' + ', '.join(empty[:5]) if empty else ''}")
        scores = fit_predict(x_all[rows][:, usable], frame["target"].to_numpy()[rows],
                             x_all[picked.index.to_numpy()][:, usable], len(window), m)
        if not all(np.isfinite(scores[name]).all() for name in MODELS):
            raise EnsembleError(f"{fit_day:%Y-%m-%d} 重訓的模型有預測值不是有限的數")
        part = picked[["date", "stock_id"]].copy()
        for name in MODELS:
            part[name] = scores[name]
        out.append(part)
    result = pd.concat(out, ignore_index=True).sort_values(["date", "stock_id"], ignore_index=True)
    by_day = result.groupby("date")
    ranks = [(by_day[name].rank(pct=True) - 0.5).fillna(0.0) for name in MODELS]
    combined = (sum(ranks) / len(ranks)).groupby(result["date"]).rank(pct=True) - 0.5
    order = combined.groupby(result["date"]).rank(method="first")   # 名次一樣時照代號，代號大的名次高
    result["prob"] = combined + 0.5
    result["pred"] = (order > by_day["stock_id"].transform("size") / 2).astype(int)
    result["date"] = result["date"].dt.strftime("%Y-%m-%d")
    return result
