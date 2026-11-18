"""傍晚打分（使用者 2026-11-17）：t 收盤、老師 Live 填好 t 那列以後，當天就替影子跑和網站上我們那份打分。

排程：oop 台北 18:00 跑一次，沒打完時 20:00 再試（deploy/crontab.txt 的 run_daily.py --sync --evening）。
    1. 讀網站的 /api/state（只讀，不上傳）。t 不在交易日清單就結束；傍晚已經打完分（site_scores.csv 有 t 那列和
       網站的分數，影子跑也打過分）也結束。
    2. 下載老師的 Live（不抓 yfinance 和其他來源）。要打分的每一檔（shadow_<t>.csv 和網站上那份的股票）都有填好的
       t 那列，才寫進 data/raw/teacher/live/，組員傍晚就拿得到；有一檔沒填好就什麼都不寫，等下一次。
    3. 答案是 Live t 那列的還原收盤 ÷ 還原開盤 − 1，和網站、特徵表的 label_intraday_return 同一條算法
       （step2_features 用的 crawler.row_filled、COL_CLOSE、COL_OPEN）。shadow_<t>.csv 的每個模型打分，
       更新 shadow_scores.csv（source 是 live；step3_train_predict.shadow_scores）。
    4. 網站上我們那份的分數、當天名次、累計分數和名次寫進 site_scores.csv，一天一列。同一份答案也重算網站上那份，
       和網站的分數差超過 1e-6 時記 WARNING（網站的分數可能四捨五入過）。我們這隊用 /api/state 的 team.id 對榜上的
       teamId，只存我們的分數、名次和隊數，不存任何隊名、帳號；檔名只存排程的 submission_<t>.csv，其他寫 other。
不上傳、不重建特徵表、不改爬蟲的 run 紀錄（data/raw/manifest.json 只更新 teacher_live 那一段的指紋）。

    main(cfg, phase, t, log)   → 這次的狀態：closed、done_before、nothing_to_score、no_answer_yet、
                                 scored（都打完了）、scored_waiting_site（網站還沒給分數，下一次再試）
"""

import json
import math

import pandas as pd

from src.pipeline import site_api, step1_crawler as crawler, step3_train_predict as train_predict, utils

SITE_SCORES = "site_scores.csv"
SITE_COLUMNS = ["date", "file", "same_as", "site_score", "rescored", "all_zero", "day_rank", "day_teams",
                "total_score", "total_rank", "teams", "all_forced_teams", "self_rank", "read_at"]
SITE_TOLERANCE = 1e-6   # 網站給的分數和用 Live 重算的差多少算不一樣（網站的分數可能四捨五入過）
INT_COLUMNS = ["day_rank", "day_teams", "total_rank", "teams", "all_forced_teams", "self_rank"]


class EveningError(RuntimeError):
    """這次打不了分。訊息是自己寫的短句。"""


def main(cfg: dict, phase: int, t: str, log, *, site=None, secrets=None) -> str:
    """第 1～4 步，回傳狀態（見檔頭）。site、secrets 給測試用；沒給時自己登入、用完關掉。"""
    if phase != 2:
        log.info("傍晚打分只做 Phase 2，這次不做")
        return "not_phase2"
    secrets = utils.load_secrets() if secrets is None else secrets
    own = site is None
    site = site_api.Site(cfg, secrets) if own else site
    try:
        state = site.state()
        if site_api.day_status(state, t) == "closed":
            log.info("%s 不在網站的交易日清單：不打分", t)
            return "closed"
        if scored_before(cfg, t):
            log.info("傍晚已經打過 %s 的分數，不重做", t)
            return "done_before"
        entry = site_api.current_entry(state, 2, t)
        sent = submitted(site, entry, t, log)
        shadow = read_shadow(cfg, t)
        stocks = sorted((set(shadow["stock_id"]) if shadow is not None else set()) | set(sent or {}))
        if not stocks:
            log.warning("%s 沒有影子跑，網站上也沒有我們的提交：沒有東西可以打分", t)
            return "nothing_to_score"
        truth = live_answers(cfg, t, stocks, secrets, log)
        if truth is None:
            return "no_answer_yet"
        if shadow is not None:
            train_predict.shadow_scores(cfg, truth, log, source="live")
        record = site_record(state, t, entry, sent, truth, shadow, stocks, log)
        write_site_scores(cfg, record)
        log.info("%s 傍晚打分：全猜 0 %s；網站上我們 %s（%s，和 %s 一樣）；當天第 %s／%s 名；累計 %s，第 %s／%s 名"
                 "（全部強制繳交的 %s 隊以外第 %s 名）", t, signed(record["all_zero"]), signed(record["site_score"]),
                 record["file"] or "沒有提交", record["same_as"] or "影子跑的哪個模型都不", record["day_rank"],
                 record["day_teams"],
                 signed(record["total_score"]), record["total_rank"], record["teams"], record["all_forced_teams"],
                 record["self_rank"])
        return "scored" if record["site_score"] is not None else "scored_waiting_site"
    finally:
        if own:
            site.close()


