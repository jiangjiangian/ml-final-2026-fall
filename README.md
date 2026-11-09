# stock-market-challenger

## 每天的流程

學校主機 oop 每天台北 07:10、07:25、07:40、07:55、08:05 跑 `run_daily_test.py --sync`，使用者的 Mac 08:15 起備援（見「排程主機」）。網站上已經有今天的提交就直接結束，不會重複上傳。一次跑五步：

1. 爬蟲 `python -m src.crawler --date <t>`：下載老師的 Training、Live、yfinance 21 個指標和期交所的台指期，原樣存進 `data/raw/`。匯率另外存 1 小時K棒；匯率和台指期都和舊檔合併。
2. 特徵 `python -m src.features --date <t>`：清理 yfinance，算每檔股票和各指標的 lag1、lag2，一列是一檔股票的一天。台指期分日盤和夜盤，夜盤清晨 05:00 收盤，當天開盤前就知道。結果一個月一檔，存在 `data/processed/features/`，每天只更新最後兩個月。
3. 模型 `src/online_lr.py`：組員的邏輯迴歸（每週重訓、每天用前一天的答案微調），特徵是組員的 26 個個股特徵加特徵表的 32 欄。每天早上重新 fit。
4. 上傳 `src/submit.py`：照網站範本寫 CSV，上傳後下載回來逐格核對。`configs/config.yaml` 的 `submit.phase` 決定交 Phase 1（84 天回測，測自動化用）還是 Phase 2（每天的 t）。
5. 推資料：`data/raw/`、`data/processed/`、`data/submission/` commit 並 push 到這個分支。

t 不是交易日時不跑爬蟲和特徵。

## 排程主機

### oop（主跑）

`oop.cs.nccu.edu.tw`：Ubuntu 22.04、16 核、24 GB、時區台北。沒有 root，不能用 Docker。

1. 從校外要先連政大 SSL VPN（Ivanti Secure Access，伺服器 `https://sslvpn.nccu.edu.tw`）才 SSH 得進去。cron 在主機上自己跑，不需要 VPN。
2. 2026-11-06 在 oop 上用 pip 連不到 pypi.org，所以套件在 Mac 上下載 Linux 版，再複製過去：
   ```bash
   uvx --from pip==24.3.1 pip download -r requirements.txt --python-version 3.12 --implementation cp \
     --abi cp312 --abi abi3 --abi none --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 \
     --platform manylinux_2_28_x86_64 --platform any --only-binary=:all: -d wheels
   scp -r wheels nccuoop:~/wheels
   ```
3. 在 oop 上：
   ```bash
   curl -fsSL https://raw.githubusercontent.com/jiangjiangian/ml-final-2026-fall/claude/stock-market-challenger/deploy/runner_setup.sh -o runner_setup.sh
   WHEELS=~/wheels bash runner_setup.sh
   ```
   第一次會建 deploy key 並印出公鑰。到 GitHub repo → Settings → Deploy keys 加上它，勾 Allow write access，再跑一次。
4. 填 `~/ml-final-2026-fall/.env`，試跑 `.venv/bin/python run_daily_test.py --dry-run`。

### Mac（備援）

`bash deploy/mac/setup.sh`：另外 clone 到 `~/ml-final-runner`，launchd 每天 08:15、08:25、08:35 跑。網站上已經有今天的提交就直接結束。

### GCP（備用）

`deploy/gcp_setup.sh`：e2-micro 免費主機只有 1 GB 記憶體，流程高峰約 750 MB，要靠 swap，所以改用 oop。

## 組員怎麼拿資料

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

`label_` 開頭的欄是答案，不能放進 X。`*_open_gap` 也不能放：歷史列有值，但每天早上 t 那列一定是空白，模型預測時只會看到空值。交易所的 `val_*`、`quote_*` 在 `exchange.enabled` 打開前，i 晚於 2026-11-06 的列也是空白（回補只到 11-06）；`kospi_*` 在爬蟲第一次抓到 `kospi.csv` 之前整欄空白，抓到之後要再 `--rebuild` 才會補齊過去的月份。驗證要按日期切，不能隨機拆列。`data/raw/yfinance/` 是 Yahoo 的原樣，沒有清理（0052 分割前的價格沒除），要用就用特徵表。

