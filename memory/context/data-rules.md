# 資料規則

寫 `crawler.py`、`features.py` 之前先讀這份。老師 ZIP 的結構和各序列的收盤時間見 `memory/projects/crawler.md`。

## 不能用未來資料

- 預測日 t 的特徵只能用 t 之前就知道的資料。t 當天的價格、成交量、法人、技術指標和 y 都不能用。
- 老師 global 表的 `^TWII`、`^KS11` 是當天收盤；`TX_OI` 疑似含收盤後才公布的資訊。這三欄只能用日期早於 t 的最後一列。
- global 表的 `^VIX`、`^IXIC`、`^GSPC`：Training 每一列放的是前一個 global 列日期的美股收盤；Live 每一列放的是日期早於該列的最後一個美股收盤。這三欄在 t 那列已經是開盤前就知道的值。
- 老師美股不退格（使用者 2026-11-08，2026-11-09 實作）：`^GSPC`、`^IXIC` 第 d 列是 d 開盤前最後一次美股收盤（2026-11-08 和 Yahoo 逐列比對，Training 1,506 列、Live 45 列沒有一列放 d 當天或更晚的收盤），所以 t 那列可以用。`teacher_gspc_fresh_ret_lag*`、`teacher_ixic_fresh_ret_lag*` 用 t 自己那列，公式和 `usd_twd_am` 一樣；Live t 那列約 05:05 填好。原本的 `teacher_gspc`、`teacher_ixic` 照舊只用 t 之前那列。`^TWII`、`^KS11`、`TX_OI` 還是只能用日期早於 t 的最後一列，`features.teacher_fresh` 放這三欄會丟錯。
- 唯一的當天資料例外（使用者 2026-11-08，2026-11-09 實作）：`kospi_open_gap`、`n225_open_gap` 放在 d 那列，用的是 d 當天的開盤，台北約 08:30 才看得到（Yahoo 延遲 20～30 分）。只進長表給組員研究，不能進 `model_columns`：`features.model_columns()` 遇到名字有 `open_gap` 的序列會丟 `FeatureError`，`tests/test_no_future_data.py` 也檢查。爬蟲丟掉日期 ≥ t 的日K，`build_features` 也不用日K的 t 那根。2026-11-11 使用者要台股開盤前拿到當天的值（yfinance、08:25、只寫進長表）：`crawler.open_today()` 在台北 08:22 以後從 Yahoo 一分鐘K棒抓當地 09:00 那根的 open 和前一天收盤，存 `data/raw/open_today/<序列>.csv`；有 d 那列就用它算 d 的開盤跳空，而且之後不換成日K算的。所以 t 那列在 08:25 的排程跑完前是空白，那天沒抓到就等日K補上。Yahoo 的 `^KS11` 晚 20 分、`^N225` 晚 15 分（11-11 各量一次），不是原本寫的 20～30 分。
- 證據：`../ml-final-archive/memory/context/data-decisions.md` 的「時間對齊驗證」，用 Yahoo 原始資料逐值比對過。
- VIXTWN（使用者 2026-11-09）：d 日的值是 d 日 13:45 收盤，台北 16:10 才公布，和 `^TWII` 一樣只能用日期早於 t 的值，t 那列最多用到 i。
- CNN 恐懼貪婪（2026-11-09 發現）：CNN 存的最後一天的分數收盤後還會改，跟著最新的 VIX 重算（11-06 那點 11-09 週一盤前還在變）。如果要到美股下一次開盤才定住，美國 d 日那點就含 20:15 ET（冬令台北 09:15、夏令 08:15）以後的 VIX 延長時段，也就是台股 t 盤中的資訊，拿來當 t 的特徵會偷看，歷史值和 07:10 抓到的也不一樣。量測確認之前不要用最後一天的分數；確認會改就用 t 之前最後一個美股交易日的前一個美股交易日（使用者 2026-11-09）。美股交易日要看道瓊的K棒，不能看 CNN 自己的日期：CNN 美國假日可能也會先建點，假日隔天那列會用到還在變的那天（審查 2026-11-09）。這個點如果在美國下一個交易日開盤時定住，那是台北 t 之前的晚上；如果在收盤時定住，最晚是台北 t 日 05:00。兩種都在 t 開盤前。那天早上沒抓到 CNN 時，檔裡這個點是前一次抓的、還沒定住的值，t 那列空白，不用它（使用者 2026-11-09）。
- 證交所、櫃買的日資料（`data/raw/twse/`、`data/raw/tpex/`，使用者 2026-11-08）：第 d 天的值是 d 那天收盤後的量（收盤價、本益比、殖利率、最後揭示買賣價量），只能當 t > d 的特徵，t 那列最多用到 i 那天。長表的 `val_*_lag1`、`quote_*_lag1`（2026-11-09 實作）存的是 i 那天的值本身，這檔股票 i 那天在兩個交易所都沒有列就空白，不往前找。價格是交易所的原始價，不和老師的還原價混用。櫃買本益比表的「每股股利」「股利年度」是事後回填的，爬蟲不存，也不能從別的地方補來用。查過櫃買的殖利率、本益比是當天的值，股價淨值比還沒查（見 `memory/projects/crawler.md` 的「有沒有偷看未來」）。