# ---------------------------------------------------------------- 讀本機的檔


def folder(cfg: dict):
    return utils.ROOT / cfg["data"]["submission_dir"]


def read_shadow(cfg: dict, t: str):
    """shadow_<t>.csv；沒有回傳 None（那天的影子跑沒做成，只打網站上那份）。"""
    path = train_predict.shadow_path(cfg, t)
    if not path.exists():
        return None
    return pd.read_csv(path, dtype={"date": str, "stock_id": str})


def scored_before(cfg: dict, t: str) -> bool:
    """傍晚已經打完 t：site_scores.csv 有 t 那列和網站的分數，shadow_<t>.csv 有的話 shadow_scores.csv 也有 t 的 live 列。"""
    try:
        table = pd.read_csv(folder(cfg) / SITE_SCORES, dtype={"date": str})
    except (OSError, ValueError):
        return False
    row = table[table["date"] == t] if "date" in table.columns else table.iloc[0:0]
    if row.empty or "site_score" not in row or row["site_score"].isna().all():
        return False
    if not train_predict.shadow_path(cfg, t).exists():
        return True
    ledger = train_predict.read_ledger(folder(cfg) / train_predict.SHADOW_SCORES)
    return any(day == t and r.get("source") == "live" for (day, _), r in ledger.items())


def write_site_scores(cfg: dict, record: dict) -> None:
    """site_scores.csv 換掉 t 那列（沒有就加），照日期排。"""
    path = folder(cfg) / SITE_SCORES
    try:
        old = pd.read_csv(path, dtype={"date": str})
        old = old[old["date"] != record["date"]] if "date" in old.columns else old.iloc[0:0]
    except (OSError, ValueError):
        old = pd.DataFrame(columns=SITE_COLUMNS)
    table = pd.concat([old.reindex(columns=SITE_COLUMNS), pd.DataFrame([record], columns=SITE_COLUMNS)])
    table = table.sort_values("date", kind="stable")
    for column in INT_COLUMNS:   # 有一列空白時 pandas 讀回來是 float，寫回去照樣寫整數
        table[column] = pd.to_numeric(table[column], errors="coerce").round().astype("Int64")
    crawler.write_atomic(path, table.to_csv(index=False).encode("utf-8"))


# ---------------------------------------------------------------- 老師 Live


