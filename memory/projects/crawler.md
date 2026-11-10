# src/crawler.py

## 狀態

- 2026-11-05：已實作（commit `f50e5a3`），實作審查（四個角度、28 個成立的發現）修完，離線測試全部通過。第一次連網試跑前要先問使用者，試跑時不上傳。
- 審查裡會改到使用者決定的兩條，使用者 2026-11-05 都回答了：「有 t 那列」「i 那天填好」改成 100 檔裡至少 90 檔（`crawler.min_stocks_filled`）；期貨成交量的防線只記錄不丟。
- 查證紀錄（本機暫存，session 結束會消失）：yfinance 1.7.0 原始碼、老師 ZIP 結構、各序列日期、舊爬蟲、兩輪審查。結論都整理在下面。

## 使用者的決定

- 2026-11-05：Live 用助教的 chatgpt.site 新入口，金鑰由使用者放 `.env` 的 `COURSE_LIVE_KEY`，不自動從課程網站抓。舊程式（`../ml-final-archive/archive/system-completion/ml_financial_prediction/src/finpred/ingestion/course.py`）會從課程網站首頁載入的 JS 找金鑰，這個做法不採用。舊入口 `https://140.112.31.182:8444/` 的 TLS 驗證會失敗，也不用（2026-11-06 改了，見下一條）。
- 2026-11-06：助教說 chatgpt.site 只給自簽憑證有問題的人用，承受不了太多流量，瀏覽器進得去原本網址的話請用原本的。使用者決定：原本的網址優先，失敗再用 chatgpt.site。不關掉憑證檢查，改成只信任它那一張自簽憑證（`configs/live_ca.pem`）。切換條件（使用者 2026-11-06 確認）：原本的網址連不上、憑證不符、逾時、5xx、金鑰被拒或 ZIP 不對時，同一輪馬上改試 chatgpt.site 一次，不等待；只是還沒有 t 那列的話不換，照舊等 3 分鐘再抓原本的。manifest 的 `teacher_live.source` 記用了哪個入口，`fallback_from` 記前面入口的錯誤。程式是 `live_clients`、`live_fetch`。
- 2026-11-06：加台指期（期交所網站下載，開關 `tx_futures.source`）。存 `data/raw/taifex/tx.csv`：期交所的欄位原樣，只留單月合約，日期改 YYYY-MM-DD、去掉空白、UTF-8。第一次從 2020-01 起照月份抓（83 個請求，間隔 2 秒，約 3 分鐘），之後從舊檔最後一天往前 7 天抓。只存 t 之前的日盤；夜盤存到 t 那列，t 那列要過了 t 當天 05:15。失敗時舊檔留著、回傳 3。每日模式沒有 t 的夜盤就等 60 秒重抓一次。過了 08:30 只試一次不重試（Claude 定的，Live 也是只試一次）。
- 2026-11-06：第一次抓期交所（21:38 那次研究模式之後另外只跑期交所那段）：83 個請求、19,856 列。日盤 1,661 天，和老師 11/06 以前的交易日完全一樣；夜盤 1,662 天（多 11/06）。沒有清理紀錄。
- 2026-11-06 台指期的獨立檢查和程式審查（兩組加確認，沒有 blocker）：
  - 夜盤日期：9,584 列全部符合「標 d 日的盤後列，漲跌 = 夜盤收盤 − 同合約前一個日盤日的結算價」，另一種標法 0 列符合。連假後那天的盤後列是連假前最後一晚的夜盤。
  - 期交所對沒有交易的區間回只有表頭的 CSV，`parse_taifex` 回傳空清單。2026-11-06 量了三種：週末 11/07～11/08、颱風假 10/23、春節 2026-02-14～02-22，都是 197 bytes 的表頭。所以跨月連假時，整段休市的那一段不會讓這步失敗（審查擔心如果回提示頁，會每天卡在同一段；量過不會）。
  - 修了：回應或舊檔讓 `csv` 出錯、舊檔有壞列時，以前會讓整支爬蟲停下，現在只算期交所這步失敗（回傳 3）；`tx_futures.yfinance.night` 填了就報錯（t 那根會被「日期 < t」丟掉，Yahoo 怎麼標夜盤日期也沒查證）；不知道 i 時 `has_day_i` 記 None，不算缺。
  - 沒修（影響小，記著）：「回傳的日子比舊檔少」只比日期不比時段；第一次跑（沒有舊檔）時過了 08:30 還是會送完 83 個月；用比舊檔早的 t 重跑會刪掉範圍內 t 的日盤，不會洩漏，之後會補回來。
- 2026-11-06：第一次試跑用使用者在本機建的 `.env`。GitHub Secrets 只有 GitHub 上的流程讀得到。
- 2026-11-05：19 個 yfinance 序列都抓，爬蟲台北 07:10 開始跑。要不要用在模型上，看驗證分數。
- 2026-11-05：輸出和 data-collection 分支（原名 peaceful-babbage）的資料對齊（2026-11-06 起 data-collection 的資料搬到這個分支，見 `memory/context/data-rules.md`）：`data/raw/teacher/training/`、`data/raw/teacher/live/`、`data/raw/yfinance/`（2026-11-06 前叫 `teacher/`、`teacher_live/`）對應舊的 `data/teacher/`、`data/teacher_live/`、`data/extra/yfinance/`，19 個代號、檔名、欄位都一樣。
- 2026-11-05：成交量要 > 0 只檢查個股和 ETF（TSM、NVDA、四檔台灣 ETF），和舊分支清理規則用成交量的範圍一樣。其他序列只查日期。
- 2026-11-05：爬蟲存 Yahoo 給的原樣，清理（壞報價、佔位K棒、0052 分割、殖利率假日K棒）放在 `features.py`，規則照舊分支。
- 2026-11-05：t 當天早上 i 那列還是 `-1`（像 10-23）時，改用早於 t 最後一個填好的交易日當 i，照常預測上傳，manifest 記 `prev_day`（實際用的那天）和 `prev_day_never_filled: true`，通知組員。`features.py` 照同一條規則。
- 2026-11-05：個別股票停牌不擋流程。「有 t 那列」「i 那天填好」看 100 檔裡有沒有 90 檔（`crawler.min_stocks_filled`）做到；停牌那幾檔自己的特徵當天空白（missing value），其他檔和市場特徵照常，和舊分支 panel 的規則一樣。審查發現 Training 有 44 天少 1～2 檔（例如 2327 連停 7～8 天）。
- 2026-11-05：期貨最後一根成交量太小的防線只記錄不丟（`low_volume_last_bar_kept`）。回測時這條會誤丟換月日、量 0 的真結算K棒（黃金 19 天、原油 7 天）。
- 2026-11-08 決定、2026-11-09 實作：`yfinance.tickers` 最後加 `kospi: ^KS11`（組員要的日韓開盤，features 用它的 open 算 `kospi_open_gap`），現在共 21 個序列。放最後，前面序列的特徵欄順序不變。不在 `volume_required`、`futures`、`model_series`（有測試）。每次多抓一個序列；韓國休市、台股開盤的日子會多等 60 秒重抓，那天 `kospi` 進 `run.no_bar_i`，不算 stale。2026-11-09 13:06 用新程式連網跑研究模式（t = 11-09，暫存的 worktree，沒有上傳）：2 分 15 秒、Yahoo 45 個請求，21 個序列和 1h 都 ok，`run.no_bar_i` 是空的，`usd_twd_1h` 的 `has_value_t` 是 True，期交所 `has_night_t` 是 True。`kospi.csv`（1,678 根，2020-01-02～2026-11-06）複製進 repo，和重建的表一起推。
- 2026-11-09（open-questions 2026-11-08 的建議）：抓的順序改成 1h 先，再照 `fetch_order()` 抓日K：`features.model_series` 裡的先，其他照 config 的順序；缺 i 那根的重抓也照這個順序。1h 和日K共用同一個限流斷路器，截止的規則不變。過了截止或斷路器跳開時，先被跳過的是不在模型裡的序列。`manifest.json` 的 `yfinance` 最後照 config 的順序排（日K、再 1h），每天的 diff 不會因為抓的順序變大。
- 2026-11-09 修 `usd_twd_am` 的舊K棒（使用者 2026-11-08 同意的定義）：`hourly_has_value(rows, target, lookback_days, prev_target)` 的 `prev_target` 是 i 的 06:00。選到的K棒要在 4 天內結束，而且晚於 `prev_target`；不知道 i 時照舊只看 4 天。`has_value_t` 是 False 時，`usd_twd_1h` 進 `run.no_bar_i` 並寫警告。週一的 t、i 是週五時，週六清晨結束的那根（紐約週五收盤）晚於週五 06:00，算有。用本機的 1h 檔試算，2024-01-23 起的 673 個交易日新舊規則沒有一天不同；用本機現在的檔（最後一根 11-06 06:00 結束）算 t = 11-09 是 False，要連網抓過新的 1h 才有值。features 那邊的規則見 `memory/projects/features.md` 的 `usd_twd_am`。