## 特徵表的欄位

`data/processed/features/` 一列是「一個預測日 t × 一檔股票」，共 80 欄：3 個鍵、2 個答案、30 個序列各 2 欄，另外 15 欄只給組員研究（交易所 9 欄、開盤跳空 2 欄、老師美股不退格 4 欄，見「只進長表的 15 欄」）。每天交件的模型只用 `manifest.json` 的 `model_columns`（下表「模型用」是「是」的 16 個序列，共 32 欄），另外加組員從老師個股表算的 26 個個股特徵。

欄的順序：鍵、`stock`、yfinance（照 `yfinance.tickers`）、老師 global、`usd_twd_am`、台指期、只進長表的 15 欄（依序是老師美股不退格 4 欄、開盤跳空 2 欄、交易所 9 欄）、答案。2026-11-09 加 `kospi` 之後，`teacher_vix` 到 `tx_night` 都往後移 2 格，請用欄名讀，不要用位置。

### lag 怎麼算

i 是 t 之前最後一個台股交易日。每個序列有兩欄：

- `<序列>_ret_lag1` = (close_i − close_(i−1)) ÷ close_(i−1)，也就是 i 那天的報酬。
- `<序列>_ret_lag2` = (close_i − close_(i−2)) ÷ close_(i−2)，也就是到 i 為止兩天累積的報酬。

細節：

- i−1、i−2 數的是這個序列自己的交易日，例如美股就數美股開盤的日子。
- 股票和 ETF 用還原價（adj_close），其他用收盤價。
- 序列在 i 那天沒有K棒（例如美國放假）就留空白，不往前找。兩個端點有一個是空的或 ≤ 0 也留空白。
- 例外：`usd_twd_am`、`tx_night` 和老師美股不退格的 `*_fresh_ret_lag*` 的分子是 t 當天清晨就知道的值，公式寫在表裡。

### 鍵和答案

| 欄位 | 說明 |
|---|---|
| `date` | 預測日 t，台股交易日 |
| `stock_id` | 老師 100 檔的代號，字串（`"2330"`） |
| `is_top50` | 1 是比賽要預測的 50 檔 |
| `label_y` | 答案：t 當天還原收盤 > 還原開盤是 1。預測日那列空白。不能當特徵 |
| `label_intraday_return` | t 當天還原收盤 ÷ 還原開盤 − 1，官方分數用。不能當特徵 |

### 序列（每個都有 `_ret_lag1`、`_ret_lag2` 兩欄）

