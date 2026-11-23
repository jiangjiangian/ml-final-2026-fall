"""src/models/m7_n1_js_online.py（N1 影子跑，使用者 2026-11-23）的測試。要在 n1 自己的環境跑：

    .venv-n1/bin/python -m pytest -q tests/test_n1_model.py

正式的 .venv 沒有 torch，整個檔會跳過。這個檔只 import m7、numpy、pandas、torch 和標準函式庫，不 import src.pipeline
（.venv-n1 沒有正式流程的套件）。老師檔和 sox、tsm_adr、vix 用 git archive 拿 models/n1/ub04_v5/meta.json 記的
正式流程 commit（f02b89d）；拿不到（淺 clone）時，用到它的測試跳過。

- 重現：從 state_2026-11-12_kd05 照每天早上的做法逐日走 11-13～11-20，和 Kaggle UB 04 的 JS_ONLINE 差不超過 1e-12，
  11-20 更新完的內容雜湊等於 state_2026-11-20_yahoo_gspc 的；54 個輸入和更新用的目標逐位元一樣。
- 每天早上：只寫 .cache/n1/ 和 data/submission/n1/；補更新、同一天不重複更新、第 2 批、新缺的股票先不更新、
  .cache/n1/ 不見時照 inputs_<t>.npz 補回來；資料不是 t 的、鎖、版本、狀態檔被改時不寫 n1_<t>.csv。
"""

import fcntl
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")
from src.models import m7_n1_js_online as m7  # noqa: E402（沒有 torch 時整個檔跳過）

