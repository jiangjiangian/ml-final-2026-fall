"""run_daily_test.py 的 git 同步和 log：用暫存資料夾裡的假 remote，不連網。"""

import logging
import subprocess
import sys

import pytest

import run_daily_test as rdt
from src import utils

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
    assert rdt.git("push").returncode == 124
    assert rdt.push(logging.getLogger("test")) is False


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


def test_script_does_not_import_src_before_sync():
    """git pull 之前不能載入 src/：不然推上去的修正這次用不到，新程式壞掉時也拿不到修正。"""
    code = "import sys; sys.path.insert(0, '.'); import run_daily_test; print(any(m.startswith('src') for m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], cwd=utils.ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
