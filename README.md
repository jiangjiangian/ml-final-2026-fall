# stock-market-challenger

## 每天的流程

學校主機 oop 每天台北 07:10、07:25、07:40、07:55、08:05 跑 `run_daily_test.py --sync`，08:25 再跑一次，補上日韓當天的開盤（見「開盤跳空」）。Mac 08:15 起的備援寫好了，還沒裝（見「排程主機」）。網站上已經有今天的提交就直接結束，不會重複上傳。一次跑六步：

1. 爬蟲 `python -m src.crawler --date <t>`：下載老師的 Training、Live、yfinance 21 個指標、期交所的台指期和 VIXTWN、CNN 恐懼貪婪指數，原樣存進 `data/raw/`。匯率另外存 1 小時K棒；匯率、台指期、VIXTWN、CNN 都和舊檔合併。
2. 特徵 `python -m src.features --date <t>`：清理 yfinance，算每檔股票和各指標的 lag1、lag2，一列是一檔股票的一天。台指期分日盤和夜盤，夜盤清晨 05:00 收盤，當天開盤前就知道。結果一個月一檔，存在 `data/processed/features/`，每天只更新最後兩個月。
3. 模型 `src/online_lr.py`：組員的邏輯迴歸（每週重訓、每天用前一天的答案微調），特徵是組員的 26 個個股特徵加特徵表的 32 欄。每天早上重新 fit。
4. 上傳 `src/submit.py`：照網站範本寫 CSV，上傳後下載回來逐格核對。`configs/config.yaml` 的 `submit.phase` 決定交 Phase 1（84 天回測，測自動化用）還是 Phase 2（每天的 t）。
5. 合併 `python -m src.merge_raw`：把 `data/raw/` 併成組員研究用的兩張表，存在 `data/merged/`（見「合併的原始資料」）。上傳之後才跑，來源沒變就跳過，失敗只寫警告。
6. 推資料：`data/raw/`、`data/processed/`、`data/submission/`、`data/merged/` commit 並 push 到這個分支。

t 不是交易日時不跑爬蟲、特徵和合併。

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

`bash deploy/mac/setup.sh`：另外 clone 到 `~/ml-final-runner`，launchd 每天 08:15、08:25、08:35 跑。網站上已經有今天的提交就直接結束。2026-11-09 還沒裝，現在只有 oop 在跑。

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

`label_` 開頭的欄是答案，不能放進 X。`*_open_gap` 不在每日模型裡：t 那列要到台北 08:25 的排程跑完（約 08:28）才有值，07 點多預測時是空白。自己的模型要用，要等 08:30 後 `git pull` 才拿得到 t 那列的值。交易所的 `val_*`、`quote_*` 在 oop 早上抓不到交易所的那天先空白，之後幾天補上。`vixtwn_lag1` 在 t ≤ 2026-08-03、`vixtwn_ret_lag1` 在 t ≤ 2026-08-04 的列空白（期交所的免費檔從 2026-08-03 開始）。驗證要按日期切，不能隨機拆列。`data/raw/yfinance/` 是 Yahoo 的原樣，沒有清理（0052 分割前的價格沒除），要用就用特徵表。

特徵表沒有的欄（老師個股表的法人、技術指標，yfinance 的開高低收量，台指期的未平倉）在 `data/merged/`，見「合併的原始資料」。

## 特徵表的欄位

`data/processed/features/` 一列是「一個預測日 t × 一檔股票」，共 84 欄：3 個鍵、2 個答案、30 個序列各 2 欄，另外 19 欄只給組員研究（交易所 9 欄、開盤跳空 2 欄、老師美股不退格 4 欄、VIXTWN 2 欄、CNN 恐懼貪婪 2 欄，見「只進長表的 19 欄」）。每天交件的模型只用 `manifest.json` 的 `model_columns`（下表「模型用」是「是」的 16 個序列，共 32 欄），另外加組員從老師個股表算的 26 個個股特徵。

欄的順序：鍵、`stock`、yfinance（照 `yfinance.tickers`）、老師 global、`usd_twd_am`、台指期、只進長表的 19 欄（依序是老師美股不退格 4 欄、開盤跳空 2 欄、交易所 9 欄、VIXTWN 2 欄、CNN 2 欄）、答案。2026-11-09 加 `kospi` 之後，`teacher_vix` 到 `tx_night` 都往後移 2 格，請用欄名讀，不要用位置。

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

