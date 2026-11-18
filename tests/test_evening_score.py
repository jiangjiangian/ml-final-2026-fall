"""傍晚打分（使用者 2026-11-17）：step6_evening_score、shadow_scores 的合併、run_daily.py --evening。

老師 Live 用真的 ZIP 格式（照 step1_crawler 的欄位做），只把下載換成假的；網站換成假的，上傳一律丟錯。不連網。
"""

import csv
import io
import json
import logging
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import run_daily as rd
from src.pipeline import site_api, step1_crawler as crawler, step3_train_predict as tp, step6_evening_score as ev, utils

LOG = logging.getLogger("test_evening")
T, PREV = "2026-11-17", "2026-11-16"
STOCKS = ["1101", "2317", "2330", "2454"]
RET = {"1101": 0.03, "2317": -0.02, "2330": 0.01, "2454": -0.005}
TOP100 = STOCKS + [str(9000 + i) for i in range(96)]
PRED_A = {"1101": 1, "2317": 0, "2330": 1, "2454": 0}
PRED_B = {"1101": 0, "2317": 0, "2330": 0, "2454": 0}
SECRETS = {"COURSE_LIVE_KEY": "live-key-秘密", "COURSE_EMAIL": "me@example.com", "COURSE_PASSWORD": "pw-秘密"}
PRIVATE = ["我們的隊名XYZ", "別隊甲", "別隊乙", "TEAMCODE77", "member@example.com", "me@example.com", "live-key-秘密",
           "pw-秘密"]


def official(pred: dict) -> float:
    return float(np.mean([(2 * pred[s] - 1) * RET[s] for s in STOCKS]))


def stock_csv(code: str, t_filled: bool) -> bytes:
    """老師個股檔：PREV、T 兩列。T 那列沒填好時 y、還原開盤、收盤都是 -1（老師早上的樣子）。"""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(crawler.STOCK_COLUMNS)
    for d, filled in ((PREV, True), (T, t_filled)):
        r = RET.get(code, 0.001) if d == T else 0.002
        cells = ["1"] * len(crawler.STOCK_COLUMNS)
        cells[0] = d
        cells[crawler.COL_OPEN] = "100" if filled else "-1"
        cells[crawler.COL_CLOSE] = repr(100 * (1 + r)) if filled else "-1"
        cells[crawler.COL_Y] = ("1" if r > 0 else "0") if filled else "-1"
        writer.writerow(cells)
    return out.getvalue().encode()


def live_zip(unfilled=()) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        rows = [",".join(crawler.GLOBAL_COLUMNS)] + [",".join([d] + ["1"] * 6) for d in (PREV, T)]
        zf.writestr("data/global/global_data.csv", "\n".join(rows) + "\n")
        for code in TOP100:
            zf.writestr(f"data/market/{code}.csv", stock_csv(code, code not in unfilled))
    return buffer.getvalue()


class FakeSite:
    """網站：state 可以換；download 回傳我們那份；post_submission 一律丟錯（傍晚不能上傳）。"""

    def __init__(self, state, rows):
        self.state_value, self.rows, self.downloads = state, rows, []

    def state(self):
        return json.loads(json.dumps(self.state_value))

    def download(self, submission_id):
        self.downloads.append(submission_id)
        return self.rows

    def post_submission(self, body):
        raise AssertionError("傍晚打分不能上傳")

    def close(self):
        pass


def site_state(score=None, days=((T, 1),)):
    sent = official(PRED_A) if score is None else score
    return {
        "phase2Days": [{"tradingDate": d, "enabled": e, "isCompetition": 1} for d, e in days],
        "team": {"id": "team-us", "name": "我們的隊名XYZ", "code": "TEAMCODE77",
                 "members": [{"email": "member@example.com"}]},
        "user": {"email": "me@example.com", "displayName": "我們的隊名XYZ"},
        "mySubmissions": [{"phase": 2, "tradingDate": T, "id": "sub-9", "fileName": "submission_2026-11-17.csv",
                           "score": sent, "submittedAt": "2026-11-16 23:29:00"}],
        "phase2Leaderboards": {T: [{"teamId": "team-us", "teamName": "我們的隊名XYZ", "score": sent},
                                   {"teamId": "x1", "teamName": "別隊甲", "score": 0.05},
                                   {"teamId": "x2", "teamName": "別隊乙", "score": None}]},
        "phase2CompetitionCumulative": [
            {"teamId": "x1", "teamName": "別隊甲", "totalScore": 0.06, "totalRank": 1, "scoredDays": 2,
             "forcedSubmissionDays": 2},
            {"teamId": "team-us", "teamName": "我們的隊名XYZ", "totalScore": 0.0126, "totalRank": 2, "scoredDays": 2,
             "forcedSubmissionDays": 0},
            {"teamId": "x2", "teamName": "別隊乙", "totalScore": 0.001, "totalRank": 3, "scoredDays": 2,
             "forcedSubmissionDays": 1}],
    }


