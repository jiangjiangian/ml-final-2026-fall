"""每天自動跑一次：爬蟲 → 特徵 → 訓練和預測 → 上傳 → 推資料。排程和手動補交都用這支。

流程（第 1～5 步在 src/pipeline/ 各有一個檔）：
    0. 同步（只在 --sync）：git pull；這支檔案被更新就用新版重新執行。pull 完才載入 src/。
    1. 看網站（check_site）：休市就結束；已經交過、上次送出還沒核對完就不上傳。
       不上傳的這幾種（休市除外）和網站讀不到時，t 當天還沒爬過就先補爬（ensure_crawled），資料照推。
    2. 爬蟲和特徵（crawl_and_build_features → step1_crawler、step2_features）：t 是今天的交易日才跑。
    3. 訓練和預測（step3_train_predict）：照 config 的 daily_model 選模型，預測 t 的 50 檔，失敗照順序換備援。
    4. 上傳（write_submission、step4_submit）：寫 submission_<t>.csv，先推上 GitHub 再 POST，最後核對網站上的檔。
       影子跑（shadow_run）：上傳之後，config 的 daily_model.shadow 列的模型都算一遍，存 shadow_<t>.csv，不上傳。
       組員已經手動交了的日子也做（用第 1 步補爬的特徵表），一天只做一次。
    5. 收尾（wrap_up）：08:25 那次補日韓當天的開盤（只進長表）、step5_merge_raw 合併原始資料、推 data/。

排程（memory/context/02-pipeline.md）：學校的 oop 台北 07:10、07:25、07:40、07:55、08:05、08:25（deploy/crontab.txt）。
網站上已經有 t 的提交就不上傳（t 還沒爬過時照樣補爬、推資料），所以排很多次也不會重複上傳。
之前的執行已經送出（upload_log 有「準備上傳」）卻沒有核對完成時，不再自動重送，留給人確認。

用法：
    python run_daily.py              交 config 的 submit.phase；t 是台北今天
    python run_daily.py --phase 2    指定 Phase；--date 2026-11-09 指定 t（不是今天時不跑爬蟲和特徵）
    python run_daily.py --sync       排程用：開始前 git pull，上傳前先推資料和「準備上傳」紀錄，結束後推 data/
    python run_daily.py --dry-run    不上傳，只印出要送的內容

Phase 1（測自動化用）：預測網站範本的 84 天（2026-06-01～09-30）× 50 檔。今天（台北）已經交過 Phase 1 就結束。
Phase 2：預測 t 的 50 檔。網站上 t 已經有提交（不算「強制繳交」）就不上傳。
t 不是交易日（不在網站的 phase2Days）：Phase 2 直接結束；Phase 1 不跑爬蟲和特徵，用現有的特徵表。
舊名字 run_daily_test.py（2026-11-15 前的排程用它）只是轉到這支。
"""

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
BRANCH = "claude/stock-market-challenger"   # 只推這個分支（CLAUDE.md）
DATA_PATHS = ("data/raw", "data/processed", "data/submission", "data/merged")   # 排程會 commit 的資料夾
UPLOAD_LOG = "data/submission/upload_log.jsonl"   # 和 config 的 data.submission_dir 一致；git_start 在讀 config 前用
LOCK_PATH = ROOT / ".cache" / "run_daily_test.lock"   # 檔名沿用舊的：交接那一次，舊版和新版還是互相擋住
REEXEC_FLAG = "RUN_DAILY_REEXEC"
ENTRY_VAR = "RUN_DAILY_ENTRY"   # 舊名字 run_daily_test.py 轉過來時，它的路徑（重新執行時從它開始）
PUSH_ATTEMPTS, PUSH_WAIT = 2, 15   # oop 連 GitHub 偶爾失敗（2026-11-07 看到一次），推送失敗等 15 秒再試一次

# src/ 的模組在 git pull 之後才載入（import_src），之前都是 None
crawler = features = train_predict = submit = merge_raw = site_api = utils = None


class StopRun(RuntimeError):
    """不能繼續。訊息是自己寫的短句。"""