### 只進長表的 19 欄

這 19 欄都不在 `model_columns`，給組員研究用（定義和決定的經過見 `memory/projects/features.md`）。四組用的時間點不一樣：

- 交易所 9 欄（`val_*_lag1`、`quote_*_lag1`）：t 那列存 i 那天收盤後的值本身，沒有和前一天比。`lag1` 指的是用 i 那天。
- 開盤跳空 2 欄（`*_open_gap`）：d 那列存 d 當天早上的開盤跳空（日韓台北 08:00 的開盤價比前一個交易日收盤漲跌多少）。t 那列在 08:25 的排程抓到後才有值，之前是空白；那天沒抓到，就等之後 Yahoo 的日K補上。這是全表唯一用到當天資料的欄，每日模型不用（`features.model_columns()` 會擋）。
- 老師美股不退格 4 欄（`*_fresh_ret_lag*`）：用老師 global t 自己那列，公式和 `usd_twd_am` 一樣，所以比 `teacher_gspc`、`teacher_ixic` 新一天。
- VIXTWN、CNN 恐懼貪婪 4 欄：VIXTWN 用 i 那天收盤的值；CNN 用 t 之前最後一個美股交易日的前一個美股交易日的分數，通常比 `vix` 舊一天（原因見「VIXTWN 和 CNN 恐懼貪婪」）。

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
| `kospi_open_gap` | Yahoo `^KS11`：當天早上抓的一分鐘K棒，沒抓到的日子用日K | d 的開盤（韓國 09:00，台北 08:00）÷ 前一個韓國交易日收盤 − 1。日K的算法是 d 那根的 open ÷ 前一根的 close，前一根跳過 Yahoo 補的佔位K棒 | t 那列在台北 08:25 的排程抓到之前；韓國休市（沒有 d 那根）；佔位K棒（開高低收相同、量 0 或空）；序列的第一根（前面沒有K棒）；價格空的或 ≤ 0；韓國 10:00（台北 09:00）才開盤的日子：每年第一個交易日（序列每年的第一根，和第一根有成交量的那根）、大學入學考試日（清單在 `configs/config.yaml` 的 `features.open_gap`） | 否，不能用 |
| `n225_open_gap` | Yahoo `^N225`，同上 | 同上（日本 09:00，台北 08:00） | t 那列在 08:25 的排程抓到之前；日本休市；佔位K棒；序列的第一根；價格空的或 ≤ 0 | 否，不能用 |

t 那列怎麼來（2026-11-11 加）：Yahoo 的韓國指數晚 20 分鐘、日經晚 15 分鐘，所以 oop 在台北 08:25 才抓。抓的是當天一分鐘K棒的第一根（當地 09:00）和 Yahoo 給的前一天收盤，存在 `data/raw/open_today/kospi.csv`、`n225.csv`（`date, open, prev_close, fetched_at`），接著重寫特徵表並推上 GitHub，大約 08:28 拿得到。當天早上抓到的值之後不會再換。沒抓到（學校網路斷線、Yahoo 還沒更新）時 t 那列空白，等 Yahoo 的日K有那一天再補，通常要一兩天。韓國 10:00 才開盤的日子（台北 09:00）抓不到。第一次正式跑是 2026-11-12；2026-11-11 那列是當天下午補抓的。

2026-11-08 的研究：扣掉現有特徵後，開盤跳空和 50 檔平均「收盤比開盤」的相關在 ±0.02 以內。

### 老師美股不退格（4 欄）

| 欄位 | 來源 | 定義 | 空白的情況 | 模型用 |
|---|---|---|---|---|
| `teacher_gspc_fresh_ret_lag1`、`teacher_gspc_fresh_ret_lag2` | 老師 global `^GSPC` | x_d 是老師 d 那列，放的是 d 開盤前最後一次美股收盤。lag_k = (x_t − x_(t 往回第 k 個台股交易日)) ÷ x_(t 往回第 k 個台股交易日)。比 `teacher_gspc` 新一天 | t 那列或往回第 k 個台股交易日在老師 global 沒有列（Training 少 112 個台股日）、`-1`、≤ 0 | 否 |
| `teacher_ixic_fresh_ret_lag1`、`teacher_ixic_fresh_ret_lag2` | 老師 global `^IXIC` | 同上 | 同上 | 否 |

