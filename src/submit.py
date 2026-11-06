"""上傳：把 submission CSV 送到課程網站，再下載回來核對。Phase 1、Phase 2 都用這裡（config 的 submit.phase）。

順序（run() 照這個走，每一步都寫進 data/submission/upload_log.jsonl）：
    1. Phase 2 先檢查還沒過 competition.upload_cutoff（台北 08:50，utils.check_deadline）。
    2. 讀 /api/state：
       - Phase 2：phase2Days 沒有 t 就是休市，結束，不算失敗。t 要 enabled，現在要在 openAt 和網站的 deadline 之間。
       - Phase 1：現在要在 config.phase1OpenAt 和 phase1Deadline 之間。
       - uploadQuota 還要有剩（每隊每天 10 次；userLimit 是 0 代表沒有個人上限）。
       網站回傳的時間沒帶時區，當成 UTC。
    3. 網站上目前有效的那份先下載存到 data/submission/backup/（Phase 1 排行從所有版本取最高分，
       上傳新的不會蓋掉最高分，但留一份比較好核對）。和這份 CSV 一樣就不再送。
    4. 寫一筆「準備上傳」，呼叫 before_post（run_daily_test.py --sync 用它先 commit、push 這筆紀錄；
       push 失敗就不上傳，不然下一次在新機器上跑看不到這筆紀錄）。
    5. POST 一次。失敗或逾時不重試，改讀 /api/state 看網站有沒有收到。
    6. 拿到 200 也要把網站上的版本下載回來逐格比對，一致才寫「完成」。

submit.enabled 是 false 時只印出要送的內容，不真的上傳。

用法：python -m src.submit --phase 2 --file data/submission/submission_2026-11-09.csv --date 2026-11-09
      python -m src.submit --phase 1 --file data/submission/submission_phase1_2026-11-07.csv
"""

import argparse
import csv
import hashlib
import io
import json
import os
import socket
import sys
from pathlib import Path

from src import crawler, site_api, utils

STATUS_DONE = "done"


# ---------------------------------------------------------------- CSV


def build_rows(phase: int, header: list, stock_ids: list, values: dict) -> list:
    """照範本的表頭和代號順序排好 CSV 的列。values 是 {(日期, 代號): 0 或 1}。缺任何一格就丟錯。"""
    rows = [list(header)]
    for sid in stock_ids:
        row = [sid]
        for d in header[1:]:
            v = values.get((d, sid))
            if v not in (0, 1):
                raise ValueError(f"{sid} 在 {d} 沒有 0/1 的預測")
            row.append(int(v))
        rows.append(row)
    return rows


def rows_to_bytes(rows: list) -> bytes:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue().encode("utf-8")


def check_rows(rows: list, phase: int, header: list, stock_ids: list):
    """格式檢查，照網站前端的規則：表頭完全一樣、代號和順序和範本一樣、每格只有 0 或 1。"""
    if [str(x) for x in rows[0]] != list(header):
        raise ValueError("表頭和範本不一樣")
    if phase == 2 and len(header) != 2:
        raise ValueError("Phase 2 的表頭要是 id,<t>")
    body = rows[1:]
    if [str(r[0]) for r in body] != list(stock_ids):
        raise ValueError("股票代號或順序和範本不一樣")
    for r in body:
        if len(r) != len(header) or any(str(v) not in ("0", "1") for v in r[1:]):
            raise ValueError(f"{r[0]} 那列的格數不對或有 0/1 以外的值")


def payload(rows: list, phase: int) -> dict:
    """CSV 的列 → 網站要的 payload（和網站前端把 CSV 轉成 JSON 的做法一樣）。"""
    header, body = rows[0], rows[1:]
    ids = [str(r[0]) for r in body]
    if phase == 1:
        return {"stockIds": ids, "dates": [str(d) for d in header[1:]],
                "predictions": [[int(v) for v in r[1:]] for r in body]}
    return {"stockIds": ids, "predictions": [int(r[1]) for r in body]}


def same_cells(a: list, b: list) -> bool:
    """兩份 CSV 的列逐格一樣（值都當字串比，0/1 的整數和字串一樣）。"""
    norm = lambda rows: [[str(v).strip() for v in r] for r in rows]
    return norm(a) == norm(b)


def read_rows(path: Path) -> list:
    return site_api.read_csv_text(Path(path).read_bytes())


