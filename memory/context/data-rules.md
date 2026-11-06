# 資料規則

寫 `crawler.py`、`features.py` 之前先讀這份。老師 ZIP 的結構和各序列的收盤時間見 `memory/projects/crawler.md`。

## 不能用未來資料

- 預測日 t 的特徵只能用 t 之前就知道的資料。t 當天的價格、成交量、法人、技術指標和 y 都不能用。
- 老師 global 表的 `^TWII`、`^KS11` 是當天收盤；`TX_OI` 疑似含收盤後才公布的資訊。這三欄只能用日期早於 t 的最後一列。
- global 表的 `^VIX`、`^IXIC`、`^GSPC`：Training 每一列放的是前一個 global 列日期的美股收盤；Live 每一列放的是日期早於該列的最後一個美股收盤。這三欄在 t 那列已經是開盤前就知道的值。
- 證據：`../ml-final-archive/memory/context/data-decisions.md` 的「時間對齊驗證」，用 Yahoo 原始資料逐值比對過。

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
- 交易日曆（使用者 2026-11-06 決定，取代「以 `phase2Days` 為準」）：老師 100 檔裡至少 `crawler.min_stocks_filled`（90）檔填好（`y` 是 0 或 1，還原開盤、收盤價 > 0）的日子才算交易日。i 是 t 之前最後一個這樣的日子；還是 `-1` 的列（10/23、當天早上 t 那列）不算，那天 global 的列也不用。`phase2Days` 只用來決定 t。config 的 `closed_days` 列 10/23，那天之後出現數值就停下。爬蟲和 `features.py` 呼叫同一個函式。細節見 `memory/projects/features.md`。global 表缺很多台股日（Training 少 112 天），不能當日曆。

## 驗證按日期切

先取出不重複的日期，對日期清單切分，再把列對回去。同一天 50 檔股票共用市場特徵，隨機拆列會偷看到答案。

## yfinance

- 每個請求至少間隔 2 秒，yfinance 自己送的請求（取 cookie、crumb、時區）也算。
- 下載時設 `auto_adjust=False`，才會同時有 `close` 和 `adj_close`。
- `end` 不含那一天，但它只限制請求的範圍。期貨在台北 07:00 後就開始下一個交易日，Yahoo 可能把盤中資料標成前一天。不存到還沒收完的K棒，要靠爬蟲自己丟掉日期 ≥ t 和週末的K棒，再檢查期貨最後一根的成交量（見 `memory/projects/crawler.md`）。
- 前一天的K棒收完時間（台北）：美股約 05:30、期貨 06:00、DXY 07:00、TWD=X 保守估 08:00。TWD=X 日期 d 那根的 close 是台北 d 日 08:00 的報價（2026-11-06 用 1h 資料對過），所以另外用 1h 取台北 t 日 06:00 的匯率（`usd_twd_am`，見 `memory/projects/features.md`）。
- 時區快取放 `configs/config.yaml` 的 `yfinance.cache_dir`（`.cache/yfinance`，不進 Git）。

## 資料放在這個分支

- 使用者 2026-11-05 決定：資料、模型、上傳紀錄都放在這個分支。組員 clone 一次就拿到全部，版本也對得上。`data/` 約 77 MB：`data/raw/` 約 46 MB（Training 解開約 45 MB，Live 每天約多 100 列，yfinance 19 個序列約 3 MB），`data/reference/` 約 31 MB。
- 使用者 2026-11-06 決定：爬資料全部交給這個分支，`claude/data-collection` 不再爬也不再更新，只留著當對照。它的 `data/` 搬到這裡：老師資料放 `data/raw/teacher/`、`data/raw/teacher_live/`（和 Training ZIP `7433b271…`、Live ZIP `eea89fce…` 逐位元組相同），其他放 `data/reference/data-collection/`。搬法和 tree hash 見 `memory/projects/features.md` 的「資料來源」。
- `data/reference/` 是凍結的快照：只給對照測試讀，每天的流程不讀，爬蟲不寫，裡面的檔都不要改。`.gitattributes` 設了 `data/reference/** -text`，Git 不改換行。清理過的 yfinance 只能放在這裡，不能放進 `data/raw/yfinance/`（那裡放 Yahoo 原樣，`features.py` 會再清理一次，0052 分割前的價格會被除兩次 7）。
- 原始資料存解開後的 CSV，不存 ZIP。老師的 CSV 每天只多幾列，Git 只記差異；ZIP 每天會整個重存。
- yfinance 的 `adj_close` 每次重抓都可能有約 1e-6 的相對浮動（0052 實測 1.041e-6）。Yahoo 每次抓都把到抓取當下為止的所有除息套到之前每一列，所以整個檔案（和 sha256）都可能變，但不跨除息日的報酬不受影響。檔案小，影響不大。
- `data/processed/` 可以從 `data/raw/` 重算，不進 Git。
- 每個檔案要小於 100 MB（GitHub 的上限）。
- 只有正式的每日流程會 commit 並推送 `data/` 和 `models/`。組員在本機跑只是測試，用 `git restore data models` 還原；推程式前先 `git pull --rebase`。
- 帳號密碼只放 `.env` 或執行環境的 secret，不進 Git，也不印到 log。