@pytest.fixture
def env(monkeypatch, tmp_path):
    """暫存的 data/raw、data/submission；Live 下載換成回傳 env["zip"]；現在是台北 T 的 18:00。"""
    raw, sub = tmp_path / "raw", tmp_path / "submission"
    (raw / "teacher" / "training").mkdir(parents=True)
    (raw / "teacher" / "training" / "info.json").write_text(json.dumps({"Top50@Y": TOP100[:50], "Top100@Y": TOP100}))
    (raw / "manifest.json").write_text(json.dumps({"run": {"target_date": T, "status": "ok"},
                                                    "teacher_live": {"status": "ok", "zip_sha256": "morning"}}))
    sub.mkdir()
    pd.DataFrame({"date": T, "stock_id": STOCKS, "pred_a": [PRED_A[s] for s in STOCKS],
                  "prob_a": 0.5, "pred_b": [PRED_B[s] for s in STOCKS], "pred_c": np.nan}).to_csv(
        sub / f"shadow_{T}.csv", index=False)
    cfg = {"data": {"submission_dir": str(sub), "raw_dir": str(raw)},
           "course_site": {"max_zip_mb": 100, "max_unzipped_mb": 512, "live": {"zip": "/data.zip"}}}
    box = {"zip": live_zip(), "calls": 0}

    def download(client, cfg, key):
        assert key == SECRETS["COURSE_LIVE_KEY"]
        box["calls"] += 1
        if isinstance(box["zip"], Exception):
            raise box["zip"]
        return box["zip"]

    class Client:
        base = "https://live.example"

    monkeypatch.setattr(crawler, "live_download", download)
    monkeypatch.setattr(crawler, "live_clients", lambda cfg: [Client(), Client()])
    fixed = datetime(2026, 11, 17, 18, 0, tzinfo=utils.TAIPEI)
    monkeypatch.setattr(utils, "taipei_now", lambda now=None: fixed if now is None else now)
    rows = [["id", T]] + [[s, str(PRED_A[s])] for s in STOCKS]
    return cfg, FakeSite(site_state(), rows), box, tmp_path


def run(env, phase=2):
    cfg, site, _, _ = env
    return ev.main(cfg, phase, T, LOG, site=site, secrets=SECRETS)


def site_scores(env):
    return pd.read_csv(Path(env[0]["data"]["submission_dir"]) / ev.SITE_SCORES, dtype={"date": str})


def ledger(env):
    return pd.read_csv(Path(env[0]["data"]["submission_dir"]) / tp.SHADOW_SCORES, dtype={"date": str})


# ---------------------------------------------------------------- 傍晚打分