| 序列 | 來源 | 是什麼 | close_i 是哪一刻的價格 | 模型用 |
|---|---|---|---|---|
| `stock` | 老師個股表 | 這檔股票自己 | 台股 i 收盤 | 是 |
| `sox` | Yahoo `^SOX` | 費城半導體指數 | 美股 i 那場收盤（台北 t 清晨 05:00 左右收） | 是 |
| `tsm_adr` | Yahoo `TSM` | 台積電在美國掛牌的股票 | 同上 | 是 |
| `nvda` | Yahoo `NVDA` | 輝達 | 同上 | 是 |
| `dji` | Yahoo `^DJI` | 道瓊工業指數 | 同上 | 是 |
| `vix` | Yahoo `^VIX` | 美股波動率指數（恐慌指數） | 同上 | 是 |
| `us10y` | Yahoo `^TNX` | 美國 10 年期公債殖利率 | 同上 | 是 |
| `us13w` | Yahoo `^IRX` | 美國 13 週國庫券殖利率 | 同上 | 是 |
| `wti` | Yahoo `CL=F` | WTI 原油期貨 | 美國 i 那天的收盤 | 是 |
| `gold` | Yahoo `GC=F` | 黃金期貨 | 同上 | 是 |
| `dxy` | Yahoo `DX-Y.NYB` | 美元指數 | 美國 i 那天收盤（台北 t 07:00 收） | 否 |
| `usd_twd` | Yahoo `TWD=X` 日K | 美元兌台幣 | 倫敦 i 日那根日K | 否 |
| `usd_twd_am` | Yahoo `TWD=X` 1 小時K | 美元兌台幣，和美股收盤同步 | 例外：x_t 是台北 t 日 06:00 的匯率，lag_k = (x_t − x_(t 往回第 k 個交易日)) ÷ x_(t 往回第 k 個交易日)。2024-01-22 以前用日K補。選到的那根沒有晚於前一個交易日 06:00 結束時（爬蟲沒抓到新的 1h、沿用舊檔）x 空白（2026-11-09 起） | 是 |
| `etf_0050` | Yahoo `0050.TW` | 元大台灣 50 | 台股 i 收盤 | 是 |
| `etf_0052` | Yahoo `0052.TW` | 富邦科技 | 同上 | 否 |
| `etf_0055` | Yahoo `0055.TW` | 元大 MSCI 金融 | 同上 | 否 |
| `etf_006201` | Yahoo `006201.TWO` | 元大富櫃 50 | 同上 | 否 |
| `n225` | Yahoo `^N225` | 日經 225 | 日本 i 日收盤 | 否 |
| `hsi` | Yahoo `^HSI` | 恒生指數 | 香港 i 日收盤 | 否 |
| `sse` | Yahoo `000001.SS` | 上證綜合指數 | 上海 i 日收盤 | 否 |
| `stoxx50e` | Yahoo `^STOXX50E` | 歐洲斯托克 50 | 歐洲 i 日收盤 | 否 |
| `gdaxi` | Yahoo `^GDAXI` | 德國 DAX | 德國 i 日收盤 | 否 |
| `kospi` | Yahoo `^KS11` | 韓國 KOSPI（2026-11-09 加） | 韓國 i 日收盤 | 否 |
| `teacher_gspc` | 老師 global `^GSPC` | S&P 500 | 老師 i 那列，放的是 i 前一場美股的收盤（前前晚） | 是 |
| `teacher_ixic` | 老師 global `^IXIC` | Nasdaq | 同上 | 是 |
| `teacher_vix` | 老師 global `^VIX` | 美股波動率指數 | 同上。Live 10/13 起不準，模型改用 `vix` | 否 |
| `teacher_twii` | 老師 global `^TWII` | 台股加權指數 | 台股 i 收盤 | 否 |
| `teacher_ks11` | 老師 global `^KS11` | 韓國 KOSPI | 韓國 i 日收盤 | 否 |
| `tx_day` | 期交所 | 台指期日盤（08:45～13:45），近月合約 | 台股 i 的日盤收盤 | 是 |
| `tx_night` | 期交所 | 台指期夜盤，近月合約 | 例外：分子是 t 清晨 05:00 收盤的夜盤。lag1 比 t 之前最後一個日盤收盤，lag2 比再前一個 | 是 |

### 只進長表的 15 欄

這 15 欄 2026-11-09 加進表裡，都不在 `model_columns`，給組員研究用（定義和決定的經過見 `memory/projects/features.md`）。三組用的時間點不一樣：

- 交易所 9 欄（`val_*_lag1`、`quote_*_lag1`）：t 那列存 i 那天收盤後的值本身，沒有和前一天比。`lag1` 指的是用 i 那天。
- 開盤跳空 2 欄（`*_open_gap`）：d 那列存 d 當天早上的開盤跳空（開盤價比前一個交易日收盤漲跌多少），台北約 08:30 才看得到。所以每天早上 t 那列是空白，隔天重寫最後兩個月時補上。這是全表唯一用到當天資料的欄，不能當 t 的特徵（`features.model_columns()` 會擋）。
- 老師美股不退格 4 欄（`*_fresh_ret_lag*`）：用老師 global t 自己那列，公式和 `usd_twd_am` 一樣，所以比 `teacher_gspc`、`teacher_ixic` 新一天。

### 交易所的估值和委買賣（9 欄）

