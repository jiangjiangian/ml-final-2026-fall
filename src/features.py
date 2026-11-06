"""特徵工程：data/raw/ → data/processed/features.csv.gz。

一列＝一檔股票（老師資料的 100 檔）× 一個台股交易日 t。欄位：
    date, stock_id            鍵；stock_id 一律當字串（"2330"），不轉成數字
    is_top50                  1＝要預測的 50 檔（info.json 的 Top50@Y）
    <名稱>_ret_lag1、_lag2   特徵，見下方
    label_y                   答案：t 當天 etl:adj_close > etl:adj_open 為 1；還不知道時空白
    label_intraday_return     答案：t 當天 etl:adj_close / etl:adj_open − 1（官方分數用）；還不知道時空白

特徵 <名稱>_ret_lag{k}：到 t 的前一個台股交易日 i 為止、往回 k 個交易日的報酬，
    t 那列 = (close_i − close_(i−k)) / close_(i−k)，i−k 數的是該序列自己的交易日；
    i 那天該序列沒有資料就留空白，不補值。k 來自 config.yaml 的 features.lags。
    名稱有三種：
    - stock：股票自己，用 features.stock_column（etl:adj_close）。這組讓 50 檔每天的值不同；
      只有市場特徵的話，同一天 50 檔的值都一樣，模型每天只會給一個答案。
    - 老師 global 表的指數：features.teacher_global。
    - yfinance 的 19 個序列：features.adj_close_kinds 裡的代號用 adj_close，其他用 close。

台股交易日的日曆：
    以老師個股檔（market/*.csv）出現過的日期為準。Live 裡的待定列，要 /api/state 的 phase2Days
    有那一天才算交易日（例如 10/23 那列一直是 -1，使用者 2026-11-05 確認是颱風假）。
    global 表缺很多台股日（Training 少 112 天），不能當日曆。

-1 的處理：
    只有 Live 的待定列是「還沒有」：個股檔 etl:adj_close 是 -1 的列整列當空白；
    global 表只有 ^TWII、^KS11、TX_OI 會用 -1 表示待定。
    其他地方的 -1 是真的數字（例如 Training 的法人買賣超有 83 格剛好是 -1 股），要保留。

訓練和預測都呼叫 build_features()，所以兩邊算出來的特徵一定一樣。
預測日 t 也會有一列，它的 label 是空白，predict.py 只取這一列。

用法：python -m src.features
"""


def load_raw(cfg: dict):
    """讀 data/raw/：老師 Training 接上 Live（Live 只取 Training 最後一天之後的列），以及 yfinance 各序列。

    yfinance 序列讀進來先清理，照舊爬蟲的 R0～R5 依序做（規則和測試資料見 memory/projects/features.md）：
    - R0 空值和 close 空的列拿掉、依日期排序。
    - R1 close 超出 [low, high] 0.5% 以上的壞報價（例如 TWD=X）。
    - R2 美債休市日（哥倫布日、退伍軍人節）的平盤K棒（^TNX、^IRX）。
    - R3 股票和 ETF 的佔位K棒和不完整K棒。
    - R4 .TW／.TWO 的分割只調了一半時補調（例如 0052 在 2025-11 的一拆七）。
    - R5 分割前的股利調整乘回去。
    刪掉的列整列拿掉，不留空白的一列（留空白會讓往回數的 i−k 錯位）。
    清理紀錄的範例在 data/reference/data-collection/extra/manifest.json（data-collection 的凍結快照）。
    回傳一個 dict。
    """
    raise NotImplementedError


def build_features(raw: dict, cfg: dict):
    """回傳 pandas DataFrame（欄位見檔案開頭）。

    只能用 t 之前的資料。t 當天的價格、成交量、法人、技術指標和 y 都不能進特徵；
    global 表的 ^TWII、^KS11、TX_OI 是當天收盤後的值，只能用日期早於 t 的最後一列。
    """
    raise NotImplementedError


def main(argv=None):
    """load_raw → build_features → 寫 data/processed/features.csv.gz。"""
    raise NotImplementedError


if __name__ == "__main__":
    main()
