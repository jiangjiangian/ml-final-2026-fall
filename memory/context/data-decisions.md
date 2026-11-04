# 資料決策紀錄

每條都附理由與證據；改動前先讀，改動後更新本檔與 `schema.json`。

## 範圍與來源
- 日期：**2020-01-01～2026-08-31**（含）。yfinance 的 `end` 不含當天，所以請求送 `2026-09-01`。
- 額外指標**全部**經 yfinance 1.7.0 `Ticker.history(interval='1d', auto_adjust=False, actions=False, repair=False)`。
- 老師 index（`^VIX ^IXIC ^GSPC ^TWII ^KS11`）不重抓，因為老師 global_data 已有。
- 老師資料來自 `origin/live-data` 的 `catalog/latest.json` → catalog → `course-training.latest_sha256` → `objects/<sha>.zip`，每層都核對 sha256，再**逐位元組**解到 `data/teacher/`。

## 19 個額外指標
| id | ticker | 類型 | 備註 |
|---|---|---|---|
| sox | ^SOX | index | |
| tsm_adr | TSM | stock | 用 adj_close |
| nvda | NVDA | stock | 2021、2024 分割 Yahoo 已調整 |
| usd_twd | TWD=X | fx | 1 USD 兌 TWD；正報酬＝台幣貶值；約 68% 列 close＝open |
| dxy | DX-Y.NYB | fx_index | |
| us10y | ^TNX | yield_percent | 百分比報價 |
| us13w | ^IRX | yield_percent | 2020–2021 近 0、偶有負值 |
| etf_006201 | 006201.TWO | etf | 櫃買代理；Yahoo 沒有櫃買指數（^TWOII／^TWO／^TPEX 皆 404 或查無） |
| etf_0050 | 0050.TW | etf | 2025-06 一拆四 Yahoo 已調整 |
| etf_0052 | 0052.TW | etf | 2025-11-17 一拆七 **Yahoo 漏調，crawler 回補 ×1/7** |
| etf_0055 | 0055.TW | etf | |
| dji、n225、hsi、sse、stoxx50e、gdaxi | ^DJI ^N225 ^HSI 000001.SS ^STOXX50E ^GDAXI | index | STOXX50E 依瑞士假日缺 21 個 Eurex 日 |
| wti、gold | CL=F、GC=F | futures | WTI 2020-04-20 為 −37.63 |

## 限流（使用者明確要求）
- 單執行緒；自訂 `PacedSession`（curl_cffi Session 子類別），yfinance 的**每個** HTTP 請求（時區、cookie、crumb、chart）都經過同一個 `RateLimiter`。
- 間隔：上一個請求**結束**後至少 2 秒，再加 0～1 秒隨機抖動。
- 重試：最多 5 次；退避 5 秒起每次加倍，上限 120 秒；被限流（429／`YFRateLimitError`）時退避 ×3。
- 404／查無代碼／`YFTzMissingError` 等永久錯誤不重試。
- yfinance 內建重試設為 0；每次 fetch 前清掉 `YfData.cache_get` 的 lru_cache，否則重試只會重播快取中的錯誤回應（審查時以 mock 重現過）。
- 熔斷：某序列因限流放棄 → 冷卻 120 秒；連續 3 個序列被限流 → 中止，保留舊檔。
- 每完成一檔就寫一次 manifest；失敗時若舊檔仍可解析就沿用（重算 hash），不會因 manifest 過期而刪檔。

## 清理規則（每筆修改都記在 manifest 的 `cleaning`）
1. **壞報價**：close 超出 [low, high] 0.5% 以上 → 刪列。實際只有 TWD=X 2 筆（2020-12-08 的 28.0 等）。0.5% 以內的 OHLC 誤差（006201 最多 0.37%）保留。
2. **佔位K棒**（只限股票／ETF）：成交量 0、OHLC 相同且等於前一收盤 → 刪列。共 22 筆，都在台灣 ETF（含 2024-01-15 四檔、0050 2025-06-11～17、0052 2025-11-19～25）。殖利率的平K棒在零利率期間多半是真的沒變動，所以不套用。
3. **漏調分割**（只限股票／ETF）：前後 close **且** adj_close 比都接近整數 n（2..50，誤差 <3%）→ 之前價格 ÷n、成交量 ×n。目前只觸發 0052。
- 台灣 ETF 缺的台股交易日（含 2021-04-06 四檔都缺）列在 `schema.json → extra.series.<id>.missing_taiwan_trading_days`。

## 時間對齊（market_features.csv）
- 對台股目標日 t：`s = 該序列 session_date <= t − 1 日曆天的最後一筆`。報酬先在完整原生序列算，再對齊；不先做多市場日期交集。
- 研究假設：美股收盤約台北 04:00–05:00，在 09:00 前；FX／期貨日K可能在台北清晨才收。未驗證歷史發布時間。
- 老師欄的實證（審查 agent 以相關係數驗證）：
  - `^GSPC／^IXIC／^VIX`：列 d 的值＝**前一個 global 列日期**的美股收盤（`^GSPC` 對 DJI 前一 global 列相關 0.94）。長假後可能落後多個美股交易日。
  - `^TWII／^KS11`：列 d＝**d 當日收盤**（`^TWII` 列報酬對 0050 同日報酬相關 0.96、對前一日 0.03）→ market_features 改放 `^TWII_prev_row`、`^KS11_prev_row`。
  - `TX_OI`：差分對同日／前一日 TWII 報酬相關都弱（0.11／−0.24），無法判定 → 標為 timing_unverified。

## transform（使用者確認過的定義）
- `r_i = (close_i − close_{i−1}) / close_{i−1}`，`i`＝日期，`close_{i−1}`＝**同一序列**的前一個交易日。
- r 放在同日期的台股交易日列；序列當天沒資料 → 空白。
- `ret_lag{k}(t)` ＝ 往前第 k 個台股交易日列的 r（lag2、lag5）。例：台股列 01-17、01-20（美股休市）、01-21、01-22 → lag2(01-21)＝r(01-17)，lag2(01-22)＝r(01-20)＝空白。
- 每個 CSV 只放一欄：`date, <id>_ret_lag{k}`；1,618 列。
- 範圍：19 個額外指標＋老師 5 指數（`teacher_*`，不含 TX_OI）＋老師 100 股（`stock_<代號>`，用 `etl:adj_close`）＝124 個特徵 × 2 個資料夾。
- 價格：股票／ETF 用 adj_close，其他用 close。殖利率也用百分比報酬（使用者選擇）。任一價格 <= 0 → 空白。
- 老師美股欄已被老師位移一次，所以 `teacher_gspc_ret_lag2` 實際比名稱更舊一點。

## 其他格式決定
- CSV 浮點數用完整精度（`repr`）；空白＝缺值。
- sha256 以 LF 行尾計算，`.gitattributes` 設 `data/** -text`，避免 Windows 換行轉換造成 hash 不符。
- 輸出檔權限 0644。
- 重抓時 Yahoo 的 adj_close 會有 <1e-6 的相對浮動（股利調整重算），其他欄完全相同。
