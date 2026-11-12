# stock-market-challenger

課程 ML 期末專案（2026 秋）的比賽程式。每個台股交易日台北 09:00 前，預測 50 檔股票當天會不會「收盤高於開盤」，把 0/1 上傳課程網站。

## 流程

學校主機 oop 每個交易日早上自動跑 `run_daily_test.py --sync`，照機器學習的四步走：

| 步驟 | 程式 | 做什麼 | 產出 |
|---|---|---|---|
| 1. 爬蟲 | `src/crawler.py` | 下載老師的 Training 和 Live、Yahoo 21 個指標、期交所的台指期和 VIXTWN、CNN 恐懼貪婪指數、證交所和櫃買的日資料，原樣存檔 | `data/raw/` |
| 2. 特徵 | `src/features.py` | 清理 Yahoo 的資料，對齊到預測日 t，算 lag。一列是一檔股票的一天 | `data/processed/features/` |
| 3. 模型 | `src/rank_ensemble.py`（現在用）、`src/persist_rule.py`、`src/online_lr.py`（備援） | 讀特徵表，輸出 50 檔的 0/1。用哪一個看 `configs/config.yaml` 的 `daily_model`，說明在 [daily-model.md](memory/reference/daily-model.md) | `data/submission/submission_<t>.csv` |
| 4. 上傳 | `src/submit.py`、`src/site_api.py` | 照網站範本寫 CSV，上傳後下載回來逐格核對 | 課程網站 |

- 串起來的程式：`run_daily_test.py`。四步跑完，再用 `src/merge_raw.py` 把原始資料併成兩張表（`data/merged/`），最後把 `data/` commit、push 到這個分支。
- 時間：台北 07:10 跑第一次，沒交成就在 07:25、07:40、07:55、08:05 再試；網站上已經有當天的提交就直接結束。08:25 再跑一次，只補日韓當天的開盤。
- t（預測日）不是交易日就不跑。
- 共用的小函式（讀設定、台北時間、log）在 `src/utils.py`。

## 組員怎麼拿資料

三種資料都在這個分支的 `data/`，每個交易日約 07:30 更新。

