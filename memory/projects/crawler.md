# src/crawler.py

## 狀態

- 2026-11-05：計畫草稿，等使用者確認。確認前不寫程式。
- 查證紀錄（本機，session 結束會消失）：yfinance 1.7.0 原始碼、老師 ZIP 結構、各序列日期、舊爬蟲。結論都整理在下面。

## 查到的事實

### 老師 ZIP

- Training：`7433b271…`，18 MB，解開 46.5 MB。102 個成員：`data/info.json`、`data/global/global_data.csv`、`data/market/<代號>.csv` × 100。從 10/27 到 11/05 抓了 11 次都沒變。
- Live：101 個成員，沒有 `info.json`。每個版本都是 2026-09-01 起的完整歷史，只會往後加列；已經填好的格子從來沒改過。
- 兩個 ZIP 的成員都以 `data/` 開頭，沒有資料夾項目、沒有 `..`、沒有絕對路徑。
- 格式差異：Training 換行是 LF，`y` 是 `0`/`1`；Live 換行是 CRLF，`y` 是 `0.0`/`1.0`，待定格是 `-1`。
- Training 有 83 格真的 `-1.0`，都在法人欄；`6446.csv` 有 2 列法人欄是空的。
- Live 的建檔時間（從 ZIP 內檔案時間推的）：每天約 07:00 一次（t 的列是待定，前一天的列已填好，美股欄已填），約 21:05～22:05 一次（t 的列填好）。00:00～07:00 之間沒有抓過，所以 06:00 抓得到 t 的列嗎還不知道。
- Live 少的平日：09-25、09-28、10-09、10-26。10-23 整列一直是 `-1`。
- Live 主機：最早是 `https://140.112.31.182:8444/`，TLS 驗證失敗（憑證沒有 IP）。舊系統改用 `fin-pred-daily.jiangxuehaokeai.chatgpt.site`，一般 TLS 可以過；預設的 Python User-Agent 會被擋（403），要用瀏覽器的 User-Agent。金鑰是課程網站前端公開的那把。

### yfinance 1.7.0 和 curl_cffi 0.16.3

- 所有 HTTP 都經過一個全程式共用的 `YfData`，最後一個傳進去的 session 會蓋掉前面的。`yf.download` 沒傳 session 時會換回沒限流的預設 session，所以不用 `yf.download`。
- curl_cffi 的 `get`、`post` 都會走 `Session.request()`，覆寫它就攔得到 yfinance 的每個請求（cookie、crumb、時區、日K）。libcurl 自動跟隨的轉址算在同一次請求裡。
- `YfData.cache_get` 是 `lru_cache`，連錯誤回應也會快取。重抓前要 `YfData.cache_get.cache_clear()`，不然只是重播舊回應。
- `yf.config.network.retries` 預設是 0。HTTP 狀態 ≥ 400 時 yfinance 會換 cookie 策略再送一次，設定關不掉；在 `request()` 裡遇到 429 就直接丟 `YFRateLimitError` 可以擋住。
- `yf.config.debug.hide_exceptions` 預設是 True，`history()` 出錯會回傳空表；要設成 False 才會丟例外。
- `end` 不含那一天，字串日期當成交易所當地的午夜。日K的索引是交易所當地日期。缺的成交量會被填成 0。
- `yf.set_tz_cache_location(d)` 把三個 sqlite 快取（時區、cookie、ISIN）都放到 d，要在第一次呼叫 yfinance 前設。
- curl_cffi 的 `Session` 預設 `impersonate=None`，要自己設成 `"chrome"`。

### 19 個序列的日期和成交量

- 成交量全是 0：`^SOX`、`DX-Y.NYB`、`^TNX`、`^IRX`、`TWD=X`。所以「美股最後一根要有成交量」只能用在 `TSM`、`NVDA`、`^DJI`，台灣 ETF 也可以用。
- 以 t = 11/17（二）、i = 11/16（一）為例，各類 11/16 那根K棒收完的時間（台北）：美股 05:30、殖利率 04:20、期貨 06:00、DXY 07:00、TWD=X 保守 08:00、亞洲 16:30 前、歐洲 01:00。
- 07:00 之後，期貨會出現日期是 t 的K棒（前一晚 18:00 ET 開盤）；08:00 之後 DXY、TWD=X、N225 也會有。這些都要丟掉。
- 2020-02～2026-09，四個美股序列晚於「前一個平日」的 240 次全部同時發生（假日），沒有單一序列落後的情況。

## 計畫

### 什麼時候跑

