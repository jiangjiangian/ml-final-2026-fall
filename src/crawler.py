"""爬蟲：下載老師資料和 yfinance 額外指標，原樣存到 data/raw/。

輸出的資料夾：
    data/raw/teacher/          老師 Training ZIP 解開後的檔案：info.json、global/global_data.csv、market/<stock_id>.csv
    data/raw/teacher_live/     老師 Live ZIP 解開後的檔案，結構和 teacher/ 一樣，每次下載覆蓋
    data/raw/yfinance/<名稱>.csv   每個額外指標一檔：date, open, high, low, close, adj_close, volume
    data/raw/manifest.json     每個檔案的下載時間、sha256 和成功或失敗

老師資料要注意的地方：
    - 兩個 ZIP 裡的路徑開頭都多一層 data/（例如 data/market/2330.csv），解壓時拿掉。
    - Training ZIP 不會再變。data/raw/teacher/ 已經有檔案、而且 sha256 和 manifest 一樣，就不重新下載。
    - Live ZIP 一天會更新不只一次。預測日 t 早上的版本已經有 t 的一列：個股欄整列是 -1，
      global 表只有 ^TWII、^KS11、TX_OI 是 -1（^VIX、^IXIC、^GSPC 已經填了前一個美股收盤）。

yfinance 要注意的地方：
    - 下載時設 auto_adjust=False，才會同時有 close 和 adj_close。
    - end 設成台北今天（yfinance 的 end 不含那一天），才不會存到還沒收盤的K棒。
    - 限流加在交給 yfinance 的 curl_cffi Session 上，yfinance 自己多送的請求（例如取 cookie）也要算在內。
      每個請求至少間隔 config.yaml 的 yfinance.min_interval_seconds 秒。
    - 時區快取用 yf.set_tz_cache_location 放到 config.yaml 的 yfinance.cache_dir（不進 Git）。

失敗時：
    - yfinance 某個序列失敗：保留前一次的檔案，在 manifest 記下失敗，繼續跑（那個特徵當天可能是空白）。
    - 老師 Live ZIP 失敗：沒有 t 前一天的資料就不能預測，停下並在 log 寫原因。

原始資料不修改，清理留給 features.py。

用法：python -m src.crawler
"""


def download_teacher(cfg: dict, secrets: dict):
    """登入課程網站，下載 Training ZIP 和最新的 Live ZIP，解開到 data/raw/。

    登入：POST cfg["course_site"]["login"]，JSON 帶 email、password。
    Live ZIP 在另一台伺服器，網址和金鑰還沒決定（見 memory/context/open-questions.md）；
    COURSE_LIVE_KEY 是空的就跳過 Live，在 manifest 記下原因。
    回傳寫入的檔案清單。
    """
    raise NotImplementedError


def download_yfinance(cfg: dict):
    """依 cfg["yfinance"]["tickers"] 逐一下載日K，從 cfg["data"]["start"] 到台北昨天。

    被 Yahoo 限流（HTTP 429）時加長等待再重試，最多 max_retries 次。
    回傳 {名稱: 成功或失敗原因}。
    """
    raise NotImplementedError


def main(argv=None):
    """依序執行 download_teacher 和 download_yfinance，最後寫 manifest.json。"""
    raise NotImplementedError


if __name__ == "__main__":
    main()
