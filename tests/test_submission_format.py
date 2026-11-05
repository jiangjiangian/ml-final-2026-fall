"""submission CSV 的格式要和課程網站要求的一樣。predict.py 寫好後拿掉 skip。"""

import pytest


@pytest.mark.skip(reason="predict.py 還是骨架")
def test_header_rows_and_values():
    """表頭是 id,<日期>；剛好 50 列；股票順序和範本一樣；值只有 0 和 1，沒有空值。"""