def test_the_shadow_and_our_submission_are_scored_from_the_live_t_row(env, caplog):
    cfg, site, box, tmp = env
    with caplog.at_level(logging.INFO):
        assert run(env) == "scored"
    scores = ledger(env)
    assert scores[["date", "model", "source"]].values.tolist() == [[T, "a", "live"], [T, "b", "live"]]
    assert scores["score"].tolist() == pytest.approx([official(PRED_A), official(PRED_B)])
    assert scores["accuracy"].tolist() == [1.0, 0.5] and (scores["cells"] == 4).all()
    row = site_scores(env).iloc[0]
    assert list(site_scores(env).columns) == ev.SITE_COLUMNS
    assert row["date"] == T and row["file"] == "submission_2026-11-17.csv" and row["same_as"] == "a"
    assert row["site_score"] == pytest.approx(official(PRED_A)) and row["rescored"] == pytest.approx(official(PRED_A))
    assert row["all_zero"] == pytest.approx(-np.mean(list(RET.values())))
    assert (row["day_rank"], row["day_teams"]) == (2, 2)   # 別隊甲 0.05 比我們高；沒分數的不算
    assert (row["total_score"], row["total_rank"], row["teams"]) == (0.0126, 2, 3)
    assert (row["all_forced_teams"], row["self_rank"]) == (1, 1)   # 別隊甲每天都是強制繳交
    assert row["read_at"] == "2026-11-17 18:00" and site.downloads == ["sub-9"]
    live = tmp / "raw" / "teacher" / "live"
    assert (live / "market" / "2330.csv").read_bytes() == stock_csv("2330", True)
    manifest = json.loads((tmp / "raw" / "manifest.json").read_text())
    assert manifest["run"] == {"target_date": T, "status": "ok"}   # 爬蟲的紀錄不動
    assert manifest["teacher_live"]["zip_sha256"] == crawler.sha256_bytes(box["zip"])
    assert manifest["teacher_live"]["date_max"] == T and manifest["teacher_live"]["status"] == "ok"
    assert manifest["teacher_live"]["evening_refresh"] == {"t": T, "time": "2026-11-17 18:00",
                                                           "source": "live.example/data.zip"}
    assert "傍晚打分：全猜 0" in caplog.text and "和 a 一樣" in caplog.text


def test_nothing_is_written_until_every_stock_has_a_filled_t_row(env, caplog):
    cfg, site, box, tmp = env
    box["zip"] = live_zip(unfilled=("2454",))
    before = (tmp / "raw" / "manifest.json").read_text()
    with caplog.at_level(logging.WARNING):
        assert run(env) == "no_answer_yet"
    assert "還有 1 檔沒填好（['2454']）" in caplog.text
    sub = Path(cfg["data"]["submission_dir"])
    assert not (sub / tp.SHADOW_SCORES).exists() and not (sub / ev.SITE_SCORES).exists()
    assert not (tmp / "raw" / "teacher" / "live").exists()
    assert (tmp / "raw" / "manifest.json").read_text() == before


def test_a_stock_we_do_not_score_may_still_be_unfilled(env):
    cfg, site, box, tmp = env
    box["zip"] = live_zip(unfilled=("9001",))   # 停牌之類，不在我們的 50 檔
    assert run(env) == "scored"


def test_a_finished_day_is_not_redone_and_a_missing_site_score_is_retried(env):
    cfg, site, box, _ = env
    site.state_value["mySubmissions"][0]["score"] = None   # 18:00 網站還沒算分
    assert run(env) == "scored_waiting_site"
    assert pd.isna(site_scores(env).iloc[0]["site_score"]) and box["calls"] == 1
    site.state_value = site_state()
    assert run(env) == "scored"   # 20:00：補上
    assert len(site_scores(env)) == 1 and site_scores(env).iloc[0]["site_score"] == pytest.approx(official(PRED_A))
    assert box["calls"] == 2
    assert run(env) == "done_before" and box["calls"] == 2   # 之後再跑：不下載


def test_without_a_shadow_file_only_our_submission_is_scored(env):
    cfg, site, box, _ = env
    tp.shadow_path(cfg, T).unlink()
    assert run(env) == "scored"
    assert not (Path(cfg["data"]["submission_dir"]) / tp.SHADOW_SCORES).exists()
    row = site_scores(env).iloc[0]
    assert pd.isna(row["same_as"]) and row["rescored"] == pytest.approx(official(PRED_A))
    assert run(env) == "done_before"


def test_closed_days_and_phase_1_do_nothing(env):
    cfg, site, box, _ = env
    site.state_value = site_state(days=((PREV, 1),))
    assert run(env) == "closed"
    assert run(env, phase=1) == "not_phase2"
    assert box["calls"] == 0 and site.downloads == []
    assert not (Path(cfg["data"]["submission_dir"]) / ev.SITE_SCORES).exists()


def test_a_live_download_error_waits_for_the_next_run(env, caplog):
    cfg, site, box, _ = env
    box["zip"] = crawler.TransientError("連不上")
    with caplog.at_level(logging.WARNING):
        assert run(env) == "no_answer_yet"
    assert box["calls"] == 2   # 原本的網址和備用網址各一次，不等待
    assert "老師 Live 下載失敗" in caplog.text
    assert not (Path(cfg["data"]["submission_dir"]) / ev.SITE_SCORES).exists()


