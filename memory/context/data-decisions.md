# 資料決策紀錄

每條都附理由與證據；改動前先讀，改動後更新本檔與 `schema.json`。

## 範圍與來源
- 日期：**2020-01-01～2026-09-30**（含；使用者 2026-11-04 從 8/31 延長）。yfinance 的 `end` 不含當天，所以請求送 `2026-10-01`。
- 額外指標**全部**經 yfinance 1.7.0 `Ticker.history(interval='1d', auto_adjust=False, actions=False, repair=False)`。
- 老師 index（`^VIX ^IXIC ^GSPC ^TWII ^KS11`）不重抓，因為老師 global_data 已有。
- 老師資料來自 `origin/live-data`（2026-11-05 起也封存在 `archive/live-data/`）的 `catalog/latest.json` → catalog → `course-training.latest_sha256` → `objects/<sha>.zip`，每層都核對 sha256，再**逐位元組**解到 `data/teacher/`。schema 另存 `teacher.members_sha256`（所有成員檔 hash 的摘要），`--keep-teacher` 會核對它，不符就拒絕。
- **9 月接老師 Live ZIP**（`course-live.latest_sha256`＝`7f4c759a…`，11/04 取得，內容 9/1～11/4）：
  - 逐位元組放到 `data/teacher_live/`（沒有 info.json）。schema 的 `teacher_live` 記 hash、`members_sha256`、使用範圍，`--keep-teacher` 一樣會核對。
  - 只取 **Training 最後日期（8/31）之後、<= 9/30** 的列，接在 Training 後面：20 個台股日、2,000 個個股列、20 個 global 列，9 月沒有待定值。
  - Live 用 `-1` 標示待定：`y=-1` → 答案空白；指數欄 `-1` → 空白。
  - 10/27～11/04 的 5 個 Live 版本裡，9 月的列完全相同（沒有被重算）。
  - 接縫驗證：100 檔在 8/31 與 9/1 的「老師 adj_close ÷ Yahoo 原始 close」完全相同 → 還原價基準一致、跨接縫報酬連續。Live 9 月 2,000 列的盤中比與 Yahoo 同日 100% 一致（錯一天約 2.3%），y 2000/2000。
  - Live global 的慣例和 Training 不同：每個台股日都有一列，休市市場沿用前一筆；美股欄＝日期 < d 的最後一個美股收盤（9 月 ^IXIC／^GSPC 20/20、^VIX 19/20），^TWII 20/20 同日、^KS11 19/20 同日（1 列韓國休市沿用）。值都在開盤前已知；9 月的 teacher_* lag 往回數的是 Live 的列。
  - 延長後 8/31 以前的值：老師相關欄完全相同；ETF／美股的 adj_close 因 Yahoo 重算有約 1e-6 以內的相對浮動（etf_0052 最大 1.04e-6；報酬絕對差：長表 ≤ 1e-6、market_features ≤ 1.1e-6；close 與缺值位置不變）。
  - 待定值 fail closed：使用範圍內只要有 -1（y、價格、指數欄、TX_OI），crawler 直接拒絕；Live 的待定列整列是 -1（10/23、11/04）。
  - 兩種待定列不一樣（2026-11-04 查證，給每日模式用；見 `archive/old-research/deploy-README-2026-11-04.md` 第 11.3、11.5 節）：
    - **當天的列**（11/04）：個股全部 -1；global 的 ^VIX／^IXIC／^GSPC 已填前一個美股收盤，^TWII／^KS11／TX_OI 是 -1。t 的特徵只讀 i＝前一個台股日以前，所以這列只當日曆。
    - **永遠不補的列**（10/23）：100 檔全是 -1，global ^TWII、TX_OI 也是 -1，^KS11 有值。Yahoo ^TWII 沒有 10/23；0050 這天是同價佔位K棒 → 很可能休市。提議：台股日曆以官方 `/api/state` 為準，不在官方日曆的待定列拿掉。**未實作，等使用者確認。**
  - 指紋：`timing_verification.verified_against` 用 `teacher_live.used_rows_sha256`（只算實際用到的 9 月列），所以每天換新的 Live ZIP 不會讓驗證失效；整份 ZIP 的 `members_sha256` 只給 `--keep-teacher` 做完整性檢查。

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
- 研究假設：美股收盤約台北 04:00–05:00，在 09:00 前；FX／期貨日K可能在台北清晨才收。（已由下方 2026-11-04 驗證段取代；仍未驗證的只有發布延遲。）
- 老師欄的實證（相關係數）：
  - `^GSPC／^IXIC／^VIX`：列 d 的值＝**前一個 global 列日期**的美股收盤（`^GSPC` 對 DJI：前一 global 列 0.87、同日 −0.18）。長假後可能落後多個美股交易日。
  - `^TWII`：列 d＝**d 當日收盤**（對 0050 同日 0.94、前一日 0.08）。
  - `^KS11`：列 d＝**d 當日收盤**（對日經225 同日 0.65、前一日 0.01）。
  - → market_features 改放 `^TWII_prev_row`、`^KS11_prev_row`、`TX_OI_prev_row`（最後一個日期 < t 的 global 列；TX_OI 是使用者 2026-11-04 同意改的）。
  - `TX_OI`：早先差分對同日／前一日 TWII 報酬相關都弱。2026-11-04 逐年 Spearman 改判為**疑似同日**（role＝suspected_same_day）：ΔTX_OI 對同日盤中報酬 2023 年 +0.37（其他 1 日變化欄逐年最大 0.18），對同日開盤跳空 2022／2023／2025 年 +0.21／+0.24／+0.38；各年正負不一，只能說疑似。使用者 2026-11-04 決定：market_features 改成 `TX_OI_prev_row`（已做）；長表與 lag 檔本來就沒有 TX_OI，不受影響。