Live t 那列的 `^GSPC`、`^IXIC` 台北約 05:05 就填好，07:10 的爬蟲抓得到。原本的 `teacher_gspc`、`teacher_ixic` 不變。往回數的是台股交易日，老師 global 缺列的日子會空白，所以 `teacher_gspc_fresh_ret_lag1` 有值的天數（1,445）比 `teacher_gspc`（1,548）少。

### VIXTWN 和 CNN 恐懼貪婪（4 欄）

- VIXTWN（臺指選擇權波動率指數）：期交所從台指選擇權的價格算的，代表市場猜台股未來一個月會晃多大，越高代表越緊張。原始檔是 `data/raw/taifex/vixtwn.csv`，存每天 13:45 收盤的值和收盤前 1 分鐘的平均。期交所的免費檔只留最近約 4 個月，所以從 2026-08-03 開始，之後每天多一天。
- CNN 恐懼貪婪指數：CNN 用 7 個美股指標（漲跌氣勢、選擇權買賣比、VIX 等）算的 0～100 分，越低代表投資人越怕。原始檔是 `data/raw/cnn/fear_greed.csv`，日期是美國日期，2021-02-01 起（更早的有兩段剛好 50.0，還有一段 0.3～3.6 的怪值，不用）。CNN 沒有公開的 API，這是它網頁畫圖用的網址，隨時可能改。
- 為什麼 CNN 用倒數第二天：CNN 存的最後一天的分數，收盤後還會跟著下一個美股交易日的盤前變，開盤後 3～14 分鐘才定住（2026-11-09、11-10 量的：11-09 的分數到台北 11-10 13:00 都是 31.71，19:03 美股盤前變成 33.23）。最後一天要到台北 t 那天晚上才定住，用它會帶到 t 收盤以後的資訊。所以用 t 之前最後一個美股交易日（叫它 e）的前一個美股交易日，它在 e 開盤後幾分鐘（台北 e 那天 22:30 後，夏令時間 21:30 後）就定住了，一定早於台北 t 開盤。定住的值是 e 開盤後約 10 分鐘的分數，不是那天收盤時的分數。通常比 `vix` 舊一天；台股休市期間美股開了 n 天時比 `vix` 新 n − 1 天（休一天時同一天，農曆年這種長假會新好幾天）。
- 那天早上沒抓到 CNN 時（例如學校網路斷線，或 CNN 自己少了 e 那天），t 那列空白（使用者 2026-11-09）：檔裡最新的美股交易日就是要用的那天，它的分數是前一次抓的，那時還沒定住。之後抓到新的、每天重寫最後兩個月時補上。道瓊的檔沒更新時不會空白，會往前選到更舊一天的分數，道瓊補上後重寫時改回來。
- 美股交易日看道瓊（`dji`）有K棒的日子：CNN 當天的點在美股開盤前就出現，美國假日可能也會建、事後才拿掉，所以不能拿 CNN 自己的日期當日曆。設定在 `configs/config.yaml` 的 `features.fear_greed`。

| 欄位 | 來源 | 定義 | 空白的情況 | 模型用 |
|---|---|---|---|---|
| `vixtwn_lag1` | 期交所 VIXTWN 月檔 | i 那天 13:45 收盤的 VIXTWN | i 沒有值、i 早於 2026-08-03 | 否 |
| `vixtwn_ret_lag1` | 同上 | (v_i − v_前一天) ÷ v_前一天，前一天數 VIXTWN 自己的日子，和 `vix_ret_lag1` 同算法 | i 或前一天沒有值 | 否 |
| `fear_greed_lag1` | CNN Fear & Greed | t 之前最後一個美股交易日的前一個美股交易日的分數（0～100）。CNN 存的是下一個美股交易日開盤後約 10 分鐘的值 | CNN 沒有那天的分數（例如 CNN 少了 2026-03-12）、那天是 CNN 檔裡最新的美股交易日（那天早上沒抓到新的）、那天早於 2021-02-01、沒有道瓊的檔 | 否 |
| `fear_greed_chg_lag1` | 同上 | 上一欄那天的分數減掉前一個美股交易日的分數，單位是「分」。2021-02-01 起最低到過 2.9（2025-04-08），1 分就是 30% 以上，所以不用漲跌幅 | 上一欄空白，或前一個美股交易日沒有分數 | 否 |

