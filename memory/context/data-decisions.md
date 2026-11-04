# 資料決策紀錄

每條都附理由與證據；改動前先讀，改動後更新本檔與 `schema.json`。

## 範圍與來源
- 日期：**2020-01-01～2026-08-31**（含）。yfinance 的 `end` 不含當天，所以請求送 `2026-09-01`。
- 額外指標**全部**經 yfinance 1.7.0 `Ticker.history(interval='1d', auto_adjust=False, actions=False, repair=False)`。
- 老師 index（`^VIX ^IXIC ^GSPC ^TWII ^KS11`）不重抓，因為老師 global_data 已有。
- 老師資料來自 `origin/live-data` 的 `catalog/latest.json` → catalog → `course-training.latest_sha256` → `objects/<sha>.zip`，每層都核對 sha256，再**逐位元組**解到 `data/teacher/`。schema 另存 `teacher.members_sha256`（所有成員檔 hash 的摘要），`--keep-teacher` 會核對它，不符就拒絕。

## 19 個額外指標
| id | ticker | 類型 | 備註 |
|---|---|---|---|
| sox | ^SOX | index | |
| tsm_adr | TSM | stock | 用 adj_close |
| nvda | NVDA | stock | 2021、2024 分割 Yahoo 已調整 |
| usd_twd | TWD=X | fx | 1 USD 兌 TWD；正報酬＝台幣貶值；約 68% 列 close＝open（close 常是倫敦日第一筆報價） |
| dxy | DX-Y.NYB | fx_index | |
| us10y | ^TNX | yield_percent | 百分比報價 |
| us13w | ^IRX | yield_percent | 2020–2021 近 0、2020-03-19～27 為負 |
| etf_006201 | 006201.TWO | etf | 櫃買代理；Yahoo 沒有櫃買指數（^TWOII／^TWO／^TPEX 皆 404 或查無） |
| etf_0050 | 0050.TW | etf | 2025-06 一拆四 Yahoo 已調整 |
| etf_0052 | 0052.TW | etf | 2025-11 一拆七：11-19～25 停牌、11-26 復牌。Yahoo 只把 **11-17 起**的K棒 ÷7（調整界線），更早的沒調，且分割前股利調整只做約 1/7 → crawler 修正 |
| etf_0055 | 0055.TW | etf | |
| dji、n225、hsi、sse、stoxx50e、gdaxi | ^DJI ^N225 ^HSI 000001.SS ^STOXX50E ^GDAXI | index | STOXX50E 依瑞士假日缺 21 個 Eurex 日 |
| wti、gold | CL=F、GC=F | futures | WTI 2020-04-20 為 −37.63 |

## 限流（使用者明確要求）
- 單執行緒；自訂 `PacedSession`（curl_cffi Session 子類別），yfinance 的**每個** HTTP 請求（時區、cookie、crumb、chart）都經過同一個 `RateLimiter`。libcurl 自動跟隨的重新導向共用該名額，上限 5 次。
- 間隔：上一個請求**結束**後至少 2 秒，再加 0～1 秒隨機抖動。
- 重試：最多 5 次；退避 5 秒起每次加倍，上限 120 秒；被限流（429／`YFRateLimitError`）時退避 ×3。
- 永久錯誤（404、查無代碼、`YFTickerMissingError`）不重試；`YFPricesMissingError`／`YFTzMissingError`（Yahoo 暫時錯誤也會丟）重試 1 次。
- yfinance 內建重試設為 0；每次 fetch 前清掉 `YfData.cache_get` 的 lru_cache，否則重試只會重播快取中的錯誤回應。
- 熔斷：某序列因限流放棄 → 冷卻 120 秒（若已達門檻或是最後一檔則不冷卻）；連續 3 個序列被限流 → 中止，保留舊檔。
- 每完成一檔就寫一次 manifest；失敗或清理後沒資料時，舊檔若仍可解析就沿用（重算 hash），不刪檔。
- 狀態：`complete`＝全部 ok 且本次都更新；`stale`＝全部 ok 但本次有失敗或中止；`partial`＝有序列不可用。
- `--timeout` 只作用在 chart 歷史請求；yfinance 的時區／cookie 請求用它自己的 10／30 秒。