- 來源：`data/raw/twse/`、`data/raw/tpex/`（見「證交所、櫃買的回補」）。這檔股票在哪個交易所有 i 那天的列就用哪邊，6446 在 2024-01-25 從櫃買轉上市。
- 兩個交易所都沒有這檔 i 那天的列（停牌、還沒抓）時，9 欄都空白，不往前找。停牌那天交易所照樣有列（收盤行情的開高低收是 `--` 或 `----`、成交股數 0，估值沿用前一天），也當成沒有列，9 欄空白。2020-01～2026-11 有 21 個這樣的股票日。
- 價格是交易所的原始價，沒有還原除權息，不要和老師的還原價混用。
- `val_pe_loss_lag1`、`quote_limit_up_lag1`、`quote_limit_down_lag1` 存 1、0 或空白。

| 欄位 | 來源 | 定義 | 空白的情況 | 模型用 |
|---|---|---|---|---|
| `val_ep_lag1` | 本益比表的本益比 | 1 ÷ 本益比（盈餘殖利率） | 虧損（證交所寫 `-`、櫃買寫 `N/A`）、本益比 ≤ 0 | 否 |
| `val_pe_loss_lag1` | 同上 | 本益比是虧損記號時 1，是數字時 0 | 沒有 i 那天的列、本益比是空的或看不懂 | 否 |
| `val_log_pb_lag1` | 本益比表的股價淨值比 | ln(股價淨值比) | 不是數字、≤ 0 | 否 |
| `val_dy_lag1` | 本益比表的殖利率(%) | 殖利率(%) ÷ 100，0 也算 | 不是數字 | 否 |
| `quote_spread_ticks_lag1` | 收盤行情的最後揭示買價、賣價 | 買價到賣價差幾檔。升降單位（一檔多少錢）：未滿 10 元 0.01，10 元起 0.05，50 元起 0.1，100 元起 0.5，500 元起 1，1000 元起 5；跨區間時一檔一檔數 | 沒有買價或賣價（證交所寫 `--`、櫃買寫 `0.00`）、買價 ≥ 賣價、價格不在升降單位的格子上 | 否 |
| `quote_rel_spread_lag1` | 同上 | (賣價 − 買價) ÷ 兩者平均 | 沒有買價或賣價、買價 ≥ 賣價 | 否 |
| `quote_imbalance_lag1` | 收盤行情的最後揭示買量、賣量 | (買量 − 賣量) ÷ (買量 + 賣量)，在 −1 到 1 之間。漲跌停鎖住時一邊是 0，所以是 1 或 −1 | 量是空的（櫃買 2020 年上半年沒有）、兩邊都是 0 | 否 |
| `quote_limit_up_lag1` | 收盤行情的最後揭示買價、賣價 | 沒有賣價、有買價（漲停鎖住）時 1，其他 0 | 只有沒有 i 那天的列（含停牌）時 | 否 |
| `quote_limit_down_lag1` | 同上 | 沒有買價、有賣價（跌停鎖住）時 1，其他 0 | 只有沒有 i 那天的列（含停牌）時 | 否 |

### 開盤跳空（2 欄）

| 欄位 | 來源 | 定義 | 空白的情況 | 模型用 |
|---|---|---|---|---|
| `kospi_open_gap` | Yahoo `^KS11` 日K | d 那根的 open ÷ 前一根的 close − 1。前一根跳過 Yahoo 補的佔位K棒 | 每天早上的 t 那列；韓國休市（沒有 d 那根）；佔位K棒（開高低收相同、量 0 或空）；序列的第一根（前面沒有K棒）；價格空的或 ≤ 0；韓國 10:00（台北 09:00）才開盤的日子：每年第一個交易日（序列每年的第一根，和第一根有成交量的那根）、大學入學考試日（清單在 `configs/config.yaml` 的 `features.open_gap`） | 否，不能用 |
| `n225_open_gap` | Yahoo `^N225` 日K | 同上 | 每天早上的 t 那列；日本休市；佔位K棒；序列的第一根；價格空的或 ≤ 0 | 否，不能用 |

