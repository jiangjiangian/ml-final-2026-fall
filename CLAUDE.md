# 專案記憶（hot cache）

完整細節在 `memory/`：術語 → `memory/glossary.md`；資料決策 → `memory/context/data-decisions.md`；
環境與分支 → `memory/context/environment.md`；這個分支的歷程與已知問題 → `memory/projects/data-folder.md`。

## 這個分支是什麼
課程 ML 期末專案（2026 秋）：預測台股 50 檔「盤中方向」`y = 1{adj_close > adj_open}`。
本分支 `claude/peaceful-babbage-09xeie` **只放資料整合成果**；完整程式（特徵管線、模型、每日提交）在預設分支 `system-completion`。

| 路徑 | 內容 |
|---|---|
| `crawler.py` | 唯一程式：yfinance 限流爬蟲 → 清理 → 老師資料 → 特徵 → transform → schema |
| `schema.json` | **所有特徵**（老師＋額外＋transform）的公式、單位、lag 規則、資料品質紀錄 |
| `data/teacher/` | 老師 Training ZIP 原樣（100 股、`global/global_data.csv`、`info.json`） |
| `data/extra/` | 19 個 yfinance 額外指標日K（已清理）＋ `manifest.json` |
| `data/features/market_features.csv` | 1,618 個台股日 × 104 欄（老師市場欄＋對齊後額外特徵） |
| `data/transform/lag2/`、`lag5/` | 124 個特徵 × 各一檔：`date, <id>_ret_lag{k}` |
| `.agents/skills/` | 既有 skills：gh-fix-ci、graphify、markitdown、rtk、security-best-practices |

## 人
| 誰 | 角色 |
|---|---|
| **jiangjiangian** | GitHub repo 擁有者 |
| **使用者** | 本分支的需求方；用繁體中文溝通 |
| **畇亦 蘇** | `system-completion` 上主要程式的 commit 作者 |

## 常用術語
| 詞 | 意思 |
|---|---|
| **老師資料** | 課程 Training ZIP（2020-01-02～2026-08-31），在 `live-data` 分支以 sha256 命名 |
| **老師 index** | global_data 的 `^VIX ^IXIC ^GSPC ^TWII ^KS11`（＋`TX_OI` 口數）；「額外指標」＝排除這些 |
| **額外指標** | 19 個 yfinance 序列（SOX、TSM、NVDA、TWD=X、DXY、^TNX、^IRX、0050/0052/0055/006201、DJI、N225、HSI、SSE、STOXX50E、DAX、CL=F、GC=F） |
| **r_i** | `(close_i − close_{i−1}) / close_{i−1}`；`i−1`＝**同一序列**的前一交易日 |
| **lag k** | 把 r 放到同日台股列（無資料留空），再往前位移 k 個台股列 |
| **ret_ks** | market_features 的 k 交易日**累積**報酬 `P[s]/P[s−k]−1`，不是 lag k |
| **s／source_date** | 對目標日 t，該序列 `<= t−1 天` 的最後一個交易日 |
| **Phase 1／2** | 靜態 84 日回測（截止 12/24）／每日 09:00 前提交 50 股 |
| **live-data** | 共用資料分支（老師 ZIP、Live、manifest、研究特徵） |

## 偏好與規則（使用者明確要求）
- 回覆用**繁體中文**；先講清楚定義讓使用者確認，再實作（例：transform 的 return）。
- 這個分支只放：`crawler.py`、`schema.json`、`data/`、`.agents/skills/`、本檔與 `memory/`（加 `.gitignore`、`.gitattributes`）。**其他東西先不要放到 GitHub。**
- 額外指標一律用 **yfinance**；範圍固定 **2020-01-01～2026-08-31**；要含**台幣匯率** TWD=X。
- 爬蟲**必須限流**（每個 HTTP 請求都過限流器，見 `memory/context/data-decisions.md`）。
- 殖利率也用百分比報酬（使用者選擇，即使接近 0 時會很大）。
- 缺漏日期留空白，不補值。
- 只推到 `claude/peaceful-babbage-09xeie`；不自行開 PR。

## 重建資料
```bash
pip install yfinance==1.7.0          # 需開放 *.finance.yahoo.com 等網域
git fetch origin live-data           # 老師 ZIP 來源
python crawler.py                    # 全部重建（約 1 分鐘）
python crawler.py --skip-download --keep-teacher   # 不連網，只重算特徵/transform/schema
```
測試在 session scratchpad，不在 repo（使用者要求分支只放上述檔案）。

## 絕對不要
- 把 `y`、當日 `etl:adj_*`、當日成交量／法人／技術指標，或老師 `^TWII`／`^KS11` 的**當日值**當輸入（後兩者是當日收盤，已實證）。
- 隨機拆股票列做驗證（同日市場特徵 50 股共用，要按日期切）。
- 把 yfinance 快取寫進 `data/`。
