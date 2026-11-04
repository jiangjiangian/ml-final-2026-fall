# 術語表（完整版）

CLAUDE.md 找不到的詞先查這裡；仍找不到就問使用者，問到後補進來。

## 資料與來源
| 詞 | 意思 | 備註 |
|---|---|---|
| 老師資料／Training ZIP | 課程提供的歷史包：100 股 CSV＋`global_data.csv`＋`info.json` | sha256 `7433b271…`，存在 `live-data:objects/` |
| Live ZIP | 9/1 之後的老師新資料（`y=-1`＝pending） | 不在本分支範圍內 |
| template | 官方預測模板（股票／日期／欄位順序） | 不在本分支 |
| Top50@Y／Top100@Y | `info.json` 的預測目標 50 股／全部 100 股 | |
| global_data | 老師全球表：`date, ^VIX, ^IXIC, ^GSPC, ^TWII, ^KS11, TX_OI` | 只有台／美／韓同日都交易的日期才有列（1,506 列，缺 112 個台股日） |
| TX_OI | 台指期外資淨未平倉口數（多減空，可負） | 單位是口數，不算 return；發布時點未驗證 |
| 老師 index | global_data 的五個指數欄 | 使用者說的「除了老師以外的 index」＝排除這五個 |
| 額外指標 | crawler.py 用 yfinance 抓的 19 個序列 | 清單見 data-decisions.md |
| live-data | 共用資料分支：catalog／manifests／objects／features／labels | 老師 ZIP 由 `git show origin/live-data:...` 取得 |
| yfinance | https://github.com/ranaroussi/yfinance，呼叫 Yahoo chart API | 釘選 1.7.0 |

## 欄位與特徵
| 詞 | 意思 |
|---|---|
| y | `1{etl:adj_close > etl:adj_open}`（盤中上漲）；只當 label |
| 盤中報酬 | `adj_close/adj_open − 1` |
| 官方分數 | `mean((2p − 1) × 盤中報酬)`，p 是 0／1 預測 |
| s／source_date | 目標日 t 時，該序列 `session_date <= t − 1 日曆天` 的最後一個交易日 |
| age_days | `t − s` 日曆天數（新鮮度） |
| `<id>_ret_{k}s` | market_features 的 k 交易日累積報酬 `P[s]/P[s−k] − 1` |
| `<id>_level`／`_level_pct` | FX／美元指數水準；殖利率水準（百分比） |
| `<id>_change_bp_{k}s` | 殖利率 k 期基點變化 `100 × (Y[s] − Y[s−k])` |
| `^TWII_prev_row`／`^KS11_prev_row` | 最後一個日期 < t 的老師 global 列之值（避開當日收盤） |
| r_i | transform 用的單日收盤報酬 `(close_i − close_{i−1}) / close_{i−1}` |
| `<id>_ret_lag{k}` | transform：往前第 k 個台股交易日列的 r_i |
| teacher_vix／ixic／gspc／twii／ks11 | transform 中老師五個指數的特徵 id |
| stock_<代號> | transform 中老師個股（`etl:adj_close`）的特徵 id |
| etf_0050／0052／0055／006201 | 台灣50／電子（富邦科技）／金融（元大MSCI金融）／櫃買（元大富櫃50）的 ETF 代理 |
| M0～M5 | 專案的市場特徵分組：M0 老師既有、M1 半導體、M2 海外個股、M3 匯率利率、M4 台灣類股、M5 其他全球 |

## 資料品質用語
| 詞 | 意思 |
|---|---|
| 壞報價（bad tick） | close 超出 [low, high] 0.5% 以上；整列刪除 |
| 佔位K棒（placeholder bar） | 股票／ETF 的零量、OHLC 相同且等於前一收盤的列；Yahoo 補的假交易日 |
| 漏調分割 | Yahoo 沒調整的分割（0052 在 2025-11-17 一拆七）；crawler 回補 |
| research_assumption | 研究假設等級：歷史發布時間未驗證，不等於可上線 |
| as-of | market_features 沿用最後可用交易日的值；休市時連續數個台股日會重複 |

## 專案流程用語（來自 system-completion）
| 詞 | 意思 |
|---|---|
| Phase 1 | 一次交 84 個日期（2026-06-01～09-30）× 50 股，截止 2026-12-24 23:59 |
| Phase 2 | 每個官方交易日 09:00（台北）前交當日 50 股 |
| cutoff | 推論資訊截止時間；專案用 08:10，老師硬截止 09:00 |
| shadow | 只旁跑記錄、不正式提交的研究流程 |
| R2／fold | 專案第二輪四模型研究／按日期劃分的驗證區間 |

## 分支
| 分支 | 用途 |
|---|---|
| `system-completion` | 預設分支：完整程式、workflows、文件 |
| `claude/peaceful-babbage-09xeie` | 本分支：只放資料整合成果 |
| `live-data` | 共用資料版本 |
| `dev`／`deep-research` | 核心開發歷史／來源研究 |
| `main` | 依原要求保留空樹 |
