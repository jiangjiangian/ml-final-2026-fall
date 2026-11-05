"""特徵只能用 t 之前的資料。features.py 寫好後拿掉 skip。"""

import pytest


@pytest.mark.skip(reason="features.py 還是骨架")
def test_changing_day_t_does_not_change_its_features():
    """把某一天 t 的收盤價改掉，t 那一列的特徵不能變，只有 t 之後的列可以變。"""


@pytest.mark.skip(reason="features.py 還是骨架")
def test_today_row_has_no_label():
    """今天那一列的 label_y、label_return 一定是空白。"""
