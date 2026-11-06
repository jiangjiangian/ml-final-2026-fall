"""訓練：讀特徵表，按日期驗證，再用全部資料訓練，存到 models/。

輸入：features.load_features() 讀回的特徵表裡 label_y 有值的列，欄位用 features.model_columns(cfg)。
輸出：
    models/model.txt             模型（LightGBM 的文字格式）
    models/feature_columns.json  欄位順序、訓練資料的最後一天、驗證分數

步驟：
    1. 驗證：最後 config.yaml 的 model.valid_days 個交易日當驗證，之前的當訓練，算出驗證分數。
       先切日期，再挑出那些日期的列；不可以隨機拆列，同一天 50 檔股票共用市場特徵。
    2. 和「全部猜 1」「全部猜 0」比。贏不了就在 log 裡寫清楚。
    3. 用同樣的參數，在全部有答案的列上重新訓練一次。存的是這個模型，
       所以最近 valid_days 天的資料也會用到。

用法：python -m src.train
"""


def split_by_date(df, valid_days: int):
    """回傳 (train_df, valid_df)。valid_df 是最後 valid_days 個交易日的全部列。"""
    raise NotImplementedError


def official_score(pred, intraday_return):
    """官方分數：每格 (2 × pred − 1) × 當天盤中報酬，再取平均。pred 是 0 或 1。"""
    raise NotImplementedError


def train_model(df, cfg: dict):
    """用 cfg["model"]["params"] 訓練並回傳模型。"""
    raise NotImplementedError


def save_model(model, feature_columns: list, info: dict, cfg: dict):
    """把模型和 feature_columns.json 寫到 models/。info 放訓練資料最後一天和驗證分數。"""
    raise NotImplementedError


def main(argv=None):
    """讀特徵表 → split_by_date → 驗證 → 用全部資料 train_model → save_model。"""
    raise NotImplementedError


if __name__ == "__main__":
    main()
