"""run_daily.py 的 git 同步和 log（用暫存資料夾裡的假 remote，不連網）、舊名字 run_daily_test.py、src/ 的新舊路徑。"""

import logging
import shutil
import subprocess
import sys

import pytest

import run_daily as rdt
from src.pipeline import utils

BRANCH = rdt.BRANCH


def sh(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repos(tmp_path, monkeypatch):
    for k in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(k, "test")
    for k in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(k, "test@example.com")
    origin, work, other = tmp_path / "origin.git", tmp_path / "work", tmp_path / "other"
    sh(tmp_path, "init", "-q", "--bare", str(origin))
    sh(tmp_path, "init", "-q", "-b", BRANCH, str(work))
    sh(work, "config", "commit.gpgsign", "false")
    (work / "data" / "submission").mkdir(parents=True)
    (work / "data" / "raw").mkdir(parents=True)
    (work / "src").mkdir()
    (work / "data" / "submission" / "run.log").write_text("a\n")
    (work / "data" / "raw" / "x.csv").write_text("1\n")
    (work / "src" / "code.py").write_text("x = 1\n")
    sh(work, "add", "-A")
    sh(work, "commit", "-q", "-m", "init")
    sh(work, "remote", "add", "origin", str(origin))
    sh(work, "push", "-q", "origin", BRANCH)
    sh(tmp_path, "clone", "-q", "-b", BRANCH, str(origin), str(other))
    sh(other, "config", "commit.gpgsign", "false")
    monkeypatch.setattr(rdt, "ROOT", work)
    return work, other


def test_leftover_log_lines_do_not_trigger_reset(repos):
    work, other = repos
    (other / "data" / "raw" / "y.csv").write_text("from the other runner\n")   # 別台推了別的檔
    sh(other, "add", "-A")
    sh(other, "commit", "-q", "-m", "other")
    sh(other, "push", "-q", "origin", BRANCH)
    (work / "data" / "submission" / "run.log").write_text("a\nleft from last run\n")
    notes = rdt.git_start()
    assert notes == ["上次留下沒 commit 的資料，先 commit 了"]
    log = sh(work, "log", "--format=%s")
    assert "Leftover data from an earlier run" in log and "other" in log      # rebase 成功，沒有丟掉
    assert (work / "data" / "raw" / "y.csv").exists()


def test_non_data_change_stops(repos):
    work, _ = repos
    (work / "src" / "code.py").write_text("x = 2\n")
    with pytest.raises(rdt.StopRun):
        rdt.git_start()


def test_conflicting_data_commits_are_dropped_but_untracked_code_is_protected(repos):
    work, other = repos
    (other / "data" / "raw" / "x.csv").write_text("theirs\n")
    sh(other, "commit", "-qam", "theirs")
    sh(other, "push", "-q", "origin", BRANCH)
    (work / "data" / "raw" / "x.csv").write_text("ours\n")
    (work / "notes.ipynb").write_text("{}")                                   # data/ 以外沒追蹤的檔
    with pytest.raises(rdt.StopRun):
        rdt.git_start()
    (work / "notes.ipynb").unlink()
    notes = rdt.git_start()
    assert "丟掉並對齊 origin" in notes[-1]
    assert (work / "data" / "raw" / "x.csv").read_text() == "theirs\n"


def test_git_timeout_is_a_failure_not_an_exception(repos, monkeypatch):
    def slow(*a, **k):
        raise subprocess.TimeoutExpired(a[0], 1)

    monkeypatch.setattr(rdt.subprocess, "run", slow)
    monkeypatch.setattr(rdt, "PUSH_WAIT", 0)
    monkeypatch.setattr(rdt, "on_branch", lambda: True)
    assert rdt.git("push").returncode == 124
    assert rdt.push(logging.getLogger("test")) is False


def test_push_retries_once_after_a_failure(repos, monkeypatch):
    work, _ = repos
    (work / "data" / "raw" / "x.csv").write_text("2\n")
    rdt.commit_data("data")
    real, calls = rdt.git, []

    def flaky(*args, **kw):
        if args[0] == "push":
            calls.append(1)
            if len(calls) == 1:
                return subprocess.CompletedProcess(args, 128, "", "Connection timed out")
        return real(*args, **kw)

    monkeypatch.setattr(rdt, "git", flaky)
    monkeypatch.setattr(rdt, "PUSH_WAIT", 0)
    assert rdt.push(logging.getLogger("test")) is True and len(calls) == 2


def test_logger_reopens_replaced_file(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "ROOT", tmp_path)
    log = utils.get_logger("watched_test", "2026-11-09")
    path = tmp_path / "data" / "submission" / "run_2026-11-09.log"
    assert not path.exists()                                                  # 第一次寫才建檔
    log.info("first")
    path.unlink()                                                             # 像 git reset 換掉檔案
    log.info("second")
    assert "second" in path.read_text() and "first" not in path.read_text()


def test_reset_keeps_upload_log_lines_origin_lacks(repos):
    work, other = repos
    (other / "data" / "raw" / "x.csv").write_text("theirs\n")
    sh(other, "commit", "-qam", "theirs")
    sh(other, "push", "-q", "origin", BRANCH)
    (work / "data" / "raw" / "x.csv").write_text("ours\n")
    (work / "data" / "submission" / "upload_log.jsonl").write_text('{"status": "not_sent", "run_id": "a"}\n')
    notes = rdt.git_start()
    assert "upload_log 補回 1 行" in notes[-1]
    assert "not_sent" in (work / "data" / "submission" / "upload_log.jsonl").read_text()
    assert sh(work, "status", "--porcelain").strip() == ""                      # 補回的行也 commit 了


def test_push_refuses_other_branches(repos):
    work, _ = repos
    sh(work, "checkout", "-q", "-b", "elsewhere")
    assert rdt.push(logging.getLogger("test")) is False
    with pytest.raises(rdt.StopRun):
        rdt.git_start()


# ---------------------------------------------------------------- GitHub 連不上時照爬照交（使用者 2026-11-17）


OOP_DNS = ("ssh: Could not resolve hostname github.com: Name or service not known\n"
           "fatal: Could not read from remote repository.")   # oop 2026-11-10～11-17 的 07:10 看到的


def failing_remote(real, code, message):
    """pull、fetch 都回傳 code 和 message 的 git；其他指令照常跑。"""
    def fake(*args, **kw):
        if args[0] in ("pull", "fetch"):
            return subprocess.CompletedProcess(args, code, "", message)
        return real(*args, **kw)
    return fake


@pytest.mark.parametrize("code, message", [(128, OOP_DNS), (124, "git fetch 超過 180 秒")], ids=["dns", "timeout"])
def test_unreachable_github_continues_with_the_local_code(repos, monkeypatch, code, message):
    work, _ = repos
    monkeypatch.setattr(rdt, "OFFLINE", False)
    monkeypatch.setattr(rdt, "GIT_RETRY_SECONDS", 0)   # 不等：試一次就放棄
    monkeypatch.setattr(rdt, "GIT_RETRY_WAIT", 1)
    real = rdt.git
    monkeypatch.setattr(rdt, "git", failing_remote(real, code, message))
    (work / "data" / "submission" / "run.log").write_text("a\nleft from last run\n")
    notes = rdt.git_start()
    head = sh(work, "rev-parse", "--short", "HEAD").strip()
    assert notes[0] == "上次留下沒 commit 的資料，先 commit 了"
    assert notes[-1].startswith("連不上 GitHub（") and "試了 1 次" in notes[-1] and f"commit {head}" in notes[-1]
    assert notes[-1].endswith("資料和上傳紀錄下次再推") and rdt.OFFLINE is True
    monkeypatch.setattr(rdt, "git", real)   # 下一次連得上：照常 pull
    assert rdt.git_start() == [] and rdt.OFFLINE is False


def test_a_git_failure_that_is_not_the_network_still_stops(repos, tmp_path, monkeypatch):
    work, _ = repos
    monkeypatch.setattr(rdt, "OFFLINE", False)
    monkeypatch.setattr(rdt, "GIT_RETRY_SECONDS", 0)
    monkeypatch.setattr(rdt, "GIT_RETRY_WAIT", 1)
    sh(work, "remote", "set-url", "origin", str(tmp_path / "moved.git"))   # 例如 repo 搬家：不是連不上網路
    with pytest.raises(rdt.StopRun, match="不像是連不上網路"):
        rdt.git_start()
    assert rdt.OFFLINE is False
    real = rdt.git
    monkeypatch.setattr(rdt, "git", failing_remote(real, 128, "ERROR: Permission to repo denied to deploy key\n"
                                                             "fatal: Could not read from remote repository."))
    with pytest.raises(rdt.StopRun, match="不像是連不上網路"):   # deploy key 被撤
        rdt.git_start()
    assert rdt.OFFLINE is False


def test_reset_after_an_offline_day_keeps_this_days_submission_files(repos):
    """07:10 連不上 GitHub、交件檔只 commit 在本機；組員晚上推了重建的資料，07:25 pull --rebase 衝突、對齊 origin。"""
    work, other = repos
    (other / "data" / "raw" / "x.csv").write_text("theirs\n")
    sh(other, "commit", "-qam", "rebuilt data")
    sh(other, "push", "-q", "origin", BRANCH)
    sub = work / "data" / "submission"
    files = {"submission_2026-11-18.csv": "id,2026-11-18\n2330,1\n", "complete_2026-11-18.json": '{"complete": false}\n',
             "run.log": "a\n07:10 offline\n"}   # run.log 在 origin 也有，這台改過
    for name, text in files.items():
        (sub / name).write_text(text)
    (sub / "upload_log.jsonl").write_text('{"status": "done", "run_id": "a"}\n')
    (work / "data" / "raw" / "x.csv").write_text("ours\n")
    rdt.commit_data("Daily run 2026-11-18: data and prepared upload")
    notes = rdt.git_start()
    assert "丟掉並對齊 origin" in notes[-1] and "upload_log 補回 1 行" in notes[-1] and "data/submission/ 留回 3 個檔" in notes[-1]
    assert (work / "data" / "raw" / "x.csv").read_text() == "theirs\n"   # 資料照 origin
    assert all((sub / name).read_text() == text for name, text in files.items())
    assert '"done"' in (sub / "upload_log.jsonl").read_text()
    assert sh(work, "status", "--porcelain").strip() == ""
    assert sh(work, "log", "-1", "--format=%s").strip() == "Keep upload records from dropped commits"


def test_git_pull_is_retried_while_github_is_unreachable(repos, monkeypatch):
    work, _ = repos
    monkeypatch.setattr(rdt, "OFFLINE", False)
    monkeypatch.setattr(rdt, "GIT_RETRY_SECONDS", 1000)
    monkeypatch.setattr(rdt, "GIT_RETRY_WAIT", 0)
    real, calls = rdt.git, []

    def flaky(*args, **kw):
        if args[0] in ("pull", "fetch"):
            calls.append(args[0])
            if len(calls) <= 2:   # 第一次 pull 和 fetch 都失敗
                return subprocess.CompletedProcess(args, 128, "", "Could not resolve host: github.com")
        return real(*args, **kw)

    monkeypatch.setattr(rdt, "git", flaky)
    assert rdt.git_start() == ["git pull 第 2 次才成功"]
    assert calls == ["pull", "fetch", "pull"] and rdt.OFFLINE is False


def before_post_result(monkeypatch, caplog, *, pushed, require=None, offline=False):
    """before_post_for 回傳的函式跑一次：commit 換成假的，push 回傳 pushed。回傳（結果, 有沒有呼叫 push）。"""
    calls = []
    monkeypatch.setattr(rdt, "commit_data", lambda message: True)
    monkeypatch.setattr(rdt, "push", lambda log: calls.append(1) or pushed)
    monkeypatch.setattr(rdt, "OFFLINE", offline)
    cfg = {"submit": {} if require is None else {"require_push_before_post": require}}
    with caplog.at_level(logging.WARNING):
        result = rdt.before_post_for(cfg, "2026-11-13", logging.getLogger("test"))()
    return result, bool(calls)


def test_before_post_uploads_without_push_only_when_the_config_says_so(monkeypatch, caplog):
    assert before_post_result(monkeypatch, caplog, pushed=True, require=True) == (True, True)
    assert before_post_result(monkeypatch, caplog, pushed=False, require=True) == (False, True)
    assert before_post_result(monkeypatch, caplog, pushed=False) == (False, True)   # 沒寫就是 true（舊的規則）
    assert "推不上 GitHub" not in caplog.text
    assert before_post_result(monkeypatch, caplog, pushed=False, require=False) == (True, True)
    assert "「準備上傳」的紀錄推不上 GitHub，先留在本機（只有 oop 一台排程，使用者 2026-11-17）；照樣上傳" in caplog.text


def test_before_post_does_not_push_when_github_was_unreachable(monkeypatch, caplog):
    assert before_post_result(monkeypatch, caplog, pushed=True, require=False, offline=True) == (True, False)
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == ["「準備上傳」的紀錄沒推（這次連不上 GitHub），先留在本機（只有 oop 一台排程，使用者 2026-11-17）；照樣上傳"]
    assert before_post_result(monkeypatch, caplog, pushed=True, require=True, offline=True) == (False, False)


def test_the_config_allows_upload_without_push_and_redo():
    cfg = utils.load_config()["submit"]
    assert cfg["require_push_before_post"] is False and cfg["redo_incomplete"] is True and cfg["redo_latest"] == "08:44"


@pytest.mark.parametrize("script", ["run_daily", "run_daily_test"])
def test_script_does_not_import_src_before_sync(script):
    """git pull 之前不能載入 src/：不然推上去的修正這次用不到，新程式壞掉時也拿不到修正。"""
    code = f"import sys; sys.path.insert(0, '.'); import {script}; print(any(m.startswith('src') for m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], cwd=utils.ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_old_script_name_runs_run_daily():
    """oop 裝好的 crontab 還在叫 run_daily_test.py：要原封不動轉到 run_daily.py（參數照傳）。"""
    out = subprocess.run([sys.executable, "run_daily_test.py", "--help"], cwd=utils.ROOT, capture_output=True,
                         text=True, check=True)
    assert "run_daily.py" in out.stdout and "--sync" in out.stdout and "--dry-run" in out.stdout


def test_old_name_passes_its_own_path_and_arguments(tmp_path):
    """舊名字轉過去時帶上自己的路徑（RUN_DAILY_ENTRY）和原本的參數。"""
    shutil.copy(utils.ROOT / "run_daily_test.py", tmp_path / "run_daily_test.py")
    (tmp_path / "run_daily.py").write_text("import os, sys\nprint(os.environ['RUN_DAILY_ENTRY'], *sys.argv[1:])\n")
    out = subprocess.run([sys.executable, str(tmp_path / "run_daily_test.py"), "--sync", "--dry-run"],
                         capture_output=True, text=True, check=True)
    assert out.stdout.split() == [str((tmp_path / "run_daily_test.py").resolve()), "--sync", "--dry-run"]


def test_reexec_starts_from_the_script_cron_called(tmp_path, monkeypatch):
    """run_daily.py 被 pull 更新時重新執行排程叫的那支：退回舊版時 run_daily_test.py 又是正式的主程式，也接得上。"""
    script = tmp_path / "run_daily.py"
    calls = []

    def pulled():
        script.write_text("new")   # 像 git pull 換掉這支檔案
        return []

    monkeypatch.setattr(rdt, "SCRIPT", script)
    monkeypatch.setattr(rdt, "git_start", pulled)
    monkeypatch.setattr(rdt.os, "execve", lambda exe, argv, env: calls.append((argv, env)))
    monkeypatch.delenv(rdt.REEXEC_FLAG, raising=False)
    monkeypatch.setenv(rdt.ENTRY_VAR, "/repo/run_daily_test.py")
    script.write_text("old")
    assert rdt.sync_with_github(True) == ([], None)
    assert calls[-1][0][1] == "/repo/run_daily_test.py" and calls[-1][1][rdt.REEXEC_FLAG] == "1"
    monkeypatch.delenv(rdt.ENTRY_VAR)
    script.write_text("old")
    rdt.sync_with_github(True)
    assert calls[-1][0][1] == str(script)                     # 直接叫 run_daily.py 時從它自己開始
    script.write_text("old")
    rdt.sync_with_github(False)                                # main(argv) 從程式裡呼叫（測試）時不重新執行
    monkeypatch.setenv(rdt.REEXEC_FLAG, "1")
    script.write_text("old")
    rdt.sync_with_github(True)                                 # 已經重新執行過一次就不再來
    assert len(calls) == 2


def test_old_import_names_still_work():
    """組員舊的 notebook 寫 from src import features：還是拿到搬家後的同一個模組。"""
    import src
    from src import features, rank_ensemble
    from src.models import m3_rank_ensemble
    from src.pipeline import step2_features
    assert features is step2_features and rank_ensemble is m3_rank_ensemble
    assert set(src.OLD_NAMES) == {"crawler", "features", "submit", "merge_raw", "site_api", "utils", "online_lr",
                                  "persist_rule", "rank_ensemble", "c2_tilt"}
    with pytest.raises(ImportError):
        from src import no_such_module  # noqa: F401


def test_every_model_in_the_registry_loads():
    """config 能填的每個名字都找得到 predict 函式（檔名或函式名打錯，這裡就會壞，不用等到早上換備援）。"""
    from src.models import MODEL_KINDS
    from src.pipeline import step3_train_predict
    assert set(MODEL_KINDS) == {"online_lr", "persist", "rank_ensemble", "c2", "c2v2d"}
    for kind in MODEL_KINDS:
        assert callable(step3_train_predict.load_model(kind)), kind
