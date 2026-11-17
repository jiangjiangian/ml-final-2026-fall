"""影子跑（使用者 2026-11-16）：step3_train_predict 的 shadow_predict、shadow_scores，和 run_daily.py 什麼時候做。
沒上傳的日子也補爬（使用者 2026-11-17）：run_daily.py 的 ensure_crawled、crawled。

模型都換成假函式，不訓練、不連網。
"""

import json
import logging
from datetime import datetime

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import run_daily as rd
from src.models import m1_online_lr as online_lr, m2_persist_rule as persist_rule, m3_rank_ensemble as rank_ensemble
from src.models import m4_c2_tilt as c2_tilt
from src.pipeline import step3_train_predict as tp, utils

LOG = logging.getLogger("test_shadow")
T = "2026-11-13"
STOCKS = ["2330", "2317", "1101", "2454"]   # 故意不照代號排：輸出要照代號排
KINDS = ["c2v2d", "c2", "rank_ensemble", "persist", "online_lr"]
BASE = {"base_pred": [1, 1, 0, 0], "base_prob": [0.8, 0.6, 0.4, 0.2]}


def frame(preds, stocks=STOCKS, **extra):
    """假的預測表：date、stock_id、prob、pred，加上 extra 的欄，列的順序照 stocks。"""
    out = pd.DataFrame({"date": T, "stock_id": stocks, "prob": np.linspace(0.1, 0.9, len(stocks)), "pred": preds})
    for name, value in extra.items():
        out[name] = value
    return out


def read(path):
    return pd.read_csv(path, dtype={"stock_id": str, "date": str}).set_index("stock_id")


@pytest.fixture
def models(monkeypatch, tmp_path):
    """五個模型換成假函式，記下呼叫順序；failing 裡的名字會丟錯。cfg 的 submission_dir 指到暫存資料夾。"""
    calls, failing = [], set()

    def fake(name, make):
        def predict(data, cfg, dates, stocks):
            calls.append(name)
            if name in failing:
                raise RuntimeError(f"{name} 壞了")
            assert dates == [T] and sorted(stocks) == sorted(STOCKS)
            return make()
        return predict

    monkeypatch.setattr(c2_tilt, "predict_c2v2d", fake("c2v2d", lambda: frame([1, 0, 1, 0], **BASE, p_up=0.7)))
    monkeypatch.setattr(c2_tilt, "predict_c2", fake("c2", lambda: frame([0, 1, 1, 0], **BASE, p_up=0.4)))
    monkeypatch.setattr(rank_ensemble, "predict", fake("rank_ensemble", lambda: frame([0, 0, 1, 1])))
    monkeypatch.setattr(persist_rule, "predict", fake("persist", lambda: frame([1, 1, 0, 0])))
    monkeypatch.setattr(online_lr, "predict", fake("online_lr", lambda: frame([1, 1, 1, 0])))
    cfg = {"daily_model": {"kind": "c2v2d", "shadow": list(KINDS)}, "data": {"submission_dir": str(tmp_path)}}
    return cfg, calls, failing


# ---------------------------------------------------------------- shadow_predict


def test_every_model_gets_its_columns_and_rank_ensemble_comes_from_c2v2d(models):
    cfg, calls, _ = models
    path = tp.shadow_predict(cfg, None, T, STOCKS, LOG)
    assert path == tp.shadow_path(cfg, T) and path.name == f"shadow_{T}.csv"
    assert calls == ["c2v2d", "c2", "persist", "online_lr"]   # rank_ensemble 沒有重新訓練
    table = pd.read_csv(path, dtype={"stock_id": str, "date": str})
    assert list(table.columns) == ["date", "stock_id", "pred_c2v2d", "prob_c2v2d", "p_up_c2v2d", "pred_c2", "prob_c2",
                                   "p_up_c2", "pred_rank_ensemble", "prob_rank_ensemble", "pred_persist",
                                   "prob_persist", "pred_online_lr", "prob_online_lr"]
    assert list(table["stock_id"]) == sorted(STOCKS) and set(table["date"]) == {T}
    by = table.set_index("stock_id").loc[STOCKS]
    assert by["pred_c2v2d"].tolist() == [1, 0, 1, 0] and by["pred_c2"].tolist() == [0, 1, 1, 0]
    assert by["pred_rank_ensemble"].tolist() == BASE["base_pred"]
    assert by["prob_rank_ensemble"].tolist() == pytest.approx(BASE["base_prob"])
    assert by["pred_persist"].tolist() == [1, 1, 0, 0] and by["pred_online_lr"].tolist() == [1, 1, 1, 0]
    assert (by["p_up_c2v2d"] == 0.7).all() and (by["p_up_c2"] == 0.4).all()


