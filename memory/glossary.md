# 名詞

## 比賽

- 預測日 t：這次要交預測的台股交易日。檔名 `submission_YYYY-MM-DD.csv` 的日期就是 t。
- y：t 當天 `adj_close > adj_open` 為 1，否則為 0。`adj_close`、`adj_open` 是調整過除權息的收盤價和開盤價，老師資料裡的欄名是 `etl:adj_close`、`etl:adj_open`。
- 官方分數：每一格（一檔股票的一天）算 (2 × 預測 − 1) × 盤中報酬（`adj_close / adj_open − 1`），再全部取平均。預測 1 拿到當天的報酬，預測 0 拿到報酬的相反數。猜對方向就加分，猜錯就扣分，漲跌越大加減越多。
- Phase 1：6/1～9/30 共 84 天的固定回測，一次交完。11/04 已交。
- Phase 2：每個交易日 09:00 前交當天 50 檔的預測。這個分支只處理 Phase 2。
- 範本：課程網站每天給的空白提交檔，定出 50 檔股票的順序。
- `Top50@Y`：`info.json` 裡要預測的 50 檔（老師資料共 100 檔，`Top100@Y`）。每天實際交哪幾檔、照什麼順序，以範本為準。

## 老師資料

- 老師資料：課程提供的資料，分 Training 和 Live 兩份。
- Training ZIP：從課程網站下載，2020-01-02～2026-08-31 的歷史資料。100 檔股票各一個 CSV、一張 global 表、一個 `info.json`。之後不會再變。
- Live ZIP：從 2026-09-01 開始，放在另一台伺服器，一天更新不只一次。沒有 `info.json`。
- 待定列：Live 裡值先填 `-1` 的列。t 當天早上的 Live 已經有 t 的一列，但還沒收盤，所以是 `-1`。
- global 表：一天一列的市場數字，例如 `^TWII`（台灣加權指數）、`^KS11`（韓國綜合指數）、`TX_OI`（台指期外資淨未平倉口數，多減空，可以是負的）、`^VIX`、`^IXIC`、`^GSPC`。

## 特徵

- lag k：t 那列放的是「到 t 的前一個台股交易日 i 為止、往回 k 個交易日」的報酬，`(close_i − close_(i−k)) / close_(i−k)`。只用 lag1、lag2（使用者和組員 2026-11-06 決定）。`ret_lag1` 是 i 那天的單日報酬；`ret_lag2` 是 i 往回 2 個交易日的累積報酬，涵蓋 i−1 和 i 這兩天的漲跌（2026-11-06 定案）。
- i：t 的前一個台股交易日。t 的特徵最晚只用到 i 收盤。
- 額外指標：老師資料以外，用 yfinance 抓的 19 個序列（清單在 `configs/config.yaml` 的 `yfinance.tickers`）。

## 程式

- manifest：下載紀錄 `data/raw/manifest.json`，記每個檔案的下載時間、sha256（由內容算出的指紋，內容一變就不同）和成功或失敗。
- 骨架：每個檔案的用途、輸入、輸出和函式介面都寫好了，函式本體是 `raise NotImplementedError`。
- 舊系統：Phase 1 用的那套程式，現在封存在 `claude/data-collection` 分支的 `archive/`。
