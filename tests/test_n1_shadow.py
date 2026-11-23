"""N1 影子跑（使用者 2026-11-23）在正式環境這一側的測試：run_daily.run_n1 什麼時候叫子程序、逾時不佔到下一個
排程時段、出事時收尾照常，主程序不 import torch，影子跑多存 c2v2d 的 4 欄，n1_<t>.csv 的打分（壞掉的檔不擋其他
模型），n1 的暫存檔不進 Git，gspc 不進特徵表和合併表。

正式的 .venv 沒有 torch：子程序換成假的 Python（shell 腳本），不跑 m7。m7 本身在 tests/test_n1_model.py（.venv-n1 跑）。
"""

import ast
import inspect
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import run_daily as rd
from src.models import MODEL_KINDS, SHADOW_ONLY
from src.pipeline import step2_features as features, step3_train_predict as tp, step5_merge_raw as merge_raw, utils
from src.pipeline import step1_crawler as crawler
from tests.test_evening_score import PRED_A, PRED_B, RET, STOCKS, T, env, ledger, official, site_scores  # noqa: F401（env 是 fixture）
from tests.test_evening_score import run as evening
from tests.test_features import fake_repo

LOG = logging.getLogger("test_n1_shadow")
ROOT = Path(rd.__file__).resolve().parent
FAKE_PYTHON = """#!/bin/sh
printf '%s\\n' "$@" > "$N1_TEST_DIR/args.txt"
env > "$N1_TEST_DIR/env.txt"
case "$N1_TEST_MODE" in
  ok) echo "n1 2026-11-17 第 1 批：寫好"; exit 0 ;;
  data) echo "n1 停下：爬蟲紀錄的 t 不是今天" >&2; exit 2 ;;
  state) echo "n1 停下：狀態檔對不上" >&2; exit 3 ;;
  busy) echo "上一次的 n1 還在跑" >&2; exit 4 ;;
  crash) echo "Traceback: boom" >&2; exit 1 ;;
  sleep) echo $$ > "$N1_TEST_DIR/pid"; exec sleep 30 ;;
  bytes) printf 'n1 \\377\\376 ok\\n'; exit 0 ;;
  leak) msg="File $N1_TEST_ROOT/src/models/m7_n1_js_online.py, line 68: import torch; File $HOME/x/.venv-n1/lib/torch/__init__.py: ModuleNotFoundError: boom"
        echo "$msg"; echo "$msg" >&2; exit "$N1_TEST_CODE" ;;
esac
"""
SLOTS = ["07:10", "07:25", "07:40", "07:55", "08:05", "08:25"]


# ---------------------------------------------------------------- 主程序不碰 torch、m7 不在模型清單


def imports_of(path: Path) -> set:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names |= {f"{node.module}.{a.name}" for a in node.names}
    return names


