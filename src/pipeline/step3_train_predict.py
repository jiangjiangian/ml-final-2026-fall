"""第 3 步：訓練和預測。照 config 的 daily_model 選模型，用 t 之前的答案訓練，預測 t 的每一檔。

    load_model_input(cfg)                          → 所有模型共用的輸入表
    train_and_predict(cfg, data, dates, stocks, log) → （用了哪個模型, 預測表）
    save_scores(cfg, pred, t, model_name, log)     → data/submission/scores_<t>.csv（只給研究用）
    log_direction(pred, model_name, log)           → c2、c2v2d 當天押的大盤方向寫進 log
    shadow_predict(cfg, data, t, stocks, log, known) → data/submission/shadow_<t>.csv（影子跑，不上傳）
    shadow_scores(cfg, data, log)                  → data/submission/shadow_scores.csv（影子跑對上答案的分數）

模型在 src/models/，名字和檔案的對照是 src/models/__init__.py 的 MODEL_KINDS。每個模型都在 predict 裡從頭訓練，
不讀也不寫 repo 根目錄的 models/。
模型開關（使用者 2026-11-12）：config 的 daily_model.kind 是主模型，fallback 是它丟錯時照順序換的備援。
影子跑（使用者 2026-11-16）：config 的 daily_model.shadow 列的模型每天都預測 t，存檔但不上傳，收盤後比分數。
"""

import importlib
import re
from pathlib import Path

import pandas as pd

from src.models import MODEL_KINDS
from src.models import m1_online_lr as online_lr
from src.pipeline import step1_crawler as crawler, utils


class ModelChoiceError(RuntimeError):
    """config 的 daily_model.kind 不能用。"""


def load_model_input(cfg: dict):
    """特徵表（data/processed/）接上個股特徵（盤中報酬的 lag 等），date 是 Timestamp。

    每個模型的 predict 都吃這張表；讀法是 m1_online_lr.load_data（最早的模型留下來的，所有模型共用）。
    這一步失敗整次就停下，因為沒有模型能用。
    """
    return online_lr.load_data(cfg)


def phase1_score(pred, data) -> float:
    """Phase 1（84 天回測）的本機官方分數，只寫進 log。"""
    return online_lr.official_score(pred, data)


def model_order(cfg: dict, log) -> list:
    """主模型加上備援，照要試的順序。主模型不認得或填 none 就丟 ModelChoiceError（不默默換備援）；
    fallback 可以是一個名字或一串名字，none 代表沒有備援，不認得或重複的名字記一行 ERROR 後跳過。
    沒有 daily_model 這個設定時用 online_lr。"""
    choice = cfg.get("daily_model") or {}
    kind = choice.get("kind", "online_lr")
    if kind not in MODEL_KINDS:
        raise ModelChoiceError(f"daily_model.kind 只能填 {list(MODEL_KINDS)}：{kind}")
    fallback = choice.get("fallback") or []
    order = [kind]
    for name in [fallback] if isinstance(fallback, str) else list(fallback):
        if str(name).lower() == "none":
            continue
        if name not in MODEL_KINDS or name in order:
            log.error("daily_model.fallback 的 %s 不認得或重複，跳過（可以填 %s）", name, list(MODEL_KINDS))
            continue
        order.append(name)
    return order


def load_model(kind: str):
    """MODEL_KINDS 的「模組:函式」→ 那個 predict 函式。用到才 import：檔案壞掉也只影響這個模型。"""
    module, _, function = MODEL_KINDS[kind].partition(":")
    return getattr(importlib.import_module(module), function or "predict")