## 證交所、櫃買的回補（2026-11-08）

### 狀態

- 2026-11-08：使用者同意做研究用的回補，只收資料，不動 `features.py`、`online_lr.py`、`run_daily_test.py`、`data/processed/` 和每天的爬蟲。程式在 `src/crawler.py` 的「證交所、櫃買中心」那段（`ExchangeBackfill`、`exchange_backfill()`），離線測試是 `tests/test_exchange.py`。
- 2026-11-09：回補跑完（台北 00:18～06:36，在開發用的 clone）。2020-01-02～2026-11-06 共 1,662 天，6,644 個請求，四個來源都沒有失敗、no_data、被擋。證交所兩個檔各 150,218 列，櫃買各 15,949 列。2026-11-08 決定的長表 9 欄讀這四個檔（見 `memory/projects/features.md`）。
- 2026-11-09：每日模式寫好（見下面「每天的步驟」），`exchange.enabled` 還是 false。
- 2026-11-10：使用者打開 `exchange.enabled`（選「今晚打開」；Claude 上午改好、推上去，下一次排程本來就是 11-11 07:10，和晚上打開一樣）。11-11 第一次跑要補 11-09、11-10 兩天，每個主機 4 個請求。測試的 `cfg` 夾具（`tests/test_crawler.py`、`test_exchange.py`）改成把開關關掉，要測這一步的測試自己打開（`daily_cfg`、`test_crawl_exchange_failure_does_not_change_the_exit_code`），不然 `crawl()` 的測試會跑真的交易所那步、碰 `.cache/` 的鎖。
- 2026-11-10 推上去之後在 oop 驗過：pull 到 `c749dda`、333 個測試通過，`.cache/` 沒有多出交易所的鎖檔。用暫存資料夾當 `raw_dir` 跑這一步（研究模式，t = 11-10，i = 11-09）：09:01 第一次證交所兩個請求都是 ConnectionError、櫃買 9 檔正常；09:03 再跑四個來源都 ok（證交所 91 檔、櫃買 9 檔，11-09 的列接在舊檔後面，舊列不變），每個主機 2 個請求。第一次多半是學校 DNS 一時查不到證交所（它 CNAME 到中華電信的 CDN；11-09 下午也只有證交所查不到）。每天的設定不重試，遇到時那天證交所的欄先空白，隔天的爬蟲補。暫存資料夾跑完就刪了。

### 每天的步驟（2026-11-09 寫好，2026-11-10 打開）

- `download_exchange()` 接在 `crawl()` 的期交所之後，每日模式和研究模式都跑。`crawl()` 多一個給測試用的參數 `exchange=`。
- 關著時完全不動：不建連線、不拿鎖、不讀檔，manifest 也沒有 `exchange`。
- 抓的日子：老師交易日曆裡早於 t 的最後 `exchange.gapfill_days`（10）天，檔案裡沒有的才抓，新的先。平常只缺 i，每個主機 2 個請求，兩個主機一共 4 個。
- 不停 07:00～09:00（`exchange.pause` 只給回補用）。過了爬蟲截止 08:30 整步跳過；每個請求送之前，等完會過截止，或過了 `daily_budget_seconds` 就停下那個主機。
- 每個主機最多 `daily_max_requests`（12）個請求。每個交易所各拿自己的鎖，回補正在跑的那個交易所這次跳過並寫警告。
- 失敗、no_data、被擋、例外都只寫警告和 `manifest["exchange"]`，不設 stale，不改爬蟲的回傳值。只有 Ctrl-C 會往外丟。
- 不寫 `exchange_backfill.json`。解析、檢查、檔數門檻、同一檔出現在兩邊、寫檔都沿用 `ExchangeBackfill`，加的參數不給就和回補一樣，回補的測試照舊通過。用真資料的副本加假主機試跑，寫出來的四個檔和回補的逐位元組相同。
- manifest 的 `exchange`：`status`（`ok`、`incomplete`、`failed`、`skipped`）、`error`（例如 `skipped_deadline`、`locked`、`no_dates`）、`prev_day`、`markets`、`locked`、`dates`、`requests`（每個主機送了幾個），`sources` 每個來源記 `file`、`ran`、`has_prev_day`、`missing_dates`、`new_dates`、`no_data`、`failures`、`requests`、`blocked`、`stopped`、`last_date`、`sha256`（`exchange_summary()`）。
- Claude 自己加的三個設定，使用者 2026-11-09 決定留著：`daily_retries: 0`（回補是等 60 秒再試一次）、`daily_max_failed_dates: 1`、`daily_budget_seconds: 180`。照回補的規則，主機卡住時這一步可能拖 10 分鐘以上，拖到上傳。
- 多花的時間：平常約 20 秒（本機讀寫約 6 秒，兩個主機同時送、請求間隔約 13 秒）；補很多天、請求數用滿約 90 秒；最壞約 5 分鐘（3 分鐘上限加最後一個請求最多 120 秒）。
- 什麼時候打開（使用者 2026-11-09）：等 11-10 07:10 新爬蟲第一次在 oop 正式跑完、成功上傳，而且 11-09 的公布時間量到 21:00 前資料已經出來，11-10 晚上才打開。一次只改一件事，出問題時好找原因。2026-11-10：07:10 那次停在 `git pull`（學校 DNS），07:25 那次上傳成功但 stale（期交所連不上，Yahoo 沒有 stoxx50e、kospi 的 11-09 那根）；使用者知道後選今晚打開。公布時間的量測在 oop 的 `~/pubtime/log.jsonl`（Mac 也跑一份，在 session 的 scratchpad `pubtime/log.jsonl`）：11-09 台北 14:30、16:00、18:00、21:00 各查一次四個 API，每筆記 `stat`、日期、列數、我們 100 檔有幾檔。
- 量到的（Mac）：收盤行情 14:30 就有（證交所 91 檔、櫃買 9 檔）；本益比 16:00 還沒有（證交所回「沒有符合條件」、櫃買 0 列），18:00 兩邊都有（91、9 檔）。所以 i 那天的資料 18:00 前就齊了，「21:00 前公布」的條件成立。oop 在 14:30 和 16:00 兩次都查不到 `www.twse.com.tw`（`Name or service not known`），櫃買正常，18:00 才好。21:00 那次 oop 和 Mac 四個 API 都正常，列數和 18:00 一樣（證交所估值 1,087、行情 1,389，櫃買 894、1,020），18:00 之後沒有再改。兩邊的量測 21:00 跑完就結束了。打開之後，oop 早上遇到 DNS 斷線的那天交易所欄會空白，之後 10 個交易日內每天的爬蟲會補。
- 打開 `exchange.enabled` 之前（2026-11-10 兩件都做完）：
  - 先量證交所、櫃買每天幾點公布 i 那天的資料，確定 07:10 抓得到。
  - 先 commit、push 回補的 `data/raw/twse`、`data/raw/tpex`、`data/raw/exchange_backfill.json`，oop 和 Mac 備援 pull 下來之後再打開。不然 oop 只會補最近約 6 天（每個主機 12 個請求、一天 2 個），生出一份不完整的檔，`--sync` commit 上去後會和開發用 clone 的完整檔衝突。
- 2026-11-08：兩位審查者看過。照意見加了：5xx 回的不是 JSON 當成被擋、連續 3 天逾時就停、每個交易所一個鎖、重試也至少隔 6.5 秒、對照表沒有的欄名寫法當格式錯誤、另一個交易所的檔讀不了只警告。

### 端點（2026-11-08 實測）

