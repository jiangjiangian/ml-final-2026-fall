"""特徵工程：data/raw/ → data/processed/features.csv.gz。

一列＝一檔股票 × 一個台股交易日 t。欄位：
    date, stock_id        鍵
    <名稱>_ret_lag2 ...   特徵；名稱和 lag 來自 config.yaml
    label_y               答案：t 當天 adj_close > adj_open 為 1；還不知道時空白
    label_return          答案：t 當天 adj_close / adj_open − 1（官方分數用）

lag k 的定義：t 那列 = (close_i − close_(i−k)) / close_(i−k)，
i = t 的前一個台股交易日，i−k 數的是該序列自己的交易日；i 那天沒有資料就留空白，不補值。

訓練和預測都呼叫 build_features()，所以兩邊算出來的特徵一定一樣。
今天（要預測的那天）也會有一列，它的 label 是空白，predict.py 只取這一列。

用法：python -m src.features
"""


def load_raw(cfg: dict):
    """讀 data/raw/：老師 Training 接上 Live（Live 只取 Training 最後一天之後的列），
    以及 yfinance 各序列。值是 -1 的格子視為「還沒有」，不當數字。回傳一個 dict。"""
    raise NotImplementedError


def build_features(raw: dict, cfg: dict):
    """回傳 pandas DataFrame（欄位見檔案開頭）。

    只能用 t 之前的資料。t 當天的價格、成交量、法人、技術指標和 y 都不能進特徵；
    老師 global 表的 ^TWII、^KS11、TX_OI 是當天收盤後的值，只能用前一列。
    """
    raise NotImplementedError


def main():
    """load_raw → build_features → 寫 data/processed/features.csv.gz。"""
    raise NotImplementedError


if __name__ == "__main__":
    main()
