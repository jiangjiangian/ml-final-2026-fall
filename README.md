# stock-market-challenger

課程 ML 期末專案（2026 秋）的比賽程式。每個台股交易日台北 09:00 前，預測 50 檔股票當天會不會「收盤高於開盤」，把 0/1 上傳課程網站。

## 流程

學校主機 oop 每個交易日早上自動跑 `run_daily.py --sync`。每一步在 `src/pipeline/` 有一個檔，照執行順序編號：

| 步驟 | 程式 | 做什麼 | 產出 |
|---|---|---|---|
| 1. 爬蟲 | `src/pipeline/step1_crawler.py` | 下載老師的 Training 和 Live、Yahoo 21 個指標、期交所的台指期和 VIXTWN、CNN 恐懼貪婪指數、證交所和櫃買的日資料，原樣存檔 | `data/raw/` |
| 2. 特徵 | `src/pipeline/step2_features.py` | 清理 Yahoo 的資料，對齊到預測日 t，算 lag。一列是一檔股票的一天 | `data/processed/features/` |
| 3. 訓練和預測 | `src/pipeline/step3_train_predict.py` | 照 `configs/config.yaml` 的 `daily_model` 選 `src/models/` 的模型，用 t 之前的答案訓練，輸出 50 檔的 0/1；算不出來照順序換備援；交完再把 `daily_model.shadow` 列的模型都算一遍（影子跑，不上傳） | `data/submission/scores_<t>.csv`、`shadow_<t>.csv` |
| 4. 上傳 | `src/pipeline/step4_submit.py`、`site_api.py` | 照網站範本寫 CSV，上傳後下載回來逐格核對 | `data/submission/submission_<t>.csv`、課程網站 |
| 5. 合併 | `src/pipeline/step5_merge_raw.py` | 把原始資料併成個股表和市場表，給組員研究，模型不看 | `data/merged/` |
| 6. 傍晚打分 | `src/pipeline/step6_evening_score.py` | 收盤後下載老師的 Live，用 t 那列替影子跑的每個模型和網站上我們那份打分，不上傳 | `data/submission/shadow_scores.csv`、`site_scores.csv` |

- 串起來的程式：`run_daily.py`。開始前先 `git pull`，五步跑完把 `data/` commit、push 到這個分支。連不上 GitHub 時重試約 2 分鐘，再不行就用 oop 上次 pull 到的程式照爬照交，資料下次再推。舊名字 `run_daily_test.py` 會直接轉到它。
- 時間：台北 07:10 跑第一次，沒交成就在 07:25、07:40、07:55、08:05 再試；網站上已經有當天的提交就不上傳；t 還沒爬過時照樣補爬、推資料（2026-11-18 起）。例外是排程自己交的那份用的資料不完整（用了備援，或方向模型的狀態有缺）：之後的時段重爬重算，補齊後預測變了才重交，一天最多多交一次，08:44 以後不再做，組員手動交的不動。08:25 再跑一次，只補日韓當天的開盤。16:10 跑 `run_daily.py --sync --evening` 打當天的分數，沒打完 20:00 再試（2026-11-18 起）。
- t（預測日）不是交易日就不跑。
- 影子跑（2026-11-16 起）：交件後，或組員已經手動交了時，`daily_model.shadow` 的模型（五個交件用的，2026-11-23 起加只記不交的 `overnight_up`、`rank_inst`）都預測 t，存 `shadow_<t>.csv`，不上傳；每個模型的官方分數在 `shadow_scores.csv`，當天傍晚就有（用老師 Live 的 t 那列打分）；網站上我們那份的分數和名次在 `site_scores.csv`。說明在 [`memory/reference/05-daily-model.md`](memory/reference/05-daily-model.md) 的「影子跑」。
- N1 影子跑（2026-11-23 起）：收尾時用自己的環境 `.venv-n1`（有 torch）開子程序，把 JS_ONLINE 加進 c2v2d 的排名集成，存 `data/submission/n1/n1_<t>.csv`，不上傳，出事也不影響交件。說明在同一份的「N1 影子跑」，裝法在 [`deploy/n1_setup.md`](deploy/n1_setup.md)。
- 共用的小函式（讀設定、台北時間、log）在 `src/pipeline/utils.py`。

### 模型

