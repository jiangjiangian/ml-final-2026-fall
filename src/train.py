"""訓練：讀特徵表，按日期切分，訓練模型，存到 models/。

輸入：data/processed/features.csv.gz 裡 label_y 有值的列。
輸出：
    models/model.txt             模型（LightGBM 的文字格式）
    models/feature_columns.json  訓練時的欄位順序、訓練資料最後一天、驗證分數

驗證按日期切：最後 config.yaml 的 model.valid_days 個交易日當驗證，之前的當訓練。
不可以隨機拆列，因為同一天 50 檔股票共用市場特徵。

用法：python -m src.train
"""


def split_by_date(df, valid_days: int):
    """回傳 (train_df, valid_df)。valid_df 是最後 valid_days 個交易日。"""
    raise NotImplementedError


def official_score(pred, intraday_return):
    """官方分數：每格 (2 × pred − 1) × 當天盤中報酬，再取平均。pred 是 0 或 1。"""
    raise NotImplementedError


def train_model(train_df, valid_df, cfg: dict):
    """用 cfg["model"] 的參數訓練。回傳 (model, 驗證分數)。

    驗證分數要和「全部猜 1」「全部猜 0」比，贏不了就在 log 裡寫清楚。
    """
    raise NotImplementedError


def save_model(model, feature_columns: list, info: dict, cfg: dict):
    """把模型和 feature_columns.json 寫到 models/。"""
    raise NotImplementedError


def main():
    """讀特徵表 → split_by_date → train_model → save_model。"""
    raise NotImplementedError


if __name__ == "__main__":
    main()