## 清理規則（每筆修改都記在 manifest 的 `cleaning`；被刪列的紀錄是 Yahoo 原始單位）
1. **壞報價**（所有序列）：close 超出 [low, high] 0.5% 以上 → 刪列。實際只有 TWD=X 2 筆（含 2020-12-08 的 28.0）。0.5% 以內的 OHLC 誤差（006201 最多 0.37%）保留。
2. **債市假日平盤K棒**（殖利率）：哥倫布日（10 月第 2 個週一）、退伍軍人節（11/11，週六提前、週日順延）的平盤K棒 → 刪列。^TNX、^IRX 各 11 筆。零利率期間其他平盤K棒是真的沒變動，保留。
3. **佔位／不完整K棒**（股票、ETF）：OHLC 相同，且（成交量 0 並等於前一收盤，或成交量 < 前 21 筆中位數的 1%）→ 刪列。共 25 筆，都在台灣 ETF（含 2024-01-15、2024-11-20、0050 2025-06-11～17、0052 2025-11-19～25）。
4. **漏調分割**（只限台股 .TW／.TWO 的股票、ETF）：前後 close **且** adj_close 比都接近整數 n（2..50，誤差 <3%）→ 之前價格 ÷n、成交量 ×n；反向（後/前≈n）則之前價格 ×n、成交量 ÷n。台股有 10% 漲跌幅，單日 2 倍以上的變動只可能是公司行動；非台股只記為 `suspected_splits_not_applied`，不修改。目前只觸發 0052。
5. **分割前股利**：修正分割時，分割前每個除息日的調整幅度（adj_close/close 比的跳動）× n。0052 的 6 個除息日（例：2022-04-20 的調整幅度從 1.21% 修成 8.46%）。修正後除息日報酬例如 2022-04-20 從 −7.05% 變成 +0.31%、2020-04-22 從 −3.59% 變成 −1.07%。
- 台灣 ETF 缺的台股交易日（含 2021-04-06 四檔都缺）列在 `schema.json → extra.series.<id>.missing_taiwan_trading_days`。

## 時間對齊（market_features.csv）
- 對台股目標日 t：`s = 該序列 session_date <= t − 1 日曆天的最後一筆`（as-of，休市會沿用）。報酬先在完整原生序列算，再對齊。
- 研究假設：美股收盤約台北 04:00–05:00，在 09:00 前；FX／期貨日K可能在台北清晨才收。未驗證歷史發布時間。
- 老師欄的實證（相關係數）：
  - `^GSPC／^IXIC／^VIX`：列 d 的值＝**前一個 global 列日期**的美股收盤（`^GSPC` 對 DJI：前一 global 列 0.87、同日 −0.18）。長假後可能落後多個美股交易日。
  - `^TWII`：列 d＝**d 當日收盤**（對 0050 同日 0.94、前一日 0.08）。
  - `^KS11`：列 d＝**d 當日收盤**（對日經225 同日 0.65、前一日 0.01）。
  - → market_features 改放 `^TWII_prev_row`、`^KS11_prev_row`（最後一個日期 < t 的 global 列）。
  - `TX_OI`：差分對同日／前一日 TWII 報酬相關都弱，無法判定 → timing_unverified。
- global_data 只有「五個老師 Yahoo 序列同日都有資料」才有列（1,506 列，缺 112 個台股日；大致是台／美／韓交集，但例如 2021-04-06 三地都有交易仍缺），缺列不代表休市。

## transform（使用者 2026-11-04 確認的定義；取代先前「位移 k 列的單日報酬」版本）
- `ret_lag{k}(t) = (close_i − close_{i−k}) / close_{i−k}`，k＝2、5（k 個交易日的累積報酬）。
- **i＝t 的前一個台股交易日**，所以只用 t 開盤前已知的收盤；該序列在 i 那天沒有資料 → 空白。
- **i−k＝同一序列往回第 k 個自己的交易日**（不是台股列）。老師 global 指數＝往回 k 個 global 列；老師個股＝該股往回 k 列。
- 例：SOX close 01-16=100、01-17=102、01-21=99（01-20 美股休市）。列 01-22 用 i＝01-21 → lag2＝99/100−1＝−1.00%；列 01-21 用 i＝01-20 → 空白。
- 每個 CSV 兩欄：`date` 與 `<id>_ret_lag{k}`（只有一個特徵欄）；1,618 列。
- 範圍：19 個額外指標＋老師 5 指數（`teacher_*`，不含 TX_OI）＋老師 100 股（`stock_<代號>`，用 `etl:adj_close`）＝124 個特徵 × 2 個資料夾。
- 價格：股票／ETF 用 adj_close，其他用 close。殖利率也用百分比報酬（使用者選擇）；us13w 在 2020-03 與 2021-02～2022-02 會有 ±100% 以上的值。
- 空白：i 那天沒資料、往回不足 k 個交易日、或 close_i／close_{i−k} 缺值或 <= 0（只看這兩個端點）。
- teacher_* 只在 i 是 global 日期時有值：lag2 1,503 列、lag5 1,500 列非空白。
- 老師美股欄已被老師位移一次，所以 `teacher_vix／ixic／gspc` 的值實際比名稱更舊一天。

## 其他格式決定
- CSV 浮點數用完整精度（`repr`）；空白＝缺值。
- sha256 以 LF 行尾計算；`.gitattributes` 對 `data/**`、`schema.json`、`.agents/skills/**` 設 `-text`，避免 Windows 換行轉換造成 hash 不符。
- 輸出檔權限 0644。
- 重抓時 Yahoo 的 adj_close 會有 <1e-6 的相對浮動（股利調整重算），其他欄完全相同。
