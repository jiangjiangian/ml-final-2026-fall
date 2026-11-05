"""預測：下載當天範本，用 models/ 的模型產生 data/submission/submission_YYYY-MM-DD.csv。

這一步要連網：範本要登入課程網站下載。

CSV 格式（Phase 2，每天交的那種）：
    第一列是表頭：id,<預測日 t，YYYY-MM-DD>
    接著 50 列，每列是股票代號和 0 或 1
    股票順序照課程網站當天的範本（config.yaml 的 course_site.template）
    不能有空值、機率或多的欄位

預測前檢查，任何一項不過就停：
    - 還沒過 t 當天的 deadline（utils.check_deadline）。
    - 特徵表裡有 t 的列，而且範本上的 50 檔都在。Live 沒更新到 t 時就沒有這一列，不能拿別天的列來用。
    - 特徵欄位和順序和 models/feature_columns.json 一樣。
    - 模型的訓練資料最後一天早於 t。

推論時只載入 models/ 裡存好的模型，不重新 fit 任何東西。

用法：python -m src.predict
"""


def load_template(cfg: dict, secrets: dict, target_date: str):
    """下載 t 的範本，回傳 50 個股票代號（照範本順序）。

    用 utf-8-sig 讀（開頭可能有 BOM），代號一律當字串。
    以範本為準；和 info.json 的 Top50@Y 不一樣時停下，在 log 寫出差異。
    """
    raise NotImplementedError


def predict_today(target_date: str, cfg: dict):
    """回傳 {stock_id: 0 或 1}，只用 target_date 那一列的特徵。"""
    raise NotImplementedError


def write_submission(predictions: dict, stock_order: list, target_date: str, cfg: dict):
    """照範本順序寫 CSV，寫完重新讀一次檢查格式。回傳檔案路徑。"""
    raise NotImplementedError


def main(argv=None):
    """check_deadline → load_template → predict_today → write_submission。"""
    raise NotImplementedError


if __name__ == "__main__":
    main()
