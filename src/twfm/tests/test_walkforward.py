"""`twfm.train.walkforward` 的測試：三段互斥、順序對、embargo 夠，而且 import 時不載入 torch。"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

import twfm.config as config
import twfm.train.walkforward as walkforward


@pytest.fixture(scope="module")
def calendar() -> pd.DatetimeIndex:
    """2004～2026 的平日，隨機拿掉約 4% 當假日。"""
    days = pd.bdate_range("2004-01-02", "2026-06-30")
    rng = np.random.default_rng(0)
    keep = rng.random(len(days)) > 0.04
    # 統一成 ns（pandas 3 可能給 us，DatetimeIndex.equals 會因為單位不同回傳 False）
    return pd.DatetimeIndex(np.asarray(days[keep].to_numpy(), dtype="datetime64[ns]"))


def _pos(cal: pd.DatetimeIndex, d: pd.Timestamp) -> int:
    return int(cal.get_loc(d))


def _between(cal: pd.DatetimeIndex, start: str, end: str) -> pd.DatetimeIndex:
    return cal[(cal >= pd.Timestamp(start)) & (cal <= pd.Timestamp(end))]


def _check_split(split: object, cal: pd.DatetimeIndex, horizon: int, embargo: int) -> None:
    """獨立於實作的檢查：每段排序不重複、都在日曆裡、互斥、順序對、間隔夠、標籤不跨段。"""
    gap = max(embargo, horizon - 1)
    parts = [split.train_dates, split.val_dates, split.test_dates]
    for d in parts:
        assert isinstance(d, pd.DatetimeIndex)
        assert d.is_monotonic_increasing and d.is_unique
        assert d.isin(cal).all()
    for a in range(3):
        for b in range(a + 1, 3):
            assert len(parts[a].intersection(parts[b])) == 0
    nonempty = [d for d in parts if len(d)]
    for a, b in zip(nonempty[:-1], nonempty[1:]):
        assert a[-1] < b[0]
        assert _pos(cal, b[0]) - _pos(cal, a[-1]) - 1 >= gap
        # 前一段最後一天的標籤看到 t+h−1，要在下一段第一天之前
        assert _pos(cal, a[-1]) + horizon - 1 < _pos(cal, b[0])


def test_required_gap() -> None:
    assert walkforward.required_gap(0, 1) == 0
    assert walkforward.required_gap(0, 5) == 4
    assert walkforward.required_gap(10, 5) == 10
    with pytest.raises(ValueError):
        walkforward.required_gap(0, 0)
    with pytest.raises(ValueError):
        walkforward.required_gap(-1, 1)


def test_fixed_split_default_dates(calendar: pd.DatetimeIndex) -> None:
    cal = calendar
    split = walkforward.fixed_split(cal, config.SplitConfig())
    train = _between(cal, "2004-01-01", "2024-06-30")
    val = _between(cal, "2024-07-01", "2025-06-30")
    test = cal[cal >= pd.Timestamp("2025-07-01")]
    # horizon 1、embargo 0：三段就是設定的日期，不去掉任何一天
    assert split.train_dates.equals(train)
    assert split.val_dates.equals(val)
    assert split.test_dates.equals(test)
    _check_split(split, cal, horizon=1, embargo=0)
    walkforward.assert_no_overlap(split, 1)
    json.dumps(split.summary())


@pytest.mark.parametrize(("horizon", "embargo"), [(5, 0), (1, 10), (5, 3), (3, 7)])
def test_fixed_split_embargo_and_horizon(calendar: pd.DatetimeIndex, horizon: int, embargo: int) -> None:
    cal = calendar
    gap = max(embargo, horizon - 1)
    split = walkforward.fixed_split(cal, config.SplitConfig(embargo_days=embargo), horizon=horizon)
    full_train = _between(cal, "2004-01-01", "2024-06-30")
    full_val = _between(cal, "2024-07-01", "2025-06-30")
    # 兩段在日曆上相鄰，所以剛好去掉 gap 天
    assert len(split.train_dates) == len(full_train) - gap
    assert split.train_dates.equals(full_train[: len(full_train) - gap])
    assert _pos(cal, split.val_dates[0]) - _pos(cal, split.train_dates[-1]) - 1 == gap
    # 驗證尾端也對測試留同樣的間隔
    assert split.val_dates.equals(full_val[: len(full_val) - gap])
    assert _pos(cal, split.test_dates[0]) - _pos(cal, split.val_dates[-1]) - 1 == gap
    _check_split(split, cal, horizon=horizon, embargo=embargo)
    walkforward.assert_no_overlap(split, horizon, embargo_days=embargo)


def test_fixed_split_test_end_and_bad_configs(calendar: pd.DatetimeIndex) -> None:
    cal = calendar
    split = walkforward.fixed_split(cal, config.SplitConfig(test_end="2025-12-31"))
    assert split.test_dates[-1] <= pd.Timestamp("2025-12-31")
    assert split.test_dates.equals(_between(cal, "2025-07-01", "2025-12-31"))
    with pytest.raises(ValueError):
        walkforward.fixed_split(cal, config.SplitConfig(train_end="2024-12-31"))
    with pytest.raises(ValueError):
        walkforward.fixed_split(cal, config.SplitConfig(val_end="2025-09-30"))
    with pytest.raises(ValueError):
        walkforward.fixed_split(cal, config.SplitConfig(train_start="2030-01-01", train_end="2030-06-30"))
    with pytest.warns(UserWarning):
        empty_test = walkforward.fixed_split(cal, config.SplitConfig(test_start="2030-01-01"))
    assert len(empty_test.test_dates) == 0


def test_walk_forward_expanding(calendar: pd.DatetimeIndex) -> None:
    cal = calendar
    horizon, embargo, val_days = 4, 2, 120
    gap = max(embargo, horizon - 1)
    splits = walkforward.walk_forward_splits(
        cal, "2015-01-01", test_months=6, val_days=val_days, embargo_days=embargo, horizon=horizon, end="2019-12-31"
    )
    assert len(splits) == 10
    assert len({s.name for s in splits}) == len(splits)
    all_test = pd.DatetimeIndex(np.concatenate([s.test_dates.to_numpy() for s in splits]))
    assert all_test.equals(_between(cal, "2015-01-01", "2019-12-31"))
    prev_train = 0
    for k, s in enumerate(splits):
        _check_split(s, cal, horizon=horizon, embargo=embargo)
        walkforward.assert_no_overlap(s, horizon, embargo_days=embargo)
        start = pd.Timestamp("2015-01-01") + pd.DateOffset(months=6 * k)
        stop = pd.Timestamp("2015-01-01") + pd.DateOffset(months=6 * (k + 1))
        assert s.test_dates[0] >= start and s.test_dates[-1] < stop
        assert s.train_dates[0] == cal[0]
        assert len(s.val_dates) == val_days
        assert _pos(cal, s.test_dates[0]) - _pos(cal, s.val_dates[-1]) - 1 == gap
        assert _pos(cal, s.val_dates[0]) - _pos(cal, s.train_dates[-1]) - 1 == gap
        assert len(s.train_dates) > prev_train
        prev_train = len(s.train_dates)


def test_walk_forward_rolling_and_end(calendar: pd.DatetimeIndex) -> None:
    cal = calendar
    for years, months in ((3, 36), (1.5, 18)):
        splits = walkforward.walk_forward_splits(
            cal, "2016-01-01", test_months=12, val_days=60, mode="rolling", train_years=years, end="2019-12-31"
        )
        assert len(splits) == 4
        for s in splits:
            _check_split(s, cal, horizon=1, embargo=0)
            lo = s.train_dates[-1] - pd.DateOffset(months=months)
            assert s.train_dates[0] > lo
            # 視窗是滿的：訓練第一天的前一個交易日已經超出範圍
            assert cal[_pos(cal, s.train_dates[0]) - 1] <= lo
    full = walkforward.walk_forward_splits(cal, "2025-01-01", test_months=6, val_days=60)
    assert full[-1].test_dates[-1] == cal[-1]
    with pytest.raises(ValueError):
        walkforward.walk_forward_splits(cal, "2016-01-01", mode="rolling")
    with pytest.raises(ValueError):
        walkforward.walk_forward_splits(cal, "2016-01-01", mode="sideways")
    with pytest.raises(ValueError):
        walkforward.walk_forward_splits(cal, "2004-02-01", val_days=120)
    with pytest.raises(ValueError):
        walkforward.walk_forward_splits(cal, "2030-01-01")


def test_assert_no_overlap_catches_bad_splits(calendar: pd.DatetimeIndex) -> None:
    cal = calendar[:300]
    Split = walkforward.Split
    good = Split("good", cal[:200], cal[200:250], cal[250:], calendar=cal)
    walkforward.assert_no_overlap(good, 1)
    with pytest.raises(AssertionError):
        walkforward.assert_no_overlap(Split("overlap", cal[:201], cal[200:250], cal[250:], calendar=cal), 1)
    with pytest.raises(AssertionError):
        walkforward.assert_no_overlap(Split("order", cal[200:250], cal[:200], cal[250:], calendar=cal), 1)
    with pytest.raises(AssertionError):
        walkforward.assert_no_overlap(Split("unsorted", cal[:200][::-1], cal[200:250], cal[250:], calendar=cal), 1)
    with pytest.raises(AssertionError):
        walkforward.assert_no_overlap(good, 3)
    with pytest.raises(AssertionError):
        walkforward.assert_no_overlap(good, 1, embargo_days=1)
    gapped = Split("gapped", cal[:198], cal[200:248], cal[250:], calendar=cal)
    walkforward.assert_no_overlap(gapped, 3)
    walkforward.assert_no_overlap(gapped, 1, embargo_days=2)
    with pytest.raises(AssertionError):
        walkforward.assert_no_overlap(gapped, 4)
    no_cal = Split("no_cal", cal[:198], cal[200:248], cal[250:])
    walkforward.assert_no_overlap(no_cal, 1)
    with pytest.raises(ValueError):
        walkforward.assert_no_overlap(no_cal, 3)
    walkforward.assert_no_overlap(no_cal, 3, calendar=cal)
    off_cal = Split("off_cal", cal[:198], cal[200:248], pd.DatetimeIndex(["2099-01-05"]), calendar=cal)
    with pytest.raises(AssertionError):
        walkforward.assert_no_overlap(off_cal, 3)
    empty_test = Split("empty_test", cal[:198], cal[200:248], pd.DatetimeIndex([]), calendar=cal)
    walkforward.assert_no_overlap(empty_test, 3)


def test_walkforward_does_not_import_torch() -> None:
    """SPEC：`twfm.train.walkforward` 只用 numpy、pandas。連套件的 `__init__` 都不能間接載入 torch。"""
    code = (
        "import importlib, sys\n"
        f"importlib.import_module({walkforward.__name__!r})\n"
        "print('torch' in sys.modules)\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.getcwd(),
        timeout=120,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "False"