# ---------------------------------------------------------------- 紀錄


def log_path(cfg: dict) -> Path:
    return utils.ROOT / cfg["data"]["submission_dir"] / "upload_log.jsonl"


def runner_name() -> str:
    """紀錄裡寫哪台機器跑的。repo 是公開的，Mac 不寫主機名（裡面有使用者的名字）。"""
    return os.environ.get("RUNNER_NAME") or ("mac" if sys.platform == "darwin" else socket.gethostname())


def append_log(cfg: dict, entry: dict):
    """upload_log.jsonl 多一行。這個檔只會往後加，兩台機器同時加時 Git 用 union 合併（.gitattributes）。"""
    entry = {"time": utils.taipei_now().isoformat(timespec="seconds"), "runner": runner_name(), **entry}
    path = log_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def backup(cfg: dict, rows: list, phase: int, entry: dict) -> Path:
    """網站上目前有效的那份存到 data/submission/backup/，檔名帶上傳時間。已經存過就不再寫。"""
    stamp = site_api.parse_time(entry.get("submittedAt")).strftime("%Y%m%dT%H%M%SZ")
    key = site_api.submission_key(phase, entry.get("tradingDate"))
    path = utils.ROOT / cfg["data"]["submission_dir"] / "backup" / f"phase{phase}_{key}_{stamp}.csv"
    if not path.exists():
        crawler.write_atomic(path, rows_to_bytes(rows))
    return path


# ---------------------------------------------------------------- 上傳


def check_window(state: dict, phase: int, t: str | None, now):
    """回傳 None 表示可以上傳；不能時回傳原因（休市回傳 "closed"）。"""
    if phase == 1:
        conf = state.get("config") or {}
        start, end = site_api.parse_time(conf.get("phase1OpenAt")), site_api.parse_time(conf.get("phase1Deadline"))
        return None if start <= now < end else f"不在 Phase 1 的開放時間（{start} ～ {end}）"
    day = site_api.phase2_day(state, t)
    if day is None:
        return "closed"
    if not day.get("enabled"):
        return f"{t} 在網站上沒有開放"
    start, end = site_api.parse_time(day.get("openAt")), site_api.parse_time(day.get("deadline"))
    return None if start <= now < end else f"不在 {t} 的開放時間（{start} ～ {end}）"


def run(cfg: dict, site, phase: int, csv_path: Path, t: str | None, log, *, before_post=None, now=None) -> str:
    """照檔案開頭的順序上傳。回傳狀態：done、same、closed、dry_run；不能上傳或核對失敗就丟錯。"""
    csv_path = Path(csv_path)
    if phase == 2:
        utils.check_deadline(cfg, t, now, key="upload_cutoff")
    rows = read_rows(csv_path)
    # 網站前端在 Phase 1 不帶 tradingDate（undefined 不會出現在 JSON 裡），這裡也一樣
    body = {"phase": phase, **({"tradingDate": t} if phase == 2 else {}), "fileName": csv_path.name,
            "payload": payload(rows, phase), "note": "auto: run_daily_test.py"}
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    base = {"phase": phase, "trading_date": site_api.submission_key(phase, t), "file": csv_path.name, "sha256": digest}

    state = site.state()
    now = utils.taipei_now(now)
    problem = check_window(state, phase, t, now)
    if problem == "closed":
        log.info("%s 不在網站的交易日清單，休市，不上傳", t)
        append_log(cfg, {**base, "status": "closed"})
        return "closed"
    if problem:
        append_log(cfg, {**base, "status": "blocked", "detail": problem})
        raise site_api.SiteError(problem)
    left = site_api.quota_left(site_api.quota(state, phase, t))
    if left is not None and left <= 0:
        append_log(cfg, {**base, "status": "blocked", "detail": "今天的上傳次數用完了"})
        raise site_api.SiteError("今天的上傳次數用完了")

    current = site_api.current_entry(state, phase, t)
    if current is not None:
        site_rows = site.download(current["id"])
        saved = backup(cfg, site_rows, phase, current)
        log.info("網站上目前有效的那份（%s，分數 %s）存到 %s", current.get("submittedAt"), current.get("score"),
                 saved.relative_to(utils.ROOT))
        if same_cells(site_rows, rows):
            log.info("網站上的版本和這份一樣，不再送")
            append_log(cfg, {**base, "status": "same"})
            return "same"

    if not cfg["submit"]["enabled"]:
        log.info("submit.enabled 是 false，不上傳。會送出：phase=%s tradingDate=%s fileName=%s，%d 檔，"
                 "猜漲的比例 %.3f，還能上傳 %s 次", phase, body.get("tradingDate"), body["fileName"],
                 len(body["payload"]["stockIds"]), mean_up(body["payload"]), left)
        append_log(cfg, {**base, "status": "dry_run"})
        return "dry_run"

    append_log(cfg, {**base, "status": "prepared"})
    if before_post is not None and not before_post():
        append_log(cfg, {**base, "status": "not_sent", "detail": "準備上傳的紀錄推不上去"})
        raise RuntimeError("準備上傳的紀錄推不上去，這次不上傳（避免下一次看不到紀錄而重送）")

    before = current
    try:
        site.post_submission(body)
        log.info("上傳送出，網站回 200")
    except (crawler.TransientError, site_api.SiteError, crawler.CrawlerError) as e:
        log.error("上傳失敗：%s。不重試，改查網站有沒有收到", e)
        append_log(cfg, {**base, "status": "post_failed", "detail": str(e)})
        verify(cfg, site, phase, t, rows, before, base, log, after_error=True)
        raise
    return verify(cfg, site, phase, t, rows, before, base, log)


