# 專案：data 資料夾整合（本分支）

**狀態**：完成，已推送到 `claude/peaceful-babbage-09xeie`
**也叫**：yfinance 爬蟲、額外指標、data folder、schema、transform

## 使用者的要求（依時間）
1. 用 yfinance 匯入老師以外的全部額外指標，寫成爬蟲腳本；範圍 2020-01-01～2026-08-31；要台幣匯率。
2. 輸出一個 schema：所有特徵＝老師的＋額外的。
3. 全部資料整合成一個 `data/` 資料夾。
4. 爬蟲要**限流**。
5. 分支只推三樣：schema、完整 data 資料夾、crawler.py。
6. 開放 Yahoo 網域後跑爬蟲並推送。
7. 回答：額外指標是否全用 yfinance？→ 是，19 個都是（老師資料則是從 live-data 取 ZIP）。
8. 新增 `data/transform/lag2`、`lag5`：每個特徵各一個 CSV（close 的 return），先說定義讓使用者確認。
9. 分支只保留 data、schema、既有 skills，其他先不要放到 GitHub；寫 CLAUDE.md 與記憶文件。
10. `crawler.py` 也保留；等審查結果出來再修。
11. lag 定義改為 `(close_i − close_{i−k}) / close_{i−k}`，i＝前一個台股交易日（使用者選擇 i−2 與「前一個台股交易日」）。
12. 問：`features/` 資料夾是什麼？→ as-of 對齊的市場特徵表（見 CLAUDE.md）。使用者 2026-11-04 決定：先保留。
13. 在 root 做檔案樹並說明如何提供組員使用 → 新增 `README.md`（檔案樹、取得方式、X/y、lag 定義、注意事項）。
14. 問：100 股的 lag2／lag5 有包含當前的 y 嗎？→ 沒有：t 那列只用 t−1 以前的收盤；合併後 corr(y_t, stock lag2)＝−0.017，若誤用當日收盤則為 0.373。
15. 整合 lag2、lag5 成可直接用的 dataframe → `data/transform/panel_lag.csv.gz`（長表、100 股＋is_top50、label_ 前綴、CSV.gz）。
16. 驗證老師與額外指標的時間對齊 → 用 Yahoo 原始日K、小時K逐值比對，沒有對齊錯誤或洩漏，資料不需修改（證據見 `data-decisions.md` 的「時間對齊驗證」）。
17. 更新 schema → `timing_verification`（含 verified_against 資料指紋、applies_to_current_data）與 `extra.series.<id>.timing`；第三輪審查（3 審查者＋3 反駁者）的發現已修：TX_OI 改判疑似同日並在文件警告、DXY 時段與 15:00 ET close、老師個股不一致日的標籤、小時K範圍的措辭、跳空測試鑑別力分類、TWD=X 跨年證據、「08:00 前」改成「07:00 以前收完」。資料檔沒變。
18. deep-research：Phase 2 自動流程怎麼準時 → `deploy/README.md`（推薦 GCP Cloud Scheduler＋Cloud Run Job 為主、GitHub dispatch／Claude 雲端排程任務為備援、Healthchecks 監控；11/04 GitHub schedule 延遲 3h42m～6h17m 全被時鐘擋下）。待使用者決定：開不開 GCP、實作分支、能否建 Claude 排程任務、告警通道。
19. TX_OI 改前一列 → market_features 的 `TX_OI` 換成 `TX_OI_prev_row`；長表與 lag 檔本來就沒有 TX_OI，不受影響。
20. 資料範圍延長到 2026-09-30 → yfinance 19 序列限流重抓；9/1～9/30 的老師資料接 Live ZIP（`data/teacher_live/`）；接縫與 Live 慣例逐值驗證；timing_verification 的數字與資料指紋全部重算。Phase 2 自動化使用者說「等下再問」。