- 證交所本益比 `BWIBBU_d?date=YYYYMMDD&selectType=ALL&response=json`：最上層 `stat`（`OK`）、`date`、`fields`、`data`。2017-04-12 起有收盤價。虧損的本益比是 `-`。`股利年度` 是 JSON 整數，不存。
- 證交所收盤行情 `MI_INDEX?date=YYYYMMDD&type=ALLBUT0999&response=json`：`tables` 裡有十張表，收盤行情是欄名有「最後揭示買價」的那張（實測在第 9 張，程式用欄名找）。沒有揭示的價格是 `--`、量是 `0`。
- 證交所休市：HTTP 200，`stat` 是「很抱歉，沒有符合條件的資料!」，沒有 `date`。
- 櫃買本益比 `peQryDate?date=YYYY/MM/DD&response=json`：`stat` 是小寫 `ok`，最上層 `date` 是 YYYYMMDD，`tables[0].date` 是民國日期。2020 年沒有「財報年/季」。虧損的本益比是 `N/A`。「每股股利」「股利年度」是事後回填的，不存。例如 2020-01-02 的 3293：每股股利 25 元、收盤 393 元，殖利率卻是 2.80%，兩個對不上。
- 櫃買收盤行情 `otc?date=YYYY/MM/DD&type=EW&response=json`：欄名有空白和 `<br>`。2020 年上半年 15 欄（沒有買賣量），約 2020-07 起 17 欄。買賣量的單位寫「千股」或「張數」，是同一個單位。價格有千分位逗號；沒有成交是 `----`，沒有揭示是價格 `0.00`、量 `0`。
- 櫃買休市和還沒公布：都回 `stat` ok、0 筆。路徑打錯會轉到 `/errors`，回 HTTP 200 的 HTML。
- 櫃買前面有 Cloudflare（回應標頭有 `Server: cloudflare`、`CF-RAY`）。擋人時常回 HTTP 503 的 HTML 驗證頁。
- 我們的 100 檔：上市 91 檔、上櫃 9 檔（3293 3529 5274 5347 6223 6274 6488 8069 8299）。6446 在 2024-01-16 到 2024-02-26 之間從上櫃轉上市，所以兩邊都查，股票在哪邊出現就從哪邊拿。2020 年是上市 90 檔、上櫃 10 檔。

### 有沒有偷看未來（2026-11-08 用存下來的回應查）

- 櫃買殖利率是當天的值：2020-01-02 上櫃 10 檔裡有 6 檔的殖利率和「回填的每股股利 ÷ 收盤」對不上（3293 是 2.80% 對 6.36%，8069 是 6.56% 對 6.27%）。2020-07-01 和 2026-11-06 全部對得上，那時股利已經公布。
- 櫃買本益比沒有被換成最新的每股盈餘：3293 的「收盤 ÷ 本益比」2020-01-02 約 23.2 元（393 ÷ 16.97），2026-11-06 約 43.3 元（736 ÷ 17.01）。
- 證交所本益比表 2020-01-02 的股利年度是 107（我們 90 檔都是），是那天已經知道的年度。
- 股價淨值比還沒查。之後可以拿一季公布的每股淨值對一次 2020 年的值。

### 存法

- 一個來源一個長表，照 date、stock_id 排序，UTF-8、LF。欄名照來源，只去掉空白和 `<br>`；櫃買的買賣量用對照表（`EXCHANGE_SPECS`）改成「最後買量」「最後賣量」。
- `data/raw/twse/valuation.csv`：date, stock_id, 收盤價, 殖利率(%), 本益比, 股價淨值比, 財報年/季。
- `data/raw/twse/quotes.csv`：date, stock_id, 開盤價, 最高價, 最低價, 收盤價, 成交股數, 最後揭示買價, 最後揭示買量, 最後揭示賣價, 最後揭示賣量。
- `data/raw/tpex/valuation.csv`：date, stock_id, 本益比, 股價淨值比, 殖利率(%), 財報年/季（來源沒有時空白）。
- `data/raw/tpex/quotes.csv`：date, stock_id, 開盤, 最高, 最低, 收盤, 成交股數, 最後買價, 最後買量, 最後賣價, 最後賣量（來源沒有買賣量時空白）。
- 格子：去掉前後空白，像數字的拿掉千分位逗號，`-`、`N/A`、`--`、`----` 原樣留。
- 成交股數不是老師的 `price:成交股數`，兩個不要混用。2330 在 2020-01-02 兩邊一樣（33282120），2026-11-06 證交所是 110,714,587 股、675,265 筆，老師 Live 是 108,891,587 股、675,253 筆。櫃買的取到整張：3293 在 2020-01-02 是 1,471,000，老師是 1,481,864。
- `data/raw/exchange_backfill.json`：每個來源檔案裡有幾天、第一天和最後一天、no_data 的日子、失敗、這次和累計的請求數、有沒有被擋、停下的原因、最後一次跑的時間。只換掉這次有跑的來源。`manifest.json` 不碰。
- 大小估計：四個檔合計約 18 MB（證交所收盤行情約 11 MB 最大），每個都遠小於 100 MB。

### 檢查

- HTTP 200、Content-Type 是 JSON、解得開。不是的話（HTML、轉到 `/errors`、403、429，或 `stat` 裡有「頻繁」「安全」）就把這個主機當成被擋，這次不再送。只看 `stat`，不掃整個回應，免得公司名稱或註解裡的字誤判。
- 回應的日期要等於要的日期，不符就當格式錯誤，這次停掉這個來源。必要的欄沒有、同一欄對到兩個來源欄、列的長度不對，也一樣。不猜欄位位置。
- 可以沒有的欄（櫃買的財報年/季、買賣量）也不默默存成空白：沒對到的來源欄名字裡有存檔欄名，或開頭是「財報」「最後買量」「最後賣量」，就是格式錯誤（例如哪年出現「最後買量(股)」）。櫃買買賣量 2020-07-01 起一定要有。
- 老師的交易日，回應裡我們的股票要夠多：證交所 85 檔、櫃買 8 檔（`exchange.<市場>.min_stocks`）。不夠記 no_data、不寫，下次再抓。空的那天不會寫成只有表頭的檔。
- 同一檔同一天出現在兩個交易所（這次抓的，或另一個交易所的舊檔）：這天記失敗，四個來源都不寫。同一個回應裡同一檔出現兩次，也記失敗。
- 只抓老師交易日曆（`trading_days()`，Training 接上 Live）裡的日子，休市日不送請求。結束日預設是本機老師資料最後一個交易日。

### 限流和時間

- 同一個主機一次一個請求，上一個請求結束後至少隔 `exchange.min_interval_seconds`（6.5 秒）。兩個主機各一個執行緒同時跑；每一天兩邊都回來後才檢查同一檔有沒有出現在兩邊。一天四個請求，全部 1,662 天約 6 小時。
- HTTP 沿用 `SiteClient`（2026-11-08 加了 `max_redirects` 和最後一個回應的狀態碼、Content-Type，課程網站、Live、期交所的行為不變）。回補的 client 不跟轉址，`read()` 用 `retries=0`，重試自己管。
- 逾時、連不上、回 JSON 的 5xx：等 60 秒再試一次（至少也隔 6.5 秒），還是不行記失敗、換下一天。5xx 回 HTML 或沒寫 Content-Type（像 Cloudflare 的驗證頁）直接當成被擋，不重試。
- 同一個主機連續 3 天（`exchange.max_failed_dates`）每個請求都逾時、連不上或 5xx，也當成被擋，這次停下。中間只要有一個回應就重新算。
- 被擋：這個主機馬上停，不自動等，回傳 3。過一陣子再手動跑，會接著做。
- 每次執行的第一個請求也先等 6.5 秒，剛按 Ctrl-C 又馬上重跑也不會太密。
- 同一個交易所同時只能有一個回補程序：`.cache/exchange_twse.lock`、`.cache/exchange_tpex.lock`（flock，和 `run_daily_test.py` 一樣）。另一個還在跑就丟 `CrawlerError`，不送請求。`exchange_backfill.json` 讀寫時另外拿 `.cache/exchange_state.lock`，分開跑 twse、tpex 兩個程序也不會互相蓋掉紀錄。
- 台北 07:00～09:00 不送請求，睡到 09:00（`exchange.pause`），避開每天的排程。

### 續跑

