# 專案：data 資料夾整合（本分支）

**狀態**：完成，已推送到 `claude/peaceful-babbage-09xeie`
**也叫**：yfinance 爬蟲、額外指標、data folder、schema

## 使用者的要求（依時間）
1. 用 yfinance 匯入老師以外的全部額外指標，寫成爬蟲腳本；範圍 2020-01-01～2026-08-31；要台幣匯率。
2. 輸出一個 schema：所有特徵＝老師的＋額外的。
3. 全部資料整合成一個 `data/` 資料夾。
4. 爬蟲要**限流**。
5. 分支只推三樣：schema、完整 data 資料夾、crawler.py。
6. 開放 Yahoo 網域後跑爬蟲並推送。
7. 回答：額外指標是否全用 yfinance？→ 是，19 個都是。
8. 新增 `data/transform/lag2`、`lag5`：每個特徵各一個 CSV（close 的 return），先說定義讓使用者確認。
9. 分支只保留 data、schema、既有 skills，其他先不要放到 GitHub；寫 CLAUDE.md 與記憶文件。

## 做法摘要
- 單一 `crawler.py`（只依賴 yfinance＋標準函式庫），一次完成：限流下載 → 清理 → 老師資料 → market_features → transform → schema。
- 一開始把程式拆成 `ml_financial_prediction/` 的多個模組＋測試＋workflow，但使用者要求只推三樣後，合併成單檔，測試移到 scratchpad。
- 起初環境擋 Yahoo（proxy 403），使用者開放網域後才實際下載。

## 審查（2026-11-04，5 個獨立 agent，26 個發現）已處理
- 高：0052 漏調一拆七 → 加分割回補。
- 中：老師 `^TWII／^KS11` 是當日收盤 → market_features 改用前一列；佔位K棒、TWD=X 壞報價 → 清理規則；yfinance lru_cache 讓重試沒真的發請求 → 清快取；yfinance 內部的 tz/cookie 請求沒被限流 → HTTP 層限流；中斷時 manifest 不同步 → 每檔寫入、失敗時保留可解析舊檔；必要序列被略過不報錯 → 計入 missing_required、exit 1；`--keep-teacher` 沒舊 schema 會失敗 → 直接驗證資料夾。
- 低：12 位小數截斷 → 完整精度；schema 文字（global 表是交集、volume 說明、close 也有分割調整、rate_limit 是 last_run）；檔案權限 0600 → 0644；連續被限流沒冷卻 → 熔斷。
- 只記錄、未改資料：TWD=X close 常等於 open（Yahoo 結構問題）；STOXX50E 依瑞士假日缺 21 天；台灣 ETF 缺 2021-04-06。

## 已知限制（交接時要說）
- 所有時間對齊都是 research_assumption，未驗證歷史發布時間。
- TWD=X 的 close 常是倫敦日第一筆報價；若要台北收盤，需另找來源（例如 live-data 的 FRED DEXTAUS，但那不是 yfinance）。
- 老師 global 表只有台／美／韓同日都交易的 1,506 天；transform 的 teacher_* 在其餘 112 天為空白。
- 授權：老師 ZIP 與 Yahoo 資料的公開再散布授權未核實。

## 數字
- 老師：100 股、161,746 列、個股日期 2020-01-02～2026-08-31；global 1,506 列。
- market_features：1,618 列 × 104 欄（6 個老師市場欄＋97 個額外特徵＋date）。
- transform：124 個特徵 × lag2／lag5 ＝ 248 個 CSV。
- data/ 約 64 MB：teacher 45M、transform 13M、extra 3.2M、features 2.5M。