def import_src():
    """git pull 之後才載入 src/：推上去的修正這次就用到；新程式 import 失敗時，修正推上去後下一次還是會先 pull。"""
    global crawler, features, train_predict, submit, merge_raw, site_api, utils
    from src.pipeline import (site_api, step1_crawler as crawler, step2_features as features,  # noqa: F811
                              step3_train_predict as train_predict, step4_submit as submit,
                              step5_merge_raw as merge_raw, utils)


# ================================================================ 整次執行


def main(argv=None) -> int:
    """讀參數、拿鎖（同一台同時只跑一個），再交給 run。回傳 exit code。"""
    args = parse_args(argv)
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_PATH, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("另一個 run_daily.py 還在跑，這次不跑")
            return 0
        return run(args, from_command_line=argv is None)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="每天自動跑一次：爬蟲 → 特徵 → 訓練和預測 → 上傳 → 推資料")
    parser.add_argument("--phase", type=int, choices=(1, 2), help="不給就用 config 的 submit.phase")
    parser.add_argument("--date", help="預測日 t（YYYY-MM-DD）；不給就是台北今天")
    parser.add_argument("--sync", action="store_true", help="git pull、push（排程用的專用 clone 才加）")
    parser.add_argument("--dry-run", action="store_true", help="不上傳，只印出要送的內容")
    args = parser.parse_args(argv)
    if args.date:
        try:
            date.fromisoformat(args.date)
        except ValueError:
            parser.error("--date 要是 YYYY-MM-DD")
    return args


def run(args, from_command_line: bool = True) -> int:
    """第 0～5 步。回傳 0（照預期結束，包含休市和已經交過）或 1（有問題要人看，寫在 data/submission/run_<t>.log）。"""
    notes, sync_error, branch_ok = [], None, False
    if args.sync:
        branch_ok = on_branch()
        notes, sync_error = sync_with_github(from_command_line)   # 第 0 步；這支被更新時不會回來
    try:
        import_src()
    except Exception as e:   # 寫到 cron.log；下一次會先 pull，修正推上去就好了
        print(f"載入 src/ 失敗：{type(e).__name__}: {str(e)[:300]}", flush=True)
        return 1

    today = utils.taipei_now().date().isoformat()
    t = args.date or today
    log = utils.get_logger("run_daily", t)   # 檔名用 t（Phase 1 時 t 就是今天）
    status, code, phase, interrupted = "failed", 1, args.phase, False
    try:
        if sync_error is not None:
            raise sync_error
        cfg = utils.load_config()   # pull 之後才讀，推上去的 config（例如 submit.phase、daily_model）這次就生效
        phase = args.phase or cfg["submit"]["phase"]
        log.info("開始：Phase %s，t = %s%s%s（執行代號 %s）", phase, t, "，--sync" if args.sync else "",
                 "，--dry-run" if args.dry_run else "", submit.RUN_ID)
        for note in notes + [n for n in [requirements_note()] if n]:
            log.warning(note)
        if args.dry_run:
            cfg["submit"]["enabled"] = False
        status = submit_today(cfg, phase, t, today, log, sync=args.sync)
        code = 0
    except BaseException as e:
        log.error("停下：%s", describe(e))
        if not isinstance(e, Exception):   # Ctrl-C 之類：收尾只推資料，再往上丟
            interrupted = True
            raise
    finally:
        log.info("結束：%s", status)
        if not wrap_up(args, t, today, phase, status, interrupted, branch_ok, log):
            code = code or 1
    return code