- global_data 只有「五個老師 Yahoo 序列同日都有資料」才有列（1,506 列，缺 112 個台股日；大致是台／美／韓交集，但例如 2021-04-06 三地都有交易仍缺），缺列不代表休市。

## 時間對齊驗證（2026-11-04，用 Yahoo 原始資料逐值比對；結論：沒有對齊錯誤、沒有洩漏）
驗證腳本只放在當時 session 的暫存區（未 commit）；要重做就照下面的方法重寫。
- **老師 global 欄**（抓 Yahoo 原始 5 指數，相對誤差 < 1e-6）：
  - `^GSPC／^IXIC／^VIX`：第 j 列＝第 j−1 列日期的 Yahoo 收盤，1505/1505 全中；第一列 2020-01-03＝2020-01-02 收盤。
  - 其中 88 列的前一列不是前一個美股日（台／韓長假後），例：2020-01-30 那列是 01-17 的收盤 → 老師美股欄有時落後好幾個美股日。
  - `^TWII`、`^KS11`：同日收盤，1506/1506 → 不能直接當 t 的輸入。transform 只用 i＝前一個台股日（i 不是 global 列就空白）；market_features 用日期 < t 的最後一個 global 列（111 天比前一個台股日更舊）。
- **老師個股日期**＝台股交易日（抽 2330、2317、2454、2881、1101）：
  - 盤中比 adj_close/adj_open 與 Yahoo 同日 close/open 一致 99.8%～99.9%（分母＝Yahoo 同日有成交量的K棒；含零量K棒為 99.7%～99.8%），錯一天只有 1.5%～7%。
  - `y＝1{adj_close > adj_open}` 同列 100%。
  - 不一致的少數日是 Yahoo 自己的資料問題，前後一天也對不上，不是日期位移：2022-08-22（5/5 檔）、2024-03-29（4/5）Yahoo 是不完整的盤中K棒；2020-02-04 Yahoo open 錯；2024-11-20 平盤K棒；2021-08-17 零量佔位K棒；2021-04-06、2025-08-01 Yahoo 缺。
