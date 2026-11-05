"""上傳：把今天的 submission CSV 送到課程網站，再下載回來核對。

順序：
    1. 檢查還沒過 09:00。
    2. 查網站目前的有效提交（config.yaml 的 course_site.state）。已經和今天的 CSV 一樣，就不再送。
    3. 先在 data/submission/upload_log.jsonl 寫一筆「準備上傳」，再 POST。
       這樣程式中途當掉時，下一次執行看得到這筆紀錄，可以先查網站再決定要不要重送。
    4. POST 之後重新查網站，逐格比對；一致才在紀錄裡寫「完成」。
       HTTP 200 不算完成，比對一致才算。

config.yaml 的 submit.enabled 是 false 時，只印出要送的內容，不真的上傳。

用法：python -m src.submit
"""


def current_submission(cfg: dict, secrets: dict, target_date: str):
    """回傳網站上 target_date 目前有效的提交內容 {stock_id: 0 或 1}，沒有就回傳 None。"""
    raise NotImplementedError


def upload(csv_path: str, cfg: dict, secrets: dict):
    """登入後 POST 到 course_site.submissions。回傳網站的回應（不含帳密）。"""
    raise NotImplementedError


def verify(csv_path: str, cfg: dict, secrets: dict, target_date: str):
    """比對網站上的版本和 csv_path，一致回傳 True。"""
    raise NotImplementedError


def main():
    """依檔案開頭的順序執行，每一步都寫進 upload_log.jsonl。"""
    raise NotImplementedError


if __name__ == "__main__":
    main()