def test_the_prediction_already_made_is_used_as_it_is(models):
    cfg, calls, _ = models
    submitted = frame([0, 0, 0, 1], base_pred=[0, 1, 0, 1], base_prob=[0.1, 0.9, 0.2, 0.8], p_up=0.55)
    by = read(tp.shadow_predict(cfg, None, T, STOCKS, LOG, known={"c2v2d": submitted})).loc[STOCKS]
    assert "c2v2d" not in calls and "rank_ensemble" not in calls
    assert by["pred_c2v2d"].tolist() == [0, 0, 0, 1]
    assert by["pred_rank_ensemble"].tolist() == [0, 1, 0, 1]   # 從 c2v2d 拿（排在 c2 前面）
    assert (by["p_up_c2v2d"] == 0.55).all()


def test_a_failing_model_leaves_blank_columns_and_the_others_still_run(models, caplog):
    cfg, calls, failing = models
    failing.add("persist")
    with caplog.at_level(logging.INFO):
        by = read(tp.shadow_predict(cfg, None, T, STOCKS, LOG))
    assert by["pred_persist"].isna().all() and by["prob_persist"].isna().all()
    assert by["pred_online_lr"].notna().all() and by["pred_c2v2d"].notna().all()
    assert "persist 算不出來（RuntimeError: persist 壞了）" in caplog.text
    assert "算不出來 persist" in caplog.text


def test_rank_ensemble_trains_itself_when_both_tilt_models_fail(models):
    cfg, calls, failing = models
    failing.update({"c2v2d", "c2"})
    by = read(tp.shadow_predict(cfg, None, T, STOCKS, LOG)).loc[STOCKS]
    assert calls == ["c2v2d", "c2", "persist", "online_lr", "rank_ensemble"]
    assert by["pred_rank_ensemble"].tolist() == [0, 0, 1, 1]
    assert by["p_up_c2v2d"].isna().all() and by["pred_c2"].isna().all()


def test_bad_prediction_tables_count_as_failures(models, monkeypatch, caplog):
    cfg, _, _ = models
    monkeypatch.setattr(online_lr, "predict", lambda data, cfg, dates, stocks: frame([1, 0, 1], stocks=STOCKS[:3]))
    monkeypatch.setattr(persist_rule, "predict", lambda data, cfg, dates, stocks: frame([1, 2, 0, 0]))
    monkeypatch.setattr(rank_ensemble, "predict", lambda data, cfg, dates, stocks: pd.concat([frame([1, 0, 1, 0])] * 2))
    cfg["daily_model"]["shadow"] = ["persist", "online_lr", "rank_ensemble"]
    with caplog.at_level(logging.WARNING):
        by = read(tp.shadow_predict(cfg, None, T, STOCKS, LOG))
    assert by[["pred_persist", "pred_online_lr", "pred_rank_ensemble"]].isna().all().all()
    assert "少了 ['2454']" in caplog.text and "不是 0／1" in caplog.text and "重複的股票" in caplog.text


def test_the_shadow_list_comes_from_the_config(caplog):
    assert tp.shadow_models({}) == [] and tp.shadow_models({"daily_model": {"shadow": []}}) == []
    assert tp.shadow_models({"daily_model": {"shadow": "none"}}) == []
    assert tp.shadow_models({"daily_model": {"shadow": "persist"}}) == ["persist"]
    with caplog.at_level(logging.ERROR):
        got = tp.shadow_models({"daily_model": {"shadow": ["c2", "xgb", "c2", "persist"]}}, LOG)
    assert got == ["c2", "persist"] and "xgb 不認得或重複" in caplog.text
    assert tp.shadow_models(utils.load_config()) == KINDS   # 使用者 2026-11-16：五個模型都做