- 日期由新到舊。檔案裡已經有的日子跳過，no_data 和失敗的日子下次會再抓。
- 每做完 20 天（`exchange.flush_every_dates`）和結束時（含 Ctrl-C）把新的列和舊檔合併、排序，用 `write_atomic` 整份換新。舊檔表頭不對就停下，不覆蓋。
- 回傳 0（沒有被擋、格式錯誤、失敗）、3（有）、130（Ctrl-C）。no_data 不算失敗。`--max-requests N` 試跑用，用完就停，不算失敗。
- 進度只印在畫面上，不寫 `data/submission/run_<t>.log`（每天的流程會 commit 那個檔），也不用帳密。
- 只跑一個交易所時，另一個交易所的檔讀不了（表頭不對、有壞列）只警告，記在 `exchange_backfill.json` 的 `last_run.warnings`，這次不拿它檢查同一檔有沒有出現在兩邊。這次要跑的交易所的檔讀不了就停下，不覆蓋。
- 只在開發用的 clone 跑（例如 Mac 的 `~/Desktop/ml-final-2026-fall`）。oop 的 `~/ml-final-2026-fall` 和 Mac 的 `~/ml-final-runner` 是排程用的 clone：`run_daily_test.py --sync` 會 `git add data/raw`，把跑一半的 CSV 和 `exchange_backfill.json` 一起 commit；`git_start` 對齊 origin 時也可能把檔案換回去。
- 跑完自己 commit，路徑寫清楚：`git add data/raw/twse data/raw/tpex data/raw/exchange_backfill.json`。

### 還沒做、要記著的

- 只跑一個交易所時，如果同一檔出現在另一個交易所的舊檔，這次只是不寫、記失敗，舊檔那邊不刪，要人看。

## VIXTWN、CNN 恐懼貪婪（使用者 2026-11-09）

### 使用者的決定

- 2026-11-09：使用者要每天的 VIXTWN（臺指選擇權波動率指數）收盤值和 CNN Fear & Greed。做到原始檔、長表研究欄、每天的爬蟲；不進 `model_columns`。
- VIXTWN 歷史只用免費的官方檔（2026-08-03 起），之後每天累積。不買、不自己用選擇權行情算、不找第三方。
- CNN 最後一天的分數如果到台股開盤後還會被改，就用再前一個美股交易日的分數（見 `memory/context/data-rules.md`）。量測和推的時間見 `memory/context/open-questions.md`。

### VIXTWN 的來源（2026-11-09 查）

- `https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/YYYYMMnew.txt`，一個月一檔，CP950，CRLF，空白分隔。前兩行是表頭和 `-----`。欄位：交易日期 `YYYYMMDD`、時間（都是 `13450000`，13:45:00.00）、臺指選擇權波動率指數、收盤前1分鐘平均指數（2020-11-23 起）。11 月的檔 346 bytes。
- 只留最近約 4 個月（「前3個月每日收盤」頁面 `cht/7/vixDaily3MNew` 列 2026/08～2026/11）：2026-08-03～11-09 共 66 天（8 月 21、9 月 20、10 月 19、11 月 6），日期和 `tx.csv` 的日盤交易日一樣。更早的月份回 302 轉到 `http://www.taifex.com.tw/file/taifex/404.htm`，`YYYYMM.txt` 也一樣。
- 當天台北 16:10 更新：`Last-Modified` 是 11-09 08:10:31 GMT、08-31 08:10:32 GMT，之後沒再改，所以隔天 07:10 一定有 i 那天的值。oop 抓得到（4.6 秒）。
- 沒用的路：期交所 E-Data Shop 賣歷史（「3,000 元／半年」，2007-01-01 起，價目表 `交易歷史資料價格及提供時間_adj.odt`，計價方式沒確認）；Wayback 只有 11 個月（201906、201907、202006～202009、202401、202402、202602～202604）；期交所 OpenAPI 沒有 VIX；HiStock 頁面的陣列是當天盤中。可以自己算：`optDataDown`（POST，`commodity_id=TXO`）有每個序列、每個時段的最後最佳買賣價和契約到期日，一天約 6,600 列、630 KB，2020 年起約 1 GB。使用者沒選。

### CNN 的來源（2026-11-09 查）

- `https://production.dataviz.cnn.io/index/fearandgreed/graphdata/<開始日>`：一個請求回開始日以後的全部，最後還有一個「現在」的點。沒有公開 API，是 CNN 網頁畫圖用的網址，隨時可能改。要瀏覽器的 User-Agent（加 `Accept: application/json`、`Referer: https://edition.cnn.com/`），curl 預設的回 418。開始日 2020-01-01 回 500；2020-09-19 從 2020-09-21 開始，約 1 MB；不給開始日回最近一年；2026-10-01 起約 21 KB。oop 抓得到（0.2～0.5 秒）。
- JSON：`fear_and_greed`（`score`、`rating`、`timestamp`、`previous_close`、`previous_1_week` 等）、`fear_and_greed_historical.data`（`x` 毫秒、`y` 分數、`rating`），另外 7 個指標各有原始值的 `data`（`market_momentum_sp500`、`stock_price_strength`、`stock_price_breadth`、`put_call_options`、`market_volatility_vix`、`junk_bond_demand`、`safe_haven_demand`，加 `market_momentum_sp125`、`market_volatility_vix_50`）。
- 每點標在美國日期的 00:00 UTC。美國 d 日那點在 d 的 00:00 UTC（冬令台北 08:00）就先建好，放前一天的值，所以日期 ≥ t 的點要丟，不是 00:00 的點（「現在」）也丟。
- 兩次請求重疊的日子值相同（開始日 2020-09-19 和 2021-01-01 比 1,469 天、和不給開始日比 250 天），只有最後一兩點會變。
- 假值：剛好 50.0 兩段，2020-09-21～10-23（25 天）、2020-11-04～2021-01-21（53 天）；中間 10-26～11-03 是 0.3～3.6，不合理。2021-02-01 起用：到 2026-11-06 有 1,449 天，`dji.csv` 的美股交易日 1,450 天，只缺 2026-03-12，沒有假日的點。2021-02-01 以後沒有剛好 50.0 的值；連續兩天同值的有 9 次（例 2021-07-02、2023-06-14）。
- 收盤後還會改：11-06（週五）那點台北 11-09 17:06 是 23.7476，17:33 變 23.6484，和即時分數一起變。7 個指標只有 VIX 在動（11-09 那點 24.19 變 24.31，週一盤前的延長時段）；VIX 指標 11-06 那點是 25.64，等於 Yahoo 收盤，沒變。`previous_close` 是 22.079，和存的 11-06 值不同。推測最後一天的總分一直拿最新的 VIX 重算，到美股下一次開盤才定住，量測中。11-09 19:18（UTC 11:02 的版本）11-06 那點是 24.54，等於即時分數，週一美股開盤前一直跟著動（17:06 23.75、17:16 23.65、17:59 23.85、19:00 24.44）。22:00（UTC 13:45 的版本）24.10、22:20（UTC 14:04）24.17，11-06 和 11-09 兩點都等於即時分數，`previous_close` 還是 22.079。美股 22:30 開盤（冬令），之後的點才看得出 11-06 會不會定住。21:00 那次學校 DNS 斷線，重試 4 次都失敗。
- CDN 快取（2026-11-09 19:15 查到）：回應經過 Fastly（`x-served-by` 是 IAD 和 HKG 兩層，`cache-control: max-age=5`）。一個網址很久沒人要時，Fastly 先回舊的那份、背景再更新：oop 19:15 要 `graphdata/2026-10-01` 拿到 UTC 09:16 的版本（17:35 那次留下的），一分鐘後 curl 再要就是 UTC 11:00。沒人要過的開始日一定是 `MISS, MISS`，拿到最新的。即時分數的 `timestamp` 比抓的時間晚約 15 分鐘（美股盤中 11-10 00:17 只晚 30 秒）。2026-11-09 22:30 試過網址後面加 `?_=…`：CDN 不看查詢字串，換不同的值還是 `HIT`、Age 一直往上加，所以要換網址只能換開始日。第一版的開始日跟著檔案最後一天走，前一天沒抓成功、或美國假日沒有新的點時，隔天會要同一個網址，拿到前一天存的那份（最後查漏 2026-11-09 找到），所以改成跟著 t 走（下面「每天的步驟」）。