def test_the_main_process_never_imports_torch_or_m7():
    files = [ROOT / "run_daily.py", ROOT / "run_daily_test.py", *sorted((ROOT / "src" / "pipeline").glob("*.py")),
             *[p for p in sorted((ROOT / "src" / "models").glob("*.py")) if p.name != "m7_n1_js_online.py"]]
    for path in files:
        names = imports_of(path)
        assert not any(n == "torch" or n.startswith("torch.") for n in names), path.name
        assert not any("m7_n1_js_online" in n for n in names), path.name
    code = ("import sys, run_daily as rd; rd.import_src(); "
            "from src.pipeline import step3_train_predict, step6_evening_score; "
            "print('torch' in sys.modules, any('m7_n1' in m for m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.split() == ["False", "False"]


def test_m7_is_not_a_model_kind_and_c2v2d_saves_its_members():
    assert not any("m7" in target for target in MODEL_KINDS.values()) and "n1" not in MODEL_KINDS
    assert "n1" not in SHADOW_ONLY
    assert tp.EXTRA_COLUMNS["c2v2d"] == ("p_up", "ridge", "kridge", "lgbm", "beta_rank")
    assert tp.EXTRA_COLUMNS["c2"] == ("p_up",)


def test_the_n1_config_block():
    conf = utils.load_config()["daily_model"]["n1"]
    assert conf["enabled"] is True and conf["python"] == ".venv-n1/bin/python"
    assert 30 <= conf["timeout_seconds"] <= 150   # 第二個早上起照實際秒數調（deploy/n1_setup.md 第 6 節），不釘死
    assert conf["start_before"] == "08:45" and conf["finish_by"] == "08:58"
    assert conf["max_runs"] == 2 and conf["cache_dir"] == ".cache/n1"
    assert (ROOT / conf["initial_dir"] / conf["start_state"]).is_dir()
    assert conf["stop_rule"] == {"days": 5, "diff": -0.0067}
    assert "n1" not in tp.shadow_models(utils.load_config())


# ---------------------------------------------------------------- run_n1 什麼時候叫


@pytest.fixture
def n1(monkeypatch, tmp_path):
    """假的 .venv-n1/bin/python（記下參數和環境變數，照 N1_TEST_MODE 結束）、暫存的 data/submission、
    台北 2026-11-17 07:30。回傳 (cfg, 叫了沒有的函式, 設定時間的函式)。"""
    rd.import_src()
    script = tmp_path / "venv-n1" / "python"
    script.parent.mkdir()
    script.write_text(FAKE_PYTHON)
    script.chmod(0o755)
    sub = tmp_path / "submission"
    sub.mkdir()
    cfg = {"data": {"submission_dir": str(sub), "raw_dir": "data/raw"},
           "daily_model": {"n1": {"enabled": True, "python": str(script), "timeout_seconds": 150,
                                  "start_before": "08:45", "finish_by": "08:58", "max_runs": 2,
                                  "initial_dir": "models/n1/ub04_v5", "start_state": "state_2026-11-20_yahoo_gspc",
                                  "cache_dir": ".cache/n1"}}}
    monkeypatch.setattr(rd.utils, "load_config", lambda: cfg)
    monkeypatch.setenv("N1_TEST_DIR", str(tmp_path))
    monkeypatch.setenv("N1_TEST_MODE", "ok")
    monkeypatch.setenv("COURSE_PASSWORD", "pw-不能給子程序")

    def clock(hhmm):
        hour, minute, *second = (int(x) for x in hhmm.split(":"))
        fixed = datetime(2026, 11, 17, hour, minute, second[0] if second else 0, tzinfo=utils.TAIPEI)
        monkeypatch.setattr(rd.utils, "taipei_now", lambda now=None: fixed if now is None else now)

    def called():
        args = tmp_path / "args.txt"
        if not args.exists():
            return None
        lines = args.read_text().splitlines()
        args.unlink()
        return lines

    clock("07:30")
    return cfg, called, clock


def write_n1(cfg, runs_and_shas, t=T, stocks=STOCKS):
    path = Path(cfg["data"]["submission_dir"]) / "n1" / f"n1_{t}.csv"
    path.parent.mkdir(exist_ok=True)
    rows = [{"run": run, "date": t, "stock_id": s, "pred_n1": 1, "pred_js_n1": 0, "shadow_sha_n1": sha}
            for run, sha in runs_and_shas for s in stocks]
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_run_n1_calls_the_n1_python_with_every_setting_and_without_secrets(n1, caplog):
    cfg, called, _ = n1
    with caplog.at_level(logging.INFO):
        rd.run_n1(T, T, 2, LOG)
    args = called()
    assert args[:4] == ["-m", "src.models.m7_n1_js_online", "--date", T]
    pairs = dict(zip(args[4::2], args[5::2]))
    assert pairs == {"--raw-dir": "data/raw", "--submission-dir": cfg["data"]["submission_dir"],
                     "--initial-dir": "models/n1/ub04_v5", "--start-state": "state_2026-11-20_yahoo_gspc",
                     "--cache-dir": ".cache/n1", "--max-runs": "2"}
    env_text = (Path(os.environ["N1_TEST_DIR"]) / "env.txt").read_text()
    assert "COURSE_" not in env_text and "pw-不能給子程序" not in env_text
    assert "n1 完成" in caplog.text and "第 1 批：寫好" in caplog.text


def test_run_n1_is_skipped_when_any_condition_fails(n1, caplog):
    cfg, called, clock = n1
    rd.run_n1(T, T, 1, LOG)   # Phase 1
    rd.run_n1(T, "2026-11-18", 2, LOG)   # t 不是今天
    assert called() is None
    cfg["daily_model"]["n1"]["enabled"] = False
    rd.run_n1(T, T, 2, LOG)
    assert called() is None
    cfg["daily_model"]["n1"]["enabled"] = True
    clock("08:45")
    with caplog.at_level(logging.INFO):
        rd.run_n1(T, T, 2, LOG)
    assert called() is None and "已經過了 08:45" in caplog.text
    clock("08:44:40")
    cfg["daily_model"]["n1"]["finish_by"] = "08:45"   # 剩 20 秒：不夠
    rd.run_n1(T, T, 2, LOG)
    assert called() is None
    cfg["daily_model"]["n1"]["finish_by"] = "08:58"
    clock("07:30")
    cfg["daily_model"]["n1"]["python"] = "/沒有這個/python"
    with caplog.at_level(logging.WARNING):
        rd.run_n1(T, T, 2, LOG)
    assert called() is None and "deploy/n1_setup.md" in caplog.text
    del cfg["daily_model"]["n1"]
    rd.run_n1(T, T, 2, LOG)   # 沒有 n1 這段設定：什麼都不做
    assert called() is None


def test_run_n1_runs_again_only_when_the_shadow_file_changed_and_at_most_twice(n1, caplog):
    cfg, called, _ = n1
    shadow = Path(cfg["data"]["submission_dir"]) / f"shadow_{T}.csv"
    write_n1(cfg, [(1, "")])   # 第 1 批算的時候還沒有 shadow 檔
    rd.run_n1(T, T, 2, LOG)
    assert called() is None
    shadow.write_text("date,stock_id\n")
    rd.run_n1(T, T, 2, LOG)
    assert called() is not None   # shadow 出現了：算第 2 批
    write_n1(cfg, [(1, ""), (2, rd.digest(shadow))])
    rd.run_n1(T, T, 2, LOG)
    assert called() is None   # 第 2 批算的就是現在這份
    shadow.write_text("date,stock_id,pred_c2v2d\n")
    with caplog.at_level(logging.INFO):
        rd.run_n1(T, T, 2, LOG)
    assert called() is None and "已經算了 2 批" in caplog.text
    assert rd.n1_batches(write_n1(cfg, [(1, "a"), (2, "b")])) == (2, "b")
    assert rd.n1_batches(Path(cfg["data"]["submission_dir"]) / "沒有.csv") == (0, None)


@pytest.mark.parametrize("mode, text", [("data", "n1 沒算（資料還不是 t 的"), ("state", "n1 沒算（狀態檔或套件版本對不上"),
                                        ("busy", "n1 沒算（上一次的 n1 還在跑"), ("crash", "n1 失敗（回傳碼 1")])
def test_child_failures_only_warn(n1, monkeypatch, caplog, mode, text):
    monkeypatch.setenv("N1_TEST_MODE", mode)
    with caplog.at_level(logging.WARNING):
        rd.run_n1(T, T, 2, LOG)
    assert text in caplog.text and "不影響交件" in caplog.text
    assert all(r.levelno <= logging.WARNING for r in caplog.records)


def test_a_child_past_its_timeout_is_killed_and_only_warns(n1, monkeypatch, caplog):
    monkeypatch.setenv("N1_TEST_MODE", "sleep")
    real_run = subprocess.run

    def short(command, **kwargs):   # 150 秒太久：同一條路，只把逾時改成 1 秒
        assert kwargs["timeout"] <= 150
        return real_run(command, **{**kwargs, "timeout": 1})

    monkeypatch.setattr(rd.subprocess, "run", short)
    with caplog.at_level(logging.WARNING):
        rd.run_n1(T, T, 2, LOG)
    assert "子程序砍掉了" in caplog.text
    pid = int((Path(os.environ["N1_TEST_DIR"]) / "pid").read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_the_timeout_never_runs_past_finish_by(n1, monkeypatch):
    cfg, _, clock = n1
    seen = []
    monkeypatch.setattr(rd.subprocess, "run", lambda command, **kw: seen.append(kw["timeout"])
                        or subprocess.CompletedProcess(command, 0, "", ""))
    rd.run_n1(T, T, 2, LOG)
    clock("08:44:00")
    rd.run_n1(T, T, 2, LOG)
    assert seen == [150.0, 150.0]   # 到 08:58 還有 14 分鐘：用 timeout_seconds
    cfg["daily_model"]["n1"]["finish_by"] = "08:45"
    rd.run_n1(T, T, 2, LOG)
    assert seen[-1] == pytest.approx(60.0)   # 到 finish_by 只剩 60 秒


def test_the_timeout_leaves_the_next_cron_slot_free(n1, monkeypatch, caplog):
    """審查 M1：n1 跑的時候 run_daily 的鎖還拿著，下一個時段拿不到鎖會整個跳過。逾時不超過到下一個時段的秒數
    減 slot_margin_seconds（留給 commit、push），不到 30 秒就不叫。沒有 next_slots 時和以前一樣。"""
    cfg, called, clock = n1
    conf = cfg["daily_model"]["n1"]
    seen = []
    monkeypatch.setattr(rd.subprocess, "run", lambda command, **kw: seen.append(kw["timeout"])
                        or subprocess.CompletedProcess(command, 0, "", ""))
    clock("07:23:30")
    rd.run_n1(T, T, 2, LOG)
    assert seen == [150.0]   # 沒有 next_slots：只看 timeout_seconds 和 finish_by
    conf.update(next_slots=SLOTS, slot_margin_seconds=90)
    with caplog.at_level(logging.INFO):
        rd.run_n1(T, T, 2, LOG)   # 到 07:25 只剩 90 秒，扣掉 90 秒：不叫
    assert seen == [150.0] and "下一個排程時段 07:25" in caplog.text and "這次不算" in caplog.text
    for hhmm, want in [("07:22", 90.0), ("07:20", 150.0), ("07:25", 150.0), ("08:03", 30.0), ("08:40", 150.0)]:
        clock(hhmm)   # 07:25 正好是時段：看下一個 07:40；08:25 以後沒有時段，只看 finish_by
        rd.run_n1(T, T, 2, LOG)
        assert seen[-1] == pytest.approx(want), hhmm
    assert len(seen) == 6


def test_next_slots_are_the_morning_cron_times():
    """next_slots 要和 deploy/crontab.txt 早上的時段一樣（改排程時兩邊一起改）。"""
    conf = utils.load_config()["daily_model"]["n1"]
    morning = []
    for line in (ROOT / "deploy" / "crontab.txt").read_text().splitlines():
        parts = line.split()
        if len(parts) > 5 and parts[0].isdigit() and "run_daily.py" in line and "--evening" not in line:
            morning.append(f"{int(parts[1]):02d}:{int(parts[0]):02d}")
    assert conf["next_slots"] == sorted(morning) == SLOTS
    # 留的秒數要夠一次 git 呼叫卡到逾時、再等 PUSH_WAIT 推第二次（第二輪審查）
    assert conf["slot_margin_seconds"] >= inspect.signature(rd.git).parameters["timeout"].default + rd.PUSH_WAIT


def test_child_output_that_is_not_utf8_still_logs(n1, monkeypatch, caplog):
    """審查 m5：子程序的輸出用 UTF-8 解碼、解不開的換成替代字元，不照 cron 的語系，也不丟 UnicodeDecodeError。"""
    monkeypatch.setenv("N1_TEST_MODE", "bytes")
    with caplog.at_level(logging.INFO):
        rd.run_n1(T, T, 2, LOG)
    assert "n1 完成" in caplog.text and "ok" in caplog.text and "沒做完" not in caplog.text


@pytest.mark.parametrize("code, text", [("0", "n1 完成"), ("2", "n1 沒算（資料還不是 t 的"), ("1", "n1 失敗（回傳碼 1")])
def test_child_output_never_puts_the_home_directory_in_the_log(n1, monkeypatch, caplog, code, text):
    """第二輪審查：.venv-n1 壞掉時 Python 在 import 套件就印 traceback，沒經過 m7 的 public，帶著 repo 和家目錄的
    絕對路徑。run_<t>.log 會推上 GitHub，run_n1 寫進 log 前先換成 . 和 ~（和 test_rank_ensemble 的備援 log 一樣）。"""
    monkeypatch.setenv("N1_TEST_MODE", "leak")
    monkeypatch.setenv("N1_TEST_ROOT", str(rd.ROOT))
    monkeypatch.setenv("N1_TEST_CODE", code)
    with caplog.at_level(logging.INFO):
        rd.run_n1(T, T, 2, LOG)
    assert text in caplog.text
    assert "./src/models/m7_n1_js_online.py" in caplog.text and "~/x/.venv-n1" in caplog.text
    assert str(rd.ROOT) not in caplog.text and str(Path.home()) not in caplog.text


# ---------------------------------------------------------------- 收尾照常


@pytest.fixture
def wrap(monkeypatch):
    rd.import_src()
    steps = []
    for name in ("fill_today_open", "merge_raw_data"):
        monkeypatch.setattr(rd, name, lambda *args, _name=name, **kwargs: steps.append(_name))
    monkeypatch.setattr(rd, "commit_data", lambda message: steps.append(("commit", message)) or True)
    monkeypatch.setattr(rd, "push", lambda log: steps.append("push") or True)
    return steps


@pytest.mark.parametrize("failure", [subprocess.TimeoutExpired(["python"], 150), RuntimeError("子程序當掉"),
                                     OSError("exec format error")])
def test_wrap_up_commits_and_pushes_whatever_n1_does(n1, wrap, monkeypatch, caplog, failure):
    def broken(command, **kwargs):
        wrap.append("n1")
        raise failure

    monkeypatch.setattr(rd.subprocess, "run", broken)
    with caplog.at_level(logging.WARNING):
        assert rd.wrap_up(rd.parse_args(["--sync"]), T, T, 2, "submitted", False, True, LOG) is True
    assert wrap == ["fill_today_open", "merge_raw_data", "n1", ("commit", f"Daily run {T} (Phase 2): submitted"), "push"]
    assert "n1" in caplog.text and "不影響交件" in caplog.text


def test_wrap_up_skips_n1_on_closed_interrupted_and_evening_runs(wrap, monkeypatch):
    monkeypatch.setattr(rd, "run_n1", lambda t, today, phase, log: wrap.append("n1"))
    rd.wrap_up(rd.parse_args(["--sync"]), T, T, 2, "closed", False, True, LOG)
    rd.wrap_up(rd.parse_args(["--sync"]), T, T, 2, "submitted", True, True, LOG)
    rd.wrap_up(rd.parse_args(["--sync", "--evening"]), T, T, 2, "scored", False, True, LOG)
    assert "n1" not in wrap
    rd.wrap_up(rd.parse_args([]), T, T, 2, "submitted", False, True, LOG)
    assert wrap[-2:] == ["merge_raw_data", "n1"]   # 沒有 --sync 也算（commit 由排程那份做）


def test_wrap_up_skips_n1_when_the_run_stopped_or_is_a_dry_run(wrap, monkeypatch):
    """審查 M1、m3：這次停下了（failed）時不跑 n1，下一個時段才準時拿到鎖；--dry-run 不用掉當天的一批。
    補開盤、合併、commit、push 照常。"""
    monkeypatch.setattr(rd, "run_n1", lambda t, today, phase, log: wrap.append("n1"))
    rd.wrap_up(rd.parse_args(["--sync"]), T, T, 2, "failed", False, True, LOG)
    assert wrap == ["fill_today_open", "merge_raw_data", ("commit", f"Daily run {T} (Phase 2): failed"), "push"]
    wrap.clear()
    rd.wrap_up(rd.parse_args(["--sync", "--dry-run"]), T, T, 2, "submitted", False, True, LOG)
    assert wrap == ["fill_today_open", "merge_raw_data", ("commit", f"Daily run {T} (Phase 2): submitted"), "push"]
    wrap.clear()
    rd.wrap_up(rd.parse_args(["--sync"]), T, T, 2, "already_submitted", False, True, LOG)
    assert "n1" in wrap


def test_n1_temp_files_are_never_committed():
    """審查 m1：n1 寫到一半被砍掉時留下的暫存檔（.<檔名>.<亂碼>.tmp）在 .gitignore 裡，commit_data 的
    git add -- data/submission 不會帶上；n1 的核對檔照常追蹤。"""
    def ignored(rel):
        return subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT, capture_output=True).returncode == 0

    assert ignored("data/submission/n1/.n1_2026-11-24.csv.a1b2c3.tmp")
    assert ignored("data/submission/n1/.inputs_2026-11-24.npz.x9y8.tmp")
    assert ignored("data/submission/.shadow_2026-11-24.csv.k3j4.tmp")
    assert not ignored("data/submission/n1/n1_2026-11-24.csv") and not ignored("data/submission/n1/inputs_2026-11-24.npz")
    assert not ignored("data/submission/shadow_2026-11-24.csv")


# ---------------------------------------------------------------- 打分


def answers(day, returns):
    data = pd.DataFrame({"date": pd.to_datetime([day] * len(STOCKS)), "stock_id": STOCKS,
                         "label_intraday_return": [returns[s] for s in STOCKS]})
    data["label_y"] = (data["label_intraday_return"] > 0).astype(int)
    return data


def test_shadow_scores_reads_both_n1_batches(tmp_path, caplog):
    cfg = {"data": {"submission_dir": str(tmp_path)}}
    pd.DataFrame({"date": T, "stock_id": STOCKS, "pred_c2v2d": [PRED_B[s] for s in STOCKS]}).to_csv(
        tmp_path / f"shadow_{T}.csv", index=False)
    (tmp_path / "n1").mkdir()
    first = {"run": 1, "date": T, "stock_id": STOCKS, "pred_n1": [PRED_B[s] for s in STOCKS],
             "pred_js_n1": [PRED_B[s] for s in STOCKS]}
    second = {**first, "run": 2, "pred_n1": [PRED_A[s] for s in STOCKS]}
    pd.concat([pd.DataFrame(first), pd.DataFrame(second)]).to_csv(tmp_path / "n1" / f"n1_{T}.csv", index=False)
    pd.DataFrame({**first, "date": "2026-11-16", "pred_n1": np.nan}).to_csv(tmp_path / "n1" / "n1_2026-11-16.csv",
                                                                            index=False)   # N1 空白的日子
    (tmp_path / "n1" / "inputs_2026-11-17.npz").write_bytes(b"x")   # 不是 n1_<日期>.csv：不讀
    with caplog.at_level(logging.INFO):
        tp.shadow_scores(cfg, pd.concat([answers(T, RET), answers("2026-11-16", RET)]), LOG)
    table = pd.read_csv(tmp_path / tp.SHADOW_SCORES, dtype={"date": str})
    got = {(r.date, r.model): r.score for r in table.itertuples()}
    assert got[(T, "n1")] == pytest.approx(official(PRED_A))   # 最後一批
    assert got[(T, "n1_run1")] == pytest.approx(official(PRED_B)) and (T, "js_n1_run1") in got
    assert got[(T, "js_n1")] == pytest.approx(official(PRED_B)) and got[(T, "c2v2d")] == pytest.approx(official(PRED_B))
    assert ("2026-11-16", "n1") not in got and ("2026-11-16", "js_n1") in got
    assert "n1 影子跑 1 天：累計 n1 − c2v2d" in caplog.text


def ledger_of(days, n1_minus_c2v2d):
    rows = []
    for day, gap in zip(days, n1_minus_c2v2d):
        rows += [{"date": day, "model": "c2v2d", "score": 0.001}, {"date": day, "model": "n1", "score": 0.001 + gap},
                 {"date": day, "model": "persist", "score": 0.5}]
    return pd.DataFrame(rows)


def test_n1_compare_applies_the_stop_rule_on_the_first_five_days(caplog):
    cfg = utils.load_config()
    days = ["2026-11-24", "2026-11-25", "2026-11-26", "2026-11-27", "2026-11-30", "2026-12-01"]
    with caplog.at_level(logging.INFO):
        tp.n1_compare(cfg, ledger_of(days[:3], [-0.004] * 3), LOG)
    assert "n1 影子跑 3 天：累計 n1 − c2v2d = -0.01200" in caplog.text
    caplog.clear()
    with caplog.at_level(logging.INFO):
        tp.n1_compare(cfg, ledger_of(days, [-0.002] * 5 + [0.05]), LOG)
    warned = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warned) == 1 and "累計 n1 − c2v2d = -0.01000" in warned[0].getMessage()
    assert "低於停止線" in warned[0].getMessage() and "共 6 天累計 +0.04000" in warned[0].getMessage()
    caplog.clear()
    with caplog.at_level(logging.INFO):
        tp.n1_compare(cfg, ledger_of(days, [-0.001] * 6), LOG)
    assert "沒有低於停止線" in caplog.text and not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_evening_scoring_scores_the_n1_file_and_waits_for_it(env):
    cfg, site, _, _ = env
    write_n1(cfg, [(1, "sha")])
    table = pd.read_csv(Path(cfg["data"]["submission_dir"]) / "n1" / f"n1_{T}.csv", dtype={"stock_id": str})
    table["pred_n1"] = table["stock_id"].map(PRED_A)
    table["pred_js_n1"] = table["stock_id"].map(PRED_B)
    table.to_csv(Path(cfg["data"]["submission_dir"]) / "n1" / f"n1_{T}.csv", index=False)
    assert evening(env) == "scored"
    scores = ledger(env).set_index("model")
    assert scores.loc["n1", "score"] == pytest.approx(official(PRED_A)) and scores.loc["n1", "source"] == "live"
    assert scores.loc["js_n1", "score"] == pytest.approx(official(PRED_B))
    assert evening(env) == "done_before"
    pd.read_csv(Path(cfg["data"]["submission_dir"]) / tp.SHADOW_SCORES).query("model not in ['n1', 'js_n1']").to_csv(
        Path(cfg["data"]["submission_dir"]) / tp.SHADOW_SCORES, index=False)
    assert evening(env) == "scored"   # n1 的列不見了：還沒打完


