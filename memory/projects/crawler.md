# src/crawler.py

## 狀態

- 2026-11-05：已實作（commit `f50e5a3`），實作審查（四個角度、28 個成立的發現）修完，離線測試全部通過。第一次連網試跑前要先問使用者，試跑時不上傳。
- 審查裡會改到使用者決定的兩條，使用者 2026-11-05 都回答了：「有 t 那列」「i 那天填好」改成 100 檔裡至少 90 檔（`crawler.min_stocks_filled`）；期貨成交量的防線只記錄不丟。
- 查證紀錄（本機暫存，session 結束會消失）：yfinance 1.7.0 原始碼、老師 ZIP 結構、各序列日期、舊爬蟲、兩輪審查。結論都整理在下面。

## 使用者的決定

- 2026-11-05：Live 用助教的 chatgpt.site 新入口，金鑰由使用者放 `.env` 的 `COURSE_LIVE_KEY`，不自動從課程網站抓。舊程式（`../ml-final-archive/archive/system-completion/ml_financial_prediction/src/finpred/ingestion/course.py`）會從課程網站首頁載入的 JS 找金鑰，這個做法不採用。舊入口 `https://140.112.31.182:8444/` 的 TLS 驗證會失敗，也不用（2026-11-06 改了，見下一條）。
- 2026-11-06：助教說 chatgpt.site 只給自簽憑證有問題的人用，承受不了太多流量，瀏覽器進得去原本網址的話請用原本的。使用者決定：原本的網址優先，失敗再用 chatgpt.site。不關掉憑證檢查，改成只信任它那一張自簽憑證（`configs/live_ca.pem`）。切換條件（使用者 2026-11-06 確認）：原本的網址連不上、憑證不符、逾時、5xx、金鑰被拒或 ZIP 不對時，同一輪馬上改試 chatgpt.site 一次，不等待；只是還沒有 t 那列的話不換，照舊等 3 分鐘再抓原本的。manifest 的 `teacher_live.source` 記用了哪個入口，`fallback_from` 記前面入口的錯誤。程式是 `live_clients`、`live_fetch`。
- 2026-11-06：第一次試跑用使用者在本機建的 `.env`。GitHub Secrets 只有 GitHub 上的流程讀得到。
- 2026-11-05：19 個 yfinance 序列都抓，爬蟲台北 07:10 開始跑。要不要用在模型上，看驗證分數。
- 2026-11-05：輸出和 data-collection 分支（原名 peaceful-babbage）的資料對齊（2026-11-06 起 data-collection 的資料搬到這個分支，見 `memory/context/data-rules.md`）：`data/raw/teacher/training/`、`data/raw/teacher/live/`、`data/raw/yfinance/`（2026-11-06 前叫 `teacher/`、`teacher_live/`）對應舊的 `data/teacher/`、`data/teacher_live/`、`data/extra/yfinance/`，19 個代號、檔名、欄位都一樣。
- 2026-11-05：成交量要 > 0 只檢查個股和 ETF（TSM、NVDA、四檔台灣 ETF），和舊分支清理規則用成交量的範圍一樣。其他序列只查日期。
- 2026-11-05：爬蟲存 Yahoo 給的原樣，清理（壞報價、佔位K棒、0052 分割、殖利率假日K棒）放在 `features.py`，規則照舊分支。
- 2026-11-05：t 當天早上 i 那列還是 `-1`（像 10-23）時，改用早於 t 最後一個填好的交易日當 i，照常預測上傳，manifest 記 `prev_day`（實際用的那天）和 `prev_day_never_filled: true`，通知組員。`features.py` 照同一條規則。
- 2026-11-05：個別股票停牌不擋流程。「有 t 那列」「i 那天填好」看 100 檔裡有沒有 90 檔（`crawler.min_stocks_filled`）做到；停牌那幾檔自己的特徵當天空白（missing value），其他檔和市場特徵照常，和舊分支 panel 的規則一樣。審查發現 Training 有 44 天少 1～2 檔（例如 2327 連停 7～8 天）。
- 2026-11-05：期貨最後一根成交量太小的防線只記錄不丟（`low_volume_last_bar_kept`）。回測時這條會誤丟換月日、量 0 的真結算K棒（黃金 19 天、原油 7 天）。

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
4. yfinance 19 個序列。
5. 檢查每個序列有沒有 i 那根，沒有的一起重抓一次。
6. 寫 manifest。

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

1. 19 個序列都抓完後，檢查每個序列有沒有日期 = i 的K棒。i 和 Live 檢查用的是同一天，也是 `features.py` 實際會用的那根。
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

- 序列的 `status`：`ok`、`failed`（沒抓到，舊檔留著）。有沒有 i 那根另外記在 `has_bar_i`，1h 記 `has_value_t`。
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