def train_and_predict(cfg: dict, data, dates: list, stocks: list, log) -> tuple:
    """照 model_order 一個一個試，回傳第一個算得出來的（模型名稱, 預測表）。

    輸入：data 是 load_model_input 的表；dates 是要預測的日子；stocks 是網站範本的股票代號。
    輸出：模型名稱（用了備援時寫成「online_lr（rank_ensemble 的備援）」）和預測表（date、stock_id、pred，
          通常還有 prob 和各模型自己的欄）。
    模型丟錯時記一行 ERROR、換下一個，當天照樣交件；最後一個也丟錯就把那個錯往上丟。
    """
    order = model_order(cfg, log)
    for position, kind in enumerate(order):
        try:
            pred = load_model(kind)(data, cfg, dates, stocks)
            return (kind if position == 0 else f"{kind}（{order[0]} 的備援）"), pred
        except Exception as e:
            if position == len(order) - 1:
                raise
            log.error("%s 算不出來（%s），改用 %s", kind, public_reason(e), order[position + 1])


def kind_of(model_name: str) -> str:
    """train_and_predict 回傳的模型名稱 → MODEL_KINDS 的名字（「c2（c2v2d 的備援）」→ c2）。"""
    return model_name.split("（", 1)[0]


def public_reason(e: BaseException) -> str:
    """模型的錯誤訊息（模型不連網站，不會帶伺服器內容）。路徑換成相對的：log 會推上 GitHub，不寫出主機的家目錄。"""
    message = str(e).replace(str(utils.ROOT), ".").replace(str(Path.home()), "~")
    return f"{type(e).__name__}: {message[:300]}"


def save_scores(cfg: dict, pred, t: str, model_name: str, log) -> None:
    """另存當天每檔的分數（使用者 2026-11-15），給每週重算成本和組員核對用。失敗只記警告，不影響上傳。

    檔名 scores_<t>.csv，放在 config 的 data.submission_dir。欄是模型輸出的全部欄（rank_ensemble 是 ridge、
    kridge、lgbm、prob、pred；c2、c2v2d 多 combined、beta_rank、p_up、tilt、score、variant 等），
    加上 model（用了哪個模型）和 rank（1～50，照 prob 排，同分時代號大的名次高）。
    """
    try:
        keep = pred.sort_values(["date", "stock_id"]).copy()
        if "prob" in keep:
            keep["rank"] = keep.groupby("date")["prob"].rank(method="first").astype(int)
        keep.insert(2, "model", model_name)
        path = utils.ROOT / cfg["data"]["submission_dir"] / f"scores_{t}.csv"
        crawler.write_atomic(path, keep.to_csv(index=False).encode("utf-8"))
        log.info("另存 %s（每檔的分數，只給研究用）", path.relative_to(utils.ROOT))
    except Exception as e:
        log.warning("每檔分數沒存成（%s），不影響上傳", short_reason(e))