def test_kind_of_strips_the_fallback_note():
    assert tp.kind_of("c2v2d") == "c2v2d" and tp.kind_of("c2（c2v2d 的備援）") == "c2"


# ---------------------------------------------------------------- shadow_scores


def test_scores_use_the_official_formula_and_skip_days_without_answers(tmp_path, caplog):
    cfg = {"data": {"submission_dir": str(tmp_path)}}
    returns = [0.01, -0.02, 0.03, -0.005]
    data = pd.DataFrame({"date": pd.to_datetime(["2026-11-12"] * 4 + [T] * 4), "stock_id": STOCKS * 2,
                         "label_intraday_return": returns + [np.nan] * 4})
    data["label_y"] = (data["label_intraday_return"] > 0).astype(float).where(data["label_intraday_return"].notna())
    for day in ("2026-11-12", T):
        pd.DataFrame({"date": day, "stock_id": STOCKS, "pred_a": [1, 0, 1, 0], "pred_b": [0, 0, 0, 0],
                      "prob_a": 0.5, "pred_c": np.nan}).to_csv(tmp_path / f"shadow_{day}.csv", index=False)
    (tmp_path / "shadow_scores.csv").write_text("舊的內容\n")   # 不能被當成某一天的影子跑
    (tmp_path / "shadow_notes.csv").write_text("x\n")
    assert tp.shadow_scores(cfg, data.iloc[4:], LOG) is None   # 一天都沒有答案
    with caplog.at_level(logging.INFO):
        out = tp.shadow_scores(cfg, data, LOG)
    ledger = pd.read_csv(out, dtype={"date": str})
    assert ledger[["date", "model"]].values.tolist() == [["2026-11-12", "a"], ["2026-11-12", "b"]]
    r = np.array(returns)
    assert ledger.loc[0, "score"] == pytest.approx(float(np.mean(np.array([1, -1, 1, -1]) * r)))
    assert ledger.loc[1, "score"] == pytest.approx(float(np.mean(-r)))
    assert ledger["accuracy"].tolist() == [1.0, 0.5] and ledger["pred_up"].tolist() == [0.5, 0.0]
    assert (ledger["cells"] == 4).all()
    assert "影子跑 2026-11-12 的官方分數：a +" in caplog.text


# ---------------------------------------------------------------- run_daily.py 什麼時候做


@pytest.fixture
def runner(monkeypatch, tmp_path):
    """run_daily 的爬蟲、讀特徵、範本、影子跑換成只記錄的假函式；現在時間固定在台北 t 的 07:30。
    兩個 manifest 放在 tmp_path，一開始都沒有（t 還沒爬過）。"""
    rd.import_src()
    steps = []
    monkeypatch.setattr(rd, "crawl_and_build_features",
                        lambda phase, t, today, trading, log: steps.append(("crawl", t, trading)))
    monkeypatch.setattr(rd.train_predict, "load_model_input", lambda cfg: steps.append("load") or "DATA")
    monkeypatch.setattr(rd, "read_template",
                        lambda site, phase, t, data: steps.append(("template", site, data)) or (["id", t], STOCKS, [t]))

    def shadow(cfg, data, t, stocks, log, known=None):
        steps.append(("shadow", data, tuple(stocks), known))
        tp.shadow_path(cfg, t).write_text("date,stock_id\n")

    monkeypatch.setattr(rd.train_predict, "shadow_predict", shadow)
    monkeypatch.setattr(rd.train_predict, "shadow_scores", lambda cfg, data, log: steps.append("scores"))
    clock(monkeypatch, 7, 30)
    cfg = {"daily_model": {"kind": "c2v2d", "shadow": ["persist"]},
           "data": {"submission_dir": str(tmp_path), "raw_dir": str(tmp_path / "raw"),
                    "processed_dir": str(tmp_path / "processed")},
           "competition": {"deadline": "09:00"}}
    return cfg, steps, {"phase2Days": [{"tradingDate": T, "enabled": 1}]}