- **額外指標的日K日期**（本次只抓 2025-11-10～2026-08-31 的小時K；Yahoo 1h 最多回溯 730 天，約到 2024-11，還能再補約一年）。較早年份：SOX、TSM、NVDA、DJI、台灣 ETF、N225 由逐年跳空測試確認；HSI、SSE、歐洲、TWD=X 方向一致但部分年份弱；DXY、^TNX、^IRX、CL=F、GC=F 沒有鑑別力，是假設：
  | 類型 | 日K d 涵蓋 | 最晚完成（台北，保守＝最後一根小時K開始＋1h） |
  |---|---|---|
  | 美股、指數、ADR（SOX TSM NVDA DJI） | 美東當地日 d 的正規盤 | d+1 05:30 |
  | 殖利率（^TNX ^IRX，Chicago 時區） | 當地日 d | d+1 04:20 |
  | 期貨（CL=F GC=F） | 前一日 18:00 ET → d 17:00 ET（「結束在 d」高低點相符 72%／81%，「從 d 開始」0%）；close 推定為 CME 結算價（CL 約 14:30、GC 約 13:30 ET，小時K無法精確驗證） | d+1 06:00 |
  | 美元指數（DX-Y.NYB） | 約前一日 19:00 ET → d 18:00 ET（含 17:00 那根小時K；「結束在 d」約 87%、「從 d 開始」約 3%，容差 2e-4）；close≈15:00 ET 報價（不是結算價） | d+1 07:00 |
  | 亞洲指數、台灣 ETF | 當地日 d | d 當天 14:00～16:30 |
  | 歐洲（STOXX50E GDAXI） | 當地日 d | d+1 01:00 |
  | **TWD=X**（London 時區） | close≈**倫敦 d 日 00:00～01:00 的報價**（中位差 1.05bp；同日 23:00 為 17bp），也就是台北 d 日早上 07:00～09:00 | 實際 d 當天早上；保守上界 d+1 08:00 |
  → 除 TWD=X 外，每根日K最晚在 d+1 07:00（台北）收完；TWD=X 只驗證 close：每一年都在美股 d−1 收盤後、美股 d 開盤前（對 DJI(<d) −0.16～−0.42、對 DJI(d) −0.07～+0.09；期間到 2026-09），高低點涵蓋區間未驗證。輸出只用日期 <= t−1 天的K棒，所以都在 t 日 07:00 前收完（市場時間；Yahoo 上架時間未驗證）。
- **輸出檔實查**：
  - market_features 19 序列 `source_date <= t−1` 全部成立。
  - transform／panel 的 i＝前一個台股日；t−i 天數分布：1 天 1,278 列，其餘 2～13 天（延長到 9/30 後）。
- **開盤跳空測試**：序列單日報酬 vs 台股 t 日開盤跳空（50 股平均）。
  - 美股 4 檔「日期 < t 的最新一根」：全期 0.51～0.66（逐年 0.35～0.74）；「日期＝t」：≈0 → 美股 d 在台股 d 收盤之後。
  - 台灣 ETF「日期＝t」：全期 0.60～0.74（逐年 0.46～0.83）；「最新 < t」：≈0 → 同一個台股日。
  - TWD=X「日期＝t」：−0.199；「最新 < t」：0.00 → 印證 d 的 close 是台北 d 日早上的報價。所以 usd_twd 特徵實際比名稱舊約一天（安全、但較不新鮮）。
- **洩漏對照**（與當日 50 股平均盤中報酬的相關）：
  - 本分支 lag2 的 |corr| 最大 0.159（teacher_gspc）；刻意改用日期＝t 的K棒最高 0.388（etf_006201）。期間 2020-01～2026-09。
  - teacher_gspc 的 0.16 已查明不是洩漏：GSPC 單日報酬對 M(t) 的相關，最新一晚 −0.130、第 2、3 晚 +0.096／+0.094（隔夜跳空後盤中反轉）。teacher_gspc lag2 剛好落在第 2～3 晚；SOX lag2 涵蓋第 1～2 晚，正負抵銷約 0.01。