### 每天的步驟（2026-11-09 寫在 worktree `/Users/ian/Desktop/ml-final-vixcnn`，11-11 推）

- 接在期交所台指期之後、交易所之前。各有開關（`vixtwn.enabled`、`cnn.enabled`），失敗、格式不對、被擋都只寫警告和 manifest，不改爬蟲的回傳值，和交易所那步一樣。過了爬蟲截止 08:30 就跳過。
- VIXTWN：抓「檔案最後一天往前 7 天」到 i 所在月份的每個月份檔，平常 1 個請求，月初 2 個。沒有檔時從 config 的開始月份抓。302 當成那個月沒有檔，不跟轉址。和台指期共用期交所的請求間隔。只存日期 < t 的列。
- CNN：一個請求，開始日跟著 t 走，每個 t 的網址都不一樣（`crawler.cnn_start`，2026-11-09 改）：平常是 t 往前 `fetch_days`（30）天；沒有舊檔、或舊檔最後一天比 t 往前 20 天還早時抓全部，開始日放在 2020-09-19（CNN 最早那天）到 2021-01-31 之間，照 t 錯開（135 天才會重複），2021-02-01 以前的點照樣丟。t = 2026-11-11 是 2021-01-28，11-12 起平常是 t 往前 30 天（11-12 是 10-13）。不重試，隔天的重疊會補回來。只存 00:00 UTC、日期 < t、≥ 2021-02-01 的點。和舊檔重疊的日子用新值，舊日子的值變了記在 manifest。manifest 記 CDN 的 `cache`（`Age`、`X-Cache`）和回應裡的 `now.timestamp`，看得出是不是舊的那份；只記不擋（週一早上 CNN 的時間可能還是週五的，用時間擋會誤判）。2026-11-10 00:17 在 Mac 用真網址試跑：兩種開始日（`2021-01-27`、`2026-10-11`）都是 `MISS, MISS`、狀態 ok，VIXTWN 4 個請求 66 天、CNN 1,450 天。
- 存檔：`data/raw/taifex/vixtwn.csv`（`date,vixtwn,vixtwn_1min_avg`）、`data/raw/cnn/fear_greed.csv`（`date,score`，date 是美國日期），照日期排序，`write_atomic`。
- 審查（2026-11-09）之後加的：i 所在的月份也 302 時 VIXTWN 記 `incomplete`（網址可能改了）。2020-11-23 起少一格的列當成格式錯誤（照空白切分不出少哪格）。CNN 不是 00:00 UTC 的點超過一個、或一個每天的點都沒有，當成格式變了。舊檔有、這次回應該有卻沒有的日子記在 `vanished_dates`，檔裡留著（CNN 美國假日先建、後來拿掉的點，features 只看道瓊的日子，用不到）。manifest 的 `now` 只留有限的數字和像時間的字串。`side_finish` 不讓例外跑出去：manifest 寫不出來時換成最短的一筆再寫。
- 第二輪審查（2026-11-09 晚上，4 個角度各一位審查、一位反駁，加一位查漏；31 個發現 28 個成立，都不是偷看）之後改的：VIXTWN 每個月份各算各的，一個月逾時或 5xx 時其他月份照抓照存，i 的月份沒抓到才算 `failed`（`failed_months` 記每個月的錯），沒抓到的月份不算不見；i 的月份沒抓到時不留空的檔。沒有 i（研究模式沒有 Live 的帳號）時，i 的月份 302 不報「網址可能改了」。CNN 的 `has_prev_day` 記 None（美國日期對不上台股的 i），t 那列要用的那天 features 自己檢查、空白時寫警告。舊檔讀不了時 `rows`、`last_dates`、`has_prev_day` 記 None，加 `old_file_unreadable`。`side_finish` 記不了檔案狀態時寫一行警告。CNN 的 x 不在 2000～2100 年當成格式變了。測試補了 11 項，31 個突變（把修正改回去）都會讓測試失敗，全部 431 個測試通過。沒改的：config 少一整節時爬蟲會停下（審查判定不是 bug：真的 config 每節都有，exchange 那節也一樣）。

## 查到的事實

### 老師 ZIP

- Training：`7433b271…`，18 MB，解開 46.5 MB。102 個成員：`data/info.json`、`data/global/global_data.csv`、`data/market/<代號>.csv` × 100。10/27～11/05 抓了 11 次都沒變。
- Live：101 個成員，沒有 `info.json`。每個版本都是 2026-09-01 起的完整歷史，只往後加列；已經填好的格子沒改過。
- 兩個 ZIP 的成員都以 `data/` 開頭，沒有資料夾項目、`..`、絕對路徑。
- 格式差異：Training 換行是 LF，`y` 是 `0`/`1`；Live 換行是 CRLF，`y` 是 `0.0`/`1.0`，待定格是 `-1`。
- Training 有 83 格真的 `-1.0`，都在法人欄；`6446.csv` 有 2 列法人欄是空的。
- Live 少的平日：09-25、09-28、10-09、10-26（沒有列）。10-23 有列，但整列一直是 `-1`，網站標「資料未齊全」。
- Live 的更新時間（使用者 2026-11-05 提供的 Live 網站「每日更新紀錄」截圖，頁面時間 11/05 18:01）：
  - t 那列在 00:00 新增，先全部填 `-1`。
  - `^IXIC`、`^GSPC`：t 當天約 04:00～05:05 填好，看過最晚 05:05:05。
  - 其他 2004 格（100 檔 × 20 欄，加 global 4 欄，含 y）：t 當天陸續填，約 21:05～22:05 填完，看過最晚 22:05:17。11/05 15:57 時填了 1502/2004。
  - 所以白天下載的 Live，t 那列可能一部分有值。待定要逐格看，不能只看整列。
  - 之前從 ZIP 內檔案時間推的「07:00、21:05 兩次建檔」不對，那只是舊系統剛好在那些時間下載。
- Live 主機：最早是 `https://140.112.31.182:8444/`，TLS 驗證失敗。助教後來給 `fin-pred-daily.jiangxuehaokeai.chatgpt.site`，一般 TLS 可以過，要用瀏覽器的 User-Agent（Python 預設的會被擋）。
- 2026-11-06 連原本的網址（沒帶金鑰）：憑證是自簽的，CN 和 SAN 都是 IP `140.112.31.182`，`CA:TRUE`，有效到 2027-10-07，SHA-256 指紋 `C1:C8:03:36:93:77:4D:CD:63:FC:66:B3:02:35:56:A6:7B:12:A5:81:36:90:74:84:23:59:B3:59:4E:84:9C:C9`。用系統憑證驗證會失敗；`requests` 的 `verify=` 指向這張憑證就過，首頁 HTTP 200，是同樣的「每日股票資料」頁，表單一樣 POST `/login`、欄位 `key`。金鑰和 chatgpt.site 是不是同一把還沒試。

### yfinance 1.7.0 和 curl_cffi 0.16.3

- 所有 HTTP 都經過全程式共用的 `YfData`，最後一個傳進去的 session 會蓋掉前面的。`yf.download` 沒傳 session 時會換回沒限流的預設 session，所以不用 `yf.download`。
- curl_cffi 的 `get`、`post` 都走 `Session.request()`，覆寫它就攔得到 yfinance 的每個請求。轉址由 libcurl 在同一次呼叫裡自己跟過去，覆寫 `request()` 管不到每一跳。
- `YfData.cache_get` 是 `lru_cache`，連錯誤回應也快取。只有在「end + 30 分鐘」早於真實現在時間時才走快取，所以正式流程 07:10 重抓台股和亞洲序列時會走快取。重抓前要 `YfData.cache_get.cache_clear()`。
- `yf.config.network.retries` 預設 0。HTTP 狀態 ≥ 400 時 yfinance 會換 cookie 策略再送一次，設定關不掉。chart 回 429 時，在 `request()` 裡直接丟 `YFRateLimitError` 擋得住；cookie、crumb 回 429 時 yfinance 會接住，不帶 crumb 照樣送 chart。
- `yf.config.debug.hide_exceptions` 預設 True，出錯時 `history()` 回傳空表；設成 False 才會丟例外。
- `YFPricesMissingError` 涵蓋「代號不存在」和「Yahoo 這次回了空結果或錯誤」，分不出來。伺服器回 HTML 時丟的是 `JSONDecodeError`。
- `end` 不含那一天，字串日期當成交易所當地的午夜（紐約是台北 13:00）。日K的索引是交易所當地日期。缺的成交量填 0。最後兩列同一天時，yfinance 丟掉倒數第二列（已收盤那根），留下最新那列。
- `yf.set_tz_cache_location(d)` 把三個 sqlite 快取（時區、cookie、ISIN）放到 d，要在第一次呼叫 yfinance 前設。
- curl_cffi 的 `Session` 預設 `impersonate=None`，要自己設 `"chrome"`。