def submit_today(cfg: dict, phase: int, t: str, today: str, log, *, sync: bool) -> str:
    """第 1～4 步和影子跑。回傳狀態：closed、already_submitted，或 step4_submit.run 的結果（done、not_sent 等）。
    影子跑不改回傳的狀態。"""
    key = site_api.submission_key(phase, t)
    site = site_api.Site(cfg, utils.load_secrets())
    try:
        try:
            state = site.state()
        except Exception:
            # 網站讀不到（登入後的 /api/state）：不上傳，照樣試爬。爬蟲會再讀一次 /api/state，還是讀不到時，
            # 要上次存的 phase2_days.json 有 t 才繼續；早上存的清單通常只到前一個交易日，所以多半停下、只記 WARNING
            ensure_crawled(cfg, phase, t, today, True, log)
            raise
        trading = site_api.day_status(state, t) != "closed"
        try:
            status = check_site(cfg, state, phase, t, today, key, log)                 # 第 1 步
        except StopRun:
            ensure_crawled(cfg, phase, t, today, trading, log)   # 上次送出還沒核對完：不重送，資料照爬
            raise
        if status == "already_submitted":
            ensure_crawled(cfg, phase, t, today, trading, log)   # 已經交過（組員先交或這台交好了）：沒爬過才爬
            shadow_run(cfg, phase, t, today, log, site=site)                            # 影子跑
        if status is not None:
            return status
        crawl_and_build_features(phase, t, today, trading, log)                        # 第 2 步：要交件，每次都爬
        if phase == 2:
            utils.check_deadline(cfg, t, key="deadline")
        data = timed(log, "讀特徵", lambda: train_predict.load_model_input(cfg))      # 第 3 步
        header, stocks, dates = read_template(site, phase, t, data)
        model_name, pred = timed(log, "模型", lambda: train_predict.train_and_predict(cfg, data, dates, stocks, log))
        if phase == 2:
            train_predict.log_direction(pred, model_name, log)
        else:
            log.info("Phase 1 本機分數：%s", train_predict.phase1_score(pred, data))
        path = write_submission(cfg, phase, t, today, header, stocks, dates, pred, model_name, log)  # 第 4 步
        if phase == 2:
            train_predict.save_scores(cfg, pred, t, model_name, log)

        def before_post():   # POST 前先把資料和「準備上傳」紀錄推上 GitHub，別台排程看得到
            commit_data(f"Daily run {key}: data and prepared upload")
            return push(log)

        result = submit.run(cfg, site, phase, path, t if phase == 2 else None, log,
                            before_post=before_post if sync else None, respect_existing=True)
        shadow_run(cfg, phase, t, today, log, data=data, stocks=stocks, known={train_predict.kind_of(model_name): pred})
        return result
    finally:
        site.close()


# ================================================================ 第 1～5 步


def check_site(cfg: dict, state: dict, phase: int, t: str, today: str, key: str, log) -> str | None:
    """第 1 步：看網站的狀態和本機的上傳紀錄，決定這次要不要做。

    回傳 None 代表要做；closed（休市）代表結束；already_submitted（已經交過）代表不上傳（submit_today 還會補爬）。
    上次已經送出卻沒有核對完成時丟 StopRun：不自動重送，留給人到網站確認。
    """
    day = site_api.day_status(state, t)   # 休市看網站的 phase2Days，不看星期幾或寫死的日曆
    if phase == 2 and day == "closed":
        log.info("%s 不在網站的交易日清單，休市：不爬、不上傳，結束", t)
        return "closed"
    if day == "not_open":
        log.warning("%s 在網站的清單上但還沒開放（enabled = 0）：照常準備，上傳前再看一次", t)
    entry = submit.existing(state, phase, t, today)
    if entry is not None:
        log.info("網站上已經有這次的提交（%s，%s 交），不上傳", entry.get("fileName"), entry.get("submittedAt"))
        return "already_submitted"
    done = submit.finished_today(cfg, phase, key, today)
    if done is not None:
        log.info("上傳紀錄說已經%s（%s），不上傳", "交好" if done["status"] == "done" else "和網站一樣", done.get("time"))
        return "already_submitted"
    pending = submit.open_prepared(cfg, phase, key, today)
    if pending is not None:
        raise StopRun(f"{pending.get('time')} {pending.get('runner')} 已經送過 {pending.get('file')} 但沒有核對完成；"
                      "不自動重送，請到網站確認後手動處理")
    return None


def ensure_crawled(cfg: dict, phase: int, t: str, today: str, trading: bool, log) -> None:
    """t 當天還沒爬過就爬（使用者 2026-11-17）：組員先交了、這台已經交好、上次送出還沒核對完、網站讀不到時，
    這次不上傳，資料照樣爬、照樣推上 GitHub（wrap_up）。要交件的那條路不經過這裡，每次排程都爬。

    只在 Phase 2、t 是今天、網站沒說休市時做。爬過的定義見 crawled()；爬過就不重爬，推上去的資料和
    交件、影子跑用的一樣。失敗時這裡只記一行 WARNING（這次本來就不上傳），下一次排程看到還沒爬過會再試；
    log 裡會多一行爬蟲自己的 ERROR「爬蟲停下」，不影響這次的結果。
    """
    try:
        if phase != 2 or t != today or not trading:
            return
        if crawled(cfg, t):
            log.info("%s 的資料之前已經爬過，不重爬", t)
            return
        log.info("這次不上傳，%s 還沒爬過：先補爬", t)
        crawl_and_build_features(phase, t, today, trading, log)
    except Exception as e:
        log.warning("補爬沒做完（%s）：這次本來就不上傳；下一次排程會再試", describe(e))