## 合併的原始資料

`data/merged/` 把 `data/raw/` 併成兩張表：個股表一列是「一天 × 一檔」，市場表一列是一天。特徵表沒有的欄（老師個股表的法人、技術指標、成交量，yfinance 的開高低收量，台指期的未平倉）從這裡拿。每一格都是來源 CSV 的原字串，沒有清理，也沒有對齊到預測日 t：d 那列放的是各來源標 d 的值，當 t 的特徵前要自己往前接（見「預測 t 時每個來源能用到哪一列」）。

瀏覽：<https://github.com/jiangjiangian/ml-final-2026-fall/tree/claude/stock-market-challenger/data/merged>

### 怎麼讀

pandas 要用 `raw.githubusercontent.com` 的網址，上面那個 `github.com/.../tree/...` 是網頁，讀不了。

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

- `asof` 會往前找：美國放假時接到的是更早那場。特徵表的做法是留空白。
- 老師個股欄 d 那列是 d 當天的值，要照 `stock_id` 往後移一列。`y` 是 d 的答案，不能當特徵。
- `y` 是 `-1` 的列還沒有資料，整列都是 `-1`（每天早上的 t、2026-10-23 颱風假）。往後移之前先把這些列的 `-1` 換成空白，不然 10/24 那列會接到 `-1`。
- 驗證按日期切，同一天的 100 檔要在同一邊。

### 三個檔

- `stock/YYYY-MM.csv.gz`：個股表，一個月一檔。鍵是 `date`、`stock_id`（字串）、`is_top50`（1 是比賽的 50 檔）。接著是老師個股表 20 欄，欄名照原樣（例如 `etl:adj_close`），Training 全部，接 Live 2026-09-01 起的列。最後是證交所、櫃買四個檔，欄名加前綴：`twse_valuation_`、`twse_quotes_`、`tpex_valuation_`、`tpex_quotes_`（例如 `twse_quotes_收盤價`）。
- `market.csv.gz`：市場表，`date` 是所有來源日期的聯集，某個來源那天沒有列時那幾欄空白。老師 global 6 欄加 `teacher_` 前綴（例如 `teacher_^GSPC`）；yfinance 21 個序列各 6 欄（`sox_open`、`sox_high`、`sox_low`、`sox_close`、`sox_adj_close`、`sox_volume`），序列名稱和代號見「序列」那張表；台指期日盤、夜盤各 17 欄（`tx_day_收盤價`、`tx_night_未沖銷契約數` 這類）；`vixtwn`、`vixtwn_1min_avg`；`fear_greed_score`。
- `manifest.json`：個股表有哪些月份、兩張表的欄名和列數、每個來源的最後一天、來源檔的指紋。

### 預測 t 時每個來源能用到哪一列

| 欄 | d 那列是什麼 | 台北幾點才知道 | 預測 t 最多用到 |
|---|---|---|---|
| 老師個股 20 欄（含 `y`） | 台股 d 的價量、法人、技術指標、答案 | d 收盤後；每天早上 t 那列是 `-1` | d 早於 t |
| `twse_*`、`tpex_*` | d 收盤後的估值和收盤行情 | d 18:00 前 | d 早於 t |
| `teacher_^VIX`、`teacher_^IXIC`、`teacher_^GSPC` | d 開盤前最後一次美股收盤（`^VIX` 的 Live 10/13 起不準，改用 `vix`） | Live 的 t 那列約 05:05 填好 | d 等於 t |
| `teacher_^TWII`、`teacher_^KS11`、`teacher_TX_OI` | d 當天收盤（`TX_OI` 可能含收盤後的資訊） | d 收盤後 | d 早於 t |
| 美國的序列：`sox`、`tsm_adr`、`nvda`、`dji`、`vix`、`us10y`、`us13w`、`wti`、`gold`、`dxy` | 美國日期 d 那場 | d 隔天清晨：美股約 05:00、期貨 06:00、DXY 07:00 | 美國日期早於 t |
| 台股 ETF：`etf_0050`、`etf_0052`、`etf_0055`、`etf_006201` | 台股 d | d 13:30 | d 早於 t |
| 亞洲、歐洲指數：`n225`、`hsi`、`sse`、`kospi`、`stoxx50e`、`gdaxi` | 當地 d 那天 | 亞洲 d 下午，歐洲 d 深夜到隔天凌晨 | d 早於 t |
| `usd_twd` | Yahoo `TWD=X` d 那根日K | 保守看成 d 隔天 08:00 | d 早於 t |
| `tx_day_*` | 台指期 d 的日盤 | d 13:45 | d 早於 t |
| `tx_night_*` | 標 d 的夜盤：前一個交易日 15:00 到 d 05:00 | d 05:00 | d 等於 t |
| `vixtwn`、`vixtwn_1min_avg` | d 13:45 收盤 | d 16:10 | d 早於 t |
| `fear_greed_score` | 美國日期 d 的分數 | 最後一天的分數之後還會變 | 用特徵表的 `fear_greed_lag1`，原因見「VIXTWN 和 CNN 恐懼貪婪」 |