### 19 個序列的日期和成交量

- 成交量全是 0：`^SOX`、`DX-Y.NYB`、`^TNX`、`^IRX`、`TWD=X`。
- 以 t = 11/17（二）、i = 11/16（一）為例，11/16 那根收完的時間（台北）：美股 05:30、殖利率 04:20、期貨 06:00、DXY 07:00、TWD=X 保守 08:00、亞洲 16:30 前、歐洲 01:00。
- 07:10 時，期貨已經在下一個交易日的盤中（18:00 ET 開盤，台北 07:00）。Yahoo 怎麼標這一列沒查證過。如果它的時間戳落在 i 那天，yfinance 的同日合併會用盤中的 10 分鐘資料蓋掉 i 那根已結算的K棒，日期還是 i。週一跑時則可能多出一根週日的K棒。離線 probe 重現過這兩種情況。
- DXY 下一段在 19:00 ET（台北 08:00）才開始；N225 08:00 開盤；TWD=X 的 t 那根從倫敦午夜（台北 08:00）開始。07:10 都還沒開始。

## 計畫

### 執行順序

`main(argv)` 依序做：

1. 讀 `/api/state`，把 `phase2Days` 的 `tradingDate`、`enabled`、`isCompetition` 存成 `data/raw/phase2_days.json`。`uploadQuota`、`mySubmissions` 不存。i 取 `phase2Days` 裡早於 t 的最後一天，不篩 `enabled`：舊紀錄只看到「當天開放提交的 slot 是 enabled=1」（`../ml-final-archive/archive/system-completion/ml_financial_prediction/docs/research/AUTOMATION.md` 第 18 行），看起來像提交窗口，不一定代表交易日。第一次真的讀到 `/api/state` 時要確認過去的日子 `enabled` 是多少。`phase2Days` 裡沒有早於 t 的日子時（Phase 2 第一天，或研究用的舊 t），取 Live 裡早於 t、已經填好的最後一天（至少 90 檔的 `y` 是 0 或 1，還原開盤價、收盤價都 > 0）。
2. 老師 Training。
3. 老師 Live。
4. yfinance：1h 先，再日K（2026-11-09 起模型用的序列先，`fetch_order()`）。
5. 檢查每個序列有沒有 i 那根，沒有的一起重抓一次。
6. 期交所台指期。
7. 證交所、櫃買（`exchange.enabled` 打開才跑，見「每天的步驟」）。
8. 寫 manifest。

`--date t`：每日模式，正式流程由 `run_daily.py` 傳進來。沒給就是研究模式，t 取台北今天，不做 Live 是否更新到 t 的檢查，也不檢查時間。

### 什麼時候跑

- 每日模式下，台北現在早於 `config.yaml` 的爬蟲開始時間（07:00）就不跑，丟錯誤。這同時守住「22:30 後不抓美股做隔天特徵」。
- 爬蟲截止（`config.yaml`，預設 08:30）：每次等待或新的一次嘗試前先看時鐘，會超過就不做。yfinance 剩下的序列沿用舊檔，標 `failed`。

### 下載和解壓（老師資料）

- HTTP：搬舊 `course.py` 的 `VerifiedSession.read()`。每個請求都有逾時（連線 10 秒、讀取 90 秒），邊下載邊數位元組，超過 100 MB 就中止；只跟隨同一個主機的轉址；GET 遇到 429、5xx 重試 2 次，POST 不重試；用瀏覽器的 User-Agent。
- Training：`data/raw/teacher/training/` 的檔案指紋和 manifest 一樣就不下載 ZIP。不一樣或沒有，才登入課程網站下載。
- Live：每次都下載。`POST /login` 帶 `COURSE_LIVE_KEY`，再 `GET /data.zip`。
- ZIP 檢查：
  1. 壓縮檔 ≤ 100 MB，解開總大小 ≤ 512 MB。
  2. 成員名稱不能重複。
  3. 成員名稱集合要剛好等於預期：Training 是 `data/info.json`、`data/global/global_data.csv`、`Top100@Y` 每一檔的 `data/market/<代號>.csv`；Live 一樣但沒有 `info.json`。
  4. 每個成員用 `read()` 讀一次，讀到結尾會自己驗 CRC，加密的會丟錯。
  5. CSV 表頭和預期一模一樣，日期是 `YYYY-MM-DD`、排好、不重複；`info.json` 要解析得出 `Top50@Y`、`Top100@Y`。
- 解壓：路徑照預期清單產生（就是拿掉開頭的 `data/`），自己寫出原始位元組，不用 `extractall`。先寫到 `data/raw/` 底下的暫存資料夾，全部成功才把舊的移開、新的換進來。失敗時舊資料還在。
- `-1` 不處理，原樣保存。

### Live 有沒有更新到 t（每日模式）

- 要有 t 的列，而且 i 那列已經填好：至少 90 檔有 t 那列；i 那天至少 90 檔的 `y` 是 0 或 1，`etl:adj_open`、`etl:adj_close` 都 > 0。法人欄的 `-1` 不看。沒填好的代號（多半是停牌）記在 `prev_day_missing_stocks`。
- 沒有 t 的列，或下載遇到逾時、連不上、5xx：等 3 分鐘重抓，最多 3 次，也受爬蟲截止限制。還是不行就丟錯誤，舊的 `teacher/live/` 留著。
- 有 t 的列，但 i 那列還是 `-1`（像 10-23）：不等，改用早於 t 最後一個填好的交易日當 i，回傳 3（使用者 2026-11-05 決定）。
- `COURSE_LIVE_KEY` 是空的：每日模式丟錯誤；研究模式跳過 Live，記在 manifest。

### yfinance 的限流

- `PacedSession`：繼承 curl_cffi 的 `Session`，覆寫 `request()`。
  - 上一個請求結束後至少等 2 秒，再加 0～1 秒隨機。
  - `impersonate="chrome"`、`retry=0`。
  - 一律把 `allow_redirects` 改成 False。遇到 3xx 自己跟過去，每一跳也經過限流器，最多 5 跳，303 改用 GET。
  - chart 回 429 就丟 `YFRateLimitError`。
  - 只數請求數和轉址次數，寫進 manifest 的 `run.yahoo_requests`、`run.yahoo_redirects`（2026-11-06 從 `http_requests`、`redirects` 改名）。課程網站和 Live 的請求數記在 `run.site_requests`。
- 開始前：`yf.set_tz_cache_location(".cache/yfinance")`、`yf.config.network.retries = 0`、`yf.config.debug.hide_exceptions = False`、`YfData(session=paced)`。
- 每個序列：`cache_clear()` 後 `yf.Ticker(代號, session=paced).history(start="2020-01-01", end=t, interval="1d", auto_adjust=False, actions=False, repair=False)`。每天重抓完整歷史。
- CL=F、GC=F 的 `end` 改用帶時區的時間：「t 那天台北 00:00」換算成紐約的日期，再取那天紐約 17:30。這在下一段交易（18:00 ET）開始之前，yfinance 會先丟掉時間戳 ≥ end 的列，再做同日合併，所以盤中那列進不來（離線 probe 驗證過；Yahoo 那邊怎麼處理沒驗證）。
- 抓回來之後：
  - 丟掉日期 ≥ t 的K棒，也丟掉日期是週六、週日的K棒。
  - CL=F、GC=F 第二道：最後一根的成交量低於前 21 根中位數的 10%，只在 manifest 記 `low_volume_last_bar_kept`，不丟（使用者 2026-11-05 決定：回測時這條會誤丟換月日、量 0 的真結算K棒，黃金 19 天、原油 7 天）。第一次實際跑確認 Yahoo 怎麼標盤中列後，再決定要不要真的丟。
  - 丟了幾根、第二道有沒有動作，記在 manifest 那個序列的 `dropped` 欄：`on_or_after_t`、`weekend`、`low_volume_last_bar_kept`。
  - 寫檔前檢查：至少剩 1 列；第一個日期不晚於舊檔的第一個日期；最後一天不早於舊檔裡早於 t 的最後一天（歷史被截短）。不符合就當這個序列失敗，舊檔留著。