def live_answers(cfg: dict, t: str, stocks: list, secrets: dict, log):
    """下載老師 Live（原本的網址優先，出錯才用備用網址；和爬蟲同一套）。stocks 每一檔都有填好的 t 那列時，
    寫進 data/raw/teacher/live/，回傳答案表（date、stock_id、label_y、label_intraday_return，Live 裡 t 那天填好的每一檔）。
    還沒填好或下載失敗時什麼都不寫、回傳 None，記 WARNING（下一次排程再試）。"""
    key = secrets.get("COURSE_LIVE_KEY")
    if not key:
        raise EveningError("沒有 COURSE_LIVE_KEY，抓不了老師的 Live")
    raw_dir = utils.ROOT / cfg["data"]["raw_dir"]
    conf = cfg["course_site"]
    stock_ids = crawler.read_info((raw_dir / "teacher" / "training" / "info.json").read_bytes())["Top100@Y"]
    run = crawler.Run(cfg, t, False, raw_dir, log)
    try:
        used, blob, files, parsed, _ = crawler.live_fetch(run, crawler.live_clients(cfg), key, stock_ids,
                                                          conf["max_zip_mb"] * 2**20, conf["max_unzipped_mb"] * 2**20)
    except crawler.CrawlerError as e:
        log.warning("老師 Live 下載失敗（%s）：這次不打分，下一次排程再試", e)
        return None
    rows = crawler.stock_rows(parsed)
    missing = [s for s in stocks if not crawler.row_filled(rows.get(s, {}).get(t))]
    if missing:
        log.warning("老師 Live 的 %s 還有 %d 檔沒填好（%s）：這次什麼都不寫，下一次排程再試", t, len(missing), missing[:5])
        return None
    crawler.replace_dir(raw_dir / "teacher" / "live", files)
    note_live(cfg, raw_dir, used, blob, files, rows, t)
    filled = sorted(s for s, by_day in rows.items() if crawler.row_filled(by_day.get(t)))
    cells = [rows[s][t] for s in filled]
    log.info("老師 Live 的 %s 那列填好了（%d 檔），寫進 data/raw/teacher/live/", t, len(filled))
    return pd.DataFrame({
        "date": pd.to_datetime([t] * len(filled)), "stock_id": filled,
        "label_y": [int(crawler.to_float(c[crawler.COL_Y])) for c in cells],
        "label_intraday_return": [crawler.to_float(c[crawler.COL_CLOSE]) / crawler.to_float(c[crawler.COL_OPEN]) - 1
                                  for c in cells]})