def log_direction(pred, model_name: str, log) -> None:
    """c2、c2v2d 的預測表有 p_up：把當天押的大盤方向寫進 log（每檔的分數在 scores_<t>.csv）。只是記錄，不丟錯。"""
    if "p_up" not in pred:
        return
    try:
        log.info("模型 %s：大盤方向 p = %.3f，傾斜 %+.3f，和 rank_ensemble 換了 %d 組，狀態缺 %d 個，重訓日 %s",
                 model_name, pred["p_up"].iloc[0], pred["tilt"].iloc[0],
                 int((pred["pred"] != pred["base_pred"]).sum() // 2), int(pred["missing_states"].iloc[0]),
                 pred["fit_day"].iloc[0])
    except Exception as e:
        log.warning("方向的紀錄沒寫成（%s）", short_reason(e))


def short_reason(e: BaseException) -> str:
    """和 run_daily.describe 一樣：自己寫的錯誤（RuntimeError、ValueError）印出訊息，其他只寫類別。"""
    return f"{type(e).__name__}: {str(e)[:300]}" if isinstance(e, (RuntimeError, ValueError)) else type(e).__name__


# ---------------------------------------------------------------- 影子跑（使用者 2026-11-16）

SHADOW_NAME = re.compile(r"shadow_(\d{4}-\d{2}-\d{2})\.csv")
SHADOW_SCORES = "shadow_scores.csv"
TILT_MODELS = ("c2v2d", "c2")   # 輸出帶 rank_ensemble 的猜法（base_pred、base_prob）和大盤方向（p_up）


def shadow_models(cfg: dict, log=None) -> list:
    """config 的 daily_model.shadow：要影子跑的模型，照寫的順序。沒寫、空的或 none 代表不做。
    不認得或重複的名字跳過（有給 log 時記一行 ERROR）。"""
    names = (cfg.get("daily_model") or {}).get("shadow") or []
    kinds = []
    for name in [names] if isinstance(names, str) else list(names):
        if str(name).lower() == "none":
            continue
        if name not in MODEL_KINDS or name in kinds:
            if log is not None:
                log.error("daily_model.shadow 的 %s 不認得或重複，跳過（可以填 %s）", name, list(MODEL_KINDS))
            continue
        kinds.append(name)
    return kinds


def shadow_path(cfg: dict, t: str) -> Path:
    """t 那天的影子跑檔案：config 的 data.submission_dir 裡的 shadow_<t>.csv。"""
    return utils.ROOT / cfg["data"]["submission_dir"] / f"shadow_{t}.csv"


def shadow_predict(cfg: dict, data, t: str, stocks: list, log, known: dict | None = None) -> Path:
    """影子跑：daily_model.shadow 的每個模型都預測 t 的每一檔，寫 shadow_<t>.csv（不上傳），回傳路徑。

    輸入：data 是 load_model_input 的表；stocks 是網站範本的股票代號；known 是這次已經算好的
          {模型名字: 預測表}（交件用的那個），直接拿、不重算，所以影子跑裡那一欄和交出去的一樣。
    輸出：每檔一列。欄是 date、stock_id，每個模型 pred_<模型>（0／1）和 prob_<模型>（當天名次換成 0～1；
          online_lr 是機率），c2、c2v2d 另有 p_up_<模型>（大盤方向的機率）。
    算不出來的模型那幾欄空白，原因記一行 WARNING，其他模型照算。
    rank_ensemble 從 c2v2d 或 c2 的輸出拿：它們先算 rank_ensemble 再調整，輸出的 base_pred、base_prob 就是它的猜法。
    兩個都沒算出來才自己訓練。c2 和 c2v2d 在同一次執行裡共用 rank_ensemble 的三個模型（m4_c2_tilt 的快取）。
    """
    kinds = shadow_models(cfg, log)
    known = dict(known or {})
    stocks = sorted(str(s) for s in stocks)
    outputs, days, failed = {}, {}, {}
    for kind in sorted(kinds, key=lambda k: k == "rank_ensemble"):   # rank_ensemble 最後，才拿得到 c2 的輸出
        try:
            if kind in known:
                pred = known[kind]
            elif kind == "rank_ensemble" and tilt_base(outputs) is not None:
                pred = tilt_base(outputs)
            else:
                pred = load_model(kind)(data, cfg, [t], stocks)
            days[kind] = one_day(pred, t, stocks)
            outputs[kind] = pred
        except Exception as e:
            failed[kind] = public_reason(e)
            log.warning("影子跑：%s 算不出來（%s），那幾欄空白", kind, failed[kind])
    table = pd.DataFrame({"date": t, "stock_id": stocks})
    for kind in kinds:
        day = days.get(kind)
        table[f"pred_{kind}"] = day["pred"].astype(int).to_numpy() if day is not None else None
        table[f"prob_{kind}"] = day["prob"].to_numpy() if day is not None and "prob" in day else None
        if kind in TILT_MODELS:
            table[f"p_up_{kind}"] = day["p_up"].to_numpy() if day is not None and "p_up" in day else None
    path = shadow_path(cfg, t)
    crawler.write_atomic(path, table.to_csv(index=False).encode("utf-8"))
    ups = "、".join(f"{k} {int(days[k]['pred'].sum())}" for k in kinds if k in days)
    first = next((k for k in kinds if k in days), None)
    gaps = "、".join(f"{k} {int((days[k]['pred'] != days[first]['pred']).sum())}" for k in kinds if k in days and k != first)
    log.info("影子跑寫好 %s：猜漲的檔數 %s%s%s（不上傳）", shown(path), ups or "（沒有）",
             f"；和 {first} 猜得不同的檔數 {gaps}" if gaps else "", f"；算不出來 {'、'.join(failed)}" if failed else "")
    return path


def one_day(pred, t: str, stocks: list) -> pd.DataFrame:
    """預測表裡 t 那天的列，照 stocks 排（index 是 stock_id）。股票重複或少了、pred 不是 0／1 就丟 ValueError。"""
    day = pred.assign(date=pd.to_datetime(pred["date"]).dt.strftime("%Y-%m-%d"), stock_id=pred["stock_id"].astype(str))
    day = day[day["date"] == t]
    if day["stock_id"].duplicated().any():
        raise ValueError(f"預測表 {t} 有重複的股票")
    day = day.set_index("stock_id").reindex(stocks)
    if day["pred"].isna().any():
        raise ValueError(f"預測表 {t} 少了 {day.index[day['pred'].isna()].tolist()[:5]}")
    if not day["pred"].isin([0, 1]).all():
        raise ValueError(f"預測表 {t} 的 pred 不是 0／1")
    return day


def tilt_base(outputs: dict):
    """c2v2d 或 c2 的輸出裡 rank_ensemble 的猜法（date、stock_id、pred、prob）；兩個都沒有就回傳 None。"""
    for kind in TILT_MODELS:
        pred = outputs.get(kind)
        if pred is not None and {"base_pred", "base_prob"} <= set(pred.columns):
            return pred[["date", "stock_id"]].assign(pred=pred["base_pred"].to_numpy(), prob=pred["base_prob"].to_numpy())
    return None


def shadow_scores(cfg: dict, data, log) -> Path | None:
    """每一份 shadow_<日期>.csv 對上答案，重寫 shadow_scores.csv，回傳路徑；還沒有任何一天有答案時不寫、回傳 None。

    答案是那天收盤後才有的 label_intraday_return，隔天早上的特徵表才有，所以 t 早上算到的是 t 之前的日子。
    每天每個模型一列：date、model、cells（格數）、score（官方分數：每格 (2 × pred − 1) × 當天盤中報酬，取平均）、
    accuracy（猜對的比例）、pred_up（猜漲的比例）。那天那個模型有任何一格缺答案就不寫。
    """
    folder = utils.ROOT / cfg["data"]["submission_dir"]
    rows = []
    for path in sorted(folder.glob("shadow_*.csv")):
        match = SHADOW_NAME.fullmatch(path.name)
        if not match:
            continue
        table = pd.read_csv(path, dtype={"date": str, "stock_id": str})
        for column in [c for c in table.columns if c.startswith("pred_")]:
            part = table[["date", "stock_id", column]].dropna().rename(columns={column: "pred"})
            if part.empty:
                continue
            got = online_lr.official_score(part.astype({"pred": int}), data)
            if "score" in got:
                rows.append({"date": match.group(1), "model": column[len("pred_"):], "cells": got["cells"],
                             "score": got["score"], "accuracy": got["accuracy"], "pred_up": got["pred_up"]})
    if not rows:
        log.info("影子跑：還沒有哪一天有答案，%s 先不寫", SHADOW_SCORES)
        return None
    ledger = pd.DataFrame(rows)
    out = folder / SHADOW_SCORES
    crawler.write_atomic(out, ledger.to_csv(index=False).encode("utf-8"))
    last = ledger[ledger["date"] == ledger["date"].max()]
    log.info("影子跑 %s 的官方分數：%s（每天的分數在 %s）", last["date"].iloc[0],
             "、".join(f"{r.model} {r.score:+.5f}" for r in last.itertuples()), shown(out))
    return out


def shown(path: Path) -> str:
    """寫進 log 的路徑：repo 裡的寫相對路徑（log 會推上 GitHub，不寫出主機的家目錄），其他只寫檔名。"""
    try:
        return str(path.relative_to(utils.ROOT))
    except ValueError:
        return path.name