- 重試：只分兩類，不看錯誤訊息的文字。
  - `YFRateLimitError`：等 15、30、60 秒。連續 2 個序列因為限流放棄，就停掉剩下的。
  - 其他所有例外：等 5、10、20 秒。
  - 最多 3 次（`yfinance.max_retries`），每次重試前 `cache_clear()`。
- 欄位：`date, open, high, low, close, adj_close, volume`，和舊分支 `data/extra/yfinance/` 一樣。

### 最後一根K棒的檢查

計畫第一版用「每個市場各自的前一個交易日」加各國假日清單。審查發現兩個問題：假日清單要人維護；漏掉一天時，9 個美國序列各等 2 分鐘，會把後面正常的序列擠掉。第二版改成（使用者 2026-11-05 同意）：

1. 每個序列都抓完後，檢查每個序列有沒有日期 = i 的K棒。i 和 Live 檢查用的是同一天，也是 `features.py` 實際會用的那根。
2. TSM、NVDA、四檔台灣 ETF 的那根另外要成交量 > 0。
3. 沒過的序列合起來，等 60 秒、`cache_clear()` 後各重抓一次。
4. 還是沒過就列在 `run.no_bar_i`、那個序列記 `has_bar_i: false`（可能是那個市場放假），流程繼續，這個特徵當天空白。使用者 2026-11-06 決定這不算失敗，不回傳 3。

### manifest

`data/raw/manifest.json`，每完成一項就整份重寫（先寫暫存檔再換名）。只記最近一次，舊的看 Git 歷史；資料被修正了什麼用 `git diff data/raw/` 看。

```json
{
  "run": {"started_at": "2026-11-17T07:10:02+08:00", "target_date": "2026-11-17", "mode": "daily",
          "status": "ok", "prev_day": "2026-11-16", "no_bar_i": [], "finished_at": "…",
          "yahoo_requests": 45, "yahoo_redirects": 0, "site_requests": 5},
  "teacher": {"status": "ok", "action": "skipped_unchanged", "zip_sha256": "7433b271…", "files_sha256": "…"},
  "phase2_days": {"status": "ok", "file": "phase2_days.json", "days": 30},
  "teacher_live": {"status": "ok", "source": "fin-pred-daily.jiangxuehaokeai.chatgpt.site/data.zip",
                   "attempts": 1, "error": null, "zip_sha256": "…", "files_sha256": "…", "date_max": "2026-11-17",
                   "has_t_row": true, "prev_day": "2026-11-16", "prev_day_planned": "2026-11-16",
                   "prev_day_never_filled": false},
  "yfinance": {
    "sox": {"ticker": "^SOX", "status": "ok", "file": "yfinance/sox.csv", "attempts": 1, "error": null,
            "dropped": {"on_or_after_t": 0, "weekend": 0, "low_volume_last_bar_kept": false},
            "rows": 1730, "date_max": "2026-11-16", "sha256": "…", "has_bar_i": true},
    "wti": {"ticker": "CL=F", "status": "failed", "file": "yfinance/wti.csv", "attempts": 4,
            "error": "JSONDecodeError", "kept_previous_file": true, "rows": 1729, "date_max": "2026-11-13",
            "sha256": "…", "end": "2026-11-16T17:30:00-05:00", "has_bar_i": true},
    "usd_twd_1h": {"ticker": "TWD=X", "interval": "1h", "file": "yfinance/usd_twd_1h.csv", "attempts": 1,
                   "error": null, "status": "ok", "fetched_rows": 170, "start": "2026-11-09", "rows": 16900,
                   "first": "2024-01-22T05:00:00+08:00", "last": "2026-11-17T05:00:00+08:00", "sha256": "…",
                   "has_value_t": true}
  }
}
```

- 序列的 `status`：`ok`、`failed`（沒抓到，舊檔留著）。有沒有 i 那根另外記在 `has_bar_i`，1h 記 `has_value_t`（2026-11-09 起要比 i 的 06:00 新才算有）。
- `exchange`：`exchange.enabled` 打開才有，欄位見「每天的步驟」。
- `run.status`：序列都 `ok`、沒有改用快取的 phase2Days、沒有 `prev_day_never_filled` 是 `ok`，否則 `stale`（回傳 3）；丟出例外時是 `failed`，`error` 是自己寫的短訊息或例外類別名稱。
- 失敗時 `teacher` 那筆照抄上一次的，下次還認得本機的 Training，不用重新下載。指紋不算點開頭的檔（`.DS_Store`）。
- sha256 用檔案原始位元組算。`.gitattributes` 的 `data/raw/** -text`、`tests/fixtures/** -text` 讓 Git 不改換行。
- 2026-11-06 從 data-collection 搬來 `data/raw/teacher/` 後，`manifest.json` 還不存在，所以第一次會下載 Training 一次再整包換進去，內容一樣，`git diff data/raw/teacher/training` 應該是空的。新算法的 `files_sha256`：Training `1c17e27f…`、Live `4675ae4d…`。舊分支的 `members_sha256`（`31bbdc99…`）算法不同（路徑帶 `data/`、先把 CRLF 換成 LF），不能互相比。
- 不記：金鑰、帳密、cookie、crumb、網址的 `?` 後面、伺服器回應的內容。錯誤只記例外類別和自己寫的短訊息。

### 失敗時

- `main(argv)` 回傳 0（全部 ok）或 3（有序列不是 ok），不在裡面呼叫 `sys.exit`。只有 `if __name__ == "__main__": sys.exit(main())` 轉成結束碼。
- 不能繼續的錯誤直接丟例外：Training 沒有可用的檔、Live 拿不到或沒更新到 t、每日模式讀不到 `/api/state`、還沒到爬蟲開始時間。
- `run_daily.py` 收到例外就停（舊檔都留著）；收到 3 就記一行 log，繼續下一步。其他步驟的 `main` 也照這個做。

### config.yaml 要改的

- `course_site.live_zip_url` 換成 `course_site.live: {base_url, login: /login, zip: /data.zip}`。
- `yfinance` 加上：隨機秒數、兩種重試的等待秒數、熔斷門檻、重檢的等待秒數、要查成交量的代號清單。
- 新增爬蟲開始時間（07:00）和爬蟲截止（08:30）。鍵名實作時再定。

### 測試（全部離線）

`tests/test_crawler.py`，用假的 `PacedSession._send`、假的 requests.Session、假的時鐘、測試裡現做的小 ZIP。`no_network` 把 curl_cffi 的 `_request_once` 和 requests 的 `send` 換成丟錯，防止不小心連網；每個測試前後重設 yfinance 的 `YfData` 單例，結果不看順序：

- 限流：連續請求間隔 ≥ 2 秒，從上一個結束算起；cookie、crumb 請求也算；302 再 200 的兩次請求也隔 ≥ 2 秒。
- 429：出在 chart 時退避而且 yfinance 不會再送一次；出在 getcrumb 時 chart 照送、也有限流。
- `YFPricesMissingError` 會重試到 `max_retries` 次（也固定住 `hide_exceptions=False`）。限流連續 2 個序列就熔斷，第三個不送。
- SiteClient：POST 不重試、GET 遇到 5xx 重試、轉到別的主機不跟、`allow_redirects` 一律 False、超過大小上限丟錯。
- 截止：08:28 Live 還沒有 t 那列時不再等；08:31 yfinance 全部跳過、舊檔不動；08:29:50 失敗時不重試；重抓 i 那根時過了截止就停。
- `cache_clear()`：固定用過去的日期（t = 2026-11-04）和台股代號，第一次 chart 回 500，重試時要看到新的 chart 請求；反向對照是不清快取時請求數是 0。
- `YfData` 用的是我們的 `PacedSession`。
- 日期：日期 ≥ t 的K棒、週末日期的K棒會被丟掉；期貨的 `end` 算對（含週一的 t）；假 chart JSON 最後時間戳是 i 的 18:10 ET（期貨盤中）時，那一列進不來，i 那根結算K棒還在。
- 空的或變短的回應：舊檔位元組不變，manifest 是 `failed`。
- i 那根的檢查：^SOX 成交量 0 要通過、NVDA 成交量 0 要不通過、沒有 i 那根的序列只重抓一輪。
- ZIP：多一個成員、少一個成員、名稱重複、表頭不對、Live 有 `info.json`、超過大小，都要拒絕；拿掉 `data/` 前綴；換行 CRLF 原樣保留。
- 解壓失敗時，舊的 `teacher/live/` 位元組不變。
- Training 指紋一樣時不下載 Training ZIP。
- Live 沒有 t 的列時會重抓再丟錯誤；`COURSE_LIVE_KEY` 空的時，每日模式丟錯誤、研究模式跳過。
- 每日模式在 07:00 前執行會丟錯誤。
- Training 的真 `-1` 和空格，解壓後位元組不變。
- 帳密：假伺服器回傳含密碼的錯誤，密碼不能出現在 manifest、log 或例外訊息裡。
- `main()` 回傳 0 或 3，不會丟 `SystemExit`。

