"""data/raw/ 的原始資料合併成兩張表，給組員研究用（使用者 2026-11-11）。

輸出在 config 的 data.merged_dir（data/merged/）：

- stock/YYYY-MM.csv.gz：一列是「一天 × 一檔」。鍵 date、stock_id、is_top50，接老師個股表 20 欄（欄名照原樣，
  Training 全部，接 Live 晚於 Training 最後一天的列），再接證交所、櫃買四個檔（欄名加 twse_valuation_ 這類前綴）。
  兩邊取聯集：老師的表跳過的停牌日，交易所有列時也留著，老師欄空白。
- market.csv.gz：一列是一天，date 是所有來源日期的聯集。老師 global（teacher_ 前綴）、yfinance 每個序列的
  開高低收量（<名稱>_open 這類）、台指期日盤和夜盤（tx_day_、tx_night_，每個日期、時段只留近月合約）、
  VIXTWN（vixtwn、vixtwn_1min_avg）、CNN 恐懼貪婪（fear_greed_score）。
- manifest.json：月份、欄名、列數、每個來源的最後一天、來源檔的指紋。沒有時間戳，資料沒變就不會變。

每一格都是來源 CSV 的原字串，不轉數字、不清理（-1、--、N/A 原樣留著）。各來源用自己的日期，沒有對齊到預測日 t：
d 那列能不能當 t 的特徵，看 README「合併的原始資料」。不併進來的：yfinance/usd_twd_1h.csv（1 小時K棒）、
open_today/（當天開盤）、json 紀錄檔。這支程式不讀也不寫 data/processed/。

    python -m src.merge_raw              # 來源檔有變才重算，只寫內容不一樣的檔
    python -m src.merge_raw --rebuild    # 不看指紋，全部重算
"""

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd

from src import crawler, utils

FORMAT = 1   # 欄位或寫法改了就加 1，下次執行就算來源沒變也會重算
STOCK_KEY = ("date", "stock_id")


class MergeError(RuntimeError):
    """來源檔不見、欄名不對、鍵重複：這次不寫任何檔。"""


# ---------------------------------------------------------------- 讀來源


def read_table(path: Path, columns: tuple, raw_dir: Path) -> pd.DataFrame:
    """讀成全是字串的表（空格是空字串），表頭要和 columns 一模一樣。"""
    name = path.relative_to(raw_dir).as_posix()
    if not path.exists():
        raise MergeError(f"{name} 不見了")
    with open(path, encoding="utf-8", newline="") as f:
        header = next(csv.reader(f), None)
    if header is None or tuple(header) != tuple(columns):
        raise MergeError(f"{name} 的表頭和預期不一樣")
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False, encoding="utf-8")


def no_duplicates(df: pd.DataFrame, key: list, name: str) -> None:
    dup = df.duplicated(key)
    if dup.any():
        first = df.loc[dup, key].iloc[0].tolist()
        raise MergeError(f"{name} 有重複的鍵 {first}")


def source_files(raw_dir: Path, cfg: dict) -> list:
    """合併會讀的所有檔，順序固定（指紋照這個順序算）。"""
    files = []
    for part in ("training", "live"):
        files += sorted((raw_dir / "teacher" / part / "market").glob("*.csv"))
        files.append(raw_dir / "teacher" / part / "global" / "global_data.csv")
    files.append(raw_dir / "teacher" / "training" / "info.json")
    files += [raw_dir / "yfinance" / f"{name}.csv" for name in cfg["yfinance"]["tickers"]]
    files.append(raw_dir / "taifex" / "tx.csv")
    files.append(raw_dir / cfg["vixtwn"]["file"])
    files.append(raw_dir / cfg["cnn"]["file"])
    files += [raw_dir / spec.file for spec in crawler.EXCHANGE_SPECS]
    return files


def source_digest(raw_dir: Path, files: list) -> str:
    """每個檔的相對路徑和 sha256 串起來再算一次 sha256，加上 FORMAT。少了檔就丟 MergeError。"""
    h = hashlib.sha256(f"format {FORMAT}\n".encode())
    for path in files:
        name = path.relative_to(raw_dir).as_posix()
        if not path.exists():
            raise MergeError(f"{name} 不見了")
        h.update(f"{name} {hashlib.sha256(path.read_bytes()).hexdigest()}\n".encode())
    return h.hexdigest()