def test_a_site_score_that_differs_from_the_live_answer_warns(env, caplog):
    cfg, site, _, _ = env
    site.state_value = site_state(score=official(PRED_A) + 0.001)
    with caplog.at_level(logging.WARNING):
        assert run(env) == "scored"
    assert "用老師 Live 重算是" in caplog.text and "不一樣" in caplog.text


def test_a_strange_submitted_file_is_not_rescored(env, caplog):
    cfg, site, _, _ = env
    site.rows = [["id", PREV]] + site.rows[1:]
    with caplog.at_level(logging.WARNING):
        assert run(env) == "scored"
    row = site_scores(env).iloc[0]
    assert pd.isna(row["rescored"]) and pd.isna(row["same_as"]) and "格式和預期不一樣" in caplog.text


def test_no_team_name_account_or_secret_reaches_files_or_the_log(env, caplog):
    cfg, site, _, tmp = env
    with caplog.at_level(logging.DEBUG):
        assert run(env) == "scored"
    texts = [caplog.text] + [p.read_text(encoding="utf-8", errors="replace") for p in tmp.rglob("*")
                             if p.is_file() and p.suffix in (".csv", ".json")]
    for text in texts:
        for word in PRIVATE:
            assert word not in text


def test_without_our_team_id_no_rank_is_recorded_and_ranks_stay_integers(env):
    cfg, site, _, _ = env
    del site.state_value["team"]   # 對不到我們這隊：不能把沒有 teamId 的那列當成我們
    for row in site.state_value["phase2CompetitionCumulative"]:
        row.pop("teamId")
    assert run(env) == "scored"
    row = site_scores(env).iloc[0]
    assert pd.isna(row["day_rank"]) and pd.isna(row["total_score"]) and pd.isna(row["self_rank"])
    assert row["teams"] == 3 and row["all_forced_teams"] == 1
    ev.write_site_scores(cfg, {**dict.fromkeys(ev.SITE_COLUMNS), "date": PREV, "total_rank": 2, "teams": 3})
    text = (Path(cfg["data"]["submission_dir"]) / ev.SITE_SCORES).read_text()
    assert ",2.0," not in text and ",3.0," not in text and len(site_scores(env)) == 2


def test_a_failed_download_still_scores_the_shadow(env, caplog):
    cfg, site, _, _ = env

    def broken(submission_id):
        raise site_api.SiteError("下載壞了")

    site.download = broken
    with caplog.at_level(logging.WARNING):
        assert run(env) == "scored"
    assert "下載網站上我們那份失敗（SiteError: 下載壞了）" in caplog.text
    assert set(ledger(env)["model"]) == {"a", "b"}
    row = site_scores(env).iloc[0]
    assert pd.isna(row["rescored"]) and row["site_score"] == pytest.approx(official(PRED_A))


def test_a_manual_file_name_is_not_stored(env, caplog):
    cfg, site, _, tmp = env
    site.state_value["mySubmissions"][0]["fileName"] = "submission_2026-11-17_張三.csv"
    with caplog.at_level(logging.INFO):
        assert run(env) == "scored"
    assert site_scores(env).iloc[0]["file"] == "other"
    texts = [caplog.text] + [p.read_text(encoding="utf-8") for p in tmp.rglob("*.csv")]
    assert all("張三" not in text for text in texts)


def test_a_site_score_rounded_to_seven_decimals_does_not_warn(env, caplog):
    cfg, site, _, _ = env
    site.state_value = site_state(score=round(official(PRED_A), 7))
    with caplog.at_level(logging.WARNING):
        assert run(env) == "scored"
    assert "用老師 Live 重算是" not in caplog.text


def test_no_live_key_stops_with_a_short_message(env):
    cfg, site, _, _ = env
    with pytest.raises(ev.EveningError, match="COURSE_LIVE_KEY"):
        ev.main(cfg, 2, T, LOG, site=site, secrets={})


# ---------------------------------------------------------------- shadow_scores 的合併


def answers(day, returns):
    data = pd.DataFrame({"date": pd.to_datetime([day] * len(STOCKS)), "stock_id": STOCKS,
                         "label_intraday_return": [returns[s] for s in STOCKS]})
    data["label_y"] = (data["label_intraday_return"] > 0).astype(int)
    return data