台北 07:10 之後。Live 約 07:00 建檔，DXY 也是 07:00 收完。TWD=X 的 i 那根要到 08:00 才算收完，先照常用，再比對隔天重抓的值，看差多少。

### 老師資料

1. Training：`data/raw/teacher/` 的檔案指紋和 manifest 一樣就跳過，不連網。不一樣或沒有，才登入課程網站下載。
2. Live：每次都下載。主機和金鑰等使用者決定，設定放 `config.yaml` 的 `course_site.live`，金鑰放 `.env` 的 `COURSE_LIVE_KEY`。
3. 檢查 ZIP（兩個都做）：
   - 大小上限：壓縮 100 MB、解開 512 MB、最多 1000 個成員。
   - 每個成員都要以 `data/` 開頭；不能有絕對路徑、`..`、反斜線、資料夾項目、symlink、加密。CRC 要通過。
   - 成員清單要剛好對：Training 是 `info.json`＋global＋100 檔；Live 一樣但沒有 `info.json`。
   - 每個 CSV 的表頭要和預期的一模一樣；日期是 `YYYY-MM-DD`、排好、不重複。
   - Live 的股票代號要和 Training 的 `Top100@Y` 一樣。
4. 解壓：只拿掉開頭的 `data/`，位元組原樣寫出（Live 的 CRLF 也保留）。先寫到暫存資料夾，全部成功才換掉舊的，所以失敗時舊資料還在。
5. Live 有沒有更新到 t（只在指定 t 時檢查）：
   - Live 要有 t 的列（待定）。
   - i 那列要已經填好。i 取 `phase2Days` 裡早於 t 的最後一天；`phase2Days` 沒涵蓋到時，取 Live 裡早於 t 的最後一天。
   - 不符合就等 3 分鐘重抓，最多 3 次，還是不行就停下（不能預測）。
   - 已填好的列和上一版比，有變就在 log 警告，不擋。
6. `-1` 不處理，原樣保存。manifest 記下哪些日期是整列待定（例如 10-23、t）。

### yfinance 的限流

- `PacedSession`：繼承 curl_cffi 的 `Session`，覆寫 `request()`。
  - 上一個請求結束後至少等 2 秒，再加 0～1 秒隨機。
  - `impersonate="chrome"`、`retry=0`、`max_redirects=5`。
  - 回應是 429 就丟 `YFRateLimitError`。
  - 只記方法、網址（拿掉 `?` 後面）、狀態碼、時間。
- 開始前：`yf.set_tz_cache_location(".cache/yfinance")`、`yf.config.network.retries = 0`、`yf.config.debug.hide_exceptions = False`、`YfData(session=paced)`。
- 每個序列：`cache_clear()` 後用 `yf.Ticker(代號, session=paced).history(start=2020-01-01, end=t, interval="1d", auto_adjust=False, actions=False, repair=False)`。每天重抓完整歷史，因為除息後 `adj_close` 會整欄重算。
- 只留日期 < t 的K棒，丟掉的根數記在 manifest。
- 重試：最多 3 次（`yfinance.max_retries`）。暫時性錯誤等 5、10、20 秒；429 等 15、30、60 秒；查無代碼不重試。
- 熔斷：連續 2 個序列被限流就停，剩下的沿用舊檔。整個 yfinance 階段最多 15 分鐘。

### 最後一根K棒的檢查

E 是 t 之前的最後一個平日。檢查不過就 `cache_clear()` 等 60 秒重抓，最多 2 次；還是不過就標 `stale`，沿用這次抓到的資料，流程繼續。

| 類型 | 序列 | 最後一根要是 | 成交量 |
|---|---|---|---|
| 美股 | TSM、NVDA、^DJI | E | 要 > 0 |
| 美股指數 | ^SOX | E | 不查 |
| 殖利率 | ^TNX、^IRX | E | 不查 |
| 期貨 | CL=F、GC=F | E | 只警告 |
| 美元 | DX-Y.NYB、TWD=X | E | 不查 |
| 台灣 ETF | 0050、0052、0055、006201 | i | 要 > 0 |
| 亞洲、歐洲 | N225、HSI、SSE、STOXX50E、GDAXI | E | 只警告 |

- 假日：最後一根比 E 舊，但 E 在 `config.yaml` 的假日清單裡，算通過並記下。
- 美股四個序列同時落後、而且落後不超過 4 天，也當假日，只警告。
- 假日清單要使用者確認。

### manifest