def load_teacher_stocks(raw_dir: Path) -> tuple:
    """回傳 (個股表, Training 最後一天)。Training 全部，接 Live 日期晚於 Training 最後一天的列（和 features.load_teacher 一樣）。"""
    train_dir, live_dir = raw_dir / "teacher" / "training" / "market", raw_dir / "teacher" / "live" / "market"
    paths = sorted(train_dir.glob("*.csv"))
    if not paths:
        raise MergeError("老師 Training 沒有個股檔")
    train = {p.stem: read_table(p, crawler.STOCK_COLUMNS, raw_dir) for p in paths}
    boundary = max(d["date"].max() for d in train.values() if len(d))
    parts = []
    for code, d in train.items():
        parts.append(d.assign(stock_id=code))
    for p in sorted(live_dir.glob("*.csv")) if live_dir.exists() else []:
        if p.stem not in train:
            raise MergeError(f"Live 有 Training 沒有的代號 {p.stem}")
        d = read_table(p, crawler.STOCK_COLUMNS, raw_dir)
        parts.append(d[d["date"] > boundary].assign(stock_id=p.stem))
    out = pd.concat(parts, ignore_index=True)
    no_duplicates(out, list(STOCK_KEY), "老師個股表")
    return out[["date", "stock_id", *crawler.STOCK_COLUMNS[1:]]], boundary


def load_teacher_global(raw_dir: Path, boundary: str) -> pd.DataFrame:
    train = read_table(raw_dir / "teacher" / "training" / "global" / "global_data.csv", crawler.GLOBAL_COLUMNS, raw_dir)
    live_path = raw_dir / "teacher" / "live" / "global" / "global_data.csv"
    parts = [train]
    if live_path.exists():
        live = read_table(live_path, crawler.GLOBAL_COLUMNS, raw_dir)
        parts.append(live[live["date"] > boundary])
    out = pd.concat(parts, ignore_index=True)
    no_duplicates(out, ["date"], "老師 global")
    return out.rename(columns={c: f"teacher_{c}" for c in crawler.GLOBAL_COLUMNS[1:]})


def near_month(tx: pd.DataFrame) -> pd.DataFrame:
    """每個日期、時段留到期月最早的合約。和 features.tx_values 一樣只看有收盤價的列；那個時段都沒成交時留到期月最早的。"""
    traded = ~tx["收盤價"].isin(["", "-"])
    tx = tx.assign(_traded=traded).sort_values(["交易日期", "交易時段", "_traded", "到期月份(週別)"],
                                               ascending=[True, True, False, True], kind="stable")
    return tx.drop_duplicates(["交易日期", "交易時段"], keep="first").drop(columns="_traded")


def load_tx(raw_dir: Path) -> list:
    tx = read_table(raw_dir / "taifex" / "tx.csv", crawler.TAIFEX_COLUMNS, raw_dir)
    unknown = set(tx["交易時段"]) - set(crawler.TAIFEX_SESSIONS)
    if unknown:
        raise MergeError(f"taifex/tx.csv 有看不懂的交易時段 {sorted(unknown)}")
    no_duplicates(tx, ["交易日期", "交易時段", "到期月份(週別)"], "taifex/tx.csv")
    tx = near_month(tx)
    keep = [c for c in crawler.TAIFEX_COLUMNS if c not in ("交易日期", "交易時段")]
    out = []
    for session, kind in crawler.TAIFEX_SESSIONS.items():
        name = crawler.TX_SERIES[kind]
        part = tx[tx["交易時段"] == session][["交易日期", *keep]]
        out.append(part.rename(columns={"交易日期": "date", **{c: f"{name}_{c}" for c in keep}}))
    return out


def build_stock(raw_dir: Path) -> pd.DataFrame:
    teacher, boundary = load_teacher_stocks(raw_dir)
    info = json.loads((raw_dir / "teacher" / "training" / "info.json").read_text(encoding="utf-8-sig"))
    top50 = {str(x) for x in info["Top50@Y"]}
    df = teacher
    for spec in crawler.EXCHANGE_SPECS:
        part = read_table(raw_dir / spec.file, spec.columns, raw_dir)
        no_duplicates(part, list(STOCK_KEY), spec.file)
        part = part.rename(columns={c: f"{spec.key}_{c}" for c in spec.columns if c not in STOCK_KEY})
        df = df.merge(part, on=list(STOCK_KEY), how="outer")
    df.insert(2, "is_top50", df["stock_id"].isin(top50).map({True: "1", False: "0"}))
    return df.sort_values(list(STOCK_KEY), kind="stable").reset_index(drop=True), boundary