def clock(monkeypatch, hour, minute):
    fixed = datetime(2026, 11, 13, hour, minute, tzinfo=utils.TAIPEI)
    monkeypatch.setattr(utils, "taipei_now", lambda now=None: fixed if now is None else now)


def test_a_manual_upload_day_writes_the_shadow_once(runner):
    cfg, steps, _ = runner
    rd.shadow_run(cfg, 2, T, T, LOG, site="SITE")   # 爬蟲由 submit_today 的 ensure_crawled 先做
    assert steps == ["load", ("template", "SITE", "DATA"), ("shadow", "DATA", tuple(STOCKS), None), "scores"]
    steps.clear()
    rd.shadow_run(cfg, 2, T, T, LOG, site="SITE")   # 07:25 那次：已經有了
    assert steps == []


def test_the_submitting_run_reuses_its_data_and_prediction(runner):
    cfg, steps, _ = runner
    rd.shadow_run(cfg, 2, T, T, LOG, data="MINE", stocks=STOCKS, known={"c2v2d": "PRED"})
    assert steps == [("shadow", "MINE", tuple(STOCKS), {"c2v2d": "PRED"}), "scores"]


def test_no_shadow_in_phase_1_when_switched_off_or_after_the_deadline(runner, monkeypatch):
    cfg, steps, _ = runner
    rd.shadow_run(cfg, 1, T, T, LOG, site="SITE")
    rd.shadow_run({**cfg, "daily_model": {"shadow": []}}, 2, T, T, LOG, site="SITE")
    rd.shadow_run({key: value for key, value in cfg.items() if key != "daily_model"}, 2, T, T, LOG, site="SITE")
    clock(monkeypatch, 9, 0)
    rd.shadow_run(cfg, 2, T, T, LOG, site="SITE")
    assert steps == []


def test_shadow_errors_only_warn_and_the_next_run_tries_again(runner, monkeypatch, caplog):
    cfg, steps, _ = runner
    working = rd.train_predict.load_model_input

    def broken(cfg):
        raise RuntimeError("特徵表壞了")

    monkeypatch.setattr(rd.train_predict, "load_model_input", broken)
    with caplog.at_level(logging.WARNING):
        assert rd.shadow_run(cfg, 2, T, T, LOG, site="SITE") is None
        rd.shadow_run({"daily_model": "c2v2d", "data": cfg["data"]}, 2, T, T, LOG, site="SITE")
    assert "影子跑沒做完（RuntimeError: 特徵表壞了）" in caplog.text and "影子跑沒做完（AttributeError）" in caplog.text
    assert not tp.shadow_path(cfg, T).exists() and steps == []
    monkeypatch.setattr(rd.train_predict, "load_model_input", working)
    rd.shadow_run(cfg, 2, T, T, LOG, site="SITE")
    assert steps[0] == "load" and tp.shadow_path(cfg, T).exists()


def test_submit_today_runs_the_shadow_after_the_upload_and_on_manual_upload_days(runner, monkeypatch):
    cfg, steps, state = runner
    shadows = []

    class Site:
        def __init__(self, cfg, secrets):
            pass

        def state(self):
            return state

        def close(self):
            steps.append("close")

    monkeypatch.setattr(rd.site_api, "Site", Site)
    monkeypatch.setattr(rd.utils, "load_secrets", lambda: {})
    monkeypatch.setattr(rd, "shadow_run", lambda *args, **kwargs: steps.append("shadow") or shadows.append(kwargs))

    monkeypatch.setattr(rd, "check_site", lambda *args: "already_submitted")   # 組員先交了
    assert rd.submit_today(cfg, 2, T, T, LOG, sync=False) == "already_submitted"
    assert steps == [("crawl", T, True), "shadow", "close"]   # 還沒爬過：先補爬，再影子跑
    assert isinstance(shadows[0]["site"], Site) and "data" not in shadows[0] and "state" not in shadows[0]

    steps.clear(), shadows.clear()
    monkeypatch.setattr(rd, "check_site", lambda *args: "closed")   # 休市：不做
    assert rd.submit_today(cfg, 2, T, T, LOG, sync=False) == "closed" and shadows == []

    steps.clear()
    monkeypatch.setattr(rd, "check_site", lambda *args: None)   # 排程自己交
    monkeypatch.setattr(rd.train_predict, "train_and_predict", lambda cfg, data, dates, stocks, log: ("c2v2d", "PRED"))
    monkeypatch.setattr(rd.train_predict, "log_direction", lambda *args: None)
    monkeypatch.setattr(rd.train_predict, "save_scores", lambda *args: None)
    monkeypatch.setattr(rd, "write_submission", lambda *args: "PATH")
    monkeypatch.setattr(rd.submit, "run", lambda *args, **kwargs: steps.append("upload") or "done")
    assert rd.submit_today(cfg, 2, T, T, LOG, sync=False) == "done"
    assert steps[-3:] == ["upload", "shadow", "close"]   # 上傳之後才做
    assert shadows[0]["known"] == {"c2v2d": "PRED"} and shadows[0]["data"] == "DATA"
    assert list(shadows[0]["stocks"]) == STOCKS

    shadows.clear()

    def post_failed(*args, **kwargs):
        raise RuntimeError("POST 失敗")

    monkeypatch.setattr(rd.submit, "run", post_failed)   # 上傳丟錯：不做影子跑，錯誤照樣往上丟
    with pytest.raises(RuntimeError, match="POST 失敗"):
        rd.submit_today(cfg, 2, T, T, LOG, sync=False)
    assert shadows == []