2026-11-08 的研究：扣掉現有特徵後，開盤跳空和 50 檔平均「收盤比開盤」的相關在 ±0.02 以內。

### 老師美股不退格（4 欄）

| 欄位 | 來源 | 定義 | 空白的情況 | 模型用 |
|---|---|---|---|---|
| `teacher_gspc_fresh_ret_lag1`、`teacher_gspc_fresh_ret_lag2` | 老師 global `^GSPC` | x_d 是老師 d 那列，放的是 d 開盤前最後一次美股收盤。lag_k = (x_t − x_(t 往回第 k 個台股交易日)) ÷ x_(t 往回第 k 個台股交易日)。比 `teacher_gspc` 新一天 | t 那列或往回第 k 個台股交易日在老師 global 沒有列（Training 少 112 個台股日）、`-1`、≤ 0 | 否 |
| `teacher_ixic_fresh_ret_lag1`、`teacher_ixic_fresh_ret_lag2` | 老師 global `^IXIC` | 同上 | 同上 | 否 |

Live t 那列的 `^GSPC`、`^IXIC` 台北約 05:05 就填好，07:10 的爬蟲抓得到。原本的 `teacher_gspc`、`teacher_ixic` 不變。往回數的是台股交易日，老師 global 缺列的日子會空白，所以 `teacher_gspc_fresh_ret_lag1` 有值的天數（1,445）比 `teacher_gspc`（1,548）少。

## 證交所、櫃買的回補（研究用）

```bash
python -m src.crawler --exchange-backfill [--start 2020-01-02] [--end YYYY-MM-DD] [--markets twse,tpex] [--max-requests N]
```

從證交所（上市）和櫃買中心（上櫃）抓 2020-01-02 起每個交易日的全市場日資料，只留老師的 100 檔。2026-11-09 回補完 2020-01-02～2026-11-06 的 1,662 天，沒有失敗。特徵表的交易所 9 欄讀這四個檔，不進模型欄。

- 每天的步驟：`exchange.enabled` 打開後，每天的爬蟲在期交所之後補 i 那天，以及最近 10 個交易日裡檔案缺的日子。平常每個主機 2 個請求，約多 20 秒；每個主機最多 12 個請求，開始 3 分鐘後不再送新的請求。失敗只寫警告和 `data/raw/manifest.json` 的 `exchange`，不影響上傳。
- 開關現在是 false：要先量證交所、櫃買每天幾點公布 i 那天的資料，確定早上抓得到；也要先把回補的檔推上去，讓 oop 和 Mac 備援 pull 到完整的檔。關著的時候，i 晚於 2026-11-06 的列交易所欄是空白；開關打開或手動回補之後，下一次每天的特徵會補上最後兩個月。
- 存法：一個來源一個長表，一列是一檔股票的一天，照日期、代號排序。欄名照來源，數字拿掉千分位逗號，`-`、`N/A`、`--`、`----` 這類記號原樣留著。
- `data/raw/twse/valuation.csv`：收盤價、殖利率(%)、本益比、股價淨值比、財報年/季。
- `data/raw/twse/quotes.csv`：開盤價、最高價、最低價、收盤價、成交股數、最後揭示買賣價和量。
- `data/raw/tpex/valuation.csv`：本益比、股價淨值比、殖利率(%)、財報年/季（2020 年的表沒有，空白）。櫃買的每股股利、股利年度是事後回填的，不存。
- `data/raw/tpex/quotes.csv`：開盤、最高、最低、收盤、成交股數、最後買賣價和量（2020 年上半年沒有買賣量，空白）。
- 時間：第 d 天的值是 d 那天收盤後才有的，只能當 d 之後的日子的特徵。
- 跑法：日期由新到舊，檔案裡已經有的日子跳過，中斷後再跑會接著做。同一個主機每個請求至少隔 6.5 秒，兩個主機同時跑，全部約 6 小時。台北 07:00～09:00 暫停。被擋（403、429、不是 JSON，含 5xx 的 HTML 頁面）或連續 3 天都逾時、5xx，就停下那個主機，不自動重試。同一個交易所同時只能跑一個（`.cache/exchange_<市場>.lock`）。進度看 `data/raw/exchange_backfill.json`。
- 在哪跑：只在自己開發用的 clone 跑。不要在 oop 的 `~/ml-final-2026-fall` 或 Mac 的 `~/ml-final-runner` 跑：那兩個 clone 的排程會 `git add data/raw`，把跑一半的檔一起 commit。跑完自己 commit，路徑寫清楚：`git add data/raw/twse data/raw/tpex data/raw/exchange_backfill.json`。
- 成交股數：交易所的成交股數和老師的 `price:成交股數` 不一定一樣（櫃買的取到整張，證交所有些天也不同），兩個不要混用。

