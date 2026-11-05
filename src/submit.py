"""上傳：把 t 的 submission CSV 送到課程網站，再下載回來核對。

順序：
    1. 檢查還沒過 config.yaml 的 competition.upload_cutoff（utils.check_deadline，key="upload_cutoff"）。
    2. 讀 /api/state：
       - phase2Days 沒有 t 就是休市，直接結束，不算失敗。
       - t 要是 enabled，現在要在 openAt 和網站的 deadline 之間。網站回傳的時間沒帶時區，當成 UTC。
       - uploadQuota 還要有剩。每隊每天的上傳次數有上限，所以不確定上次有沒有送成功時，先查網站，不要直接重送。
    3. 網站目前的有效提交已經和這份 CSV 一樣，就不再送。
    4. 先在 data/submission/upload_log.jsonl 寫一筆「準備上傳」，再 POST。
       如果每次都在全新的機器上跑（雲端的機器跑完就清空），這筆紀錄要先 commit 並 push 成功才 POST，
       push 失敗就不上傳；不然下一次執行看不到這筆紀錄，可能會重送。
    5. POST 之後就算拿到 HTTP 200，也要用 course_site.submission_file 把網站上的版本下載回來逐格比對；
       一致才在紀錄裡寫「完成」。

POST 失敗或逾時不自動重試，改回第 2 步查網站有沒有收到。
config.yaml 的 submit.enabled 是 false 時，只印出要送的內容，不真的上傳。

用法：python -m src.submit
"""


def site_state(cfg: dict, secrets: dict):
    """登入後讀 /api/state，回傳 dict（交易日、截止、上傳次數、目前的提交）。"""
    raise NotImplementedError


def current_submission(state: dict, cfg: dict, secrets: dict, target_date: str):
    """回傳網站上 t 目前有效的提交內容 {stock_id: 0 或 1}，沒有就回傳 None。

    從 state 的 mySubmissions 找到 id，再 GET course_site.submission_file。
    """
    raise NotImplementedError


def upload(csv_path: str, target_date: str, cfg: dict, secrets: dict):
    """把 CSV 轉成 JSON，POST 到 course_site.submissions。回傳網站的回應（不含帳密）。

    JSON 格式（舊程式的研究整理出來的，還沒實際送過）：
        {"phase": 2, "tradingDate": "YYYY-MM-DD", "fileName": "submission_YYYY-MM-DD.csv",
         "payload": {"stockIds": [50 個代號字串], "predictions": [50 個 0 或 1]}}
    """
    raise NotImplementedError


def verify(csv_path: str, state: dict, cfg: dict, secrets: dict, target_date: str):
    """比對網站上的版本和 csv_path，一致回傳 True。"""
    raise NotImplementedError


def main(argv=None):
    """依檔案開頭的順序執行，每一步都寫進 upload_log.jsonl。"""
    raise NotImplementedError


if __name__ == "__main__":
    main()