## 美股的日期

- yfinance 的日K用該市場當地的交易日期。預測 11/17（二）時，最新能用的美股K棒是 11/16（一）的收盤，台北 11/17 05:00 收完。
- 正式流程的爬蟲排在台北 06:00 之後。
- 抓完要檢查：每個序列都要有「前一個台股交易日 i」那根K棒，也就是特徵會用的那根；沒有就重抓一次，還是沒有就讓那個特徵空白。成交量要 > 0 只檢查個股和 ETF。指數、匯率、殖利率在 Yahoo 上成交量永遠是 0，只查日期（使用者 2026-11-05 決定，取代原本的「前一個美股交易日」規則）。
- 不要在台北 22:30 之後抓美股做隔天的特徵。那時美股已經開盤，抓到的是還沒收盤的K棒。
- 其他市場（亞洲、歐洲、匯率、期貨、殖利率）的K棒收完時間不同，要分開檢查。

## -1 和交易日曆

- 只有 Live 待定列的 `-1` 代表「還沒有資料」。
- Training 法人欄有 83 格是真的 `-1`（剛好買賣超 1 股），要保留。
- 10/23 那列一直是 `-1`：使用者 2026-11-05 確認是颱風假，台股休市。
- 交易日曆（使用者 2026-11-06 決定，取代「以 `phase2Days` 為準」）：老師 100 檔裡至少 `crawler.min_stocks_filled`（90）檔填好（`y` 是 0 或 1，還原開盤、收盤價 > 0）的日子才算交易日。i 是 t 之前最後一個這樣的日子；還是 `-1` 的列（10/23、當天早上 t 那列）不算，那天 global 的列也不用。`phase2Days` 只用來決定 t。config 的 `closed_days` 列 10/23，那天之後出現數值就停下。爬蟲和 `features.py` 呼叫同一個函式。細節見 `memory/projects/features.md`。global 表缺很多台股日（Training 少 112 天），不能當日曆。缺的原因（2026-11-09 和 yfinance 的日期比過）：老師只留台、韓、美三邊同一個日期都有開市的日子。112 天裡 62 天是韓國休市（`kospi.csv` 沒有那天），48 天是美國同一個日期休市（`dji` 沒有那天，例如感恩節、7/4、MLK），2020-01-02 是第一天，2021-04-06 找不到原因。反過來看，韓國休市的 64 個台股日有 62 個缺，美國同一天休市的 54 個有 53 個缺。所以這些列的資訊其實存在（例如美國休市那天，那列該放的是前一晚的美股收盤），是老師合併時丟掉的。

## 驗證按日期切

先取出不重複的日期，對日期清單切分，再把列對回去。同一天 50 檔股票共用市場特徵，隨機拆列會偷看到答案。

## 資料來源