### 原樣保留的地方

- `-1`：老師 Live 待定列整列是 `-1`，代表還沒有資料。Training 法人欄有 83 格是真的 `-1`（剛好買賣超 1 股），不能一律換成空白。
- yfinance：沒有清理，0052 分割前的價格沒除。`adj_close` 每天會因為 Yahoo 重新套除息有約百萬分之一的浮動，所以 `market.csv.gz` 幾乎每天都會換。要乾淨的報酬用特徵表。
- 交易所：價格是原始價，沒有還原除權息，不要和老師的還原價混用。`-`、`--`、`----`、`N/A` 這類記號原樣留著，有這些記號的欄讀進來是字串。成交股數和老師的 `price:成交股數` 不一定一樣。
- 停牌日：老師的表跳過了 21 個停牌的股票日，交易所那天有列，所以這些列只有交易所欄。
- 台指期：每個日期、時段只留近月合約（到期月最早、有成交的那張），和特徵表選的一樣。`tx_day_到期月份(週別)` 寫是哪一張，結算日那天還是要到期的那張。夜盤的 `tx_night_結算價`、`tx_night_未沖銷契約數` 期交所不公布，每列都是 `-`。
- 沒併進來的：`yfinance/usd_twd_1h.csv`（1 小時K棒，和日表對不上）、`open_today/`（當天開盤，隔天 yfinance 的日K就有）、`data/raw/` 的 json 紀錄檔。

### 更新

排程每次上傳完、推資料之前跑 `python -m src.merge_raw`：來源檔的指紋沒變就跳過；有變就重算全部，只寫內容不一樣的檔，所以通常只動最後一個月和 `market.csv.gz`。休市日不跑，失敗只寫警告，不影響上傳。07:10 那次跑完約 07:30 推上來，那時 t 那列的老師個股欄還是 `-1`。

```bash
python -m src.merge_raw              # 來源有變才重算
python -m src.merge_raw --rebuild    # 不看指紋，全部重算
```

## 證交所、櫃買的回補（研究用）

```bash
python -m src.crawler --exchange-backfill [--start 2020-01-02] [--end YYYY-MM-DD] [--markets twse,tpex] [--max-requests N]
```

從證交所（上市）和櫃買中心（上櫃）抓 2020-01-02 起每個交易日的全市場日資料，只留老師的 100 檔。2026-11-09 回補完 2020-01-02～2026-11-06 的 1,662 天，沒有失敗。特徵表的交易所 9 欄讀這四個檔，不進模型欄。