`src/models/` 一個檔一個模型，照做出來的日期編號。說明和回測在 [05-daily-model.md](memory/reference/05-daily-model.md)。

| 檔案 | config 的名字 | 做出來 | 現在 |
|---|---|---|---|
| `m1_online_lr.py` | `online_lr` | 2026-11-05 | 第四個備援（11-07～11-11 交件用） |
| `m2_persist_rule.py` | `persist` | 2026-11-12 | 第三個備援（11-12 交件用） |
| `m3_rank_ensemble.py` | `rank_ensemble` | 2026-11-12 | 第二個備援（11-13 交件用），也是 C2 的底 |
| `m4_c2_tilt.py` | `c2v2d`、`c2` | 2026-11-15 | 主模型 `c2v2d`，第一個備援 `c2`（11-16 起） |
| `m5_overnight_up.py` | `overnight_up` | 2026-11-20 | 只影子跑、不交件：前一晚美股大跌就全猜漲，其他日子照排名集成 |
| `m6_rank_inst.py` | `rank_inst` | 2026-11-20 | 只影子跑、不交件：排名集成的 41 欄加法人買賣超 23 欄；早上法人資料沒到就傍晚補算 |
| `m7_n1_js_online.py` | 沒有（不在 `MODEL_KINDS`） | 2026-11-23 | N1 影子跑：Kaggle 訓練好的 JS_ONLINE 每天更新一步，加進 c2v2d 的排名集成；在 `.venv-n1` 用子程序跑，只記不交 |

m1～m6 都在預測那天早上從頭訓練，不存檔。根目錄的 `models/` 只放 m7 的起始狀態（`models/n1/`）。

### 手動跑

```bash
python run_daily.py --dry-run                     # 跑完整個流程，不上傳
python run_daily.py --phase 2 --date 2026-11-17   # 指定 t（不是今天時不跑爬蟲和特徵）
python -m src.pipeline.step1_crawler              # 只跑爬蟲（研究模式，不檢查時間）
python -m src.pipeline.step2_features --rebuild   # 特徵欄改了以後，重建整張特徵表
python -m src.pipeline.step5_merge_raw            # 重算合併表
python -m pytest tests/                           # 離線測試
```

舊的 import 只有 `from src import features` 這種寫法還能用；`import src.features`、`from src.features import ...`、`python -m src.features` 都要改成新路徑。

## 組員怎麼拿資料

三種資料都在這個分支的 `data/`，每個交易日約 07:30 更新。