`data/raw/manifest.json`，每完成一項就整份重寫（先寫暫存檔再換名）。只記最近一次；舊的看 Git 歷史。

```json
{
  "run": {"started_at": "2026-11-17T07:10:02+08:00", "finished_at": "...", "target_date": "2026-11-17",
          "status": "ok", "yfinance_version": "1.7.0", "http_requests": 41, "slept_seconds": 98.2},
  "teacher": {"status": "ok", "action": "skipped_unchanged", "zip_sha256": "7433b271…",
              "files_sha256": "…", "date_min": "2020-01-02", "date_max": "2026-08-31"},
  "teacher_live": {"status": "ok", "source": "fin-pred-daily.jiangxuehaokeai.chatgpt.site/data.zip",
                   "downloaded_at": "…", "zip_sha256": "…", "files_sha256": "…",
                   "date_min": "2026-09-01", "date_max": "2026-11-17",
                   "pending_dates": ["2026-10-23", "2026-11-17"], "prev_day": "2026-11-16",
                   "prev_day_filled": true, "attempts": 1, "error": null},
  "yfinance": {
    "sox": {"ticker": "^SOX", "status": "ok", "file": "yfinance/sox.csv", "sha256": "…", "rows": 1730,
            "date_min": "2020-01-02", "date_max": "2026-11-16", "dropped_on_or_after_t": 0,
            "last_bar": {"date": "2026-11-16", "close": 7012.3, "volume": 0},
            "expected_last": "2026-11-16", "check": "ok", "attempts": 1,
            "fetched_at": "…", "kept_previous_file": false, "error": null,
            "revision_of_previous_last_bar": {"date": "2026-11-13", "old_close": 6990.1, "new_close": 6990.1}}
  }
}
```

- `status`：`ok`（全部正常）、`stale`（有序列失敗或過期，用舊檔或這次的資料繼續）、`failed`（老師資料有問題，要停）。
- sha256 一律用檔案原始位元組算。加 `.gitattributes` 的 `data/raw/** -text`，Git 不改換行。
- 不記：金鑰、帳密、cookie、crumb、網址的 `?` 後面、伺服器回應的內容。錯誤只記例外類別和自己寫的短訊息。

### 失敗時

| 情況 | 處理 | 結束碼 |
|---|---|---|
| 全部正常 | 寫 manifest | 0 |
| yfinance 有序列失敗或過期 | 舊檔留著，manifest 記下，流程繼續 | 3 |
| Training 本機沒有或指紋不符，下載或檢查又失敗 | 停 | 1 |
| Live 下載、登入、檢查失敗，或重抓 3 次還沒更新到 t | 舊的 `teacher_live/` 留著，停 | 1 |

`run_daily.py` 遇到 3 繼續，遇到 1 停。

### 測試（全部離線）

`tests/test_crawler.py`，用假的 transport、假的時鐘、測試裡現做的小 ZIP，不連網：

- 限流：連續請求的間隔 ≥ 2 秒，從上一個結束算起；yfinance 自己的 cookie、crumb 請求也算進去。
- 重試：429 退避 ×3 而且不會被 yfinance 自己再送一次；查無代碼不重試；每次重試前有 `cache_clear()`。
- `YfData` 用的是我們的 `PacedSession`。
- 日期：日期 ≥ t 的K棒會被丟掉（例如期貨、N225 的 t 那根）。
- 最後一根K棒：照上表逐類測，包括 ^SOX 成交量 0 要通過、NVDA 成交量 0 要不通過、假日清單、四個美股一起落後。
- ZIP：拿掉 `data/`；`..`、絕對路徑、反斜線、資料夾項目、多或少成員、表頭不對、Live 有 `info.json`、超過大小，都要拒絕。
- 解壓失敗時，舊的 `teacher_live/` 一個位元組都沒變。
- Training 指紋一樣時，不發任何網路請求。
- Live 沒更新到 t、i 還是待定時，會重抓再停下；10-23 這種不在 `phase2Days` 的待定列不影響判斷。
- Training 的真 `-1` 和空格，解壓後位元組不變。
- 帳密：故意讓假伺服器回傳含密碼的錯誤，密碼不能出現在 manifest、log 或例外訊息裡。

## 要使用者決定的事

- Live 用哪個主機、金鑰怎麼拿（見 `memory/context/open-questions.md`）。
- 成交量規則改成只查 TSM、NVDA、^DJI 和台灣 ETF。
- 各市場的假日清單（11/26、12/25、1/1 等）。
- 正式流程的爬蟲排在 07:10。