## 做法摘要
- 單一 `crawler.py`（只依賴 yfinance＋標準函式庫），一次完成：限流下載 → 清理 → 老師資料 → market_features → transform → schema。
- 一開始把程式拆成 `ml_financial_prediction/` 的多個模組＋測試＋workflow，但使用者要求只推三樣後，合併成單檔，測試只留在 session 暫存區（未保存）。
- 起初環境擋 Yahoo（proxy 403），使用者開放網域後才實際下載。

## 第一輪審查（5 個獨立 agent，26 個發現）已處理
- 高：0052 漏調一拆七 → 分割回補。
- 中：老師 `^TWII／^KS11` 是當日收盤 → market_features 改用前一列；零量佔位K棒、TWD=X 壞報價 → 清理規則；yfinance lru_cache 讓重試沒真的發請求 → 清快取；yfinance 內部 tz/cookie 請求沒被限流 → HTTP 層限流；中斷時 manifest 不同步 → 每檔寫入；必要序列被略過不報錯 → 計入 missing_required；`--keep-teacher` 沒舊 schema 會失敗 → 直接驗證資料夾。
- 低：12 位小數截斷 → 完整精度；schema 文字修正；檔案權限 → 0644；連續被限流 → 熔斷。

## 第二輪審查（5 個獨立 agent）
- transform 248 檔逐格獨立重算：397,338 個非空白值全部一致、無洩漏；老師資料與 ZIP 逐位元組一致。
- 已修：
  - 高：0052 分割前股利調整只做約 1/7，造成除息日假的 −2%～−8% → 股利幅度 ×7。
  - 中：2024-11-20 三檔 ETF 的不完整K棒 → 低量平盤規則；`YFPricesMissingError`／`YFTzMissingError` 不重試 → 重試 1 次；熔斷時仍回報 complete → 新增 stale 狀態、結束碼 3；`--keep-teacher` 不核對 hash → `members_sha256`；schema 的 transform 路徑少 `data/` → 補上；文件說測試在暫存區 → 改成「沒有存放」；skills 依賴已移除的 `tools/` → 在 environment.md 說明取回方式。
  - 低：殖利率在債市假日的平盤K棒 → 刪除；非台股的疑似分割不再自動修改；清理後沒資料會覆蓋舊檔 → 先檢查；重新導向次數上限 5；`--timeout` 範圍寫清楚；最後一檔不再冷卻；`.gitignore` 加 `graphify-out/` 等；`.gitattributes` 對 skills 也設 `-text`；^KS11 證據、global 表描述、分割日期描述、反向分割說明等文字修正。
- 只記錄、未改資料：TWD=X close 常等於 open；STOXX50E 依瑞士假日缺 21 天；台灣 ETF 缺 2021-04-06；殖利率百分比報酬的極端值（使用者選擇保留）。

## 已知限制（交接時要說）
- 日期語意已用 Yahoo 原始資料驗證（2026-11-04）；但歷史上幾點真的抓得到（發布延遲）沒有驗證，所以仍標 research_assumption。
- TWD=X 日期 d 的 close≈倫敦 d 日 00:00～01:00 報價（台北 d 日早上），所以 usd_twd 特徵比名稱舊約一天；若要台北收盤，需另找來源（例如 live-data 的 FRED DEXTAUS，但那不是 yfinance）。
- 老師 global 表只有 1,506 天；transform 的 teacher_* 只在「前一個台股日」是 global 日期時有值（lag2 1,503、lag5 1,500 列）。
- 授權：老師 ZIP 與 Yahoo 資料的公開再散布授權未核實。

## 數字
- 老師：Training 100 股、161,746 列、2020-01-02～2026-08-31；global 1,506 列、缺 112 個台股日。Live（只用 9 月）2,000 列、global 20 列。
- market_features：1,638 列 × 104 欄（date＋6 個老師市場欄＋97 個額外特徵）。
- transform：124 個特徵 × lag2／lag5 ＝ 248 個 CSV。
- panel：163,800 列 × 56 欄（50 個特徵），有答案 163,746 列，top50 81,900 列，7 MB；老師缺列仍是 54 格。
- data/ 約 71 MB：teacher 45M、transform 20M（含 panel 7M）、extra 3.2M、features 2.5M。
