# 合併的原始資料（data/merged/）

`data/merged/` 的三個檔、每個來源預測 t 時能用到哪一列、哪些地方原樣保留、什麼時候更新。怎麼讀檔見 `README.md` 的「組員怎麼拿資料」。

每一格都是來源 CSV 的原字串，沒有清理，也沒有對齊到預測日 t：d 那列放的是各來源標 d 的值，當 t 的特徵前要自己往前接。

## 三個檔

- `stock/YYYY-MM.csv.gz`：個股表，一個月一檔，一列是「一天 × 一檔」。鍵是 `date`、`stock_id`（字串）、`is_top50`（1 是比賽的 50 檔）。接著是老師個股表 20 欄，欄名照原樣（例如 `etl:adj_close`），Training 全部，接 Live 2026-09-01 起的列。最後是證交所、櫃買四個檔，欄名加前綴：`twse_valuation_`、`twse_quotes_`、`tpex_valuation_`、`tpex_quotes_`（例如 `twse_quotes_收盤價`）。
- `market.csv.gz`：市場表，一列是一天。`date` 是所有來源日期的聯集，某個來源那天沒有列時那幾欄空白。老師 global 6 欄加 `teacher_` 前綴（例如 `teacher_^GSPC`）；yfinance 21 個序列各 6 欄（`sox_open`、`sox_high`、`sox_low`、`sox_close`、`sox_adj_close`、`sox_volume`），序列名稱和代號見 `memory/reference/feature-table.md`；台指期日盤、夜盤各 17 欄（`tx_day_收盤價`、`tx_night_未沖銷契約數` 這類）；`vixtwn`、`vixtwn_1min_avg`；`fear_greed_score`。
- `manifest.json`：個股表有哪些月份、兩張表的欄名和列數、每個來源的最後一天、來源檔的指紋。

## 預測 t 時每個來源能用到哪一列

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
| `fear_greed_score` | 美國日期 d 的分數 | 最後一天的分數之後還會變 | 用特徵表的 `fear_greed_lag1`，原因見 `memory/reference/feature-table.md` 的註 6 |

## 往前接的時候要注意

- `asof`（README 的範例函式）會往前找：美國放假時接到的是更早那場。特徵表的做法是留空白。
- 老師個股欄 d 那列是 d 當天的值，要照 `stock_id` 往後移一列。`y` 是 d 的答案，不能當特徵。
- `y` 是 `-1` 的列還沒有資料，整列都是 `-1`（每天早上的 t、2026-10-23 颱風假）。往後移之前先把這些列的 `-1` 換成空白，不然 10/24 那列會接到 `-1`。
- 驗證按日期切，同一天的 100 檔要在同一邊。

## 原樣保留的地方

- `-1`：老師 Live 待定列整列是 `-1`，代表還沒有資料。Training 法人欄有 83 格是真的 `-1`（剛好買賣超 1 股），不能一律換成空白。
- yfinance：沒有清理，0052 分割前的價格沒除。`adj_close` 每天會因為 Yahoo 重新套除息有約百萬分之一的浮動，所以 `market.csv.gz` 幾乎每天都會換。要乾淨的報酬用特徵表。
- 交易所：價格是原始價，沒有還原除權息，不要和老師的還原價混用。`-`、`--`、`----`、`N/A` 這類記號原樣留著，有這些記號的欄讀進來是字串。成交股數和老師的 `price:成交股數` 不一定一樣。
- 停牌日：老師的表跳過了 21 個停牌的股票日，交易所那天有列，所以這些列只有交易所欄。
- 台指期：每個日期、時段只留近月合約（到期月最早、有成交的那張），和特徵表選的一樣。`tx_day_到期月份(週別)` 寫是哪一張，結算日那天還是要到期的那張。夜盤的 `tx_night_結算價`、`tx_night_未沖銷契約數` 期交所不公布，每列都是 `-`。
- 沒併進來的：`yfinance/usd_twd_1h.csv`（1 小時K棒，和日表對不上）、`open_today/`（當天開盤，隔天 yfinance 的日K就有）、`data/raw/` 的 json 紀錄檔。

## 更新

排程每次上傳完、推資料之前跑 `python -m src.merge_raw`：來源檔的指紋沒變就跳過；有變就重算全部，只寫內容不一樣的檔，所以通常只動最後一個月和 `market.csv.gz`。休市日不跑，失敗只寫警告，不影響上傳。07:10 那次跑完約 07:30 推上來，那時 t 那列的老師個股欄還是 `-1`。

```bash
python -m src.merge_raw              # 來源有變才重算
python -m src.merge_raw --rebuild    # 不看指紋，全部重算
```