### 第一次實際跑要確認的事

- 台北 07:10～13:00 之間跑一次（`submit.enabled` 還是 false），確認 wti、gold 有 i 那根，`dropped.low_volume_last_bar_kept` 有沒有動作。
- `/api/state` 的 `phase2Days` 裡，過去的日子 `enabled` 是多少；10-23 在不在裡面。
- 轉址實際有沒有發生（manifest 的 `run.yahoo_redirects`）。
- 2026-11-06 data-collection 交接加的：
  - `run.yahoo_requests`：沒有快取時約 40，有快取約 20（加 1h 會多一兩個）。78 代表 cookie 沒存起來。
  - TWD=X：07:10 存一份 1d 和最近 5 天的 1h，10:00 左右和隔天早上各再抓一次，看 i 那根的 close 三次是否相同、是否等於倫敦 i 日 00:00 那一小時的 close。
  - `usd_twd_am` 補值用的日K：2024 年以後冬令、夏令各挑一天，把日K close 和台北 07:00、08:00 開始的 1h 比，確認它是哪一刻的報價（2026-11-06 加）。
  - 冬令週一 05:00（台北）那根 1h 是不是真的不存在（2026-11-06 加）。
  - 07:10 時 Live t 那列的 `^VIX` 是不是 `-1`。
  - `git diff data/raw/teacher/training` 要是空的；`data/raw/teacher/live` 只多新的列。
  - 跑完做 `features.py` 的對照測試 (b)（見 `memory/projects/features.md`）。
  - 1h 第一次用 `period="730d"`、`prepost=True` 抓（`prepost=True` 還沒對真的 Yahoo 試過）：第一根約在 2024-01，平日一天約 24 根，`has_value_t` 是 true（2026-11-06 加）。
  - 跑完 features 後，`data/processed/manifest.json` 的 `warnings` 要是空的，才 commit `data/processed/`（2026-11-06 加）。
  - 2026-11-06 第一次連網發現：Yahoo 的最後一根成交量之後還會改（凍結檔 11/04 那根：tsm_adr +0.51%、nvda +0.47%、wti +20.7%、gold +42.7%），而且期貨最後一根的成交量會先填成前一根的值（wti、gold 11/04 和 11/05 一樣），所以 `low_volume_last_bar_kept` 這道防線實際上不會觸發。成交量只有 R3 用到（6 個個股和 ETF），不影響特徵。
  - 期交所 t 的夜盤幾點出現在網站上（組員說 06:00 抓得到）；07:10 那次的 `taifex.has_night_t`、`rechecked`（2026-11-06 加）。

### data-collection 交接：要調整的地方（2026-11-06 都做完了）

使用者 2026-11-06 的決定：第 1 點登入暫時性錯誤重試 2 次，`/api/state` 讀不到改用快取（要有 t）；第 5 點沒有 i 那根不算失敗，另記 `run.no_bar_i`；其他照建議做；`crawler.py` 維持一個檔，不拆。
截止的做法：過了 08:30 不直接放棄，每一步只試一次、不等待不重試（課程網站、Live、登入的重試都看 `run.can_wait`），每個請求最多 `course_site.total_timeout_seconds`（120）秒。還有 30 分鐘可以交，放棄只會確定漏交。

原本的清單：

1. 課程網站登入的 POST 只送一次，逾時或 5xx 整次就停。每日模式讀不到 `/api/state` 也停。登入不是上傳，可以考慮暫時性錯誤重試 2 次，但和「POST 失敗不自動重試」有關，由使用者決定。`/api/state` 失敗時可以改用快取的 `data/raw/phase2_days.json`（裡面要有 t）。
2. 截止（08:30）在登入、`/api/state`、Training、Live 第一次嘗試之前都沒檢查。串流下載的 (10, 90) 秒逾時只限制兩塊資料之間的等待，整個下載沒有總時間上限。yfinance 開始前最壞約 38 分鐘（推論）。建議每一步之前檢查截止，每個請求加總時間上限。
3. 08:30 以後才開始跑時，19 個序列都標 `skipped_deadline`、留舊檔，檢查 i 那根只看 status 是 ok 的序列。所以 `features.py` 一定要找日期剛好是 i 的那一列。爬蟲建議每個序列都記 `has_bar_i`。
4. Yahoo cookie 的 bug：`.cache/yfinance/cookies.db` 裡的 cookie 沒有 A3 時，yfinance 1.7.0 `data.py:211` 丟 `KeyError`，不算暫時性錯誤，19 個序列全部失敗（約 11 分鐘），之後每次都壞，直到有人刪掉快取。已重現。修法：包住 `YfData._load_cookie_curlCffi`，遇到 `KeyError` 回傳 False，加離線測試。
5. 1,660 天裡有 282 天（17.0%）至少一個序列沒有 i 那根，多半是外國放假。現在每次都等 60 秒重抓、標 `stale`、回傳 3。最近會遇到 t = 2026-11-24 缺 N225、t = 2026-11-27 缺 9 個美國相關序列。建議只有 `no_bar_i` 時不設 `stale`，另記 `run.no_bar_i`，回傳 3 留給真的失敗。由使用者決定。
6. `run.http_requests` 只算 Yahoo。建議改名 `yahoo_requests`，另加 `site_requests`。
7. 過時的註解（`config.yaml` 的期貨防線、`lags`）2026-11-06 已改。

寫 `features.py` 時多出來、也要放進第 4 步計畫的事（2026-11-06）：
- 交易日規則已經寫成 `crawler.trading_days()`（和 `row_filled()`），`features.py` 在用。`live_check` 還是舊的「`phase2Days` 早於 t 的最後一天」，要改成呼叫 `trading_days()`，並讀 `crawler.closed_days`。
- 匯率 1h：每次抓 TWD=X 的 1h，和舊的 `data/raw/yfinance/usd_twd_1h.csv` 合併（Yahoo 只給大約兩年多，不能整個蓋掉），只留結束時間早於爬蟲開始時間的K棒。欄位照 `features.HOURLY_COLUMNS`。

### 爬蟲要跑多久（data-collection 2026-11-06 量的）

- 時間花在限流：沒有快取 40 個請求，等約 92～97 秒；保留 `.cache/yfinance` 時 20 個請求，約 48 秒。
- 只抓一小段日期省不了時間：完整歷史 165 KB 0.71 秒，兩週 2.4 KB 0.33 秒，19 個代號只省約 7 秒。
- 正常一次 1～2 分鐘。Live 晚兩次多 6 分鐘。Yahoo 那段最壞被 08:30 擋下，約 08:33 結束（模擬）。
- 真正會遲交的是觸發時間（GitHub Actions 11/04 晚 3 小時 42 分到 6 小時 17 分），以及第 1、2 點的單點失敗。

- 2026-11-05：最後一根K棒的檢查改成「有沒有 i 那根」，取代「每個市場的前一個交易日加假日清單」。這和舊分支 `data/transform/`、`panel_lag.csv.gz` 的算法一樣（用 i 那根，沒有就空白）。
- 2026-11-05：使用者同意照這個計畫開始寫程式和離線測試。第一次連網試跑前要先問。