| 資料 | 內容 | 瀏覽 |
|---|---|---|
| 特徵表（做好 lag） | 一列是「預測日 t × 一檔股票」，110 欄，已經對齊到 t，可以直接訓練 | [data/processed](https://github.com/jiangjiangian/ml-final-2026-fall/tree/claude/stock-market-challenger/data/processed) |
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

- 每一欄的定義：見 [`memory/reference/02-feature-table.md`](memory/reference/02-feature-table.md)。
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

- 沒有對齊到 t：d 那列放的是各來源標 d 的值，當 t 的特徵前要自己往前接。每個來源能用到哪一列，見 [`memory/reference/04-merged-data.md`](memory/reference/04-merged-data.md)。
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

完整的表在 [`memory/reference/02-feature-table.md`](memory/reference/02-feature-table.md)：每一欄的來源、是什麼、定義、用的是哪一刻的值、模型用不用、什麼時候空白。110 欄分成六組：

| 組 | 欄數 | 例子 | 在 `model_columns` 裡 |
|---|---|---|---|
| 鍵 | 3 | `date`、`stock_id`、`is_top50` | 不適用 |
| 產業 | 3 | `industry_original`、`industry_group`、`industry_group_id`（每檔固定） | 都不在 |
| 個股 | 25 | `stock_ret_lag1`、`stock_intraday_ret_lag1`、`stock_open_lag1` | 25 欄都在 |
| 市場序列 | 58 | 29 個序列各有 lag1、lag2，例如 `sox_ret_lag1`、`tx_night_ret_lag1` | 15 個序列的 30 欄 |
| 只給研究 | 19 | `val_*`、`quote_*`、`*_open_gap`、`*_fresh_ret_*`、`vixtwn_*`、`fear_greed_*` | 都不在 |
| 答案 | 2 | `label_y`、`label_intraday_return` | 不能當特徵 |

## 更多說明

細節都移到 `memory/`，README 只留上面這些。

| 想知道 | 看 |
|---|---|
| 特徵表每一欄的定義和空白的情況 | [`memory/reference/02-feature-table.md`](memory/reference/02-feature-table.md) |
| 合併表的欄位、每個來源能用到哪一列 | [`memory/reference/04-merged-data.md`](memory/reference/04-merged-data.md) |
| 每天交件的模型和回測 | [`memory/reference/05-daily-model.md`](memory/reference/05-daily-model.md) |
| 排程主機怎麼裝 | [`memory/reference/06-runner-hosts.md`](memory/reference/06-runner-hosts.md) |
| 證交所、櫃買的檔案和回補 | [`memory/reference/03-exchange-backfill.md`](memory/reference/03-exchange-backfill.md) |
| 每天的流程細節、失敗時怎麼手動交 | [`memory/context/02-pipeline.md`](memory/context/02-pipeline.md) |
| 比賽規則和課程網站 | [`memory/context/01-competition.md`](memory/context/01-competition.md) |

## 檔案樹

```text
ml-final-2026-fall/            （分支 claude/stock-market-challenger）
├── README.md                  流程、組員怎麼拿資料、檔案樹（這份）
├── CLAUDE.md                  給 Claude Code：規則和 memory/ 的索引
├── run_daily.py               排程跑的這支：同步 → 爬蟲 → 特徵 → 訓練和預測 → 上傳 → 合併 → 推資料
├── run_daily_test.py          舊名字，直接轉到 run_daily.py（oop 裝好的 crontab 還在叫它）
├── requirements.txt           套件和鎖定的版本
├── requirements-n1.txt        N1 影子跑自己的環境 .venv-n1 的套件（torch CPU 版等，和 Kaggle 一樣的版本）
├── .env.example               帳號密碼的範例；真的值放 .env（不進 Git）
├── configs/
│   ├── config.yaml            所有設定：網址、Yahoo 代號、特徵、模型、截止時間
│   └── live_ca.pem            Live 網址的自簽憑證（公開的，不是密碼）
├── src/
│   ├── pipeline/              每天的流程，照執行順序編號
│   │   ├── step1_crawler.py        1. 爬蟲：下載所有來源到 data/raw/
│   │   ├── step2_features.py       2. 特徵：data/raw/ → data/processed/features/
│   │   ├── step3_train_predict.py  3. 訓練和預測：選模型、換備援、存每檔的分數
│   │   ├── step4_submit.py         4. 上傳：寫 CSV、上傳、下載回來核對
│   │   ├── step5_merge_raw.py      5. 合併：data/raw/ → data/merged/ 的兩張表
│   │   ├── step6_evening_score.py  6. 傍晚打分：老師 Live 的 t 那列 → 影子跑和網站上那份的分數
│   │   ├── site_api.py             課程網站的 API（登入、範本、上傳、下載）
│   │   └── utils.py                共用：讀設定和帳密、台北時間、截止檢查、log
│   ├── models/                每天交件可以選的模型，照做出來的日期編號
│   │   ├── __init__.py             config 的名字和檔案的對照（MODEL_KINDS），每個模型的輸入和輸出
│   │   ├── m1_online_lr.py         組員的邏輯迴歸（2026-11-05）
│   │   ├── m2_persist_rule.py      持續性規則（2026-11-12）
│   │   ├── m3_rank_ensemble.py     排名集成（2026-11-12）
│   │   ├── m4_c2_tilt.py           C2、C2v2d：排名集成加大盤方向的傾斜（2026-11-15，現在用 c2v2d）
│   │   ├── m5_overnight_up.py      隔夜大跌全猜漲（2026-11-20，只影子跑，不能交件）
│   │   ├── m6_rank_inst.py         法人組排名集成（2026-11-20，只影子跑，不能交件）
│   │   └── m7_n1_js_online.py      N1 影子跑：JS_ONLINE 每天更新、加進 c2v2d（2026-11-23，.venv-n1 的子程序，只記不交）
│   └── twfm/                  RP 40 研究用：Kronos 這類時序基礎模型在台股的微調套件（說明在 src/twfm/README.md），正式流程不 import
├── data/
│   ├── raw/                   爬蟲寫的，和來源一模一樣
│   │   ├── teacher/           training/ 是 Training ZIP 解開（不會再變）；live/ 是 Live ZIP 解開，每天換新
│   │   ├── yfinance/          21 個指標，一個序列一個 CSV；usd_twd_1h.csv 是匯率的 1 小時K棒；gspc.csv 只給 N1 影子跑，不進特徵表和合併表
│   │   ├── taifex/            tx.csv：台指期日盤和夜盤；vixtwn.csv：VIXTWN
│   │   ├── cnn/               fear_greed.csv：CNN 恐懼貪婪指數
│   │   ├── open_today/        kospi.csv、n225.csv：日韓當天的開盤，08:25 抓
│   │   ├── twse/              證交所：valuation.csv 估值、quotes.csv 收盤行情
│   │   ├── tpex/              櫃買中心：valuation.csv、quotes.csv
│   │   ├── manifest.json      下載紀錄
│   │   ├── phase2_days.json   課程網站的交易日清單
│   │   └── exchange_backfill.json   證交所、櫃買回補的進度
│   ├── processed/             特徵表（做好 lag）
│   │   ├── industry/          tw_top100_industry.csv：100 檔的產業對照表，特徵表的產業欄用
│   │   ├── features/          YYYY-MM.csv.gz，一個月一檔，每天只更新最後兩個月
│   │   └── manifest.json      有哪些月份、模型用哪些欄、清理紀錄
│   ├── merged/                合併的原始資料
│   │   ├── stock/             YYYY-MM.csv.gz：一列是一天 × 一檔
│   │   ├── market.csv.gz      一列是一天
│   │   └── manifest.json      月份、欄名、列數、各來源的最後一天
│   └── submission/            每天的產出
│       ├── submission_YYYY-MM-DD.csv   上傳的 0/1
│       ├── scores_YYYY-MM-DD.csv       當天每檔的模型分數和名次（2026-11-16 起，研究用，不上傳）
│       ├── shadow_YYYY-MM-DD.csv       影子跑：每個模型當天各自的猜法（2026-11-17 起，不上傳）
│       ├── shadow_scores.csv           影子跑每天每個模型的官方分數（當天傍晚就有）
│       ├── site_scores.csv             網站上我們那份每天的分數、名次、累計名次（2026-11-18 起）
│       ├── n1/                         N1 影子跑：n1_YYYY-MM-DD.csv 每檔的猜法，inputs_YYYY-MM-DD.npz 當天用的輸入（2026-11-23 起）
│       ├── run_YYYY-MM-DD.log          執行紀錄，失敗時先看這個
│       ├── upload_log.jsonl            上傳紀錄
│       └── backup/                     上傳前先下載網站上那一份
├── memory/                    專案的說明和紀錄，一個主題一個檔；整理原則在 memory/README.md
│   ├── README.md              三個資料夾放什麼、檔名怎麼編號、增刪檔案時要改哪裡
│   ├── context/               專案的規則和環境：01-competition、02-pipeline、03-open-questions、04-environment、05-data-rules
│   ├── projects/              每條工作線的設計和進度：01-crawler 到 23-recent-prediction-research
│   └── reference/             給組員查的說明（2026-11-12 從 README 移過來）
│       ├── 01-glossary.md          名詞
│       ├── 02-feature-table.md     特徵表每一欄：來源、定義、時間、模型用不用、空白的情況
│       ├── 03-exchange-backfill.md 證交所、櫃買的檔案和回補
│       ├── 04-merged-data.md       合併表的三個檔、每個來源能用到哪一列
│       ├── 05-daily-model.md       每天交件的模型、回測和影子跑
│       └── 06-runner-hosts.md      排程主機怎麼裝
├── deploy/
│   ├── runner_setup.sh        排程主機（學校的 oop）的安裝
│   ├── n1_setup.md            N1 影子跑的環境 .venv-n1：下載套件、在 oop 安裝、測試、重現檢查、試跑、上線
│   ├── crontab.txt            排程的時間
│   ├── mac/                   Mac 備援（還沒裝）
│   └── gcp_setup.sh           GCP 主機的安裝（備用）
├── notebooks/                 實驗的地方，每天的自動流程不會讀這裡；整理原則在 notebooks/README.md
│   ├── README.md              放什麼、不放什麼、檔名怎麼取
│   ├── teammate/              組員的 notebook 01～05（只在本機，沒進 Git）
│   │   ├── README.md          每本做什麼、輸入檔從哪裡來
│   │   ├── exports/           html 匯出
│   │   └── data/              連到 data/raw/teacher/ 的捷徑，notebook 用相對路徑讀
│   └── kaggle/                在 Kaggle 上跑的研究，一個系列一個資料夾（只在本機，沒進 Git）：2026-11-05～06 的平行訓練（memory/projects/02-kaggle-models.md）、BT 突破研究（11-breakthrough-research）、DR 概念漂移（16-concept-drift）、KD 從頭設計（17-kdd-models-from-scratch）、RB 反彈訊號（18-rebound-signal）、RP 全新研究管線（22-ml-research-pipeline）
│       ├── README.md          怎麼建 dataset、推 notebook、收結果
│       ├── build_dataset.sh   複製 raw、建立或更新 Kaggle dataset tw-intraday-data
│       ├── push_all.sh        把每本 notebook 推到 Kaggle（--only <slug> 只推一本）
│       ├── pull_outputs.sh    看狀態，把完成的 output/ 下載回來（下載的是暫存，看完就刪）
│       └── data/              Kaggle dataset 的內容
│           ├── twfeat.py              讀資料、算特徵、評估的模組
│           ├── check_twfeat.py        本機的輕量檢查；輸出 check_output.txt
│           ├── dataset-metadata.json  Kaggle dataset 的 metadata（KAGGLE_USER 是佔位字串）
│           ├── README.md              dataset 的內容說明
│           └── raw/                   老師資料和 yfinance 的複本（不進 Git）
├── tests/                     離線測試，用 pytest 跑
│   ├── test_crawler.py        爬蟲（假伺服器、假時鐘）
│   ├── test_exchange.py       爬蟲：證交所、櫃買
│   ├── test_vixtwn_cnn.py     爬蟲和特徵：VIXTWN、CNN 恐懼貪婪
│   ├── test_open_today.py     爬蟲和特徵：日韓當天的開盤
│   ├── test_features.py       特徵：清理、交易日、lag、和舊分支凍結資料的對照
│   ├── test_features_new_columns.py   特徵：只給研究的欄
│   ├── test_no_future_data.py 特徵：只能用 t 之前的資料
│   ├── test_rank_ensemble.py  模型：排名集成、備援的順序
│   ├── test_persist_rule.py   模型：持續性規則、模型開關
│   ├── test_online_lr.py      模型：組員的邏輯迴歸
│   ├── test_submit.py         上傳：假網站，不重試、核對
│   ├── test_submission_format.py   上傳：CSV 的欄位、列數、0/1
│   ├── test_run_daily.py      每日流程：git 同步、log、舊名字和舊路徑還能用
│   ├── test_overnight_up.py   隔夜大跌全猜漲的規則（只影子跑）
│   ├── test_rank_inst.py      法人組排名集成（只影子跑）和傍晚補算
│   ├── test_redo.py           每日流程：資料不完整時補齊後重交
│   ├── test_evening_score.py  傍晚打分：老師 Live 的答案、網站的分數和名次、不上傳
│   ├── test_merge_raw.py      合併表
│   ├── test_n1_shadow.py      N1 影子跑在正式環境這一側：什麼時候叫子程序、出事時照常收尾、打分、gspc 不進特徵表
│   ├── test_n1_model.py       N1 影子跑本身（.venv-n1 跑）：和 Kaggle UB 04 逐位元一樣、每天的步驟、只寫自己的檔
│   ├── fixtures/              凍結的參考資料，不要改：data-collection/ 是舊分支的對照資料，n1/ 是 Kaggle UB 04 的輸出
│   └── data_exchange/         證交所、櫃買真回應剪小的版本
├── models/                    放訓練好的模型檔；交件的模型每天重訓、不存檔
│   └── n1/ub04_v5/            N1 影子跑的起始狀態（Kaggle UB 04 第 5 版的 JS_ONLINE 權重），只讀；每天更新的狀態在 .cache/n1/（不進 Git）
├── .claude/                   Claude Code 的專案設定和輸出風格
├── .gitignore                 哪些檔案不進 Git
└── .gitattributes             data/raw/、tests/fixtures/、models/n1/ 不改換行；upload_log.jsonl 用 union 合併
```