| 資料 | 內容 | 瀏覽 |
|---|---|---|
| 特徵表（做好 lag） | 一列是「預測日 t × 一檔股票」，107 欄，已經對齊到 t，可以直接訓練 | [data/processed](https://github.com/jiangjiangian/ml-final-2026-fall/tree/claude/stock-market-challenger/data/processed) |
| 合併的原始資料 | `data/raw/` 併成個股表和市場表。原字串，沒清理，沒對齊到 t | [data/merged](https://github.com/jiangjiangian/ml-final-2026-fall/tree/claude/stock-market-challenger/data/merged) |
| 原始檔 | 爬蟲下載的原樣，一個來源一個資料夾 | [data/raw](https://github.com/jiangjiangian/ml-final-2026-fall/tree/claude/stock-market-challenger/data/raw) |

pandas 要用 `raw.githubusercontent.com` 開頭的網址（下面的 `BASE`）。表裡的連結是給人看的網頁，pandas 讀不了。

### 特徵表（做好 lag）

```python
import json, urllib.request
import pandas as pd

BASE = "https://raw.githubusercontent.com/jiangjiangian/ml-final-2026-fall/claude/stock-market-challenger/data/processed"
info = json.load(urllib.request.urlopen(f"{BASE}/manifest.json"))
df = pd.concat(pd.read_csv(f"{BASE}/features/{m}.csv.gz", dtype={"stock_id": str}, parse_dates=["date"])
               for m in info["months"])
train = df[df["label_y"].notna()]   # 預測日 t 那列還沒有答案
X, y = train[info["model_columns"]], train["label_y"]
```

- 每一欄的定義：見 [`memory/reference/feature-table.md`](memory/reference/feature-table.md)。
- 答案：`label_` 開頭的兩欄，不能放進 X。
- `info["model_columns"]`：組員的邏輯迴歸用的 55 欄。其他特徵欄只給研究，要用請先看它什麼時候空白。
- 驗證：按日期切，不能隨機拆列。
- 請用欄名讀，不要用位置，之後還會加欄。

### 合併的原始資料

特徵表沒有的欄（老師個股表的法人、技術指標、成交量，Yahoo 的開高低收量，台指期的未平倉）從這裡拿。

```python
import json, urllib.request
import pandas as pd

BASE = "https://raw.githubusercontent.com/jiangjiangian/ml-final-2026-fall/claude/stock-market-challenger/data/merged"
info = json.load(urllib.request.urlopen(f"{BASE}/manifest.json"))
stock = pd.concat(pd.read_csv(f"{BASE}/stock/{m}.csv.gz", dtype={"stock_id": str}, parse_dates=["date"])
                  for m in info["stock"]["months"])
market = pd.read_csv(f"{BASE}/market.csv.gz", parse_dates=["date"])

def asof(left, cols, same_day=False):
    """left 每一列接上 cols 在日期早於 d（same_day=True 時含 d）的最後一筆值。cols 只放同一個來源的欄。"""
    right = market[["date", *cols]].dropna(subset=cols, how="all")
    return pd.merge_asof(left.sort_values("date"), right, on="date", allow_exact_matches=same_day)

x = asof(stock, ["sox_close", "nvda_adj_close"])                          # 美股：美國日期早於 d 的最後一場
x = asof(x, ["tx_night_收盤價"], same_day=True)                           # 夜盤：標 d 的那場 05:00 就收了
x = asof(x, ["tx_day_未沖銷契約數"])                                       # 日盤的未平倉：d 收盤後才知道
x["volume_prev"] = x.groupby("stock_id")["price:成交股數"].shift(1)        # 老師個股欄：用前一個交易日
```

- 沒有對齊到 t：d 那列放的是各來源標 d 的值，當 t 的特徵前要自己往前接。每個來源能用到哪一列，見 [`memory/reference/merged-data.md`](memory/reference/merged-data.md)。
- 老師個股欄 d 那列是 d 當天的值，要照 `stock_id` 往後移一列。`y` 是 d 的答案，不能當特徵。
- `y` 是 `-1` 的列還沒有資料，整列都是 `-1`。往後移之前先把這些列換成空白。

### 原始檔

```python
RAW = "https://raw.githubusercontent.com/jiangjiangian/ml-final-2026-fall/claude/stock-market-challenger/data/raw"
sox = pd.read_csv(f"{RAW}/yfinance/sox.csv")                                           # Yahoo 的費城半導體指數
tsmc = pd.read_csv(f"{RAW}/teacher/live/market/2330.csv")                             # 老師 Live 的台積電
```

每個資料夾放什麼，見下面的檔案樹。`data/raw/yfinance/` 是 Yahoo 的原樣，沒有清理（0052 分割前的價格沒除），要乾淨的報酬用特徵表。

## 特徵表的欄位

完整的表在 [`memory/reference/feature-table.md`](memory/reference/feature-table.md)：每一欄的來源、是什麼、定義、用的是哪一刻的值、模型用不用、什麼時候空白。107 欄分成五組：

| 組 | 欄數 | 例子 | 在 `model_columns` 裡 |
|---|---|---|---|
| 鍵 | 3 | `date`、`stock_id`、`is_top50` | 不適用 |
| 個股 | 25 | `stock_ret_lag1`、`stock_intraday_ret_lag1`、`stock_open_lag1` | 25 欄都在 |
| 市場序列 | 58 | 29 個序列各有 lag1、lag2，例如 `sox_ret_lag1`、`tx_night_ret_lag1` | 15 個序列的 30 欄 |
| 只給研究 | 19 | `val_*`、`quote_*`、`*_open_gap`、`*_fresh_ret_*`、`vixtwn_*`、`fear_greed_*` | 都不在 |
| 答案 | 2 | `label_y`、`label_intraday_return` | 不能當特徵 |

## 更多說明

細節都移到 `memory/`，README 只留上面這些。

| 想知道 | 看 |
|---|---|
| 特徵表每一欄的定義和空白的情況 | [`memory/reference/feature-table.md`](memory/reference/feature-table.md) |
| 合併表的欄位、每個來源能用到哪一列 | [`memory/reference/merged-data.md`](memory/reference/merged-data.md) |
| 每天交件的模型和回測 | [`memory/reference/daily-model.md`](memory/reference/daily-model.md) |
| 排程主機怎麼裝 | [`memory/reference/runner-hosts.md`](memory/reference/runner-hosts.md) |
| 證交所、櫃買的檔案和回補 | [`memory/reference/exchange-backfill.md`](memory/reference/exchange-backfill.md) |
| 每天的流程細節、失敗時怎麼手動交 | [`memory/context/pipeline.md`](memory/context/pipeline.md) |
| 比賽規則和課程網站 | [`memory/context/competition.md`](memory/context/competition.md) |

## 檔案樹

```text
ml-final-2026-fall/            （分支 claude/stock-market-challenger）
├── README.md                  流程、組員怎麼拿資料、檔案樹（這份）
├── CLAUDE.md                  給 Claude Code：規則和 memory/ 的索引
├── run_daily_test.py          排程跑的這支：爬蟲 → 特徵 → 模型 → 上傳 → 合併 → 推資料
├── run_daily.py               骨架，沒在用
├── requirements.txt           套件和鎖定的版本
├── .env.example               帳號密碼的範例；真的值放 .env（不進 Git）
├── configs/
│   ├── config.yaml            所有設定：網址、Yahoo 代號、特徵、模型、截止時間
│   └── live_ca.pem            Live 網址的自簽憑證（公開的，不是密碼）
├── src/
│   ├── crawler.py             1. 爬蟲：下載所有來源到 data/raw/
│   ├── features.py            2. 特徵：data/raw/ → data/processed/features/
│   ├── rank_ensemble.py       3. 模型：排名集成（現在用）
│   ├── persist_rule.py        3. 模型：持續性規則（第一個備援）
│   ├── online_lr.py           3. 模型：組員的邏輯迴歸（第二個備援）
│   ├── submit.py              4. 上傳：寫 CSV、上傳、下載回來核對
│   ├── site_api.py            4. 上傳：課程網站的 API（登入、範本、上傳、下載）
│   ├── merge_raw.py           data/raw/ → data/merged/ 的兩張表
│   ├── utils.py               共用：讀設定和帳密、台北時間、截止檢查、log
│   ├── train.py               骨架，沒在用
│   └── predict.py             骨架，沒在用
├── data/
│   ├── raw/                   爬蟲寫的，和來源一模一樣
│   │   ├── teacher/           training/ 是 Training ZIP 解開（不會再變）；live/ 是 Live ZIP 解開，每天換新
│   │   ├── yfinance/          21 個指標，一個序列一個 CSV；usd_twd_1h.csv 是匯率的 1 小時K棒
│   │   ├── taifex/            tx.csv：台指期日盤和夜盤；vixtwn.csv：VIXTWN
│   │   ├── cnn/               fear_greed.csv：CNN 恐懼貪婪指數
│   │   ├── open_today/        kospi.csv、n225.csv：日韓當天的開盤，08:25 抓
│   │   ├── twse/              證交所：valuation.csv 估值、quotes.csv 收盤行情
│   │   ├── tpex/              櫃買中心：valuation.csv、quotes.csv
│   │   ├── manifest.json      下載紀錄
│   │   ├── phase2_days.json   課程網站的交易日清單
│   │   └── exchange_backfill.json   證交所、櫃買回補的進度
│   ├── processed/             特徵表（做好 lag）
│   │   ├── features/          YYYY-MM.csv.gz，一個月一檔，每天只更新最後兩個月
│   │   └── manifest.json      有哪些月份、模型用哪些欄、清理紀錄
│   ├── merged/                合併的原始資料
│   │   ├── stock/             YYYY-MM.csv.gz：一列是一天 × 一檔
│   │   ├── market.csv.gz      一列是一天
│   │   └── manifest.json      月份、欄名、列數、各來源的最後一天
│   └── submission/            每天的產出
│       ├── submission_YYYY-MM-DD.csv   上傳的 0/1
│       ├── run_YYYY-MM-DD.log          執行紀錄，失敗時先看這個
│       ├── upload_log.jsonl            上傳紀錄
│       └── backup/                     上傳前先下載網站上那一份
├── memory/                    專案的說明和紀錄，一個主題一個檔
│   ├── reference/             給組員查的說明（2026-11-12 從 README 移過來）
│   │   ├── feature-table.md   特徵表每一欄：來源、定義、時間、模型用不用、空白的情況
│   │   ├── merged-data.md     合併表的三個檔、每個來源能用到哪一列
│   │   ├── daily-model.md     每天交件的模型和回測
│   │   ├── runner-hosts.md    排程主機怎麼裝
│   │   └── exchange-backfill.md   證交所、櫃買的檔案和回補
│   ├── glossary.md            名詞
│   ├── context/               competition、pipeline、data-rules、environment、open-questions
│   └── projects/              crawler、features、kaggle-models 的設計紀錄
├── deploy/
│   ├── runner_setup.sh        排程主機（學校的 oop）的安裝
│   ├── crontab.txt            排程的時間
│   ├── mac/                   Mac 備援（還沒裝）
│   └── gcp_setup.sh           GCP 主機的安裝（備用）
├── notebooks/
│   └── README.md              實驗的檔名和注意事項；每天的自動流程不會讀這裡
├── tests/                     離線測試，用 pytest 跑
│   ├── test_crawler.py        爬蟲（假伺服器、假時鐘）
│   ├── test_exchange.py       爬蟲：證交所、櫃買
│   ├── test_vixtwn_cnn.py     爬蟲和特徵：VIXTWN、CNN 恐懼貪婪
│   ├── test_open_today.py     爬蟲和特徵：日韓當天的開盤
│   ├── test_features.py       特徵：清理、交易日、lag、和舊分支凍結資料的對照
│   ├── test_features_new_columns.py   特徵：只給研究的欄
│   ├── test_no_future_data.py 特徵：只能用 t 之前的資料
│   ├── test_persist_rule.py   模型：持續性規則、模型開關
│   ├── test_online_lr.py      模型：組員的邏輯迴歸
│   ├── test_submit.py         上傳：假網站，不重試、核對
│   ├── test_submission_format.py   上傳：CSV 的欄位、列數、0/1
│   ├── test_run_daily_test.py 每日流程：git 同步、log
│   ├── test_merge_raw.py      合併表
│   ├── fixtures/              舊分支 data-collection 的凍結資料，只給對照測試用，不要改
│   └── data_exchange/         證交所、櫃買真回應剪小的版本
├── models/                    空的
├── .claude/                   Claude Code 的專案設定和輸出風格
├── .gitignore                 哪些檔案不進 Git
│   ├── test_rank_ensemble.py  模型：排名集成、備援的順序
└── .gitattributes             data/raw/、tests/fixtures/ 不改換行；upload_log.jsonl 用 union 合併
```