def crawled(cfg: dict, t: str) -> bool:
    """data/raw/manifest.json 的 run 是 t、狀態 ok 或 stale（有序列沿用舊檔也算），
    而且 data/processed/manifest.json 的 last_date 是 t。爬到一半停下（running、failed）不算。"""
    try:
        run = json_field(ROOT / cfg["data"]["raw_dir"] / "manifest.json", "run") or {}
        last = json_field(ROOT / cfg["data"]["processed_dir"] / "manifest.json", "last_date")
        return run.get("target_date") == t and run.get("status") in ("ok", "stale") and last == t
    except (OSError, ValueError, AttributeError):
        return False


def crawl_and_build_features(phase: int, t: str, today: str, trading: bool, log) -> None:
    """第 2 步：step1_crawler 抓到 data/raw/，step2_features 重寫 data/processed/。

    只在 t 是今天、而且是交易日時跑。Phase 2 失敗就往上丟（整次停下）；Phase 1 用現有的特徵表繼續。
    """
    if not (trading and t == today):
        log.info("%s 不跑爬蟲和特徵（%s），用現有的特徵表", t, "休市" if not trading else "t 不是今天")
        return
    try:
        code = timed(log, "爬蟲", lambda: crawler.main(["--date", t]))
        if code == 3:
            log.warning("爬蟲有序列沿用舊檔（見 data/raw/manifest.json），繼續")
        timed(log, "特徵", lambda: features.main(["--date", t]))
    except Exception as e:
        if phase == 2:
            raise
        log.warning("爬蟲或特徵失敗（%s），Phase 1 用現有的特徵表繼續", describe(e))


def read_template(site, phase: int, t: str, data) -> tuple:
    """網站的提交範本 → （表頭, 股票代號, 要預測的日子）。範本和特徵表對不上就丟 StopRun。"""
    if phase == 1:
        header, stocks = site.template(1)
        dates = header[1:]
        phase1_dates_ok(dates, data)
        return header, stocks, dates
    header, stocks = site.template(2, t)
    if header != ["id", t]:
        raise StopRun(f"Phase 2 範本的表頭不是 id,{t}")
    if not (data["date"].dt.strftime("%Y-%m-%d") == t).any():
        raise StopRun(f"特徵表沒有 {t} 的列（Live 還沒更新？）")
    return header, stocks, [t]


def phase1_dates_ok(dates: list, data) -> None:
    """Phase 1 範本的 84 天要和特徵表在那段期間有答案的交易日一樣。"""
    have = data.loc[data["label_y"].notna(), "date"].dt.strftime("%Y-%m-%d")
    have = sorted(d for d in set(have) if dates[0] <= d <= dates[-1])
    if have != list(dates):
        extra, lost = sorted(set(have) - set(dates)), sorted(set(dates) - set(have))
        raise StopRun(f"Phase 1 範本的日子和交易日曆不一樣：範本多 {lost[:5]}，日曆多 {extra[:5]}")


def write_submission(cfg: dict, phase: int, t: str, today: str, header: list, stocks: list, dates: list, pred,
                     model_name: str, log) -> Path:
    """第 4 步前半：預測表 → 網站格式的 CSV（step4_submit 檢查格式），寫到 data/submission/，回傳路徑。"""
    values = {(r.date, r.stock_id): int(r.pred) for r in pred.itertuples()}
    rows = submit.build_rows(phase, header, stocks, values)
    submit.check_rows(rows, phase, header, stocks)
    name = f"submission_{t}.csv" if phase == 2 else f"submission_phase1_{today}.csv"
    path = ROOT / cfg["data"]["submission_dir"] / name
    crawler.write_atomic(path, submit.rows_to_bytes(rows))
    log.info("寫好 %s：%d 檔 × %d 天，模型 %s，猜漲 %.3f", path.relative_to(ROOT), len(stocks), len(dates), model_name,
             pred["pred"].mean())
    return path