def test_the_morning_rewrite_keeps_evening_rows_it_cannot_score(env):
    cfg, _, _, _ = env
    tp.shadow_scores(cfg, answers(T, RET), LOG, source="live")
    nothing = answers(PREV, {s: 0.0 for s in STOCKS})   # 隔天早上的特徵表沒有 T 的答案（例如爬蟲沒跑成）
    tp.shadow_scores(cfg, nothing, LOG)
    assert ledger(env)[["date", "model", "source"]].values.tolist() == [[T, "a", "live"], [T, "b", "live"]]


def test_the_same_morning_answer_is_quiet_and_a_different_one_warns_and_wins(env, caplog):
    cfg, _, _, _ = env
    tp.shadow_scores(cfg, answers(T, RET), LOG, source="live")
    with caplog.at_level(logging.WARNING):
        tp.shadow_scores(cfg, answers(T, RET), LOG)
    assert "不一樣" not in caplog.text and set(ledger(env)["source"]) == {"features"}
    changed = {**RET, "2330": -0.01}
    with caplog.at_level(logging.WARNING):
        tp.shadow_scores(cfg, answers(T, changed), LOG)
    assert "影子跑 2026-11-17 a 的分數和之前（答案來自 features）不一樣" in caplog.text
    got = ledger(env).set_index("model")["score"]
    assert got["a"] == pytest.approx(float(np.mean([(2 * PRED_A[s] - 1) * changed[s] for s in STOCKS])))


def test_an_old_ledger_without_source_still_reads_and_keeps_its_rows(env):
    cfg, _, _, _ = env
    sub = Path(cfg["data"]["submission_dir"])
    (sub / tp.SHADOW_SCORES).write_text("date,model,cells,score,accuracy,pred_up\n2026-11-16,c2v2d,50,0.0102,0.5,0.5\n")
    tp.shadow_scores(cfg, answers(T, RET), LOG, source="live")
    table = ledger(env)
    assert table[["date", "model", "source"]].values.tolist() == [
        ["2026-11-16", "c2v2d", "features"], [T, "a", "live"], [T, "b", "live"]]
    assert list(table.columns) == tp.LEDGER_COLUMNS


# ---------------------------------------------------------------- run_daily.py --evening


@pytest.fixture
def evening_run(monkeypatch):
    """run_daily.run 的外圍換成只記錄的假函式：不 pull、不碰 git、log 不寫進 repo。"""
    rd.import_src()
    steps = []
    monkeypatch.setattr(rd, "on_branch", lambda: True)
    monkeypatch.setattr(rd, "sync_with_github", lambda from_command_line: ([], None))
    monkeypatch.setattr(rd.utils, "get_logger", lambda name, t: LOG)
    monkeypatch.setattr(rd.utils, "load_config", lambda: {"submit": {"phase": 2}})
    monkeypatch.setattr(rd.utils, "taipei_now", lambda now=None: datetime(2026, 11, 17, 18, 0, tzinfo=utils.TAIPEI))
    monkeypatch.setattr(rd.evening_score, "main",
                        lambda cfg, phase, t, log: steps.append(("evening", phase, t)) or "scored")
    for name in ("submit_today", "fill_today_open", "merge_raw_data"):
        monkeypatch.setattr(rd, name, lambda *args, _name=name, **kwargs: steps.append(_name))
    monkeypatch.setattr(rd, "commit_data", lambda message: steps.append(("commit", message)) or True)
    monkeypatch.setattr(rd, "push", lambda log: steps.append("push") or True)
    return steps


def test_evening_runs_only_the_scoring_and_pushes_data(evening_run):
    assert rd.run(rd.parse_args(["--sync", "--evening"]), from_command_line=False) == 0
    assert evening_run == [("evening", 2, T), ("commit", f"Evening score {T} (Phase 2): scored"), "push"]


def test_evening_without_sync_does_not_touch_git(evening_run):
    assert rd.run(rd.parse_args(["--evening", "--date", PREV]), from_command_line=False) == 0
    assert evening_run == [("evening", 2, PREV)]


def test_the_morning_run_still_does_its_wrap_up(evening_run):
    assert rd.run(rd.parse_args(["--sync"]), from_command_line=False) == 0
    assert evening_run[0] == "submit_today" and "fill_today_open" in evening_run and "merge_raw_data" in evening_run
    assert ("commit", f"Daily run {T} (Phase 2): None") in evening_run