def test_evening_scoring_with_only_an_n1_file(env):
    cfg, site, _, _ = env
    tp.shadow_path(cfg, T).unlink()
    write_n1(cfg, [(1, "")])
    assert evening(env) == "scored"
    assert set(ledger(env)["model"]) == {"n1", "js_n1"}
    assert evening(env) == "done_before"


@pytest.mark.parametrize("text", [
    "run,date,pred_n1\n1,2026-11-17,1\n",                                                    # 少了 stock_id
    "".join(["run,date,stock_id,pred_n1\n"] + [f"1,{T},{s},2\n" for s in STOCKS]),           # pred 不是 0／1
    "".join(["run,date,stock_id,pred_n1\n"] + [f"x,{T},{s},1\n" for s in STOCKS]),           # run 不是數字
    "".join(["run,date,stock_id,pred_n1\n"] + [f"1,{T},{s},1\n" for s in [*STOCKS, "9999"]]),  # Live 沒有的代號
])
def test_a_broken_n1_file_never_stops_the_evening_scoring(env, caplog, text):
    """審查 m2：n1 只記不交。n1_<t>.csv 有問題時只記 WARNING，影子跑和網站上那份照常打分、照常寫檔。"""
    cfg, _, _, _ = env
    folder = Path(cfg["data"]["submission_dir"]) / "n1"
    folder.mkdir()
    (folder / f"n1_{T}.csv").write_text(text)
    with caplog.at_level(logging.WARNING):
        assert evening(env) == "scored"
    assert site_scores(env)["date"].tolist() == [T]
    models = set(ledger(env)["model"])
    assert models == {"a", "b"}   # n1 沒有分數，其他模型照常
    assert not [r for r in caplog.records if r.levelno > logging.WARNING]