- 每天的步驟：`exchange.enabled` 2026-11-10 打開，11-11 起每天的爬蟲在期交所之後補 i 那天，以及最近 10 個交易日裡檔案缺的日子。平常每個主機 2 個請求，約多 20 秒；每個主機最多 12 個請求，開始 3 分鐘後不再送新的請求。失敗只寫警告和 `data/raw/manifest.json` 的 `exchange`，不影響上傳。
- 公布時間：i 那天的資料台北 18:00 前就齊（2026-11-09 量的：收盤行情 14:30 有，本益比 16:00 還沒有、18:00 有），早上 07:10 抓得到。
- 沒抓到的日子：oop 早上連不上交易所的那天先空白，之後 10 個交易日內每天的爬蟲會補，下一次每天的特徵重寫最後兩個月時跟著補上。斷超過 10 個交易日，要在開發用的 clone 手動回補再 `--rebuild`（`memory/context/pipeline.md` 有步驟）。
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
│   ├── crontab.txt            排程主機的 crontab（台北 07:10 到 08:05 五次，08:25 補日韓開盤）
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
│   │   ├── taifex/            tx.csv：期交所的台指期，日盤和夜盤，只留單月合約；vixtwn.csv：VIXTWN 每天 13:45 收盤的值
│   │   ├── cnn/               fear_greed.csv：CNN 恐懼貪婪指數，美國日期，2021-02-01 起
│   │   ├── open_today/        kospi.csv、n225.csv：日韓當天的開盤和前一天收盤，08:25 的排程抓，一天一列
│   │   ├── twse/              證交所：valuation.csv 本益比、殖利率、股價淨值比；quotes.csv 收盤行情（長表的交易所欄用）
│   │   ├── tpex/              櫃買中心：valuation.csv、quotes.csv，欄位見「證交所、櫃買的回補」
│   │   ├── exchange_backfill.json   回補的進度：每個來源寫了幾天、no_data 的日子、失敗、請求數、有沒有被擋
│   │   ├── phase2_days.json   課程網站的交易日清單（/api/state 的 phase2Days）
│   │   └── manifest.json      下載紀錄
│   ├── processed/             特徵表，組員從這裡拿資料
│   │   ├── features/          YYYY-MM.csv.gz，一個月一檔，每天只更新最後兩個月
│   │   └── manifest.json      有哪些月份、模型用哪些欄、清理紀錄
│   ├── merged/                data/raw/ 合併成的兩張表，給組員研究（見「合併的原始資料」）
│   │   ├── stock/             YYYY-MM.csv.gz：一列是一天 × 一檔，老師個股表加證交所、櫃買
│   │   ├── market.csv.gz      一列是一天：老師 global、yfinance、台指期近月、VIXTWN、CNN
│   │   └── manifest.json      月份、欄名、列數、各來源的最後一天、來源檔的指紋
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
│   ├── crawler.py             下載老師資料、yfinance 額外指標、台指期、VIXTWN 和 CNN 恐懼貪婪；--exchange-backfill 回補證交所、櫃買（exchange.enabled 打開後每天也補）
│   ├── features.py            原始資料 → 特徵表；訓練和預測用同一個函式
│   ├── train.py               按日期切分、驗證、訓練、存模型
│   ├── predict.py             下載當天範本，產生 t 那天 50 檔的 submission CSV
│   ├── submit.py              上傳 CSV，再下載回來核對；Phase 1、2 都用
│   ├── site_api.py            課程網站的 API：登入、state、範本、上傳、下載
│   ├── online_lr.py           組員的邏輯迴歸和 26 個個股特徵（run_daily_test.py 用）
│   ├── merge_raw.py           data/raw/ → data/merged/ 的兩張表（run_daily_test.py 上傳後跑）
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
    ├── test_features_new_columns.py  只進長表的交易所、開盤跳空、老師美股不退格欄和 usd_twd_am 的舊K棒規則
    ├── test_vixtwn_cnn.py         VIXTWN、CNN 恐懼貪婪：爬蟲的兩步（假伺服器）和長表的 4 欄
    ├── test_open_today.py         日韓當天的開盤：08:25 那一步（假的 Yahoo）、長表 t 那列的 open_gap、每日流程怎麼接
    ├── test_no_future_data.py     特徵只能用 t 之前的資料；開盤跳空只用到 d 當天，不能進模型欄
    ├── test_online_lr.py          組員的模型：個股特徵不偷看，每天的模式和回測一樣
    ├── test_submit.py             上傳流程：假網站，不重試、核對、跳過的規則
    ├── test_run_daily_test.py     git 同步（假 remote）和 log 檔被換掉後重開
    ├── test_merge_raw.py          合併表：每格和來源一樣、近月合約、只寫有變的檔、來源壞掉時不寫檔
    └── test_submission_format.py  CSV 的欄位、列數、0/1
```