def wrap_up(args, t: str, today: str, phase, status: str, interrupted: bool, branch_ok: bool, log) -> bool:
    """第 5 步，前面成功或失敗都做。休市日和被中斷時只推資料。回傳資料有沒有推上去（沒有 --sync 時是 True）。"""
    if args.sync and not interrupted and status != "closed":
        fill_today_open(t, today, log)   # 只在排程的 clone 做
    if not interrupted and status != "closed":
        merge_raw_data(log)
    if not (args.sync and branch_ok):
        return True
    try:
        commit_data(f"Daily run {t} (Phase {phase}): {status}")
        if push(log):
            return True
        log.error("資料推不上去，下次執行會再推")
    except Exception as e:
        log.error("推資料失敗：%s", describe(e))
    return False


def shadow_run(cfg: dict, phase: int, t: str, today: str, log, *, site=None, data=None, stocks=None,
               known=None) -> None:
    """影子跑（使用者 2026-11-16）：config 的 daily_model.shadow 列的模型都預測 t，存 data/submission/shadow_<t>.csv，
    不上傳；再把以前每天的影子跑對上答案，重寫 shadow_scores.csv（step3_train_predict 的 shadow_predict、shadow_scores）。

    交件的那次在上傳之後做，用交件那次的特徵表和預測（data、stocks、known）。組員已經手動交了的日子
    （check_site 回 already_submitted）沒有這些：submit_today 先用 ensure_crawled 補爬，這裡讀特徵表、讀範本（給 site）。
    只在 Phase 2、t 當天的截止時間（09:00）前、shadow_<t>.csv 還沒有時做，所以一天六次排程只做一次；
    截止後不做，因為之後的資料可能被改過（例如老師的 WTI、黃金在 07:10 之後還會更新）。
    任何錯誤只記一行 WARNING，不改這次執行的結果，也不會上傳任何東西。
    """
    try:
        if phase != 2 or not train_predict.shadow_models(cfg):
            return
        path = train_predict.shadow_path(cfg, t)
        if path.exists():
            log.info("影子跑：%s 已經有了，不重算", train_predict.shown(path))
            return
        try:
            utils.check_deadline(cfg, t, key="deadline")
        except RuntimeError:
            log.info("影子跑：已經過了 %s 的截止時間，不做", t)
            return
        if data is None:
            data = timed(log, "讀特徵", lambda: train_predict.load_model_input(cfg))
            _, stocks, _ = read_template(site, phase, t, data)
        timed(log, "影子跑", lambda: train_predict.shadow_predict(cfg, data, t, stocks, log, known=known))
        train_predict.shadow_scores(cfg, data, log)
    except Exception as e:
        log.warning("影子跑沒做完（%s）：不影響上傳；shadow_<t>.csv 沒寫成時下一次排程會再試", describe(e))


def fill_today_open(t: str, today: str, log) -> None:
    """日韓當天的開盤（使用者 2026-11-11，只進長表）：台北 08:22 以後（排程 08:25）從 Yahoo 抓，抓到新的就重寫
    特徵表，t 那列的 kospi_open_gap、n225_open_gap 才有值。特徵表的最後一天不是 t（今天沒跑成）就不抓。
    模型和上傳不看這兩欄。任何錯誤只記 log，不改這次執行的結果。"""
    try:
        if t != today:
            return
        cfg = utils.load_config()
        manifest = ROOT / cfg["data"]["processed_dir"] / "manifest.json"
        if json_field(manifest, "last_date") != t:
            return
        if crawler.open_today(cfg, t, log)["written"]:
            timed(log, "特徵（補上當天開盤）", lambda: features.main(["--date", t]))
    except Exception as e:
        log.warning("當天開盤那一步沒做完（%s）：只影響長表的 open_gap 兩欄", describe(e))


