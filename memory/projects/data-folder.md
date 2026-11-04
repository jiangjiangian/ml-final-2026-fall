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
12. 問：`features/` 資料夾是什麼？→ as-of 對齊的市場特徵表（見 CLAUDE.md），使用者尚未決定是否保留。

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
- 所有時間對齊都是 research_assumption，未驗證歷史發布時間。
- TWD=X 的 close 常是倫敦日第一筆報價；若要台北收盤，需另找來源（例如 live-data 的 FRED DEXTAUS，但那不是 yfinance）。
- 老師 global 表只有 1,506 天；transform 的 teacher_* 只在「前一個台股日」是 global 日期時有值（lag2 1,503、lag5 1,500 列）。
- 授權：老師 ZIP 與 Yahoo 資料的公開再散布授權未核實。

## 數字
- 老師：100 股、161,746 列、個股日期 2020-01-02～2026-08-31；global 1,506 列、缺 112 個台股日。
- market_features：1,618 列 × 104 欄（date＋6 個老師市場欄＋97 個額外特徵）。
- transform：124 個特徵 × lag2／lag5 ＝ 248 個 CSV。
- data/ 約 64 MB：teacher 45M、transform 13M、extra 3.2M、features 2.5M。