ROOT = Path(m7.__file__).resolve().parents[2]
INITIAL = ROOT / "models" / "n1" / "ub04_v5"
FIXTURES = ROOT / "tests" / "fixtures" / "n1"
META = json.loads((INITIAL / "meta.json").read_text(encoding="utf-8"))
PRODUCTION = META["commits"]["production"]
YAHOO_SHA = META["states"]["state_2026-11-20_yahoo_gspc"]["content_sha256"]
CONT = ["2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]
MEMBERS = ["ridge", "kridge", "lgbm", "js", "beta_rank", "p"]


def have_commit() -> bool:
    out = subprocess.run(["git", "cat-file", "-e", f"{PRODUCTION}^{{commit}}"], cwd=ROOT, capture_output=True)
    return out.returncode == 0


needs_commit = pytest.mark.skipif(not have_commit(), reason=f"這個 clone 沒有 {PRODUCTION[:7]}（git archive 拿不到老師檔）")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- 不用老師檔的


def test_versions_and_initial_folder_are_what_ub04_used():
    assert {"torch": torch.__version__, "numpy": np.__version__, "pandas": pd.__version__} == \
        {k: m7.PINNED[k] for k in ("torch", "numpy", "pandas")}
    shas = json.loads((INITIAL / "sha256.json").read_text())
    for name in ("meta.json", "norm.npz"):
        assert sha(INITIAL / name) == shas[name]
    for state in ("state_2026-11-12_kd05", "state_2026-11-20_yahoo_gspc"):
        for name in m7.STATE_FILES:
            assert sha(INITIAL / state / name) == shas[f"{state}/{name}"]
        assert m7.content_sha(m7.load_state(INITIAL / state)) == META["states"][state]["content_sha256"]
    assert META["features"] == m7.FEATURES and META["constants"]["online_lr"] == m7.ONLINE_LR


def test_restore_builds_the_nets_before_setting_the_random_state():
    snap = m7.load_state(INITIAL / "state_2026-11-20_yahoo_gspc")
    models = m7.restore(snap)
    assert torch.equal(torch.get_rng_state(), snap["rng"])   # 建 Net 用掉的亂數不影響之後的 dropout
    assert m7.content_sha(m7.snapshot(models)) == YAHOO_SHA


def test_us_inputs_follow_the_d06_rule():
    bars = pd.DataFrame({"date": pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-30"]),
                         "open": [1.0, 2, 3, 3, 5], "high": [2.0, 3, 4, 4, 6], "low": [0.5, 1, 2, 2, 4],
                         "close": [1.5, 2.5, 3.5, 3.5, 5.5], "adj_close": [1.5, 2.5, 3.5, 3.5, 5.5]})
    days = pd.to_datetime(["2026-10-02", "2026-10-06", "2026-10-07", "2026-10-30", "2026-11-02"])
    got = m7.last_bar_ret(bars, days).to_numpy()
    # 10-06 是 10-05 的複製K棒，丟掉；10-30 那天取到的 10-05 早了 25 天、10-30 那根離上一根也超過 16 天：都空白
    assert np.allclose(got, [np.nan, 0.4, 0.4, np.nan, np.nan], equal_nan=True)
    assert m7.last_bar_date(bars, pd.Timestamp("2026-10-07")) == pd.Timestamp("2026-10-05")


def bars_until(last: str) -> pd.DataFrame:
    days = pd.bdate_range("2026-11-02", last)
    prices = np.linspace(100.0, 110.0, len(days))
    return pd.DataFrame({"date": days, "open": prices, "high": prices + 1, "low": prices - 1, "close": prices,
                         "adj_close": prices})


def crawled_ok() -> dict:
    """爬蟲每個美股序列都抓成的 manifest（只留 us_check 讀的兩段）。"""
    return {"yfinance": {name: {"status": "ok"} for name in ("sox", "tsm_adr", "vix", "dji", "dxy")},
            "yfinance_extra": {"gspc": {"status": "ok"}}}


def test_stale_us_flag_also_reads_the_crawler_status():
    """第二輪審查：Yahoo 整個抓不到時每個檔（dji 也是）都留著一樣舊的檔，只比日期看不出來。manifest 記這次沒抓成
    （status 不是 ok，或沒有紀錄）就記 stale_us_n1。原本的兩條（比 dji 舊、值是空白）照舊。"""
    t = pd.Timestamp("2026-11-25")
    us_bars = {name: bars_until("2026-11-24") for name in [*m7.US_FILES, m7.US_CALENDAR]}
    row = pd.Series({name: 0.01 for name in m7.US_FILES})
    used, stale = m7.us_check(us_bars, row, t, crawled_ok())
    assert stale == 0 and set(used.values()) == {pd.Timestamp("2026-11-24")}
    for section, name in [("yfinance", "sox"), ("yfinance", "tsm_adr"), ("yfinance", "vix"), ("yfinance", "dji"),
                          ("yfinance_extra", "gspc")]:
        manifest = crawled_ok()
        manifest[section][name] = {"status": "failed", "kept_previous_file": True}
        assert m7.us_check(us_bars, row, t, manifest)[1] == 1, name
    manifest = crawled_ok()
    manifest["yfinance"]["dxy"]["status"] = "failed"   # n1 不讀的序列沒抓成：不算
    assert m7.us_check(us_bars, row, t, manifest)[1] == 0
    del manifest["yfinance_extra"]   # gspc 那一步丟錯、沒寫紀錄
    assert m7.us_check(us_bars, row, t, manifest)[1] == 1
    assert m7.us_check(us_bars, row, t, {})[1] == 1
    assert m7.us_check({**us_bars, "sox": bars_until("2026-11-23")}, row, t, crawled_ok())[1] == 1
    assert m7.us_check(us_bars, pd.Series({**row.to_dict(), "vix": np.nan}), t, crawled_ok())[1] == 1


def picks():
    table = pd.read_csv(FIXTURES / "n1_picks_ub04.csv", parse_dates=["date"], dtype={"stock_id": str},
                        float_precision="round_trip")
    return table.sort_values(["date", "stock_id"]).reset_index(drop=True)


def test_n1_formula_matches_ub04_picks():
    ref = picks()
    out = m7.n1_frame(ref[["date", "stock_id"] + MEMBERS])
    assert (out["pred_n1"].to_numpy() == ref["pred_n1"].to_numpy()).all()
    assert (out["pred_c2v2d"].to_numpy() == ref["pred_c2v2d_prod"].to_numpy()).all()
    for column in ("comb3", "comb4", "k_t", "tilt", "score_n1"):
        assert np.abs(out[column].to_numpy() - ref[column].to_numpy()).max() <= 1e-12, column
    yahoo = m7.n1_frame(ref[["date", "stock_id"] + MEMBERS].assign(js=ref["js_yahoo_gspc"]))
    assert (yahoo["pred_n1"].to_numpy() == ref["pred_n1_yahoo_gspc"].to_numpy()).all()
    assert out.groupby("date")["pred_n1"].sum().eq(25).all()


def test_n1_today_reads_the_c2v2d_columns_of_the_shadow_file(tmp_path):
    day = picks()
    day = day[day["date"] == "2026-11-20"]
    shadow = pd.DataFrame({"date": "2026-11-20", "stock_id": day["stock_id"], "pred_c2v2d": day["pred_c2v2d_prod"],
                           "p_up_c2v2d": day["p"], **{f"{m}_c2v2d": day[m] for m in ("ridge", "kridge", "lgbm",
                                                                                      "beta_rank")}})
    path = tmp_path / "shadow_2026-11-20.csv"
    shadow.iloc[::-1].to_csv(path, index=False)   # 列的順序不影響
    js = pd.DataFrame({"stock_id": day["stock_id"], "js": day["js_yahoo_gspc"].astype(np.float32)})
    table, note = m7.n1_today(js, META["top50"], pd.Timestamp("2026-11-20"), path)
    assert note == "" and table["stock_id"].tolist() == META["top50"]
    assert (table["pred_n1"].to_numpy() == day["pred_n1_yahoo_gspc"].to_numpy()).all()
    assert (table["c2v2d_same_n1"] == 1).all() and table["prob_n1"].between(0, 1).all()
    shadow.assign(lgbm_c2v2d=np.nan).to_csv(path, index=False)
    table, note = m7.n1_today(js, META["top50"], pd.Timestamp("2026-11-20"), path)
    assert note == "c2v2d 有空白" and table["pred_n1"].isna().all() and table["pred_js_n1"].sum() == 25
    shadow.drop(columns="beta_rank_c2v2d").to_csv(path, index=False)
    assert m7.n1_today(js, META["top50"], pd.Timestamp("2026-11-20"), path)[1] == "shadow 沒有 beta_rank_c2v2d"
    assert m7.n1_today(js, META["top50"], pd.Timestamp("2026-11-20"), tmp_path / "沒有.csv")[1] == "沒有 shadow 檔"


# ---------------------------------------------------------------- 重現（只換平台）


@pytest.fixture(scope="module")
def replayed(tmp_path_factory):
    if not have_commit():
        pytest.skip(f"這個 clone 沒有 {PRODUCTION[:7]}")
    return m7.replay_check(ROOT, "models/n1/ub04_v5", tmp_path_factory.mktemp("replay"))


@needs_commit
def test_replay_from_kd05_matches_ub04_bit_for_bit(replayed):
    assert replayed["days"] == CONT and [u["date"] for u in replayed["updates"]] == CONT
    assert replayed["cells"] == 300 and replayed["unmatched"] == 0
    assert replayed["max_abs_diff"] <= 1e-12, \
        f"max_abs_diff {replayed['max_abs_diff']}：照 deploy/n1_setup.md 的「重現檢查沒過」處理"
    assert replayed["content_sha256"] == YAHOO_SHA, \
        "11-20 的狀態和 Kaggle 不一樣：照 deploy/n1_setup.md 的「重現檢查沒過」處理"


@needs_commit
def test_the_54_inputs_and_update_targets_match_ub04(replayed):
    ref = pd.read_csv(FIXTURES / "inputs_cont_ub04.csv.gz", dtype={"date": str, "stock_id": str},
                      float_precision="round_trip")
    columns = [f"{c}__yahoo_gspc" if c in ("spx_x", "gspc") else c for c in m7.FEATURES]
    updates = {m7.day_text(r["date"]): r for r in replayed["updates_raw"]}
    assert sorted(ref["date"].unique()) == CONT
    for day, block in ref.groupby("date"):
        assert block["stock_id"].tolist() == META["all100"]
        want = block[columns].to_numpy(np.float64).astype(np.float32)
        mine = replayed["day_inputs"][pd.Timestamp(day)]
        assert np.array_equal(mine["x"], want, equal_nan=True), f"{day} 預測那天的 54 個輸入"
        assert np.array_equal(mine["bars"], block["bars"].to_numpy(np.float64)), day
        update = updates[day]
        assert np.array_equal(update["x"], want, equal_nan=True), f"{day} 隔天更新時的 54 個輸入"
        assert np.array_equal(update["trainable"], block["trainable"].to_numpy(bool)), day
        assert np.array_equal(update["target"], block["target_main"].to_numpy(np.float64).astype(np.float32),
                              equal_nan=True), day
        assert update["rows"] == int(block["trainable"].sum())


# ---------------------------------------------------------------- 每天早上（假的 repo，資料是 f02b89d 的）


@pytest.fixture(scope="module")
def prod_raw(tmp_path_factory):
    if not have_commit():
        pytest.skip(f"這個 clone 沒有 {PRODUCTION[:7]}")
    return m7.replay_inputs(ROOT, PRODUCTION, tmp_path_factory.mktemp("prod"))


def make_repo(tmp_path, prod_raw) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(prod_raw, repo / "data" / "raw")
    yf = repo / "data" / "raw" / "yfinance"
    shutil.copy(yf / "sox.csv", yf / "gspc.csv")   # 只測流程：gspc 的K棒用 sox 的代替
    (repo / "data" / "submission").mkdir(parents=True)
    return repo


def set_manifest(repo, t, prev, missing=(), never_filled=False, status="ok"):
    (repo / "data" / "raw" / "manifest.json").write_text(json.dumps({
        "run": {"target_date": t, "status": status, "prev_day": prev},
        "teacher_live": {"prev_day": prev, "prev_day_never_filled": never_filled,
                         "prev_day_missing_stocks": list(missing)},
        **crawled_ok()}))


def add_day(repo, day, skip=()):
    """老師 Live 每檔加 day 那一列（拿最後一列有值的改日期和收盤），skip 的股票不加。day 以後的列先拿掉。"""
    for path in sorted((repo / "data" / "raw" / "teacher" / "live" / "market").glob("*.csv")):
        data = path.read_bytes()
        newline = b"\r\n" if b"\r\n" in data else b"\n"
        lines = [line for line in data.split(newline) if line]
        rows = [r for r in lines[1:] if r.split(b",")[0].decode() < day]
        if path.stem not in skip:
            cells = next(r for r in reversed(rows) if r.split(b",")[1] != b"-1").split(b",")
            cells[0] = day.encode()
            cells[1] = repr(float(cells[1]) * (1 + 0.004 * (sum(path.stem.encode()) % 7 - 3))).encode()
            rows.append(b",".join(cells))
        path.write_bytes(newline.join([lines[0], *rows]) + newline)


def write_shadow(repo, t, p_up=0.6, members=True):
    rng = np.random.default_rng(int(t[-2:]) * 100 + int(p_up * 100))
    top50 = META["top50"]
    frame = pd.DataFrame({"date": pd.Timestamp(t), "stock_id": top50, "ridge": rng.normal(size=50),
                          "kridge": rng.normal(size=50), "lgbm": rng.normal(size=50), "js": 0.0,
                          "beta_rank": rng.uniform(-0.5, 0.5, 50), "p": p_up})
    shadow = pd.DataFrame({"date": t, "stock_id": top50, "pred_c2v2d": m7.n1_frame(frame)["pred_c2v2d"],
                           "prob_c2v2d": 0.5, "p_up_c2v2d": p_up})
    if members:
        for name in ("ridge", "kridge", "lgbm", "beta_rank"):
            shadow[f"{name}_c2v2d"] = frame[name]
    path = repo / "data" / "submission" / f"shadow_{t}.csv"
    shadow.to_csv(path, index=False)
    return path


def files_of(root: Path, skip=(".cache/n1", "data/submission/n1")) -> dict:
    out = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and not any(rel == s or rel.startswith(s + "/") for s in skip):
            out[rel] = sha(path)
    return out


def run_m7(repo, t) -> int:
    """跑一次 m7.main，確認只寫了 .cache/n1/ 和 data/submission/n1/，起始資料夾沒被動。"""
    before, initial = files_of(repo), files_of(INITIAL, skip=())
    code = m7.main(["--date", t, "--root", str(repo), "--initial-dir", str(INITIAL)])
    assert files_of(repo) == before, "n1 寫了 .cache/n1/ 和 data/submission/n1/ 以外的檔"
    assert files_of(INITIAL, skip=()) == initial
    return code


def n1_table(repo, t) -> pd.DataFrame:
    text = {c: str for c in ("date", "stock_id", "updated_n1", "state_n1", "note_n1", "state_sha_n1", "shadow_sha_n1",
                             "inputs_sha_n1")}
    return pd.read_csv(repo / "data" / "submission" / "n1" / f"n1_{t}.csv", dtype=text)


def npz(repo, name) -> dict:
    with np.load(repo / "data" / "submission" / "n1" / name) as saved:
        return {key: saved[key] for key in saved.files}


@needs_commit
def test_daily_runs_catch_up_hold_batches_and_recover(prod_raw, tmp_path):
    repo = make_repo(tmp_path, prod_raw)
    out = repo / "data" / "submission" / "n1"
    line = repo / ".cache" / "n1" / "ub04_v5"

    # 11-23：狀態已經到 11-20，直接預測
    set_manifest(repo, "2026-11-23", "2026-11-20")
    shadow = write_shadow(repo, "2026-11-23")
    assert run_m7(repo, "2026-11-23") == 0
    day1 = n1_table(repo, "2026-11-23")
    assert len(day1) == 50 and set(day1["run"]) == {1} and day1["stock_id"].tolist() == META["top50"]
    assert day1["pred_n1"].sum() == 25 and day1["pred_js_n1"].sum() == 25 and (day1["c2v2d_same_n1"] == 1).all()
    assert day1["js_n1"].notna().all() and day1["k_t_n1"].notna().all()
    assert day1["state_n1"].eq("2026-11-20").all() and day1["state_sha_n1"].eq(YAHOO_SHA).all()
    assert day1["updated_n1"].isna().all() and day1["stale_n1"].eq(0).all()
    assert day1["stale_us_n1"].eq(0).all()   # f02b89d 的 sox、tsm_adr、vix、dji 都到 11-19，manifest 都抓成
    assert day1["shadow_sha_n1"].eq(sha(shadow)).all()
    assert day1["inputs_sha_n1"].eq(sha(out / "inputs_2026-11-23.npz")).all()
    assert json.loads((line / "current.json").read_text())["content_sha256"] == YAHOO_SHA
    saved = npz(repo, "inputs_2026-11-23.npz")
    assert saved["update_dates"].size == 0 and saved["pred_x"].shape == (100, 54) and int(saved["pred_mask"].sum()) == 50
    assert list(saved["features"]) == m7.FEATURES and str(saved["line"][0]) == "ub04_v5"

    # 同一份 shadow 再跑：不重算
    first = (out / "n1_2026-11-23.csv").read_bytes()
    assert run_m7(repo, "2026-11-23") == 0 and (out / "n1_2026-11-23.csv").read_bytes() == first

    # shadow 變了（重交後重寫）：第 2 批加在後面，狀態不再更新
    write_shadow(repo, "2026-11-23", p_up=0.3)
    assert run_m7(repo, "2026-11-23") == 0
    both = (out / "n1_2026-11-23.csv").read_bytes()
    assert both.startswith(first) and set(n1_table(repo, "2026-11-23")["run"]) == {1, 2}
    assert npz(repo, "inputs_2026-11-23_run2.npz")["update_dates"].size == 0
    write_shadow(repo, "2026-11-23", p_up=0.8)
    assert run_m7(repo, "2026-11-23") == 0 and (out / "n1_2026-11-23.csv").read_bytes() == both   # 最多 2 批

    # 11-24：補更新 11-23；shadow 沒有 c2v2d 的成員分數，N1 空白、JS 照記
    add_day(repo, "2026-11-23")
    set_manifest(repo, "2026-11-24", "2026-11-23")
    write_shadow(repo, "2026-11-24", members=False)
    assert run_m7(repo, "2026-11-24") == 0
    day2 = n1_table(repo, "2026-11-24")
    assert day2["updated_n1"].eq("2026-11-23").all() and day2["state_n1"].eq("2026-11-23").all()
    assert day2["pred_n1"].isna().all() and day2["note_n1"].str.contains("ridge_c2v2d").all()
    assert day2["pred_js_n1"].sum() == 25
    sha_1123 = day2["state_sha_n1"].iloc[0]
    assert json.loads((line / "current.json").read_text()) | {"switched_at": None} == {
        "state": "state_2026-11-23", "last_update_date": "2026-11-23", "content_sha256": sha_1123, "switched_at": None}
    meta = json.loads((line / "state_2026-11-23" / "meta.json").read_text())
    assert meta["parent"] == "state_2026-11-20" and meta["parent_content_sha256"] == YAHOO_SHA
    assert meta["features_from"]["teacher"] == "2020-01-02" and meta["environment"]["torch"] == m7.PINNED["torch"]
    saved = npz(repo, "inputs_2026-11-24.npz")
    assert list(saved["update_dates"]) == ["2026-11-23"] and list(saved["state_before"]) == [YAHOO_SHA]
    assert list(saved["state_after"]) == [sha_1123] and saved["upd_x"].shape == (100, 54)

    # 11-25：S 在 11-24 新缺（11-23 還有）：先不更新 11-24，用 11-23 的狀態預測
    missing = META["top50"][0]
    add_day(repo, "2026-11-24", skip={missing})
    set_manifest(repo, "2026-11-25", "2026-11-24", missing=[missing])
    write_shadow(repo, "2026-11-25")
    assert run_m7(repo, "2026-11-25") == 0
    day3 = n1_table(repo, "2026-11-25")
    assert day3["stale_n1"].eq(1).all() and day3["updated_n1"].isna().all() and day3["state_sha_n1"].eq(sha_1123).all()
    saved = npz(repo, "inputs_2026-11-25.npz")
    assert list(saved["held_missing"]) == [missing] and list(saved["prev_day_missing"]) == [missing]

    # 11-26：還是缺的當停牌，照有的列更新 11-24、11-25（最多延一次）
    add_day(repo, "2026-11-25")
    set_manifest(repo, "2026-11-26", "2026-11-25")
    write_shadow(repo, "2026-11-26")
    assert run_m7(repo, "2026-11-26") == 0
    day4 = n1_table(repo, "2026-11-26")
    assert day4["updated_n1"].eq("2026-11-24 2026-11-25").all() and day4["stale_n1"].eq(0).all()
    sha_1125 = day4["state_sha_n1"].iloc[0]

    # .cache/n1 不見：從起始狀態重來，照 inputs_*.npz 補回 11-23～11-25，再補更新 11-26
    shutil.rmtree(line)
    add_day(repo, "2026-11-26")
    set_manifest(repo, "2026-11-27", "2026-11-26")
    write_shadow(repo, "2026-11-27")
    assert run_m7(repo, "2026-11-27") == 0
    recovered = json.loads((line / "state_2026-11-25" / "meta.json").read_text())
    assert recovered["content_sha256"] == sha_1125 and [u["date"] for u in recovered["updates"]] == [
        "2026-11-23", "2026-11-24", "2026-11-25"]
    day5 = n1_table(repo, "2026-11-27")
    assert day5["updated_n1"].eq("2026-11-26").all() and day5["state_n1"].eq("2026-11-26").all()
    assert list(npz(repo, "inputs_2026-11-27.npz")["state_before"]) == [sha_1125]


@needs_commit
def test_nothing_is_written_when_the_data_or_the_state_is_wrong(prod_raw, tmp_path, monkeypatch):
    repo = make_repo(tmp_path, prod_raw)
    out = repo / "data" / "submission" / "n1"
    write_shadow(repo, "2026-11-23")
    for args in ([("2026-11-20", "2026-11-19")], [("2026-11-23", "2026-11-20"), {"never_filled": True}],
                 [("2026-11-23", "2026-11-20"), {"status": "failed"}], [("2026-11-23", "2026-11-19")]):
        set_manifest(repo, *args[0], **(args[1] if len(args) > 1 else {}))
        assert run_m7(repo, "2026-11-23") == m7.CODE_DATA, args
    assert not out.exists()

    set_manifest(repo, "2026-11-23", "2026-11-20")
    gspc = repo / "data" / "raw" / "yfinance" / "gspc.csv"
    kept = gspc.read_bytes()
    gspc.unlink()   # 上線第一天爬蟲抓 ^GSPC 失敗（審查 m4）：不用空白的 gspc 照算，回傳碼 2，隔天再算
    assert run_m7(repo, "2026-11-23") == m7.CODE_DATA
    gspc.write_bytes(kept)
    with open(repo / ".cache" / "n1" / "n1.lock", "w") as lock:   # 上一次還在跑
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert run_m7(repo, "2026-11-23") == m7.CODE_BUSY
    monkeypatch.setitem(m7.PINNED, "torch", "0.0.0+cpu")
    assert run_m7(repo, "2026-11-23") == m7.CODE_STATE
    monkeypatch.undo()
    assert not out.exists()

    assert run_m7(repo, "2026-11-23") == 0
    written = (out / "n1_2026-11-23.csv").read_bytes()
    seed = repo / ".cache" / "n1" / "ub04_v5" / "state_2026-11-20" / "seed0.pt"
    data = bytearray(seed.read_bytes())
    data[len(data) // 2] ^= 0xFF   # 狀態檔被改過
    seed.write_bytes(bytes(data))
    write_shadow(repo, "2026-11-23", p_up=0.2)
    assert run_m7(repo, "2026-11-23") == m7.CODE_STATE
    assert (out / "n1_2026-11-23.csv").read_bytes() == written