def merge_raw_data(log) -> None:
    """step5_merge_raw：data/raw/ 合併成 data/merged/ 的兩張表（使用者 2026-11-11，給組員研究，模型和上傳不看）。
    在上傳之後、推資料之前跑，不拖慢上傳。來源檔沒變就跳過（約 0.3 秒），有變約 20 秒。任何錯誤只記 log。"""
    try:
        timed(log, "合併原始資料", lambda: merge_raw.main([]))
    except Exception as e:
        log.warning("合併原始資料沒做完（%s）：只影響 data/merged/，下次執行會再做", describe(e))


# ================================================================ 第 0 步：和 GitHub 同步（只用標準函式庫）


def sync_with_github(from_command_line: bool) -> tuple:
    """git pull（git_start）。回傳（要寫進 log 的提醒, 同步的錯誤或 None）；錯誤等 log 開好再寫。

    這支檔案被 pull 更新時，用新版重新執行一次（os.execve 不會回來；鎖的 fd 不會傳下去，新的那次重新拿鎖）。
    重新執行的是排程當初叫的那支：cron 叫 run_daily_test.py 時從它開始，退回舊版（它又變回正式的主程式）時也接得上。
    crontab 改成直接叫 run_daily.py 之後，回滾時這支不能變回骨架（memory/context/02-pipeline.md「檔案結構為什麼這樣」）。
    """
    before = digest(SCRIPT)
    try:
        notes = git_start()
    except Exception as e:
        return [], e
    if digest(SCRIPT) != before and not os.environ.get(REEXEC_FLAG) and from_command_line:
        entry = os.environ.get(ENTRY_VAR) or str(SCRIPT)
        print(f"run_daily.py 被 git pull 更新了，從 {Path(entry).name} 重新執行", flush=True)
        os.execve(sys.executable, [sys.executable, entry, *sys.argv[1:]], {**os.environ, REEXEC_FLAG: "1"})
    return notes, None


def git(*args, timeout=180):
    """跑 git，逾時回傳 returncode 124（不丟錯，呼叫的人照失敗處理）。不會跳出問密碼的提示。"""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(["git", *args], 124, "", f"git {args[0]} 超過 {timeout} 秒")


def short(text: str) -> str:
    return " ".join(text.split())[-300:]


def on_branch() -> bool:
    return git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == BRANCH


def data_only(paths) -> bool:
    """paths 是不是都在 DATA_PATHS 裡（排程只能自己 commit 資料，程式的改動要人來）。"""
    return all(any(p == d or p.startswith(d + "/") for d in DATA_PATHS) for p in paths if p)


def commit_data(message: str) -> bool:
    """DATA_PATHS 有改動就 commit，回傳有沒有 commit。"""
    r = git("add", "--", *[p for p in DATA_PATHS if (ROOT / p).exists()])
    if r.returncode != 0:
        raise StopRun(f"git add 失敗：{short(r.stderr or r.stdout)}")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return False
    r = git("commit", "-m", message)
    if r.returncode != 0:
        raise StopRun(f"git commit 失敗：{short(r.stderr or r.stdout)}")
    return True


def push(log) -> bool:
    """先 pull --rebase 再 push 到 BRANCH，失敗等 PUSH_WAIT 秒再試一次（推 git 不是送 POST，重試沒有副作用）。
    不在 BRANCH 上或都失敗回傳 False（不丟錯）。"""
    if not on_branch():
        log.error("目前不在 %s，不推", BRANCH)
        return False
    for attempt in range(1, PUSH_ATTEMPTS + 1):
        r = git("pull", "--rebase", "--autostash", "origin", BRANCH)
        if r.returncode != 0:
            git("rebase", "--abort")
            what = "git pull --rebase"
        else:
            r = git("push", "origin", f"HEAD:{BRANCH}")
            if r.returncode == 0:
                return True
            what = "git push"
        log.error("%s 失敗（第 %d 次）：%s", what, attempt, short(r.stderr or r.stdout))
        if attempt < PUSH_ATTEMPTS:
            time.sleep(PUSH_WAIT)
    return False