def verify(cfg, site, phase, t, rows, before, base, log, *, after_error=False) -> str:
    """讀 /api/state，找到新的那份，下載回來逐格比對。一致回傳 done；不一致丟錯。"""
    state = site.state()
    entry = site_api.current_entry(state, phase, t)
    is_new = entry is not None and (before is None or entry.get("id") != before.get("id")
                                    or entry.get("submittedAt") != before.get("submittedAt"))
    if not is_new:
        detail = "網站上沒有新的提交"
        append_log(cfg, {**base, "status": "not_received" if after_error else "verify_failed", "detail": detail})
        if after_error:
            log.error("%s：這次沒有送成功，要手動上傳的話先確認網站", detail)
            return "not_received"
        raise site_api.SiteError(detail)
    site_rows = site.download(entry["id"])
    if not same_cells(site_rows, rows):
        append_log(cfg, {**base, "status": "mismatch", "detail": f"網站上的版本 {entry.get('id')} 和送出的不一樣"})
        raise site_api.SiteError("網站上的版本和送出的不一樣")
    append_log(cfg, {**base, "status": STATUS_DONE, "site_id": str(entry.get("id")),
                     "submitted_at": entry.get("submittedAt"), "score": entry.get("score")})
    log.info("核對完成：網站上的版本 %s 和送出的逐格一樣（上傳時間 %s，分數 %s）", entry.get("id"),
             entry.get("submittedAt"), entry.get("score"))
    return STATUS_DONE


def mean_up(p: dict) -> float:
    preds = p["predictions"]
    flat = [v for row in preds for v in row] if preds and isinstance(preds[0], list) else list(preds)
    return sum(flat) / len(flat) if flat else 0.0


def main(argv=None) -> int:
    """手動上傳一份已經做好的 CSV（照範本檢查格式後送出）。"""
    parser = argparse.ArgumentParser(description="上傳 submission CSV 到課程網站，再下載回來核對")
    parser.add_argument("--phase", type=int, choices=(1, 2), required=True)
    parser.add_argument("--file", required=True, help="要上傳的 CSV")
    parser.add_argument("--date", help="Phase 2 的預測日 t（YYYY-MM-DD）")
    args = parser.parse_args(argv)
    if args.phase == 2 and not crawler.is_iso_date(args.date or ""):
        parser.error("Phase 2 要給 --date YYYY-MM-DD")
    cfg = utils.load_config()
    key = args.date if args.phase == 2 else utils.taipei_now().date().isoformat()
    log = utils.get_logger("submit", key)
    site = site_api.Site(cfg, utils.load_secrets())
    try:
        header, ids = site.template(args.phase, args.date)
        check_rows(read_rows(Path(args.file)), args.phase, header, ids)
        status = run(cfg, site, args.phase, Path(args.file), args.date if args.phase == 2 else None, log)
    finally:
        site.close()
    log.info("上傳：%s", status)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
