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
