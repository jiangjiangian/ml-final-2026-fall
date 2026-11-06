"""submission CSV 的格式要和課程網站要求的一樣（規則照網站前端把 CSV 轉成 JSON 的程式）。"""

import pytest

from src import site_api, submit

T = "2026-11-09"
IDS = ["2330", "2317", "0050"]


def test_header_rows_and_values():
    """表頭是 id,<預測日>；列數和範本一樣；股票順序和範本一樣；代號是字串；值只有 0 和 1，沒有空值。"""
    rows = submit.build_rows(2, ["id", T], IDS, {(T, "2330"): 1, (T, "2317"): 0, (T, "0050"): 0})
    back = site_api.read_csv_text(submit.rows_to_bytes(rows))
    assert back == [["id", T], ["2330", "1"], ["2317", "0"], ["0050", "0"]]   # 0050 的 0 開頭留著
    submit.check_rows(back, 2, ["id", T], IDS)
    for bad in ([["id", T], ["2330", "1"], ["2317", "0"]],                     # 少一列
                [["id", T], ["2330", "1"], ["2317", "0.7"], ["0050", "0"]],   # 機率
                [["id", T], ["2330", "1"], ["2317", ""], ["0050", "0"]],      # 空值
                [["id", T, "x"], ["2330", "1", "1"], ["2317", "0", "1"], ["0050", "0", "1"]]):
        with pytest.raises(ValueError):
            submit.check_rows(bad, 2, ["id", T], IDS)