- 仍未驗證：Yahoo 歷史上「幾點真的能抓到」這根日K（發布延遲）；所以 schema 仍標 research_assumption。

## transform（使用者 2026-11-04 確認的定義；取代先前「位移 k 列的單日報酬」版本）
- `ret_lag{k}(t) = (close_i − close_{i−k}) / close_{i−k}`，k＝2、5（k 個交易日的累積報酬）。
- **i＝t 的前一個台股交易日**，所以只用 t 開盤前已知的收盤；該序列在 i 那天沒有資料 → 空白。
- **i−k＝同一序列往回第 k 個自己的交易日**（不是台股列）。老師 global 指數＝往回 k 個 global 列；老師個股＝該股往回 k 列。
- 例：SOX close 01-16=100、01-17=102、01-21=99（01-20 美股休市）。列 01-22 用 i＝01-21 → lag2＝99/100−1＝−1.00%；列 01-21 用 i＝01-20 → 空白。
- 每個 CSV 兩欄：`date` 與 `<id>_ret_lag{k}`（只有一個特徵欄）；1,638 列（2020-01-02～2026-09-30）。
- 範圍：19 個額外指標＋老師 5 指數（`teacher_*`，不含 TX_OI）＋老師 100 股（`stock_<代號>`，用 `etl:adj_close`）＝124 個特徵 × 2 個資料夾。
- 價格：股票／ETF 用 adj_close，其他用 close。殖利率也用百分比報酬（使用者選擇）；us13w 在 2020-03 與 2021-02～2022-02 會有 ±100% 以上的值。
- 空白：i 那天沒資料、往回不足 k 個交易日、或 close_i／close_{i−k} 缺值或 <= 0（只看這兩個端點）。
- teacher_* 只在 i 是 global 日期時有值：lag2 1,523 列、lag5 1,520 列非空白（Training 1,506 列＋Live 9 月 20 列）。
- 老師美股欄已被老師位移：Training 列＝前一個 global 列日期的收盤（長假後可能落後多個美股日）；Live 9 月列＝日期 < d 的最後一個美股收盤。

## 長表 panel_lag.csv.gz（使用者 2026-11-04 選擇）
- 形狀：長表，每列＝一股 × 一個台股交易日；**全部 100 股**（`is_top50` 標記官方 50 檔），100 × 1,638＝163,800 列的完整格子，依 date、stock_id 排序。
- 欄位（56）：`date, stock_id, is_top50, has_teacher_row`＋`stock_ret_lag2/5`（該股自己的）＋48 個市場特徵（19 額外＋5 老師指數 × lag2/5，同日各股相同）＋`label_y, label_intraday_return`。
- 答案放**同一檔**、欄名加 `label_` 前綴（使用者選擇）；README 示範用 `"_ret_lag" in c` 選特徵，自然排除答案。
- 格式：CSV.gz（使用者選擇；gzip mtime=0、壓縮等級 9，可重現），7 MB。schema 記 `sha256_csv_uncompressed`（跨環境比對用）與 `sha256_gz`。
- 數值和 lag 檔完全相同（同一份計算結果寫兩次），已獨立逐格核對：特徵、label_y、盤中報酬皆 0 不一致。
- 老師缺列的 54 格：`has_teacher_row=0`，答案空白，特徵照常計算。
- 特徵缺值比例 3.65%（延長到 9/30 後）。

## 其他格式決定
- CSV 浮點數用完整精度（`repr`）；空白＝缺值。
- sha256 以 LF 行尾計算；`.gitattributes` 對 `data/**`、`schema.json`、`.agents/skills/**` 設 `-text`，避免 Windows 換行轉換造成 hash 不符。
- 輸出檔權限 0644。
- 重抓時 Yahoo 的 adj_close 會有 <1e-6 的相對浮動（股利調整重算），其他欄完全相同。