# ---------------------------------------------------------------- 沒上傳的日子也補爬（使用者 2026-11-17）


def mark_crawled(cfg, t, status="ok", last=None):
    """寫兩個 manifest：爬蟲的 run 是 t、狀態 status；特徵表的 last_date 是 last（預設 t）。"""
    raw, processed = Path(cfg["data"]["raw_dir"]), Path(cfg["data"]["processed_dir"])
    raw.mkdir(exist_ok=True), processed.mkdir(exist_ok=True)
    (raw / "manifest.json").write_text(json.dumps({"run": {"target_date": t, "status": status}}))
    (processed / "manifest.json").write_text(json.dumps({"last_date": last or t}))


def fake_site(monkeypatch, steps, state=None, error=None):
    class Site:
        def __init__(self, cfg, secrets):
            pass

        def state(self):
            if error:
                raise error
            return state

        def close(self):
            steps.append("close")

    monkeypatch.setattr(rd.site_api, "Site", Site)
    monkeypatch.setattr(rd.utils, "load_secrets", lambda: {})


def test_crawled_needs_both_manifests_to_say_t(runner):
    cfg, _, _ = runner
    assert not rd.crawled(cfg, T)   # 兩個都沒有
    for status, ok in [("ok", True), ("stale", True), ("running", False), ("failed", False)]:
        mark_crawled(cfg, T, status)
        assert rd.crawled(cfg, T) is ok, status
    mark_crawled(cfg, "2026-11-12")
    assert not rd.crawled(cfg, T)   # 上一天的
    mark_crawled(cfg, T, last="2026-11-12")
    assert not rd.crawled(cfg, T)   # 爬好了，特徵表沒重寫
    (Path(cfg["data"]["processed_dir"]) / "manifest.json").write_text("{壞掉")
    assert not rd.crawled(cfg, T)


def test_already_submitted_days_crawl_once_even_without_shadow_or_after_9(runner, monkeypatch):
    cfg, steps, state = runner
    cfg = {**cfg, "daily_model": {"kind": "c2v2d", "shadow": []}}   # 影子跑關掉也要爬
    fake_site(monkeypatch, steps, state)
    monkeypatch.setattr(rd, "check_site", lambda *args: "already_submitted")
    assert rd.submit_today(cfg, 2, T, T, LOG, sync=False) == "already_submitted"
    assert steps == [("crawl", T, True), "close"]
    steps.clear()
    mark_crawled(cfg, T)   # 07:25 那次：已經爬過
    assert rd.submit_today(cfg, 2, T, T, LOG, sync=False) == "already_submitted"
    assert steps == ["close"]
    steps.clear()
    mark_crawled(cfg, "2026-11-12")
    clock(monkeypatch, 9, 30)   # 09:00 以後手動跑
    rd.submit_today(cfg, 2, T, T, LOG, sync=False)
    assert steps == [("crawl", T, True), "close"]


