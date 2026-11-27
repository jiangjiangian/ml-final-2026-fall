"""`twfm.data.dataset` 的測試。

- 每個樣本的視窗最後一天 < t，而且就是 i（t 的前一個交易日）。
- 截斷測試（主要的防洩漏檢查）：把 ≥ t0 的價格、美股、法人、融資全部亂改、或再把 t0 以後的列刪掉，
  從長表一路重建股票池、樣本、協變量（`build_covariates`）、store、dataset，t ≤ t0 的樣本輸入
  （含 `stock_cov`、`market_cov`）要逐位元相同，標籤看到的最後一天 t+h−1 < t0 的標籤、`target_z`、
  `exec_*` 也要相同。刪掉 t0 以後的列時，t+h−1 > t0 的樣本沒有標籤，要被丟掉。
- 手算的小例子：標籤、`target_z`、漲跌停遮罩、`horizon` 2 的還原報酬、下市股。
- `DayBatchSampler` 同一天不拆開；`make_loader` 的形狀和型別。
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")

import twfm.config as config  # noqa: E402
import twfm.data.align as align  # noqa: E402
import twfm.data.dataset as dataset  # noqa: E402
import twfm.data.synthetic as synthetic  # noqa: E402
import twfm.data.universe as universe_mod  # noqa: E402

LOOKBACK = 16
INPUT_KEYS = ("levels", "stamps", "rets", "stock_cov", "market_cov")


# ---------------------------------------------------------------------------
# 共用的小工具
# ---------------------------------------------------------------------------


def _ns_index(values: object) -> pd.DatetimeIndex:
    """轉成 ns 解析度的 DatetimeIndex。"""
    idx = pd.DatetimeIndex(pd.to_datetime(values))
    return pd.DatetimeIndex(np.asarray(idx.to_numpy(), dtype="datetime64[ns]"))


def _i8(t: object) -> int:
    """日期轉成 ns 整數，當字典的鍵。"""
    return int(pd.Timestamp(t).to_datetime64().astype("datetime64[ns]").astype(np.int64))


def _cfg(**kw: object) -> object:
    base: dict[str, object] = {
        "lookback": LOOKBACK,
        "universe_refresh": "monthly",
        "universe_size": 20,
        "universe_lookback_days": 20,
        "min_close": 0.0,
    }
    base.update(kw)
    return config.DataConfig(**base)


def _simple_universe(panel: pd.DataFrame, calendar: object, lookback: int) -> pd.DataFrame:
    """不靠 `build_universe` 的股票池：四碼普通股、i 那天有列、t 以前至少 `lookback` 列。

    只看 t 以前有沒有列，構造上就不會偷看。
    """
    cal = _ns_index(calendar)
    sid_all = np.asarray(panel["stock_id"].astype(str).to_numpy(), dtype=str)
    common = pd.Series(sid_all).str.fullmatch(r"[1-9]\d{3}").to_numpy()
    sids = np.array(sorted(set(sid_all[common].tolist())), dtype=str)
    d_pos = cal.get_indexer(_ns_index(panel["date"]))[common]
    s_pos = np.searchsorted(sids, sid_all[common])
    assert (d_pos >= 0).all(), "panel 有不在 calendar 的日期"
    pres = np.zeros((len(cal), len(sids)), dtype=bool)
    pres[d_pos, s_pos] = True
    before = np.zeros(pres.shape, dtype=np.int64)
    before[1:] = np.cumsum(pres, axis=0)[:-1]
    at_i = np.zeros(pres.shape, dtype=bool)
    at_i[1:] = pres[:-1]
    ti, si = np.nonzero(at_i & (before >= lookback))
    return pd.DataFrame({"date": cal[ti], "stock_id": sids[si]})


def _universe(source: str, panel: pd.DataFrame, cal: pd.DatetimeIndex, cfg: object) -> pd.DataFrame:
    if source == "simple":
        return _simple_universe(panel, cal, int(cfg.lookback))
    return universe_mod.build_universe(panel, cal, cfg)


SideTables = tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]


def _side_tables(market: object) -> SideTables:
    """`(us_daily, inst_daily, margin_daily)`。"""
    return market.us_daily, market.inst_daily, market.margin_daily


def _build(
    panel: pd.DataFrame, side: SideTables, cal: pd.DatetimeIndex, cfg: object, source: str
) -> tuple[object, object]:
    """從長表一路建到 dataset：股票池 → 樣本 → 協變量 → store → dataset。

    協變量用 pipeline 實際呼叫的 `build_covariates`，同一份（可能被亂改過的）輸入，
    所以截斷測試也檢查得到 `stock_cov`、`market_cov` 有沒有偷看。
    """
    us, inst, margin = side
    uni = _universe(source, panel, cal, cfg)
    samples = dataset.build_samples(panel, uni, cal, cfg)
    store = dataset.PanelStore(panel)
    stock_cov, market_cov = align.build_covariates(panel, us, inst, margin, None, cal, cfg, universe=uni)
    ds = dataset.PanelWindowDataset(store, samples, stock_cov, market_cov, int(cfg.lookback))
    return samples, ds


def _keys(samples: object) -> dict[tuple[int, str], int]:
    """(t 的 ns 整數, 股票代號) → 樣本序號。"""
    d = samples.dates.astype("datetime64[ns]").astype(np.int64)
    return {(int(a), str(b)): k for k, (a, b) in enumerate(zip(d.tolist(), samples.stock_ids.tolist()))}


def _corrupt(panel: pd.DataFrame, t0: pd.Timestamp, mode: str, seed: int) -> pd.DataFrame:
    """把 date ≥ t0 的價、量、參考價全部換成亂數（仍然是合法的 K 棒）。

    `truncate` 再把 date > t0 的列刪掉（保留 t0 那天，t0 的樣本才不會因為別的原因消失）。
    """
    p = panel.copy()
    p["date"] = _ns_index(p["date"])
    for col in ("open", "high", "low", "close", "volume", "amount", "ref_price"):
        p[col] = p[col].astype("float64")
    m = (p["date"] >= t0).to_numpy()
    n = int(m.sum())
    assert n > 0
    rng = np.random.default_rng(seed)
    o = rng.uniform(5.0, 900.0, n)
    c = rng.uniform(5.0, 900.0, n)
    p.loc[m, "open"] = o
    p.loc[m, "close"] = c
    p.loc[m, "high"] = np.maximum(o, c) * rng.uniform(1.0, 1.08, n)
    p.loc[m, "low"] = np.minimum(o, c) * rng.uniform(0.92, 1.0, n)
    p.loc[m, "ref_price"] = rng.uniform(5.0, 900.0, n)
    p.loc[m, "volume"] = np.round(rng.uniform(1e3, 1e8, n))
    p.loc[m, "amount"] = rng.uniform(1e5, 1e11, n)
    if mode == "truncate":
        p = p.loc[p["date"] <= t0].reset_index(drop=True)
    return p


def _corrupt_side(market: object, t0: pd.Timestamp, mode: str, seed: int) -> SideTables:
    """美股、法人、融資裡日期 ≥ t0 的列換成亂數；`truncate` 再刪掉日期 > t0 的列。

    美股收盤和融資餘額保持大於 0（`validate_us` 會檢查收盤）。
    """
    rng = np.random.default_rng(seed)
    us = market.us_daily.copy()
    us["close"] = us["close"].astype("float64")
    m = (us["us_date"] >= t0).to_numpy()
    us.loc[m, "close"] = rng.uniform(100.0, 10000.0, int(m.sum()))
    inst = market.inst_daily.copy()
    m = (inst["date"] >= t0).to_numpy()
    for col in ("foreign_net", "trust_net", "dealer_net"):
        inst[col] = inst[col].astype("float64")
        inst.loc[m, col] = np.round(rng.uniform(-1.0e6, 1.0e6, int(m.sum())))
    margin = market.margin_daily.copy()
    margin["margin_balance"] = margin["margin_balance"].astype("float64")
    m = (margin["date"] >= t0).to_numpy()
    margin.loc[m, "margin_balance"] = np.round(rng.uniform(10.0, 1.0e6, int(m.sum())))
    if mode == "truncate":
        us = us.loc[us["us_date"] <= t0].reset_index(drop=True)
        inst = inst.loc[inst["date"] <= t0].reset_index(drop=True)
        margin = margin.loc[margin["date"] <= t0].reset_index(drop=True)
    return us, inst, margin


@pytest.fixture(scope="module")
def market() -> object:
    return synthetic.make_synthetic_market(n_stocks=30, n_days=260, seed=11)


@pytest.fixture(scope="module")
def cal(market: object) -> pd.DatetimeIndex:
    return _ns_index(market.calendar)


# ---------------------------------------------------------------------------
# 視窗
# ---------------------------------------------------------------------------


def test_every_window_ends_at_i_strictly_before_t(market: object, cal: pd.DatetimeIndex) -> None:
    cfg = _cfg()
    uni = _simple_universe(market.panel, cal, LOOKBACK)
    samples = dataset.build_samples(market.panel, uni, cal, cfg)
    store = dataset.PanelStore(market.panel)
    ds = dataset.PanelWindowDataset(store, samples, None, None, LOOKBACK)
    assert len(samples) >= 500
    cal_i8 = cal.asi8

    for k in range(len(samples)):
        t = samples.dates[k]
        wd, lv, rt, st = store.window(samples.stock_ids[k], t, LOOKBACK)
        assert wd.shape == (LOOKBACK,)
        assert wd[-1] < t
        assert np.all(np.diff(wd.astype(np.int64)) > 0)
        pos = int(np.searchsorted(cal_i8, _i8(t)))
        assert cal_i8[pos] == _i8(t)
        # 股票池要求 i 那天有列，所以視窗最後一天就是 i
        assert int(wd[-1].astype(np.int64)) == int(cal_i8[pos - 1])

    # 抽 200 個樣本，和直接從長表切出來的比
    panel = market.panel.copy()
    panel["date"] = _ns_index(panel["date"])
    panel["stock_id"] = panel["stock_id"].astype(str)
    groups = {s: g.sort_values("date").reset_index(drop=True) for s, g in panel.groupby("stock_id")}
    rng = np.random.default_rng(0)
    for k in rng.choice(len(samples), size=min(200, len(samples)), replace=False).tolist():
        t = pd.Timestamp(samples.dates[k])
        g = groups[str(samples.stock_ids[k])]
        exp = g.loc[g["date"] < t].tail(LOOKBACK)
        wd, lv, rt, st = store.window(samples.stock_ids[k], samples.dates[k], LOOKBACK)
        np.testing.assert_array_equal(wd, exp["date"].to_numpy().astype("datetime64[ns]"))
        assert lv.dtype == np.float32 and rt.dtype == np.float32 and st.dtype == np.float32
        assert lv.shape == (LOOKBACK, 6) and rt.shape == (LOOKBACK, 5) and st.shape == (LOOKBACK, 5)
        ratio = exp["close"].to_numpy(dtype="float64") / exp["open"].to_numpy(dtype="float64")
        np.testing.assert_allclose(lv[:, 3] / lv[:, 0], ratio, rtol=1e-5)
        np.testing.assert_allclose(rt[:, 2], np.log(ratio), rtol=1e-4, atol=1e-6)
        np.testing.assert_allclose(lv[:, 5], exp["amount"].to_numpy(dtype="float64"), rtol=1e-6)
        di = pd.DatetimeIndex(wd)
        np.testing.assert_array_equal(st[:, 0], 0.0)
        np.testing.assert_array_equal(st[:, 1], 0.0)
        np.testing.assert_array_equal(st[:, 2], np.asarray(di.weekday, dtype=np.float32))
        np.testing.assert_array_equal(st[:, 3], np.asarray(di.day, dtype=np.float32))
        np.testing.assert_array_equal(st[:, 4], np.asarray(di.month, dtype=np.float32))
        item = ds[k]
        assert torch.equal(item["levels"], torch.from_numpy(lv))
        assert torch.equal(item["rets"], torch.from_numpy(rt))
        assert torch.equal(item["stamps"], torch.from_numpy(st))


def test_window_uses_rows_strictly_before_t(market: object) -> None:
    store = dataset.PanelStore(market.panel)
    sid = max(store.stock_ids.tolist(), key=lambda s: len(store.stock_dates(s)))
    d = store.stock_dates(sid)
    k = LOOKBACK + 3
    wd, *_ = store.window(sid, d[k], LOOKBACK)
    assert wd[-1] == d[k - 1] and wd[0] == d[k - LOOKBACK]
    # t 不是這檔的交易日（同一天中午）：視窗包含那天以前最後一列
    wd2, *_ = store.window(sid, pd.Timestamp(d[k]) + pd.Timedelta(hours=12), LOOKBACK)
    assert wd2[-1] == d[k]
    # 字串的 t 也可以
    wd3, *_ = store.window(sid, str(pd.Timestamp(d[k]).date()), LOOKBACK)
    assert wd3[-1] == d[k - 1]
    # 剛好 lookback 列可以，少一列不行
    wd4, *_ = store.window(sid, d[LOOKBACK], LOOKBACK)
    assert wd4[0] == d[0]
    with pytest.raises(ValueError):
        store.window(sid, d[LOOKBACK - 1], LOOKBACK)
    with pytest.raises(KeyError):
        store.window("NO_SUCH_STOCK", d[k], LOOKBACK)
    # 回傳的是複本，改了不會動到 store
    _, before, _, _ = store.window(sid, d[k], LOOKBACK)
    _, lv, rt, st = store.window(sid, d[k], LOOKBACK)
    lv[:] = -1.0
    rt[:] = -1.0
    st[:] = -1.0
    _, lv_again, rt_again, st_again = store.window(sid, d[k], LOOKBACK)
    np.testing.assert_array_equal(lv_again, before)
    assert not (rt_again == -1.0).all() and not (st_again == -1.0).all()


# ---------------------------------------------------------------------------
# 截斷測試（主要的防洩漏檢查）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["simple", "build_universe"])
@pytest.mark.parametrize("horizon", [1, 3])
@pytest.mark.parametrize("mode", ["scramble", "truncate"])
def test_truncation_leaves_past_inputs_and_labels_unchanged(
    market: object, cal: pd.DatetimeIndex, mode: str, horizon: int, source: str
) -> None:
    pos_t0 = int(len(cal) * 0.6)
    t0 = cal[pos_t0]
    t0_i8 = _i8(t0)
    cfg = _cfg(horizon=horizon)
    s_a, ds_a = _build(market.panel, _side_tables(market), cal, cfg, source)
    s_b, ds_b = _build(
        _corrupt(market.panel, t0, mode, seed=5), _corrupt_side(market, t0, mode, seed=6), cal, cfg, source
    )
    key_a = _keys(s_a)
    key_b = _keys(s_b)
    cal_i8 = cal.asi8

    def label_end(k: tuple[int, str]) -> int:
        """標籤看到的最後一天 t+h−1 在日曆裡的位置。"""
        return int(np.searchsorted(cal_i8, k[0])) + horizon - 1

    # 1. t ≤ t0 的樣本集合（股票池和「t 那天有列」都只看 ≤ t 的資料）。
    #    刪掉 t0 以後的列時，t+h−1 > t0 的樣本沒有標籤（不能拿較短的報酬代替），要被丟掉。
    early_a = {k for k in key_a if k[0] <= t0_i8}
    early_b = {k for k in key_b if k[0] <= t0_i8}
    if mode == "truncate":
        assert early_b == {k for k in early_a if label_end(k) <= pos_t0}
    else:
        assert early_a == early_b
    common = early_b
    assert len(common) >= 300, f"可比較的樣本太少（{len(common)}），測試會失去意義"
    assert any(k[0] == t0_i8 for k in early_a), "t0 當天沒有樣本"
    if mode == "scramble" or horizon == 1:
        assert any(k[0] == t0_i8 for k in common), "t0 當天沒有可比較的樣本"
    else:
        assert not any(k[0] == t0_i8 for k in common), "t0 的標籤會看到刪掉的列，應該沒有樣本"

    # 2. t ≤ t0 的輸入逐位元相同（含 t0 當天：t0 的列被亂改，但不該進 t0 的視窗和協變量）
    assert len(ds_a.stock_cov_cols) > 0 and len(ds_a.market_cov_cols) > 0, "沒有協變量，比較會失去意義"
    for key in sorted(common):
        xa = ds_a[key_a[key]]
        xb = ds_b[key_b[key]]
        assert xa["stock_cov"].numel() > 0 and xa["market_cov"].numel() > 0
        for name in INPUT_KEYS:
            assert torch.equal(xa[name], xb[name]), f"{name} 在 {key} 不同：t 的輸入看到了 ≥ t0 的資料"
        assert int(xa["day_id"]) == int(xb["day_id"])

    # 3. 標籤看到的最後一天 t+h−1 < t0 的樣本，標籤、target_z、exec 都相同
    label_keys = sorted(k for k in common if label_end(k) < pos_t0)
    assert len(label_keys) >= 200, f"可比較的標籤太少（{len(label_keys)}）"
    ia = np.array([key_a[k] for k in label_keys], dtype=np.int64)
    ib = np.array([key_b[k] for k in label_keys], dtype=np.int64)
    np.testing.assert_array_equal(s_a.label_r[ia], s_b.label_r[ib])
    np.testing.assert_array_equal(s_a.target_z[ia], s_b.target_z[ib])
    np.testing.assert_array_equal(s_a.exec_long_ok[ia], s_b.exec_long_ok[ib])
    np.testing.assert_array_equal(s_a.exec_short_ok[ia], s_b.exec_short_ok[ib])
    np.testing.assert_array_equal(s_a.day_ids[ia], s_b.day_ids[ib])

    # 4. 防止測試空轉：亂改確實改到了 t0 以後的東西
    t0_keys = [k for k in common if k[0] == t0_i8]
    if t0_keys:
        assert any(s_a.label_r[key_a[k]] != s_b.label_r[key_b[k]] for k in t0_keys), "t0 的標籤沒變，亂改沒有生效"
    if mode == "scramble":
        late = [k for k in key_a if k[0] > t0_i8 and k in key_b]
        assert late, "t0 以後沒有共同樣本"
        changed = any(not torch.equal(ds_a[key_a[k]]["levels"], ds_b[key_b[k]]["levels"]) for k in late[:200])
        assert changed, "t0 以後的視窗沒變，亂改沒有生效"
        changed_cov = any(
            not torch.equal(ds_a[key_a[k]]["stock_cov"], ds_b[key_b[k]]["stock_cov"]) for k in late[:200]
        )
        assert changed_cov, "t0 以後的個股協變量沒變，亂改沒有生效"
        changed_mkt = any(
            not torch.equal(ds_a[key_a[k]]["market_cov"], ds_b[key_b[k]]["market_cov"]) for k in late[:200]
        )
        assert changed_mkt, "t0 以後的市場協變量沒變，亂改沒有生效"
    else:
        assert not any(k[0] > t0_i8 for k in key_b), "刪掉 t0 以後的列，卻還有 t0 以後的樣本"


# ---------------------------------------------------------------------------
# 樣本表和標籤
# ---------------------------------------------------------------------------


def _hand_panel() -> pd.DataFrame:
    """手算用的小長表（2020 年，漲跌停 10%）。

    - 1101：01-07 除息（前一天收 51，參考價 49）。
    - 2330：01-07 開盤 110 = 漲停（參考價 100）。
    - 2317：01-06 停牌；01-07 開盤 18 = 跌停（參考價 20）。
    - 1301：01-06 之後下市。
    """
    rows = [
        # date, stock_id, open, high, low, close, ref_price
        ("2020-01-02", "1101", 50.0, 51.0, 49.0, 50.0, 50.0),
        ("2020-01-03", "1101", 50.0, 51.0, 49.5, 50.0, 50.0),
        ("2020-01-06", "1101", 50.0, 51.5, 49.5, 51.0, 50.0),
        ("2020-01-07", "1101", 49.0, 50.6, 48.8, 50.47, 49.0),
        ("2020-01-08", "1101", 50.47, 50.9, 50.1, 50.47, 50.47),
        ("2020-01-02", "2330", 100.0, 101.0, 99.0, 100.0, 100.0),
        ("2020-01-03", "2330", 100.0, 101.0, 99.0, 100.0, 100.0),
        ("2020-01-06", "2330", 100.0, 101.0, 99.0, 100.0, 100.0),
        ("2020-01-07", "2330", 110.0, 110.0, 105.0, 108.0, 100.0),
        ("2020-01-08", "2330", 108.0, 109.0, 107.0, 108.0, 108.0),
        ("2020-01-02", "2317", 20.0, 20.5, 19.5, 20.0, 20.0),
        ("2020-01-03", "2317", 20.0, 20.5, 19.5, 20.0, 20.0),
        ("2020-01-07", "2317", 18.0, 19.0, 18.0, 18.9, 20.0),
        ("2020-01-08", "2317", 18.9, 19.2, 18.6, 18.9, 18.9),
        ("2020-01-02", "1301", 30.0, 30.5, 29.5, 30.0, 30.0),
        ("2020-01-03", "1301", 30.0, 30.5, 29.5, 30.0, 30.0),
        ("2020-01-06", "1301", 30.0, 31.5, 29.8, 31.5, 30.0),
    ]
    df = pd.DataFrame(rows, columns=["date", "stock_id", "open", "high", "low", "close", "ref_price"])
    df["date"] = _ns_index(df["date"])
    df["market"] = "twse"
    df["volume"] = 1_000_000.0
    df["amount"] = df["close"] * df["volume"]
    return df[["date", "stock_id", "market", "open", "high", "low", "close", "volume", "amount", "ref_price"]]


HAND_CAL = _ns_index(["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07", "2020-01-08"])


def _hand_universe(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [(d, s) for d in dates for s in ("1101", "1301", "2317", "2330")], columns=["date", "stock_id"]
    )


def _z(r: list[float]) -> np.ndarray:
    a = np.asarray(r, dtype=np.float64)
    return (a - a.mean()) / a.std()


def test_build_samples_hand_example_horizon_1() -> None:
    panel = _hand_panel()
    cfg = _cfg(lookback=2)
    samples = dataset.build_samples(panel, _hand_universe(["2020-01-06", "2020-01-07"]), HAND_CAL, cfg)
    # 01-06 的 2317 停牌、01-07 的 1301 已下市，都沒有樣本
    assert [str(pd.Timestamp(d).date()) for d in samples.dates] == ["2020-01-06"] * 3 + ["2020-01-07"] * 3
    assert samples.stock_ids.tolist() == ["1101", "1301", "2330", "1101", "2317", "2330"]
    # day_ids 是 t 在日曆裡的位置
    assert samples.day_ids.tolist() == [2, 2, 2, 3, 3, 3]
    r = [51.0 / 50.0 - 1, 31.5 / 30.0 - 1, 0.0, 50.47 / 49.0 - 1, 18.9 / 18.0 - 1, 108.0 / 110.0 - 1]
    assert samples.label_r.dtype == np.float32
    np.testing.assert_allclose(samples.label_r, np.asarray(r, dtype=np.float32), rtol=1e-6)
    z = np.concatenate([_z(r[:3]), _z(r[3:])])
    assert samples.target_z.dtype == np.float32
    np.testing.assert_allclose(samples.target_z, z, atol=1e-6)
    # 2330 在 01-07 開盤漲停：不能買；2317 在 01-07 開盤跌停：不能放空
    assert samples.exec_long_ok.tolist() == [True, True, True, True, True, False]
    assert samples.exec_short_ok.tolist() == [True, True, True, True, False, True]

    # dates 參數只留指定的 t；整天保留，target_z 不變
    only = dataset.build_samples(
        panel, _hand_universe(["2020-01-06", "2020-01-07"]), HAND_CAL, cfg, dates=pd.DatetimeIndex(["2020-01-07"])
    )
    assert only.stock_ids.tolist() == ["1101", "2317", "2330"]
    np.testing.assert_array_equal(only.target_z, samples.target_z[3:])
    sel = samples.select_dates(pd.DatetimeIndex(["2020-01-07"]))
    np.testing.assert_array_equal(sel.label_r, only.label_r)

    frame = samples.to_frame()
    assert list(frame.columns) == [
        "date", "stock_id", "day_id", "label_r", "target_z", "exec_long_ok", "exec_short_ok",
    ]
    assert frame["exec_long_ok"].tolist() == [1, 1, 1, 1, 1, 0]


def test_build_samples_hand_example_horizon_2() -> None:
    panel = _hand_panel()
    cfg = _cfg(lookback=2, horizon=2)
    uni = _hand_universe(["2020-01-06", "2020-01-07", "2020-01-08"])
    samples = dataset.build_samples(panel, uni, HAND_CAL, cfg)
    # 01-08 的 t+1 超出日曆，沒有標籤
    assert [str(pd.Timestamp(d).date()) for d in samples.dates] == ["2020-01-06"] * 3 + ["2020-01-07"] * 3
    assert samples.stock_ids.tolist() == ["1101", "1301", "2330", "1101", "2317", "2330"]
    expected = [
        # 1101：01-06 開 50 → 01-07 收 50.47，中間除息 51 → 49，還原後報酬含息
        50.47 / (50.0 * 49.0 / 51.0) - 1,
        # 1301：01-07 已下市，用 01-07 以前最後一筆收盤（01-06）
        31.5 / 30.0 - 1,
        108.0 / 100.0 - 1,
        50.47 / 49.0 - 1,
        18.9 / 18.0 - 1,
        108.0 / 110.0 - 1,
    ]
    np.testing.assert_allclose(samples.label_r, np.asarray(expected, dtype=np.float32), rtol=1e-5)


def test_horizon_label_needs_end_day_inside_panel() -> None:
    """日曆比 panel 長時（例如即時預測用全年的日曆），t+h−1 晚於 panel 最後一天的樣本沒有標籤。

    不能拿最後一筆收盤代替，否則 h 天的標籤會悄悄變成比較短的報酬。下市股在 panel 結束前的缺列照樣用最後一筆收盤。
    """
    panel = _hand_panel()
    long_cal = _ns_index([*HAND_CAL.strftime("%Y-%m-%d").tolist(), "2020-01-09", "2020-01-10"])
    cfg = _cfg(lookback=2, horizon=2)
    uni = _hand_universe(["2020-01-06", "2020-01-07", "2020-01-08"])
    samples = dataset.build_samples(panel, uni, long_cal, cfg)
    same = dataset.build_samples(panel, uni, HAND_CAL, cfg)
    # 01-08 的 t+1 = 01-09 在日曆裡，但 panel 只到 01-08，沒有標籤
    assert [str(pd.Timestamp(d).date()) for d in samples.dates] == ["2020-01-06"] * 3 + ["2020-01-07"] * 3
    assert samples.stock_ids.tolist() == same.stock_ids.tolist()
    np.testing.assert_array_equal(samples.label_r, same.label_r)
    np.testing.assert_array_equal(samples.day_ids, same.day_ids)
    assert "1301" in samples.stock_ids.tolist()


def test_target_z_is_clipped_daily_zscore(market: object, cal: pd.DatetimeIndex) -> None:
    clip = 1.0
    samples = dataset.build_samples(
        market.panel, _simple_universe(market.panel, cal, LOOKBACK), cal, _cfg(target_clip_z=clip)
    )
    frame = samples.to_frame()
    for _, g in frame.groupby("date"):
        r = g["label_r"].to_numpy(dtype="float64")
        sd = r.std()
        z = (r - r.mean()) / sd if sd > 1e-12 else np.zeros_like(r)
        np.testing.assert_allclose(g["target_z"].to_numpy(), np.clip(z, -clip, clip), atol=1e-4)
    assert np.abs(samples.target_z).max() <= clip
    assert (np.abs(samples.target_z) == clip).any(), "clip 1.0 應該裁到一些樣本"
    # 標籤就是原始的 close / open − 1，不裁
    panel = market.panel.copy()
    panel["date"] = _ns_index(panel["date"])
    panel["stock_id"] = panel["stock_id"].astype(str)
    merged = frame[["date", "stock_id", "label_r"]].merge(panel, on=["date", "stock_id"], how="left")
    raw = merged["close"].to_numpy(dtype="float64") / merged["open"].to_numpy(dtype="float64") - 1
    np.testing.assert_allclose(merged["label_r"].to_numpy(), raw, rtol=1e-5, atol=1e-7)
    # 同一天同一個 day_id，日期越後 day_id 越大
    per_day = frame.groupby("date")["day_id"].nunique()
    assert (per_day == 1).all()
    first = frame.groupby("date")["day_id"].first()
    assert first.is_monotonic_increasing and first.is_unique


# ---------------------------------------------------------------------------
# Dataset、協變量
# ---------------------------------------------------------------------------


def test_dataset_rejects_samples_without_enough_history(market: object, cal: pd.DatetimeIndex) -> None:
    uni = _simple_universe(market.panel, cal, 4)
    samples = dataset.build_samples(market.panel, uni, cal, _cfg())
    store = dataset.PanelStore(market.panel)
    with pytest.raises(ValueError):
        dataset.PanelWindowDataset(store, samples, None, None, LOOKBACK)


def _cov_frames(samples: object, cal: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    """可以反推 (date, stock_id) 的協變量表；日期故意用 s 和 ms 解析度、列順序打亂。"""
    pos = cal.get_indexer(pd.DatetimeIndex(samples.dates))
    code = pos * 10000.0 + np.array([int(s) for s in samples.stock_ids], dtype=np.float64)
    stock_cov = pd.DataFrame(
        {"code": code, "const": 1.0},
        index=pd.MultiIndex.from_arrays(
            [pd.DatetimeIndex(samples.dates).as_unit("s"), samples.stock_ids], names=["date", "stock_id"]
        ),
    ).sample(frac=1.0, random_state=0)
    days = pd.DatetimeIndex(np.unique(samples.dates))
    market_cov = pd.DataFrame(
        {"day": cal.get_indexer(days).astype(np.float64)}, index=days.as_unit("ms").rename("date")
    ).iloc[::-1]
    return stock_cov, market_cov


def test_dataset_aligns_covariates(market: object, cal: pd.DatetimeIndex) -> None:
    samples = dataset.build_samples(market.panel, _simple_universe(market.panel, cal, LOOKBACK), cal, _cfg())
    store = dataset.PanelStore(market.panel)
    stock_cov, market_cov = _cov_frames(samples, cal)
    drop_k = 7
    hit = (stock_cov.index.get_level_values(0) == pd.Timestamp(samples.dates[drop_k])) & (
        stock_cov.index.get_level_values(1) == str(samples.stock_ids[drop_k])
    )
    assert int(np.asarray(hit).sum()) == 1
    stock_cov = stock_cov.loc[~np.asarray(hit)]
    drop_day = pd.Timestamp(samples.dates[-1])
    n_market = len(market_cov)
    market_cov = market_cov.loc[np.asarray(market_cov.index != drop_day)]
    assert len(market_cov) == n_market - 1

    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        ds = dataset.PanelWindowDataset(store, samples, stock_cov, market_cov, LOOKBACK)
    messages = " ".join(str(w.message) for w in rec)
    assert "stock_cov" in messages and "market_cov" in messages
    assert ds.stock_cov_cols == ["code", "const"]
    assert ds.market_cov_cols == ["day"]

    pos = cal.get_indexer(pd.DatetimeIndex(samples.dates))
    for k in list(range(0, len(samples), 37)) + [drop_k, len(samples) - 1]:
        item = ds[k]
        assert item["stock_cov"].dtype == torch.float32 and item["market_cov"].dtype == torch.float32
        if k == drop_k:
            assert item["stock_cov"].tolist() == [0.0, 0.0]
        else:
            assert item["stock_cov"].tolist() == [float(pos[k] * 10000 + int(samples.stock_ids[k])), 1.0]
        if pd.Timestamp(samples.dates[k]) == drop_day:
            assert item["market_cov"].tolist() == [0.0]
        else:
            assert item["market_cov"].tolist() == [float(pos[k])]
        assert int(item["index"]) == k
        assert int(item["day_id"]) == int(samples.day_ids[k])


# ---------------------------------------------------------------------------
# 分批
# ---------------------------------------------------------------------------


def test_day_batch_sampler_never_splits_a_day() -> None:
    rng = np.random.default_rng(3)
    day_ids = rng.permutation(np.repeat(np.arange(10, 23), rng.integers(1, 9, 13)))
    n_days = len(np.unique(day_ids))
    for shuffle in (False, True):
        for cap in (None, 3):
            sampler = dataset.DayBatchSampler(day_ids, batch_days=4, shuffle=shuffle, seed=1, max_stocks_per_day=cap)
            batches = list(sampler)
            assert len(batches) == len(sampler) == math.ceil(n_days / 4)
            where: dict[int, int] = {}
            for b, batch in enumerate(batches):
                assert all(type(i) is int for i in batch)
                days = sorted(set(day_ids[batch].tolist()))
                assert 1 <= len(days) <= 4
                for d in days:
                    assert d not in where, f"第 {d} 天被拆到兩個 batch"
                    where[d] = b
                    chosen = sorted(i for i in batch if day_ids[i] == d)
                    full = np.flatnonzero(day_ids == d).tolist()
                    if cap is None:
                        assert chosen == full
                    else:
                        assert len(chosen) == min(cap, len(full)) and set(chosen) <= set(full)
            assert set(where) == set(day_ids.tolist())
            flat = [i for batch in batches for i in batch]
            assert len(flat) == len(set(flat))
            if cap is None:
                assert sorted(flat) == list(range(len(day_ids)))
            if not shuffle:
                order = [int(day_ids[batch[0]]) for batch in batches]
                assert order == sorted(order)

    sampler = dataset.DayBatchSampler(day_ids, 4, True, 7)
    first = list(sampler)
    assert list(sampler) == first
    sampler.set_epoch(1)
    second = list(sampler)
    assert second != first
    again = dataset.DayBatchSampler(day_ids, 4, True, 7)
    again.set_epoch(1)
    assert list(again) == second
    fixed = dataset.DayBatchSampler(day_ids, 4, False, 0, max_stocks_per_day=2)
    a = list(fixed)
    fixed.set_epoch(5)
    assert list(fixed) == a


def test_make_loader_shapes_and_whole_days(market: object, cal: pd.DatetimeIndex) -> None:
    samples = dataset.build_samples(market.panel, _simple_universe(market.panel, cal, LOOKBACK), cal, _cfg())
    store = dataset.PanelStore(market.panel)
    stock_cov, market_cov = _cov_frames(samples, cal)
    ds = dataset.PanelWindowDataset(store, samples, stock_cov, market_cov, LOOKBACK)
    loader = dataset.make_loader(ds, samples.day_ids, batch_days=3, shuffle=True, seed=0, num_workers=0)
    n_days = len(np.unique(samples.day_ids))
    assert len(loader) == math.ceil(n_days / 3)

    batch = next(iter(loader))
    n = len(batch["index"])
    expected = {
        "levels": ((n, LOOKBACK, 6), torch.float32),
        "stamps": ((n, LOOKBACK, 5), torch.float32),
        "rets": ((n, LOOKBACK, 5), torch.float32),
        "stock_cov": ((n, 2), torch.float32),
        "market_cov": ((n, 1), torch.float32),
        "target_z": ((n,), torch.float32),
        "label_r": ((n,), torch.float32),
        "day_id": ((n,), torch.int64),
        "index": ((n,), torch.int64),
        "exec_long_ok": ((n,), torch.bool),
        "exec_short_ok": ((n,), torch.bool),
    }
    assert set(batch) == set(expected)
    for name, (shape, dtype) in expected.items():
        assert tuple(batch[name].shape) == shape, name
        assert batch[name].dtype == dtype, name
    idx = batch["index"].numpy()
    np.testing.assert_array_equal(batch["day_id"].numpy(), samples.day_ids[idx])
    np.testing.assert_array_equal(batch["label_r"].numpy(), samples.label_r[idx])
    days = np.unique(samples.day_ids[idx])
    assert len(days) <= 3
    for d in days.tolist():
        assert set(np.flatnonzero(samples.day_ids == d).tolist()) <= set(idx.tolist())

    loader.batch_sampler.set_epoch(1)
    seen = np.concatenate([b["index"].numpy() for b in loader])
    assert sorted(seen.tolist()) == list(range(len(samples)))
    with pytest.raises(ValueError):
        dataset.make_loader(ds, samples.day_ids[:-1], 3, False, 0, 0)