def build_market(raw_dir: Path, cfg: dict, boundary: str) -> tuple:
    """回傳 (市場表, {來源: 最後一天})。"""
    parts = {"teacher_global": load_teacher_global(raw_dir, boundary)}
    for name in cfg["yfinance"]["tickers"]:
        d = read_table(raw_dir / "yfinance" / f"{name}.csv", crawler.YF_COLUMNS, raw_dir)
        parts[name] = d.rename(columns={c: f"{name}_{c}" for c in crawler.YF_COLUMNS[1:]})
    tx_day, tx_night = load_tx(raw_dir)
    parts["tx_day"], parts["tx_night"] = tx_day, tx_night
    parts["vixtwn"] = read_table(raw_dir / cfg["vixtwn"]["file"], crawler.VIXTWN_COLUMNS, raw_dir)
    cnn = read_table(raw_dir / cfg["cnn"]["file"], crawler.FEAR_GREED_COLUMNS, raw_dir)
    parts["fear_greed"] = cnn.rename(columns={"score": "fear_greed_score"})
    df = None
    for name, d in parts.items():
        no_duplicates(d, ["date"], name)
        df = d if df is None else df.merge(d, on="date", how="outer")
    last = {name: (d["date"].max() if len(d) else None) for name, d in parts.items()}
    return df.sort_values("date", kind="stable").reset_index(drop=True), last


# ---------------------------------------------------------------- 寫檔


def to_csv_gz(df: pd.DataFrame) -> bytes:
    """和 features.to_csv_gz 同樣的寫法：UTF-8、LF、gzip 的 mtime 固定，同樣的內容得到同樣的位元組。"""
    text = df.to_csv(index=False, lineterminator="\n")
    return gzip.compress(text.encode("utf-8"), compresslevel=6, mtime=0)


def write_if_changed(path: Path, payload: bytes) -> bool:
    if path.exists() and path.read_bytes() == payload:
        return False
    crawler.write_atomic(path, payload)
    return True


def merge(cfg: dict, raw_dir: Path, out_dir: Path, rebuild: bool = False) -> dict:
    """來源有變（或 rebuild）就重算兩張表，只寫內容不一樣的檔。回傳 {status, written, ...}。"""
    files = source_files(raw_dir, cfg)
    digest = source_digest(raw_dir, files)
    manifest_path = out_dir / "manifest.json"
    try:
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    previous = previous if isinstance(previous, dict) else {}
    expected = [f"stock/{m}.csv.gz" for m in previous.get("stock", {}).get("months", [])] + ["market.csv.gz"]
    if not rebuild and previous.get("source_digest") == digest and all((out_dir / p).exists() for p in expected):
        return {"status": "unchanged", "written": []}

    stock, boundary = build_stock(raw_dir)
    market, last = build_market(raw_dir, cfg, boundary)
    last["stock"] = stock["date"].max()
    months = stock["date"].str[:7]
    all_months = sorted(months.unique())
    written = []
    for m in all_months:
        if write_if_changed(out_dir / "stock" / f"{m}.csv.gz", to_csv_gz(stock[months == m])):
            written.append(f"stock/{m}.csv.gz")
    for path in sorted((out_dir / "stock").glob("*.csv.gz")):
        if path.name[:7] not in all_months:
            path.unlink()
            written.append(f"刪掉 stock/{path.name}")
    if write_if_changed(out_dir / "market.csv.gz", to_csv_gz(market)):
        written.append("market.csv.gz")
    report = {
        "format": FORMAT,
        "teacher_training_last_date": boundary,
        "stock": {"months": all_months, "rows": len(stock), "columns": list(stock.columns)},
        "market": {"file": "market.csv.gz", "rows": len(market), "first_date": market["date"].iloc[0],
                   "last_date": market["date"].iloc[-1], "columns": list(market.columns)},
        "last_dates": last,
        "source_digest": digest,
    }
    payload = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if write_if_changed(manifest_path, payload):
        written.append("manifest.json")
    return {"status": "written" if written else "same", "written": written, "stock_rows": len(stock),
            "market_rows": len(market)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="data/raw/ → data/merged/（個股表一個月一檔、市場表一檔）")
    parser.add_argument("--rebuild", action="store_true", help="不看來源指紋，全部重算")
    args = parser.parse_args(argv)
    cfg = utils.load_config()
    log = utils.get_logger("merge_raw", utils.taipei_now().date().isoformat())
    result = merge(cfg, utils.ROOT / cfg["data"]["raw_dir"], utils.ROOT / cfg["data"]["merged_dir"], args.rebuild)
    if result["status"] == "unchanged":
        log.info("合併表：來源沒變，不重算")
    else:
        written = result["written"]
        log.info("合併表：個股 %d 列、市場 %d 列；寫了 %d 個檔%s", result["stock_rows"], result["market_rows"],
                 len(written), f" {written}" if 0 < len(written) <= 5 else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