- 使用者 2026-11-06：資料來源盡量只用 yfinance 和老師的資料，要加別的來源先問。
- 使用者 2026-11-08 同意加證交所（`www.twse.com.tw`）和櫃買中心（`www.tpex.org.tw`）：`BWIBBU_d`、`MI_INDEX`、`peQryDate`、`otc` 四個「指定日期、全市場」的端點，只留老師的 100 檔。研究用的回補（`python -m src.crawler --exchange-backfill`）2026-11-09 跑完 2020-01-02～2026-11-06，長表的 9 欄讀這些檔，不進模型欄。每天的爬蟲那一步（`download_exchange`）使用者 2026-11-10 打開（`exchange.enabled`），11-11 起每天補 i。端點、欄位和檢查見 `memory/projects/crawler.md` 的「證交所、櫃買的回補」。
- 使用者 2026-11-09 要加：期交所的 VIXTWN 月檔（和台指期同一個主機 `www.taifex.com.tw`）和 CNN Fear & Greed（`production.dataviz.cnn.io`，CNN 網頁畫圖用的網址，沒有公開 API）。只進長表研究欄。VIXTWN 歷史只用免費的官方檔（2026-08-03 起），不買、不自己算、不找第三方。細節見 `memory/projects/crawler.md` 的「VIXTWN、CNN 恐懼貪婪」。
- 台指期（2026-11-06 查）：yfinance 沒有可用的台指期。`IX0126.TW`（臺指期貨指數）Yahoo 只給最近 5 天；搜得到的 `TWN-X26.SI` 是新加坡的富時台灣期貨，一個到期月一個代號。老師 global 表只有 `TX_OI`（未平倉口數），沒有價格。期交所官網 `https://www.taifex.com.tw/cht/3/futDataDown`（POST，`down_type=1&commodity_id=TX`，一次最多一個月，CP950 編碼）有日盤和夜盤；標 t 日的「盤後」列是 i 日 15:00 到 t 日 05:00 的夜盤，漲跌是拿 i 日結算價算的。
- 期交所 OpenAPI `https://openapi.taifex.com.tw/v1/DailyMarketReportFut` 沒有日期參數，只給一天，而且比網站慢：2026-11-06 22:09 OpenAPI 還是 11/05，網站下載已經有 11/06 的日盤和夜盤。所以每天也用網站下載（重抓最近 7 天，漏掉的日子會自己補回來）。
- 開關切到 yfinance 時，`tx_futures.yfinance.night` 填了會報錯：一般的 yfinance 序列只留日期 < t 的K棒，t 那根夜盤會被丟掉；Yahoo 用哪一天標夜盤也沒查證，標成開始那天的話歷史列會用到開盤後的資料。只填日盤代號時 `tx_night` 每一列都空白。要開放夜盤，先查清楚 Yahoo K棒的日期，再讓 t 那根走期交所那樣的路（照 `night_ready` 決定收不收）。t 的夜盤幾點出現在網站上還沒量過，第一次早上跑時記下來（組員說 06:00 抓得到）。

## yfinance

- 每個請求至少間隔 2 秒，yfinance 自己送的請求（取 cookie、crumb、時區）也算。
- 下載時設 `auto_adjust=False`，才會同時有 `close` 和 `adj_close`。
- `end` 不含那一天，但它只限制請求的範圍。期貨在台北 07:00 後就開始下一個交易日，Yahoo 可能把盤中資料標成前一天。不存到還沒收完的K棒，要靠爬蟲自己丟掉日期 ≥ t 和週末的K棒，再檢查期貨最後一根的成交量（見 `memory/projects/crawler.md`）。
- 前一天的K棒收完時間（台北）：美股約 05:30、期貨 06:00、DXY 07:00、TWD=X 保守估 08:00。TWD=X 日期 d 那根的 close 是台北 d 日早上、開盤前的報價（倫敦 d 日 00:00～01:00；2026-11-06 只對過 11/04 一天，和 08:00 那根 1h 相同），所以另外用 1h 取台北 t 日 06:00 前最後一根的匯率（`usd_twd_am`，見 `memory/projects/features.md`）。那根要晚於 i 的 06:00 結束，不然是沒更新的舊檔，空白（2026-11-09 修）。
- 時區快取放 `configs/config.yaml` 的 `yfinance.cache_dir`（`.cache/yfinance`，不進 Git）。