def test_an_unverified_upload_crawls_and_still_stops(runner, monkeypatch):
    cfg, steps, state = runner
    fake_site(monkeypatch, steps, state)

    def pending(*args):
        raise rd.StopRun("已經送過但沒有核對完成")

    monkeypatch.setattr(rd, "check_site", pending)
    monkeypatch.setattr(rd, "shadow_run", lambda *args, **kwargs: steps.append("shadow"))
    with pytest.raises(rd.StopRun, match="沒有核對完成"):
        rd.submit_today(cfg, 2, T, T, LOG, sync=False)
    assert steps == [("crawl", T, True), "close"]   # 不上傳、不影子跑


def test_site_down_still_crawls_and_the_error_comes_through(runner, monkeypatch):
    cfg, steps, _ = runner
    fake_site(monkeypatch, steps, error=ConnectionError("網站連不上"))
    with pytest.raises(ConnectionError, match="網站連不上"):
        rd.submit_today(cfg, 2, T, T, LOG, sync=False)
    assert steps == [("crawl", T, True), "close"]


def test_closed_days_other_dates_and_phase_1_do_not_crawl(runner, monkeypatch):
    cfg, steps, state = runner
    fake_site(monkeypatch, steps, state)
    monkeypatch.setattr(rd, "check_site", lambda *args: "closed")
    assert rd.submit_today(cfg, 2, T, T, LOG, sync=False) == "closed"
    rd.ensure_crawled(cfg, 2, T, "2026-11-14", True, LOG)   # t 不是今天
    rd.ensure_crawled(cfg, 1, T, T, True, LOG)   # Phase 1
    rd.ensure_crawled(cfg, 2, T, T, False, LOG)   # 網站說休市
    assert steps == ["close"]


def test_a_failed_catch_up_crawl_only_warns_and_the_next_run_tries_again(runner, monkeypatch, caplog):
    cfg, steps, state = runner
    fake_site(monkeypatch, steps, state)
    monkeypatch.setattr(rd, "check_site", lambda *args: "already_submitted")
    monkeypatch.setattr(rd, "shadow_run", lambda *args, **kwargs: steps.append("shadow"))

    def broken(phase, t, today, trading, log):
        raise RuntimeError("Live 還沒好")

    monkeypatch.setattr(rd, "crawl_and_build_features", broken)
    with caplog.at_level(logging.WARNING):
        assert rd.submit_today(cfg, 2, T, T, LOG, sync=False) == "already_submitted"
    assert "補爬沒做完（RuntimeError: Live 還沒好）" in caplog.text and steps == ["shadow", "close"]
    monkeypatch.setattr(rd, "crawl_and_build_features",
                        lambda phase, t, today, trading, log: steps.append(("crawl", t, trading)))
    steps.clear()
    rd.submit_today(cfg, 2, T, T, LOG, sync=False)
    assert steps == [("crawl", T, True), "shadow", "close"]


def test_the_submitting_path_crawls_every_time(runner, monkeypatch):
    cfg, steps, state = runner
    fake_site(monkeypatch, steps, state)
    mark_crawled(cfg, T)   # 已經爬過也照爬：Live 晚更新時下一次才抓得到
    monkeypatch.setattr(rd, "check_site", lambda *args: None)
    monkeypatch.setattr(rd.train_predict, "train_and_predict", lambda cfg, data, dates, stocks, log: ("c2v2d", "PRED"))
    monkeypatch.setattr(rd.train_predict, "log_direction", lambda *args: None)
    monkeypatch.setattr(rd.train_predict, "save_scores", lambda *args: None)
    monkeypatch.setattr(rd, "write_submission", lambda *args: "PATH")
    monkeypatch.setattr(rd.submit, "run", lambda *args, **kwargs: steps.append("upload") or "done")
    monkeypatch.setattr(rd, "shadow_run", lambda *args, **kwargs: steps.append("shadow"))
    assert rd.submit_today(cfg, 2, T, T, LOG, sync=False) == "done"
    assert steps[0] == ("crawl", T, True) and steps[-3:] == ["upload", "shadow", "close"]