## 檔案樹

```text
ml-final-2026-fall/            （分支 claude/stock-market-challenger）
├── README.md                  流程、組員怎麼拿資料、檔案樹（這份）
├── CLAUDE.md                  給 Claude Code：規則和 memory/ 的索引
├── memory/                    給 Claude Code 的專案記憶，一個主題一個檔
│   ├── glossary.md            名詞
│   ├── context/
│   │   ├── competition.md     比賽規則、課程網站 API、上傳的規矩、Phase 1 結果
│   │   ├── pipeline.md        每天的流程、指令、失敗時怎麼手動交
│   │   ├── data-rules.md      時間對齊、美股日期、-1、交易日曆、資料存放
│   │   ├── environment.md     本機環境、分支、舊系統封存、skills
│   │   └── open-questions.md  還沒決定的事
│   └── projects/
│       ├── crawler.md         src/crawler.py 的設計和進度
│       └── features.md        src/features.py 的規劃：清理規則、交易日、lag、對照測試
├── .claude/
│   ├── settings.json          Claude Code 專案設定（輸出風格用 team-docs）
│   ├── output-styles/
│   │   └── team-docs.md       回覆和文件的寫法
│   └── skills/                graphify、humanizer（只在本機，不進 Git）
├── requirements.txt           套件和鎖定的版本
├── .gitignore                 哪些檔案不進 Git
├── .gitattributes             data/raw/、tests/fixtures/ 的檔案 Git 不改換行，sha256 才對得上；upload_log.jsonl 用 union 合併
├── .env.example               帳號密碼的範例；真的值放 .env（不進 Git）
├── run_daily.py               一個指令跑完一天：爬蟲 → 特徵 → 訓練 → 預測 → 上傳（還是骨架）
├── run_daily_test.py          排程跑的這支（測試版）：爬蟲 → 特徵 → 組員的邏輯迴歸 → 上傳 → 推資料
├── deploy/
│   ├── runner_setup.sh        排程主機（學校的 oop）的安裝：deploy key、uv、clone、Python 3.12、cron，不用 sudo
│   ├── gcp_setup.sh           GCP 主機的安裝（備用）：時區、swap、clone、venv、cron
│   ├── crontab.txt            排程主機的 crontab（台北 07:10 到 08:05 五次）
│   └── mac/                   Mac 備援：setup.sh 裝 launchd，com.mlfinal.backup.plist 每天 08:15、08:25、08:35 跑
├── configs/
│   ├── config.yaml            網站網址、yfinance 代號、特徵、模型參數、截止時間
│   └── live_ca.pem            Live 原本網址的自簽憑證，爬蟲只信任這一張（公開的，不是密碼）
├── data/
│   ├── raw/                   爬蟲寫的，和來源一模一樣
│   │   ├── teacher/
│   │   │   ├── training/      網站的 Training ZIP 解開（不會再變）
│   │   │   └── live/          網站的 Live ZIP 解開，每天整包換新（Live 本身每天多一列）
│   │   ├── yfinance/          21 個額外指標，一個序列一個 CSV；usd_twd_1h.csv 是匯率的 1 小時K棒
│   │   ├── taifex/            tx.csv：期交所的台指期，日盤和夜盤，只留單月合約
│   │   ├── twse/              證交所：valuation.csv 本益比、殖利率、股價淨值比；quotes.csv 收盤行情（長表的交易所欄用）
│   │   ├── tpex/              櫃買中心：valuation.csv、quotes.csv，欄位見「證交所、櫃買的回補」
│   │   ├── exchange_backfill.json   回補的進度：每個來源寫了幾天、no_data 的日子、失敗、請求數、有沒有被擋
│   │   ├── phase2_days.json   課程網站的交易日清單（/api/state 的 phase2Days）
│   │   └── manifest.json      下載紀錄
│   ├── processed/             特徵表，組員從這裡拿資料
│   │   ├── features/          YYYY-MM.csv.gz，一個月一檔，每天只更新最後兩個月
│   │   └── manifest.json      有哪些月份、模型用哪些欄、清理紀錄
│   └── submission/            每天的產出
│       ├── submission_YYYY-MM-DD.csv   要上傳的 0/1
│       ├── submission_phase1_YYYY-MM-DD.csv   Phase 1 測試上傳的 0/1（84 天 × 50 檔）
│       ├── backup/                     上傳前先下載網站上目前有效的那份
│       ├── upload_log.jsonl            上傳紀錄
│       └── run_YYYY-MM-DD.log          執行紀錄，失敗時先看這個
├── models/                    model.txt（模型）、feature_columns.json（欄位順序和訓練資訊）
├── notebooks/
│   └── README.md              實驗的檔名和注意事項；每天的自動流程不會讀這裡
├── src/
│   ├── __init__.py
│   ├── crawler.py             下載老師資料、yfinance 額外指標和台指期；--exchange-backfill 回補證交所、櫃買（exchange.enabled 打開後每天也補）
│   ├── features.py            原始資料 → 特徵表；訓練和預測用同一個函式
│   ├── train.py               按日期切分、驗證、訓練、存模型
│   ├── predict.py             下載當天範本，產生 t 那天 50 檔的 submission CSV
│   ├── submit.py              上傳 CSV，再下載回來核對；Phase 1、2 都用
│   ├── site_api.py            課程網站的 API：登入、state、範本、上傳、下載
│   ├── online_lr.py           組員的邏輯迴歸和 26 個個股特徵（run_daily_test.py 用）
│   └── utils.py               讀設定和帳密、台北時間、截止檢查、log
└── tests/
    ├── fixtures/data-collection/  舊分支 data-collection 的凍結資料，只給對照測試用，不要改
    │   ├── extra/                 清理過的 yfinance 19 個序列和 manifest.json（清理紀錄）
    │   ├── yfinance_raw_0820473/  還沒清理的 Yahoo 原樣（到 2026-08-31），測清理用
    │   ├── teacher_live/          舊長表用的那份 Live（eea89fce，9/1～11/5）
    │   ├── transform/             舊長表 panel_lag.csv.gz（2020-01-02～2026-11-04），對照測試 (a) 的標準答案
    │   └── schema.json            舊長表所有欄位的定義和驗證紀錄
    ├── data_exchange/             證交所、櫃買真回應剪小的版本（2026-11-08 存的），給 test_exchange.py 用
    ├── test_crawler.py            爬蟲的離線測試（假伺服器、假時鐘）
    ├── test_exchange.py           證交所、櫃買的離線測試：解析、檢查、限流、鎖、續跑、暫停時段、每天的步驟
    ├── test_features.py           清理、交易日、lag，以及和 data-collection 凍結資料的對照測試
    ├── test_features_new_columns.py  只進長表的 15 欄和 usd_twd_am 的舊K棒規則
    ├── test_no_future_data.py     特徵只能用 t 之前的資料；開盤跳空只用到 d 當天，不能進模型欄
    ├── test_online_lr.py          組員的模型：個股特徵不偷看，每天的模式和回測一樣
    ├── test_submit.py             上傳流程：假網站，不重試、核對、跳過的規則
    ├── test_run_daily_test.py     git 同步（假 remote）和 log 檔被換掉後重開
    └── test_submission_format.py  CSV 的欄位、列數、0/1
```