def git_start() -> list:
    """開始前同步。data/ 以外有改動就停（不自動清掉）；data/ 裡上次留下的改動先 commit；再 pull --rebase。

    pull 失敗時先 fetch，再在本機 rebase（不用網路，暫時連不上時這樣就好了）。還是衝突，而且本機多出來的
    commit 只動 data/、也沒有 data/ 以外沒追蹤的檔，才丟掉它們、對齊 origin（資料這次重抓）；丟之前把
    upload_log 裡 origin 沒有的行補回去，「沒送出」「失敗」這些紀錄不能跟著不見。不然停下等人處理。
    這裡不寫 log（log 檔本身在 data/submission/，寫了會讓 pull 失敗），要記的話回傳給呼叫的人，pull 完再寫。
    """
    notes = []
    if not on_branch():
        raise StopRun(f"目前不在 {BRANCH}，--sync 只在這個分支上跑")
    changed = [line[3:] for line in git("status", "--porcelain", "--untracked-files=no").stdout.splitlines()]
    if not data_only(changed):
        raise StopRun(f"工作目錄有 data/ 以外的改動，不自動同步：{[p for p in changed if not data_only([p])][:5]}")
    if commit_data("Leftover data from an earlier run"):
        notes.append("上次留下沒 commit 的資料，先 commit 了")
    r = git("pull", "--rebase", "origin", BRANCH)
    if r.returncode == 0:
        return notes
    git("rebase", "--abort")
    if git("fetch", "origin", BRANCH).returncode != 0:
        raise StopRun(f"git pull、fetch 都失敗（網路？）：{short(r.stderr or r.stdout)}")
    if git("rebase", f"origin/{BRANCH}").returncode == 0:
        notes.append("git pull 失敗，fetch 之後在本機 rebase 成功")
        return notes
    git("rebase", "--abort")
    ahead = git("rev-list", f"origin/{BRANCH}..HEAD").stdout.split()
    touched = git("diff", "--name-only", f"origin/{BRANCH}...HEAD").stdout.split()
    untracked = git("ls-files", "--others", "--exclude-standard").stdout.split()
    if not (ahead and data_only(touched) and data_only(untracked)):
        raise StopRun(f"git pull --rebase 失敗：{short(r.stderr or r.stdout)}")
    ours = read_lines(ROOT / UPLOAD_LOG)
    git("reset", "--hard", f"origin/{BRANCH}")
    theirs = set(read_lines(ROOT / UPLOAD_LOG))
    keep = [line for line in ours if line and line not in theirs]
    if keep:
        (ROOT / UPLOAD_LOG).parent.mkdir(parents=True, exist_ok=True)
        with open(ROOT / UPLOAD_LOG, "a", encoding="utf-8") as f:
            f.write("".join(line + "\n" for line in keep))
        commit_data("Keep upload records from dropped commits")
    notes.append(f"git pull 失敗；本機多出的 {len(ahead)} 個 commit 只動 data/，丟掉並對齊 origin"
                 f"（{', '.join(c[:8] for c in ahead)}），upload_log 補回 {len(keep)} 行")
    return notes


# ================================================================ 小工具


def timed(log, name: str, fn):
    """跑 fn，log 寫「name 完成（N 秒）」，回傳 fn 的結果。"""
    started = time.monotonic()
    result = fn()
    log.info("%s 完成（%.0f 秒）", name, time.monotonic() - started)
    return result


def describe(e: BaseException) -> str:
    """寫進 log 的錯誤。自己寫的錯誤（src/ 的 Error 類別都是 RuntimeError）和 ValueError 印出訊息，
    其他只寫類別（訊息可能帶伺服器內容）。"""
    return f"{type(e).__name__}: {str(e)[:300]}" if isinstance(e, (RuntimeError, ValueError)) else type(e).__name__


def requirements_note() -> str | None:
    """runner_setup.sh 裝套件時記下 requirements.txt 的 sha256；不一樣了代表套件要重裝（oop 連不到 PyPI，不自動裝）。"""
    stamp = ROOT / ".venv" / "requirements.sha256"
    if not stamp.exists():
        return None
    if stamp.read_text().split()[0:1] != [digest(ROOT / "requirements.txt")]:
        return "requirements.txt 和安裝時不一樣：套件可能要重裝（memory/reference/06-runner-hosts.md）"
    return None


def digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def json_field(path: Path, key: str):
    return json.loads(path.read_text(encoding="utf-8")).get(key)


def read_lines(path: Path) -> list:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


if __name__ == "__main__":
    sys.exit(main())
