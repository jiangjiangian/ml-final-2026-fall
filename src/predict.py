"""預測：用今天的特徵和 models/ 的模型，產生 data/submission/submission_YYYY-MM-DD.csv。

CSV 格式（Phase 2）：
    第一列是表頭：id,<今天的日期 YYYY-MM-DD>
    接著 50 列，每列是股票代號和 0 或 1
    股票順序照課程網站當天的範本（config.yaml 的 course_site.template）
    不能有空值、機率或多的欄位

預測前檢查：
    - 特徵欄位和順序要和 models/feature_columns.json 一樣，不一樣就停。
    - 模型的訓練資料最後一天要早於今天。
    - 推論時不重新 fit 任何東西。

用法：python -m src.predict
"""


def load_template(cfg: dict, secrets: dict, target_date: str):
    """下載當天的空白提交檔，回傳 50 個股票代號（照範本順序）。"""
    raise NotImplementedError


def predict_today(target_date: str, cfg: dict):
    """回傳 {stock_id: 0 或 1}，只用 target_date 那一列的特徵。"""
    raise NotImplementedError


def write_submission(predictions: dict, stock_order: list, target_date: str, cfg: dict):
    """照範本順序寫 CSV，寫完重新讀一次檢查格式。回傳檔案路徑。"""
    raise NotImplementedError


def main():
    """load_template → predict_today → write_submission。"""
    raise NotImplementedError


if __name__ == "__main__":
    main()