## 資料放在這個分支

- 使用者 2026-11-05 決定：資料、模型、上傳紀錄都放在這個分支。組員 clone 一次就拿到全部，版本也對得上。`data/` 約 62 MB：`data/raw/` 約 46 MB（Training 解開約 45 MB，Live 每天約多 100 列，yfinance 19 個序列約 3 MB，這是 2026-11-05 的數字，2026-11-09 起是 21 個），`tests/fixtures/` 約 15 MB（2026-11-06 刪掉沒人讀的 15 MB 後）。2026-11-09 證交所、櫃買回補完，`data/raw/twse/`、`data/raw/tpex/` 多約 19 MB（證交所收盤行情 11 MB 最大）。
- 使用者 2026-11-06 決定：爬資料全部交給這個分支，`claude/data-collection` 不再爬也不再更新，只留著當對照。它的 `data/` 搬到這裡：老師資料放 `data/raw/teacher/training/`、`data/raw/teacher/live/`（和 Training ZIP `7433b271…`、Live ZIP `eea89fce…` 逐位元組相同），其他放 `tests/fixtures/data-collection/`（使用者 2026-11-06 從 `data/reference/` 搬過去，`data/` 底下只留流程會讀寫的資料）。搬法和 tree hash 見 `memory/projects/features.md` 的「資料來源」。
- `tests/fixtures/` 是凍結的快照：只給對照測試讀，每天的流程不讀，爬蟲不寫，裡面的檔都不要改。`.gitattributes` 設了 `tests/fixtures/** -text`，Git 不改換行。清理過的 yfinance 只能放在這裡，不能放進 `data/raw/yfinance/`（那裡放 Yahoo 原樣，`features.py` 會再清理一次，0052 分割前的價格會被除兩次 7）。
- 原始資料存解開後的 CSV，不存 ZIP。老師的 CSV 每天只多幾列，Git 只記差異；ZIP 每天會整個重存。
- yfinance 的 `adj_close` 每次重抓都可能有約 1e-6 的相對浮動（0052 實測 1.041e-6）。Yahoo 每次抓都把到抓取當下為止的所有除息套到之前每一列，所以整個檔案（和 sha256）都可能變，但不跨除息日的報酬不受影響。檔案小，影響不大。
- `data/merged/` 進 Git（使用者 2026-11-11）：組員要一個網址拿到所有原始資料的每個欄，`src/merge_raw.py` 把 `data/raw/` 併成個股表（一列是一天 × 一檔，一個月一檔）和市場表（一列是一天，一檔）。放在 `data/merged/`，不放 `data/raw/`：`data/raw/` 維持「和來源一模一樣」，Kaggle 的 `build_dataset.sh` 和回補的 `git add data/raw` 都不會帶到它。使用者同時決定：兩張表用 `date` 接，不做寬表（市場欄每檔重複 100 次會大好幾倍）；各來源用自己的日期，不對齊到 t（對齊過的報酬在特徵表），README 每個來源寫「預測 t 最多用到哪一列」；每天跟著排程更新。每一格是來源 CSV 的原字串（`-1`、`--`、`N/A` 都不動），台指期每個日期、時段只留近月（到期月最早、有成交的那張，和 `features.tx_values` 一樣）。不併 `usd_twd_1h.csv`、`open_today/`、json 紀錄檔。2026-11-11 用真資料逐格核對過：每一格和來源相同，鍵是各來源的聯集。大小：個股表 gzip 約 27 MB（83 個月），市場表約 1 MB。
- `data/processed/` 進 Git（使用者 2026-11-06）：特徵表一個月一檔，每天只重寫最後兩個月，組員用網址讀。可以從 `data/raw/` 用 `python -m src.features --rebuild` 重算。
- 每個檔案要小於 100 MB（GitHub 的上限）。
- 只有正式的每日流程會 commit 並推送 `data/` 和 `models/`。組員在本機跑只是測試，用 `git restore data models` 還原；推程式前先 `git pull --rebase`。
- 帳號密碼只放 `.env` 或執行環境的 secret，不進 Git，也不印到 log。
