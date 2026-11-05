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
- 抓完要檢查：美股序列最後一根K棒的日期是前一個美股交易日，而且有成交量。不符合就重抓。`^SOX` 的成交量在 Yahoo 上全是 0，這條要怎麼套用等使用者決定（見 `memory/projects/crawler.md`）。
- 不要在台北 22:30 之後抓美股做隔天的特徵。那時美股已經開盤，抓到的是還沒收盤的K棒。
- 其他市場（亞洲、歐洲、匯率、期貨、殖利率）的K棒收完時間不同，要分開檢查。

## -1 和交易日曆

- 只有 Live 待定列的 `-1` 代表「還沒有資料」。
- Training 法人欄有 83 格是真的 `-1`（剛好買賣超 1 股），要保留。
- 10/23 那列一直是 `-1`，很可能是休市日。
- 交易日曆：以 `/api/state` 的 `phase2Days` 為準。歷史部分以老師個股檔出現過的日期為準。global 表缺很多台股日（Training 少 112 天），不能當日曆。

## 驗證按日期切

先取出不重複的日期，對日期清單切分，再把列對回去。同一天 50 檔股票共用市場特徵，隨機拆列會偷看到答案。

## yfinance

- 每個請求至少間隔 2 秒，yfinance 自己送的請求（取 cookie、crumb、時區）也算。
- 下載時設 `auto_adjust=False`，才會同時有 `close` 和 `adj_close`。
- `end` 不含那一天，設成台北今天就不會存到今天的K棒。前一天的K棒有沒有收完要看各市場的時間：美股約 05:30、期貨 06:00、DXY 07:00、TWD=X 保守估 08:00（台北時間）。
- 時區快取放 `configs/config.yaml` 的 `yfinance.cache_dir`（`.cache/yfinance`，不進 Git）。

## 資料放在這個分支

- 使用者 2026-11-05 決定：資料、模型、上傳紀錄都放在這個分支。組員 clone 一次就拿到全部，版本也對得上。資料量小：Training 解開約 45 MB，Live 每天約多 100 列，yfinance 19 個序列約 3 MB。
- 原始資料存解開後的 CSV，不存 ZIP。老師的 CSV 每天只多幾列，Git 只記差異；ZIP 每天會整個重存。
- yfinance 的 `adj_close` 每次重抓都可能有小於 1e-6 的浮動，除息後還會整欄重算，所以整個檔案（和 sha256）都可能變。檔案小，影響不大。
- `data/processed/` 可以從 `data/raw/` 重算，不進 Git。
- 每個檔案要小於 100 MB（GitHub 的上限）。
- 只有正式的每日流程會 commit 並推送 `data/` 和 `models/`。組員在本機跑只是測試，用 `git restore data models` 還原；推程式前先 `git pull --rebase`。
- 帳號密碼只放 `.env` 或執行環境的 secret，不進 Git，也不印到 log。