def test_a_broken_n1_file_never_stops_the_morning_shadow_scores(tmp_path, caplog, monkeypatch):
    """審查 m2：早上的 shadow_scores 也一樣。n1 打分或累計比較丟錯時只記 WARNING，其他模型的分數照寫。"""
    cfg = {"data": {"submission_dir": str(tmp_path)}}
    pd.DataFrame({"date": T, "stock_id": STOCKS, "pred_c2v2d": [PRED_B[s] for s in STOCKS]}).to_csv(
        tmp_path / f"shadow_{T}.csv", index=False)
    (tmp_path / "n1").mkdir()
    pd.DataFrame({"run": 1, "date": T, "stock_id": STOCKS, "pred_n1": [PRED_A[s] for s in STOCKS]}).to_csv(
        tmp_path / "n1" / f"n1_{T}.csv", index=False)
    real, calls = tp.online_lr.official_score, []

    def flaky(part, data):   # 影子檔先打分；之後 n1 那一個丟錯
        calls.append(1)
        if len(calls) > 1:
            raise RuntimeError("壞了")
        return real(part, data)

    monkeypatch.setattr(tp.online_lr, "official_score", flaky)
    with caplog.at_level(logging.WARNING):
        tp.shadow_scores(cfg, answers(T, RET), LOG)
    got = {r.model: r.score for r in pd.read_csv(tmp_path / tp.SHADOW_SCORES).itertuples()}
    assert got == {"c2v2d": pytest.approx(official(PRED_B))} and "打不了分" in caplog.text

    monkeypatch.setattr(tp.online_lr, "official_score", real)
    monkeypatch.setattr(tp, "n1_compare", lambda *args: 1 / 0)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        tp.shadow_scores(cfg, answers(T, RET), LOG)
    got = {r.model: r.score for r in pd.read_csv(tmp_path / tp.SHADOW_SCORES).itertuples()}
    assert got["c2v2d"] == pytest.approx(official(PRED_B)) and got["n1"] == pytest.approx(official(PRED_A))
    assert "累計比較沒做完" in caplog.text