def note_live(cfg: dict, raw_dir, used, blob: bytes, files: dict, rows: dict, t: str) -> None:
    """data/raw/manifest.json 的 teacher_live 換成傍晚這份的指紋和最後一天，加 evening_refresh（哪天、幾點、從哪個入口）。
    manifest 的其他段（包含爬蟲的 run）不動，所以補爬的判斷（run_daily.crawled）不受影響。"""
    path = raw_dir / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    if not isinstance(manifest, dict):
        manifest = {}
    entry = manifest.get("teacher_live") if isinstance(manifest.get("teacher_live"), dict) else {}
    entry.update({"zip_sha256": crawler.sha256_bytes(blob), "files_sha256": crawler.files_digest(files),
                  "date_max": max(d for by_day in rows.values() for d in by_day),
                  "evening_refresh": {"t": t, "time": utils.taipei_now().strftime("%Y-%m-%d %H:%M"),
                                      "source": crawler.live_host(used) + cfg["course_site"]["live"]["zip"]}})
    manifest["teacher_live"] = entry
    crawler.write_atomic(path, (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())


# ---------------------------------------------------------------- 網站上我們那份和排行榜


def submitted(site, entry, t: str, log):
    """下載網站上我們那份，轉成 {代號: 0／1}。沒有提交、下載失敗或格式不對回傳 None（只是不重算它，影子跑照樣打分）。"""
    if not entry:
        return None
    try:
        rows = site.download(entry["id"])
    except Exception as e:
        log.warning("下載網站上我們那份失敗（%s），不重算它的分數", train_predict.short_reason(e))
        return None
    return submitted_preds(rows, t, log)


def submitted_preds(rows: list, t: str, log):
    """網站上那份提交的 CSV 列 → {代號: 0／1}。表頭不是 id,t 或有格不是 0／1 時記 WARNING、回傳 None（只是不重算）。"""
    if not rows or rows[0] != ["id", t] or any(len(r) != 2 or r[1] not in ("0", "1") for r in rows[1:]):
        log.warning("網站上那份提交的格式和預期不一樣，不重算它的分數")
        return None
    return {r[0]: int(r[1]) for r in rows[1:]}


def site_record(state: dict, t: str, entry, sent, truth, shadow, stocks: list, log) -> dict:
    """site_scores.csv 的一列（欄見 SITE_COLUMNS）。拿不到的格留空。
    same_as：網站上那份和 shadow_<t>.csv 的哪些模型 50 檔都一樣（用 / 隔開）。
    day_rank：當天的分數比我們高的隊數 + 1。total_rank：網站給的累計名次。
    all_forced_teams：每天都是網站強制繳交（自己沒交過）的隊數；self_rank：扣掉這些隊以後我們的累計名次。"""
    r = truth.set_index("stock_id")["label_intraday_return"].reindex(stocks)
    record = dict.fromkeys(SITE_COLUMNS)
    record.update(date=t, all_zero=float(-r.mean()), read_at=utils.taipei_now().strftime("%Y-%m-%d %H:%M"))
    if entry:
        name = entry.get("fileName")
        record.update(file=name if name == f"submission_{t}.csv" else "other", site_score=number(entry.get("score")))
    if sent and set(sent) == set(stocks):
        p = pd.Series(sent).reindex(stocks)
        record["rescored"] = float(((2 * p - 1) * r).mean())
        record["same_as"] = same_models(shadow, sent)
    if record["site_score"] is not None and record["rescored"] is not None \
            and abs(record["site_score"] - record["rescored"]) > SITE_TOLERANCE:
        log.warning("網站給我們 %s 的分數 %+.6f，用老師 Live 重算是 %+.6f，不一樣：答案的算法可能和網站不同",
                    t, record["site_score"], record["rescored"])
    team = (state.get("team") or {}).get("id")   # 沒有時對不到任何一隊，名次留空（不會把別隊當成我們）
    day = board_rows((state.get("phase2Leaderboards") or {}).get(t))
    ours = next((row for row in day if team is not None and row.get("teamId") == team), None)
    scores = [number(row.get("score")) for row in day]
    scores = [s for s in scores if s is not None]
    if ours is not None and number(ours.get("score")) is not None:
        mine = number(ours.get("score"))
        record.update(day_rank=1 + sum(s > mine + 1e-12 for s in scores), day_teams=len(scores))
    total = board_rows(state.get("phase2CompetitionCumulative"))
    ours = next((row for row in total if team is not None and row.get("teamId") == team), None)
    forced = [row for row in total if all_forced(row)]
    record.update(teams=len(total) or None, all_forced_teams=len(forced) if total else None)
    if ours is not None and number(ours.get("totalScore")) is not None:
        mine = number(ours.get("totalScore"))
        others = [number(row.get("totalScore")) for row in total if row is not ours and not all_forced(row)]
        record.update(total_score=mine, total_rank=ours.get("totalRank"),
                      self_rank=1 + sum(s is not None and s > mine + 1e-12 for s in others))
    return record


def board_rows(board) -> list:
    """排行榜（list，或帶 rows 的 dict）→ 每隊一個 dict 的 list。"""
    rows = board if isinstance(board, list) else (board or {}).get("rows") if isinstance(board, dict) else None
    return [row for row in rows or [] if isinstance(row, dict)]


def all_forced(row: dict) -> bool:
    """這隊有分數的每一天都是網站強制繳交（全猜 0），自己沒交過。"""
    days, forced = number(row.get("scoredDays")), number(row.get("forcedSubmissionDays"))
    return days is not None and forced is not None and days > 0 and forced >= days


def same_models(shadow, sent: dict):
    if shadow is None:
        return None
    table = shadow.set_index("stock_id")
    names = []
    for column in [c for c in table.columns if c.startswith("pred_")]:
        pred = table[column].reindex(list(sent))
        if pred.notna().all() and (pred.astype(int) == pd.Series(sent)).all():
            names.append(column[len("pred_"):])
    return "/".join(names) or None


def number(value):
    """有限的數字轉成 float，其他（None、字串、NaN）回傳 None。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def signed(value) -> str:
    return "（沒有）" if value is None else f"{value:+.5f}"
