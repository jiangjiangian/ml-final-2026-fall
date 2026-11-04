# 專案記憶（hot cache）

更多細節在 `memory/`：術語 → `memory/glossary.md`；資料決策 → `memory/context/data-decisions.md`；
環境、分支與 skills → `memory/context/environment.md`；本分支歷程、審查與已知限制 → `memory/projects/data-folder.md`。

## 這個分支是什麼
課程 ML 期末專案（2026 秋）：預測台股 50 檔「盤中方向」`y = 1{adj_close > adj_open}`。
本分支 `claude/peaceful-babbage-09xeie` **只放資料整合成果**；完整程式（特徵管線、模型、每日提交）在預設分支 `system-completion`。

| 路徑 | 內容 |
|---|---|
| `README.md` | 給組員：檔案樹、取得方式、X/y 切法、lag 定義、注意事項 |
| `crawler.py` | 唯一程式：yfinance 限流爬蟲 → 清理 → 老師資料 → features → transform → panel → schema |
| `schema.json` | **所有特徵**（老師＋額外＋transform）的公式、單位、lag 規則、清理紀錄、hash；`timing_verification` 是時間對齊驗證紀錄 |
| `data/teacher/` | 老師 Training ZIP 原樣（100 股、`global/global_data.csv`、`info.json`），到 2026-08-31 |
| `data/teacher_live/` | 老師 Live ZIP 原樣（`7f4c759a…`，9/1～11/4）；**只用 9/1～9/30**，接在 Training 後面 |
| `data/extra/` | 19 個 yfinance 額外指標日K（已清理）＋ `manifest.json`（限流、重試、清理紀錄） |
| `data/features/market_features.csv` | 1,638 個台股日 × 104 欄：老師市場欄（`^TWII/^KS11/TX_OI` 都用 `_prev_row`）＋as-of 對齊的額外特徵（`_ret_1s/5s/20s` 等） |
| `data/transform/panel_lag.csv.gz` | **組員直接用**：100 股 × 1,638 天＝163,800 列 × 56 欄（鍵、旗標、50 個 lag 特徵、`label_y`、`label_intraday_return`），7 MB |
| `data/transform/lag2/`、`lag5/` | 124 個特徵各一檔：`date, <id>_ret_lag{k}` |
| `deploy/README.md` | Phase 2 每日自動提交的部署設計：GitHub schedule 為何延遲、推薦 GCP Cloud Scheduler＋Cloud Run Job 為主、備援與監控、時間表、實作清單；第 10 節免費方案（不綁卡版＝Cloudflare＋cron-job.org→dispatch）、第 11 節 raw→模型輸入、第 12 節 Mermaid 流程圖 |
| `.agents/skills/` | 既有 Codex 格式 skills（Claude Code 不會自動載入，需要時直接讀 SKILL.md） |

## 人
| 誰 | 角色 |
|---|---|
| **jiangjiangian** | GitHub repo 擁有者 |
| **使用者** | 本分支的需求方；用繁體中文溝通 |
| **畇亦 蘇** | `system-completion` 上主要程式的 commit 作者 |

## 常用術語
| 詞 | 意思 |
|---|---|
| **老師資料** | 課程 Training ZIP（2020-01-02～2026-08-31）＋ Live ZIP（9/1 起，本分支只用到 9/30），在 `live-data` 分支以 sha256 命名 |
| **老師 index** | global_data 的 `^VIX ^IXIC ^GSPC ^TWII ^KS11`（＋`TX_OI` 口數）；「額外指標」＝排除這些 |
| **額外指標** | 19 個 yfinance 序列：SOX、TSM、NVDA、TWD=X、DXY、^TNX、^IRX、0050/0052/0055/006201、DJI、N225、HSI、SSE、STOXX50E、DAX、CL=F、GC=F |
| **lag k（transform）** | 台股日 t 那列＝`(close_i − close_{i−k}) / close_{i−k}`，**i＝t 的前一個台股交易日**，i−k 數該序列自己的交易日；i 那天沒資料就空白 |
| **panel** | `data/transform/panel_lag.csv.gz` 長表；`label_` 開頭的欄是答案，不可當輸入 |
| **ret_ks（features）** | as-of 對齊的 k 交易日累積報酬 `P[s]/P[s−k]−1`，休市沿用不留空 |
| **s／source_date** | features 中，該序列 `<= t−1 天` 的最後一個交易日 |
| **Phase 1／2** | 靜態 84 日回測（截止 12/24）／每日 09:00 前提交 50 股 |
| **live-data** | 共用資料分支（老師 ZIP、Live、manifest、研究特徵） |

## 偏好與規則（使用者明確要求）
- 回覆用**繁體中文**；先講清楚定義讓使用者確認，再實作。
- 這個分支只放：`crawler.py`、`schema.json`、`data/`、`.agents/skills/`、`README.md`、`deploy/`（使用者 2026-11-04 要求放 Phase 2 部署設計）、本檔與 `memory/`（加 `.gitignore`、`.gitattributes`）。**其他東西先不要放到 GitHub。** `crawler.py` 由使用者明確要求保留（2026-11-04）。
- 額外指標一律用 **yfinance**；範圍固定 **2020-01-01～2026-09-30**（使用者 2026-11-04 從 8/31 延長）；要含**台幣匯率** TWD=X。9 月的老師資料用 Live ZIP。
- 爬蟲**必須限流**（每個 HTTP 請求都過限流器，見 `memory/context/data-decisions.md`）。
- 殖利率也用百分比報酬（使用者選擇，即使接近 0 時數值很大）。
- 缺漏日期留空白，不補值。
- 審查有發現時，等審查結果出來再一起修（使用者偏好）。
- 只推到 `claude/peaceful-babbage-09xeie`；不自行開 PR。

## 重建資料
```bash
pip install yfinance==1.7.0          # 需開放 finance.yahoo.com 等網域（見 environment.md）
git fetch origin live-data           # 老師 ZIP 來源
python crawler.py                    # 全部重建（約 1 分鐘）
python crawler.py --skip-download --keep-teacher   # 不連網，只重算 features/transform/schema（會核對 Training 與 Live 檔的 hash）
```
結束碼：0 完成；1 必要序列缺；2 錯誤；3 本次有序列失敗或中止（沿用舊檔，status＝stale）。
**目前沒有存放測試**：測試只在當時 session 的暫存區，使用者要求分支不放其他檔案，所以已隨 session 消失；改動 crawler.py 前請先補測試（不要 commit，除非使用者同意）。

## 絕對不要
- 把 `y`、當日 `etl:adj_*`、當日成交量／法人／技術指標，或老師 `^TWII`／`^KS11` 的**當日值**當輸入（兩者已逐值驗證是當日收盤）。
- 把老師 global 的**同日** `TX_OI` 當輸入（逐年相關性顯示疑似含當日資訊）；market_features 已改放 `TX_OI_prev_row`（使用者 2026-11-04 同意）。
- 隨機拆股票列做驗證（同日市場特徵 50 股共用，要按日期切）。
- 把 yfinance 快取、`graphify-out/`、`tools/` 或其他非允許檔案 commit 到本分支。