# ---------------------------------------------------------------- gspc 不進特徵表和合併表


def test_gspc_raw_file_changes_neither_the_feature_table_nor_the_merge(tmp_path, monkeypatch):
    days = ["2025-10-30", "2025-10-31", "2025-11-03", "2025-11-04"]
    cfg = fake_repo(tmp_path, monkeypatch, days)
    assert cfg["yfinance"]["extra_tickers"] == {"gspc": "^GSPC"}   # 真的設定，不是測試另外拿掉
    assert features.main(["--date", "2025-11-05"]) == 0
    processed = tmp_path / "data" / "processed"
    before, info_before = features.load_features(processed), json.loads((processed / "manifest.json").read_text())
    yf = tmp_path / "data" / "raw" / "yfinance"
    (yf / "gspc.csv").write_bytes(crawler.rows_to_csv([[d] + [str(6000.0 + j)] * 5 + ["0"] for j, d in enumerate(days)]))
    assert features.main(["--date", "2025-11-05", "--rebuild"]) == 0
    after, info_after = features.load_features(processed), json.loads((processed / "manifest.json").read_text())
    pd.testing.assert_frame_equal(before, after)
    assert info_after["columns"] == info_before["columns"] and info_after["model_columns"] == info_before["model_columns"]
    assert not any("gspc" in c and not c.startswith("teacher_") for c in info_after["columns"])
    assert "gspc" not in features.load_raw(cfg)["yfinance"]
    files = merge_raw.source_files(tmp_path / "data" / "raw", cfg)
    assert yf / "gspc.csv" not in files and all(p.name != "gspc.csv" for p in files)
