"""爬蟲：下載老師資料和 yfinance 額外指標，原樣存到 data/raw/。

輸出的資料夾：
    data/raw/teacher/          老師 Training ZIP 解開後的檔案（info.json、global/、market/<stock_id>.csv）
    data/raw/teacher_live/     老師 Live ZIP 解開後的檔案（每天更新；當天那一列的值是 -1，代表還沒有）
    data/raw/yfinance/<名稱>.csv   每個額外指標一檔：date, open, high, low, close, adj_close, volume
    data/raw/manifest.json     每個檔案的下載時間和 sha256，之後才查得到某天用了哪一版

規則：
    - 原始資料不修改，清理留給 features.py。
    - yfinance 每個請求至少間隔 config.yaml 的 yfinance.min_interval_seconds 秒。
    - 某個來源失敗時，保留前一次的檔案，並在 manifest 記下失敗，不要讓整個流程停在這裡。

用法：python -m src.crawler
"""


def download_teacher(cfg: dict, secrets: dict):
    """登入課程網站，下載 Training ZIP 和當天的 Live ZIP，解開到 data/raw/。

    步驟：POST cfg["course_site"]["login"] 登入 → GET training_zip → 解壓。
    Live ZIP 在另一台伺服器，需要 COURSE_LIVE_KEY，網址還沒決定（見 README「還沒決定的事」）。
    回傳寫入的檔案清單。
    """
    raise NotImplementedError


def download_yfinance(cfg: dict):
    """依 cfg["yfinance"]["tickers"] 逐一下載日K，從 cfg["data"]["start"] 到今天。

    每個請求之間等待，被 Yahoo 限流（HTTP 429）時加長等待再重試，最多 max_retries 次。
    回傳 {名稱: 成功或失敗原因}。
    """
    raise NotImplementedError


def main():
    """依序執行 download_teacher 和 download_yfinance，最後寫 manifest.json。"""
    raise NotImplementedError


if __name__ == "__main__":
    main()
