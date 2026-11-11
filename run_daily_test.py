"""每天自動跑一次（測試版）：爬蟲 → 特徵 → 模型 → CSV → 上傳 → 推資料。

排程（memory/context/pipeline.md）：學校的 oop 台北 07:10、07:25、07:40、07:55、08:05、08:25，使用者的 Mac 08:15 起備援，跑同一個指令。
網站上已經有今天的提交就直接結束，所以不會重複上傳。
08:25 那次多做一件事（open_today_step，只在 --sync 時）：抓日韓當天的開盤，補上特徵表 t 那列的 open_gap 兩欄，不影響上傳。
每次結束前（休市日除外）更新 data/merged/（merged_step，使用者 2026-11-11）：data/raw/ 合併成給組員研究的兩張表，
來源沒變就跳過，失敗只寫警告。

用法：
    python run_daily_test.py              交 config 的 submit.phase；t 是台北今天
    python run_daily_test.py --phase 2    指定 Phase；--date 2026-11-09 指定 t（不是今天時不跑爬蟲和特徵）
    python run_daily_test.py --sync       排程用：開始前 git pull，上傳前先推資料和「準備上傳」紀錄，結束後推 data/
    python run_daily_test.py --dry-run    不上傳，只印出要送的內容

Phase 1（測自動化用）：預測網站範本的 84 天（2026-06-01～09-30）× 50 檔。今天（台北）已經交過 Phase 1 就結束。
Phase 2：預測 t 的 50 檔。網站上 t 已經有提交（不算「強制繳交」）就結束。
t 不是交易日（不在 phase2Days）：Phase 2 直接結束；Phase 1 不跑爬蟲和特徵，用現有的特徵表。
之前的執行已經送出（upload_log 有「準備上傳」）卻沒有核對完成時，不再自動重送，留給人確認。

--sync 時先 git pull 才載入 src/：推上去的修正這次就用到；新程式 import 失敗時，修正推上去後下一次還是會先 pull。
這支檔案自己被 pull 更新時，用新版重新執行一次。
模型看 config 的 daily_model.kind（使用者 2026-11-12，見 daily_predict）：persist 是持續性規則（src/persist_rule.py，
不用訓練），online_lr 是組員的邏輯迴歸（src/online_lr.py，每天早上重新 fit）。兩個都不讀 models/。
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
DATA_PATHS = ("data/raw", "data/processed", "data/submission", "data/merged")
UPLOAD_LOG = "data/submission/upload_log.jsonl"   # 和 config 的 data.submission_dir 一致；git_start 在讀 config 前用
LOCK_PATH = ROOT / ".cache" / "run_daily_test.lock"
REEXEC_FLAG = "RUN_DAILY_TEST_REEXEC"
PUSH_ATTEMPTS, PUSH_WAIT = 2, 15   # oop 連 GitHub 偶爾失敗（2026-11-07 看到一次），推送失敗等 15 秒再試一次

crawler = features = merge_raw = online_lr = persist_rule = site_api = submit = utils = None   # import_src() 之後才有


class StopRun(RuntimeError):
    """不能繼續。訊息是自己寫的短句。"""


def import_src():
    """git pull 之後才載入 src/ 的模組。"""
    global crawler, features, merge_raw, online_lr, persist_rule, site_api, submit, utils
    from src import crawler, features, merge_raw, online_lr, persist_rule, site_api, submit, utils  # noqa: F811


# ---------------------------------------------------------------- git（--sync 才用；只用標準函式庫）


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


def commit_data(message: str) -> bool:
    """DATA_PATHS（data/raw、data/processed、data/submission、data/merged）有改動就 commit，回傳有沒有 commit。"""
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


def data_only(paths) -> bool:
    return all(any(p == d or p.startswith(d + "/") for d in DATA_PATHS) for p in paths if p)


def read_lines(path: Path) -> list:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


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


def digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


# ---------------------------------------------------------------- 流程


def phase1_dates_ok(dates: list, data) -> None:
    """範本的 84 天要和特徵表在那段期間有答案的交易日一樣。"""
    have = data.loc[data["label_y"].notna(), "date"].dt.strftime("%Y-%m-%d")
    have = sorted(d for d in set(have) if dates[0] <= d <= dates[-1])
    if have != list(dates):
        extra, lost = sorted(set(have) - set(dates)), sorted(set(dates) - set(have))
        raise StopRun(f"Phase 1 範本的日子和交易日曆不一樣：範本多 {lost[:5]}，日曆多 {extra[:5]}")


def step(log, name, fn):
    started = time.monotonic()
    result = fn()
    log.info("%s 完成（%.0f 秒）", name, time.monotonic() - started)
    return result


def daily_predict(cfg: dict, data, dates: list, ids: list, log) -> tuple:
    """照 config 的 daily_model.kind 選每天交件的模型，回傳（用了哪個模型, 預測）。沒有這個設定時用 online_lr。

    persist（持續性規則）算不出來、daily_model.fallback 又是 online_lr 時，改用組員的邏輯迴歸，當天照樣交件。
    """
    choice = cfg.get("daily_model") or {}
    kind = choice.get("kind", "online_lr")
    if kind == "persist":
        try:
            return "persist", persist_rule.predict(data, cfg, dates, ids)
        except Exception as e:
            if choice.get("fallback") != "online_lr":
                raise
            log.error("持續性規則算不出來（%s），改用組員的邏輯迴歸", describe(e))
            return "online_lr（persist 的備援）", online_lr.predict(data, cfg, dates, ids)
    if kind != "online_lr":
        raise StopRun(f"daily_model.kind 只能是 persist 或 online_lr：{kind}")
    return "online_lr", online_lr.predict(data, cfg, dates, ids)


def pipeline(cfg: dict, args, phase: int, t: str, today: str, log) -> str:
    key = site_api.submission_key(phase, t)
    site = site_api.Site(cfg, utils.load_secrets())
    try:
        state = site.state()
        day = site_api.day_status(state, t)   # 休市看網站的 phase2Days，不看星期幾或寫死的日曆
        trading = day != "closed"
        if phase == 2 and day == "closed":
            log.info("%s 不在網站的交易日清單，休市：不爬、不上傳，結束", t)
            return "closed"
        if day == "not_open":
            log.warning("%s 在網站的清單上但還沒開放（enabled = 0）：照常準備，上傳前再看一次", t)
        entry = submit.existing(state, phase, t, today)
        if entry is not None:
            log.info("網站上已經有這次的提交（%s，%s 交），結束", entry.get("fileName"), entry.get("submittedAt"))
            return "already_submitted"
        done = submit.finished_today(cfg, phase, key, today)
        if done is not None:
            log.info("上傳紀錄說已經%s（%s），結束", "交好" if done["status"] == "done" else "和網站一樣",
                     done.get("time"))
            return "already_submitted"
        pending = submit.open_prepared(cfg, phase, key, today)
        if pending is not None:
            raise StopRun(f"{pending.get('time')} {pending.get('runner')} 已經送過 {pending.get('file')} 但沒有核對完成；"
                          "不自動重送，請到網站確認後手動處理")

        if trading and t == today:
            try:
                code = step(log, "爬蟲", lambda: crawler.main(["--date", t]))
                if code == 3:
                    log.warning("爬蟲有序列沿用舊檔（見 data/raw/manifest.json），繼續")
                step(log, "特徵", lambda: features.main(["--date", t]))
            except Exception as e:
                if phase == 2:
                    raise
                log.warning("爬蟲或特徵失敗（%s），Phase 1 用現有的特徵表繼續", describe(e))
        else:
            log.info("%s 不跑爬蟲和特徵（%s），用現有的特徵表", t, "休市" if not trading else "t 不是今天")

        if phase == 2:
            utils.check_deadline(cfg, t, key="deadline")
        data = step(log, "讀特徵", lambda: online_lr.load_data(cfg))
        if phase == 1:
            header, ids = site.template(1)
            dates = header[1:]
            phase1_dates_ok(dates, data)
        else:
            header, ids = site.template(2, t)
            if header != ["id", t]:
                raise StopRun(f"Phase 2 範本的表頭不是 id,{t}")
            if not (data["date"].dt.strftime("%Y-%m-%d") == t).any():
                raise StopRun(f"特徵表沒有 {t} 的列（Live 還沒更新？）")
            dates = [t]
        model_name, pred = step(log, "模型", lambda: daily_predict(cfg, data, dates, ids, log))
        if phase == 1:
            log.info("Phase 1 本機分數：%s", online_lr.official_score(pred, data))
        values = {(r.date, r.stock_id): int(r.pred) for r in pred.itertuples()}
        rows = submit.build_rows(phase, header, ids, values)
        submit.check_rows(rows, phase, header, ids)
        name = f"submission_{t}.csv" if phase == 2 else f"submission_phase1_{today}.csv"
        path = ROOT / cfg["data"]["submission_dir"] / name
        crawler.write_atomic(path, submit.rows_to_bytes(rows))
        log.info("寫好 %s：%d 檔 × %d 天，模型 %s，猜漲 %.3f", path.relative_to(ROOT), len(ids), len(dates), model_name,
                 pred["pred"].mean())

        def before_post():
            commit_data(f"Daily run {key}: data and prepared upload")
            return push(log)

        return submit.run(cfg, site, phase, path, t if phase == 2 else None, log,
                          before_post=before_post if args.sync else None, respect_existing=True)
    finally:
        site.close()


def open_today_step(t: str, today: str, log) -> None:
    """日韓當天的開盤（使用者 2026-11-11，只進長表）：台北 08:22 以後（排程 08:25）從 Yahoo 抓，抓到新的就重寫
    特徵表，t 那列的 kospi_open_gap、n225_open_gap 才有值。特徵表的最後一天不是 t（今天沒跑成）就不抓。
    模型和上傳不看這兩欄。任何錯誤只記 log，不改這次執行的結果。"""
    try:
        if t != today:
            return
        cfg = utils.load_config()
        info = json.loads((ROOT / cfg["data"]["processed_dir"] / "manifest.json").read_text(encoding="utf-8"))
        if info.get("last_date") != t:
            return
        if crawler.open_today(cfg, t, log)["written"]:
            step(log, "特徵（補上當天開盤）", lambda: features.main(["--date", t]))
    except Exception as e:
        log.warning("當天開盤那一步沒做完（%s）：只影響長表的 open_gap 兩欄", describe(e))


def merged_step(log) -> None:
    """data/raw/ 合併成 data/merged/ 的兩張表（使用者 2026-11-11，給組員研究，模型和上傳不看）。
    在上傳之後、推資料之前跑，不拖慢上傳。來源檔沒變就跳過（約 0.3 秒），有變約 20 秒。任何錯誤只記 log。"""
    try:
        step(log, "合併原始資料", lambda: merge_raw.main([]))
    except Exception as e:
        log.warning("合併原始資料沒做完（%s）：只影響 data/merged/，下次執行會再做", describe(e))


def describe(e: BaseException) -> str:
    """錯誤訊息只用自己寫的那幾種，其他只寫類別（訊息可能帶伺服器內容）。"""
    own = (StopRun, crawler.CrawlerError, features.FeatureError, online_lr.ModelError, site_api.SiteError,
           RuntimeError, ValueError)   # merge_raw.MergeError、persist_rule.RuleError 是 RuntimeError
    return f"{type(e).__name__}: {str(e)[:300]}" if isinstance(e, own) else type(e).__name__


def requirements_note() -> str | None:
    """runner_setup.sh 裝套件時記下 requirements.txt 的 sha256；不一樣了代表套件要重裝（oop 連不到 PyPI，不自動裝）。"""
    stamp = ROOT / ".venv" / "requirements.sha256"
    if not stamp.exists():
        return None
    if stamp.read_text().split()[0:1] != [digest(ROOT / "requirements.txt")]:
        return "requirements.txt 和安裝時不一樣：套件可能要重裝（README「排程主機」）"
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="每天自動跑一次：爬蟲 → 特徵 → 模型 → 上傳 → 推資料")
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
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_PATH, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("另一個 run_daily_test.py 還在跑，這次不跑")
            return 0
        return locked_main(args, argv)


def locked_main(args, argv=None) -> int:
    notes, sync_error, branch_ok = [], None, False
    if args.sync:
        branch_ok = on_branch()
        before = digest(SCRIPT)
        try:
            notes = git_start()
        except Exception as e:   # 載入 src 之後再寫進 log
            sync_error = e
        else:
            if digest(SCRIPT) != before and not os.environ.get(REEXEC_FLAG) and argv is None:
                print("run_daily_test.py 被 git pull 更新了，用新版重新執行", flush=True)
                os.execve(sys.executable, [sys.executable, str(SCRIPT), *sys.argv[1:]],
                          {**os.environ, REEXEC_FLAG: "1"})   # 鎖的 fd 不會傳下去，新的那次重新拿鎖
    try:
        import_src()
    except Exception as e:   # 新推的程式 import 失敗：寫到 cron.log；下一次會先 pull，修正推上去就好了
        print(f"載入 src/ 失敗：{type(e).__name__}: {str(e)[:300]}", flush=True)
        return 1

    today = utils.taipei_now().date().isoformat()
    t = args.date or today
    log = utils.get_logger("run_daily_test", t)   # 檔名用 t（Phase 1 時 t 就是今天）
    status, code, phase, interrupted = "failed", 1, args.phase, False
    try:
        if sync_error is not None:
            raise sync_error
        cfg = utils.load_config()   # pull 之後才讀，推上去的 config（例如 submit.phase）這次就生效
        phase = args.phase or cfg["submit"]["phase"]
        log.info("開始：Phase %s，t = %s%s%s（執行代號 %s）", phase, t, "，--sync" if args.sync else "",
                 "，--dry-run" if args.dry_run else "", submit.RUN_ID)
        for note in notes + [n for n in [requirements_note()] if n]:
            log.warning(note)
        if args.dry_run:
            cfg["submit"]["enabled"] = False
        status = pipeline(cfg, args, phase, t, today, log)
        code = 0
    except BaseException as e:
        log.error("停下：%s", describe(e))
        if not isinstance(e, Exception):
            interrupted = True
            raise
    finally:
        log.info("結束：%s", status)
        if args.sync and not interrupted and status != "closed":
            open_today_step(t, today, log)   # 只在排程的 clone 做；自己接住所有錯誤
        if not interrupted and status != "closed":
            merged_step(log)                 # 自己接住所有錯誤
        if args.sync and branch_ok:
            try:
                commit_data(f"Daily run {t} (Phase {phase}): {status}")
                if not push(log):
                    log.error("資料推不上去，下次執行會再推")
                    code = code or 1
            except Exception as e:
                log.error("推資料失敗：%s", describe(e))
                code = code or 1
    return code


if __name__ == "__main__":
    sys.exit(main())
