# src/features.py

## 狀態

- 2026-11-06：規劃中，等使用者確認後才寫程式。
- 這份的內容來自 data-collection 的交接文件（`origin/claude/data-collection` `cb03a34` 的 `memory/projects/handoff-stock-market-challenger.md`）。data-collection 之後不再更新，所以要用的部分都抄到這裡。數字除了標「推論」的，都是那邊實際量過的。

## 使用者的決定

- 2026-11-06：lag 只用 lag1、lag2，不用 lag5。使用者和組員都同意。`configs/config.yaml` 的 `features.lags` 是 `[1, 2]`。
- 2026-11-06：組員要的 12 個序列確定之前，先把 25 個序列（個股自己加 24 個市場序列）的 lag1、lag2 都產出來，之後由模型挑欄。
- 2026-11-06：交易日照下面「交易日和 i」那條規則，取代「以 `phase2Days` 為準」。
- 2026-11-06：台幣匯率另外加一個和美股收盤同步的序列 `usd_twd_am`：台北日期 d 的值是 TWD=X 小時資料在台北 d 日 06:00 的報價（05:00 開始那根 1h 的 close）。組員要求「跟美股收盤同步、變成預測那天早上的指標」，使用者交給 Claude 決定。
  - 06:00 在美股收盤之後（冬令 05:00、夏令 04:00），07:10 的爬蟲一定抓得到，不用 08:00 後再抓。
  - 這個序列的 lag 用 t 自己的值當 cur：lag_k(t) = (x_t − x_{t 往回第 k 個台股交易日}) / 那個值。值在 t 開盤前就知道，不算用到 t 當天的資料。
  - Yahoo 小時資料從 2024-01-22 開始，更早的列空白。舊的 `usd_twd`（日期 i 那根日K，台北 i 日 08:00）照樣保留。
  - 爬蟲要多抓並保存 1h 序列，Yahoo 只給大約兩年多，所以要合併舊檔、不能整個蓋掉（第 4 步的爬蟲計畫裡處理）。
- 還在等：
  - lag2 的意思。2026-11-04 定的是「到 i 為止兩天的累積報酬」，另一種讀法是「i 前一天的單日報酬」。使用者已經問組員，回覆前照累積版做。
  - 組員要哪 12 個序列（見「組員的特徵」）。

## 資料來源

2026-11-06 從 data-collection `a806959` 搬來（這個分支的 commit `Move data-collection's data/ into this branch`），commit 後 8 個 tree hash 都核對過：

| 來源 | 這個分支 | tree hash |
|---|---|---|
| `a806959:data/teacher/` | `data/raw/teacher/` | `61da1df7…` |
| `a806959:data/teacher_live/` | `data/raw/teacher_live/` | `50225f19…` |
| `a806959:data/teacher_live/` | `data/reference/data-collection/teacher_live/` | `50225f19…` |
| `a806959:data/extra/` | `data/reference/data-collection/extra/` | `281446bd…` |
| `a806959:data/features/` | `data/reference/data-collection/features/` | `08b5cb3e…` |
| `a806959:data/transform/` | `data/reference/data-collection/transform/` | `9747c7bc…` |
| `a806959:schema.json` | `data/reference/data-collection/schema.json` | blob `19b27071…` |
| `0820473:data/extra/yfinance/` | `data/reference/data-collection/yfinance_raw_0820473/` | `d2257778…` |

- `data/raw/teacher/` 和 Training ZIP `7433b271…` 逐位元組相同（LF），`data/raw/teacher_live/` 和 Live ZIP `eea89fce…` 相同（CRLF）。
- `data/raw/teacher_live/` 帶金鑰連網跑時會被新的 Live 蓋掉，對照測試要用 `reference/` 那份。
- `yfinance_raw_0820473/` 是還沒清理的 Yahoo 原樣，2026-11-04 07:35 UTC 抓的，資料到 8/31。
- `schema.json`、`extra/manifest.json` 裡的路徑是舊 repo 的（`data/extra/…`）。比對前要換：`data/teacher` → `data/raw/teacher`，`data/{extra,features,transform,teacher_live}` → `data/reference/data-collection/…`。

## 交易日和 i（使用者 2026-11-06 決定照交接文件改）

現在有三套說法：
- data-collection 用寫死的 `LIVE_CLOSED_DAYS` 把 10/23 從日曆拿掉，所以 t = 10/27 的 i 是 10/22。
- 爬蟲的 `live_check` 取 `phase2Days` 裡早於 t 的最後一天；那天在 Live 裡沒填好，就退回最後一個填好的日子，並標 `prev_day_never_filled`、回傳 3。
- `src/features.py` 的說明和 `memory/context/data-rules.md` 寫「交易日曆以 `phase2Days` 為準」，Live 待定列只要 `phase2Days` 有就算交易日。如果 `phase2Days` 有 10/23，訓練特徵的 i 會是 10/23，每天預測時的 i 卻是 10/22。

決定的規則（爬蟲和 `features.py` 呼叫同一個函式）：
- 某天算台股交易日：那天老師個股資料填好了，也就是 100 檔裡至少 `crawler.min_stocks_filled`（90）檔的 `y` 是 0 或 1，而且 `etl:adj_open`、`etl:adj_close` > 0。
- i 是 t 之前最後一個這樣的日子。還是 `-1` 的列（10/23、當天早上 t 那列）不當 i，往回數 i−k 時也不算，那天 global 表的列也不用。
- 單一檔股票那天是 `-1` 或沒有列（停牌），就當這檔沒有那一列。
- `phase2Days` 只用來決定 t，不會讓日曆多出日子。
- config 加 `closed_days: [2026-10-23]`。那天之後出現數值就停下來（每日流程報錯，不是叫人看）。
- 這條規則下長表的日曆剛好 1,660 天（2020-01-02～2026-11-04，沒有 10/23），和 data-collection 相同。

Live global 表的 `-1`：`eea89fce` 只有兩列有。10/23 是 `^TWII`、`TX_OI`；11/05（t 那列，08:55 下載）是 `^TWII`、`^KS11`、`TX_OI`。07:10 時 `^VIX` 是不是 `-1` 沒量過，所以 6 欄（`^VIX ^IXIC ^GSPC ^TWII ^KS11 TX_OI`）的 `-1` 都當缺值，一格一格判斷。

## lag 的公式

- i：t 之前最後一個台股交易日。close：股票和 ETF（TSM、NVDA、0050、0052、0055、006201、老師個股）用 `adj_close`，其他用 `close`。i−1、i−2 往回數這個序列自己的列。
- lag_k(t) = (close_i − close_{i−k}) / close_{i−k}。函式寫成可以帶任意 k，正式只產 k = 1、2，對照測試用 k = 2、5。
- 序列在 i 那天沒有K棒就留空白，不往前找；不能用「最後一根 ≤ i」，因為 08:30 後才跑時爬蟲會留著舊檔。兩個端點任一是空的或 ≤ 0 也留空白（WTI 2020-04-20 是 −37.63，^IRX 2020-03 有負值）。
- 寫成 `(cur − base) / base`。用 `cur / base − 1`（pandas `pct_change`）時 76,675 個市場格裡有 74,262 個最後一位不同，最大差 4.4e-16；那樣的話對照容差設成絕對值 1e-15。

測試值（data-collection 的凍結資料，算過兩次）：

| 序列 | t | i | lag1 | lag2 |
|---|---|---|---|---|
| 2330 | 2026-11-04 | 11/03 | −0.015021459227467818 | −0.03164556962025325 |
| 2330 | 2026-10-27 | 10/22 | −0.014462809917355376 | −0.00831600831600827 |
| sox | 2026-11-04 | 11/03 | 0.02634213957551902 | −0.008270284379704918 |
| sox | 2026-10-27 | 10/22 | −0.06723524369545192 | −0.04890450322862169 |
| sox | 2026-09-08 | 9/07（美國勞動節） | 空白 | 空白 |
| teacher_vix | 2026-10-27 | 10/22 | −0.10418906802463328 | −0.10418906802463328 |
| 2327 | 2022-11-01 | 10/31，i−1 是 10/19（停牌） | 0.09880239520958087 | 沒算 |

teacher_vix 的 lag1 和 lag2 一樣，因為 Live 的 10/20、10/21 都沿用 18.62。2327 在 2022-10-20～10-28 停牌，t = 10/21～10/31 的 lag 都是空白。

副作用：
- 老師 global 的 `^GSPC`、`^IXIC`、`^VIX` 每一列已經是前一個美股交易日的值，所以 `teacher_gspc` 的 lag1 比 yfinance 美股的 lag1 晚一天（和前一列 `dji` lag1 相關 0.867，同一列只有 −0.176）。
- 只用 lag1、lag2 時，台股連休中間那幾天的美股報酬不會出現在任何一列。以 SOX 來說，這種日子從 20 天變成 57 天。
- 停牌或休市之後，lag1 會跨過整段空檔，分布有長尾。
- TWD=X 日期 d 那根的 close 是台北 d 日 08:00 左右的報價（2026-11-06 用 1h 資料對過：11/04 日K 32.733，小時資料 08:00 是 32.73）。用 i 那根時，匯率比美股舊將近一天。Yahoo 的 1h 資料從 2024-01-22 開始。

## yfinance 清理規則 R0～R5

照順序做，和舊爬蟲（data-collection `crawler.py:493-625`）一樣。紀錄裡的價格是 Yahoo 原始單位，還沒做分割修正。刪掉的列要整列拿掉，不能留成空白的一列：實測留空白時，7 個序列有 295 個 lag2、lag5 格和長表不同。

### R0 篩掉不能用的列（全部序列）

- None、bool、NaN、inf 當空值。close 是空的列整列拿掉（爬蟲把 NaN 存成空字串，所以 `features.py` 要自己做）。
- 期貨和殖利率以外的序列出現 close ≤ 0：舊程式讓整個序列失敗、沿用舊檔。日期重複也一樣。
- 依日期排序。

### R1 壞報價（全部 19 個序列）

low、high 都有值而且 low ≤ high 時才檢查。close < low − 0.005 × |low|，或 close > high + 0.005 × |high|（嚴格不等式），刪掉這一列。只看 close。

### R2 債市假日的平盤K棒（只有 ^TNX、^IRX）

開高低收相同（不看 adj_close 和成交量），而且日期是哥倫布日（10 月、週一、8～14 號）或退伍軍人節（11/11；週六提前到 11/10，週日延到 11/12），刪掉。下一個是 2026-11-11（週三），在 Phase 2 期間。

### R3 佔位K棒（只有股票和 ETF：TSM、NVDA、0050、0052、0055、006201）

依日期掃 R1、R2 留下的列，第一列一定保留，只看開高低收相同的K棒：
- 成交量是 0 或空的，而且 close 和前一個「保留下來的」列的 close 完全相等，刪掉。連續停牌時，每一根都和停牌前最後一根比。
- 其他情況：取前 21 個保留下來的列裡不是 0 的成交量，排序後取 `recent[len // 2]`（偶數個時是上中位數，和 `statistics.median` 不同）。成交量不是 0 而且小於這個數的 1%，刪掉（不完整的K棒）。
- 成交量 0 但 close 和前一列不同的平盤K棒，兩條都不成立，保留。

### R4 台股分割（股票和 ETF）

看相鄰兩個保留下來的列 (prev, cur)：
- ratio = prev.close / cur.close，n = round(ratio)。2 ≤ n ≤ 50 而且 |ratio − n| / n < 0.03，factor 是 n。不成立時用 1/ratio 再檢查一次，成立的話 factor 是 1/n（反向合併）。任一價格是空的或 ≤ 0 不算。
- adj_close 的比值也要算出一模一樣的 factor。
- 代號不是 `.TW`、`.TWO` 結尾（TSM、NVDA）只記錄，不改資料。
- 台股：分界那列之前的每一列，開高低收和 adj_close 都除以 factor，成交量乘以 factor。分界那列和之後不動。往下掃時用修正過的值。

### R5 分割前的股利調整乘回去

R4 修正台股之後立刻做（Yahoo 對分割前的除息只調了約 1/n）：
- r_t = adj_close / close（用除過 factor 的值），範圍是分界之前的列。分界前不到 2 列，或有空值、≤ 0，直接結束。
- level 從分界前一列的 r 開始，那一列的 adj_close 不改。
- 從分界前第二列往回到第一列：step = 1 − r_t / r_{t+1}。step > 1e-5 時 fixed = min(step × factor, 0.95)，level 乘上 (1 − fixed)，記一筆 {ex_date = 下一列的日期, yahoo_fraction = step, rescaled_fraction = fixed}；否則 level 乘上 r_t / r_{t+1}。
- 每一列的 adj_close 設成 close × level。

### 測試資料

凍結的 `data/reference/data-collection/extra/manifest.json` 有 62 筆紀錄，每筆都有原始值：
- 壞報價 2：usd_twd 2020-12-08、2024-08-28。
- 債市假日 24：^TNX、^IRX 各 12 天（2020-10-12、2020-11-11、2021-10-11、2021-11-11、2022-10-10、2022-11-11、2023-10-09、2024-10-14、2024-11-11、2025-10-13、2025-11-11、2026-10-12）。
- 佔位 29：成交量 0 的 26 筆（006201 10、0050 7、0052 7、0055 2，含 2026-10-23 颱風假的 4 筆），不完整的 3 筆（0050、0052、0055 都在 2024-11-20）。
- 分割 1：0052，分界 2025-11-17，factor 7。2025-11-14 原始 (O 248.3000030517578, H 249.64999389648438, L 248.0500030517578, C 248.5, adj 242.5469207763672, V 5021929)，修正後 (35.47142900739397, 35.66428484235491, 35.43571472167969, 35.5, 34.6495601109096, 35153503)。
- 股利乘回 6：都是 0052（yahoo_fraction → rescaled_fraction）：2020-04-22 0.0042352 → 0.0296467、2021-04-20 0.0011495 → 0.0080467、2022-04-20 0.0120857 → 0.0845996、2023-04-21 0.0053832 → 0.0376827、2024-04-18 0.0057143 → 0.0400004、2025-04-23 0.0030159 → 0.0211113。分割後的 2026-04-20 是 Yahoo 自己調的，不動。

要保留的反例（寫成單元測試）：
- usd_twd 2020-03-31、006201 2021-09-13：close 在高低區間外，但只超出 0.358%、0.368%。
- ^TNX 2023-11-10：日期符合退伍軍人節，但不是平盤。
- 0050、0052 的 2025-04-07、04-10：跌停平盤，成交量正常。
- 006201 2023-11-01：平盤，成交量 1000，是中位數的 5%。
- 0055 2020-09-18：close 等於前一列，但成交量 10188，是中位數的 25%。

## 清理細節的決定（使用者 2026-11-06）

1. close ≤ 0（期貨、殖利率以外）和日期重複：只丟那一列（重複的日期留最後一列），每筆記在清理紀錄。和舊程式不同，舊程式讓整個序列失敗。
2. 中位數各用各的：R3 照舊用上中位數 `recent[len // 2]`，結果才和凍結資料一樣；爬蟲的期貨防線維持 `statistics.median`。兩個函式分開寫，不共用。
3. adj_close 空的那一列當缺值：那天的價格空白，用到它的 lag 留空白，不退回用 close。
4. 反向合併（使用者交給 Claude 決定）：照樣修正價格和成交量，但不做 R5 的股利乘回，只在清理紀錄記一筆。目前沒有實例。
5. Yahoo 修好 0052 的歷史時，R4 不觸發，資料本來就對。使用者要全自動、不要叫人看：每天的流程沒有要人確認的步驟。對照測試 (b) 只在第一次連網時跑一次，分割那筆不見了、但價格和修正後一致時自動算通過。

## 對照測試

### (a) 離線

- 輸入：`data/reference/data-collection/extra/yfinance/` 的 19 個凍結檔、`data/raw/teacher/`、`data/reference/data-collection/teacher_live/`（只取 ≤ 2026-11-04，10/23 依交易日規則拿掉）。
- 清理開著跑，要 0 筆紀錄（凍結檔再清一次是 0 筆，位元組不變）。
- 日曆剛好 1,660 天，沒有 10/23。
- `stock_ret` 和 24 個市場序列的 lag2、lag5，和 `transform/panel_lag.csv.gz` 逐格相同，空白位置也一樣。用 repr 字串比，或 `pandas.read_csv(..., float_precision="round_trip")`。
- 快速檢查 lag2 有值的列數：sox 1603、usd_twd 1654、us13w 1585、etf_0050 1649、n225 1552、teacher_* 1545。
- lag1 沒有對照答案，用上面的測試值。

### (a2) 離線，測清理

- 輸入：`yfinance_raw_0820473/`（到 2026-08-31）。
- 清理後和凍結檔 ≤ 2026-08-31 的部分比：日期、開高低收、成交量完全相同，adj_close 相對差 ≤ 2e-6（實測 8.2e-7）。
- 紀錄 56 筆，日期和規則都相同：壞報價 2、債市假日 22、佔位 25、分割 1、股利 6。和 62 筆差的 6 筆是 2026-10-12 的兩筆債市假日和 2026-10-23 的四筆佔位K棒。

### (b) 第一次連網之後

- `data/raw/yfinance/` 清理後，取 ≤ 2026-11-04 和凍結檔比。日期集合、開高低收和成交量要相同，≤ 11/04 的 (序列, 日期, 規則) 剛好是那 62 筆。
- adj_close 不比水準，比 lag2：絕對差 ≤ 5e-6（實測最大 9.85e-7），跨過 11/04 之後新除息日的格子除外。
- close 有任何不同就當成 Yahoo 改了歷史，給人看，不放寬容差。
- 11/04 之後的新紀錄（例如 2026-11-11 退伍軍人節）可以接受，記下來。
- 接下來可能的除息（推論，照 2025 年）：0055、006201 約 11 月下旬，NVDA 約 12 月初，TSM 約 12 月中，0050 約 1 月下旬。

## 組員的特徵

- 組員的 notebook 是 `feature_switch_2.ipynb`（不在 repo），讀他自己用 `build_dataset.py` 產生的 `train_data_v2.csv`，lag 欄來自 data-collection 的長表。資料搬過來後，他的腳本要改讀新位置。
- notebook 裡的集合：`us_tech`（sox、tsm_adr、nvda、teacher_ixic 的 lag2）、`key_lag2`（再加 teacher_gspc、teacher_vix、etf_0050、usd_twd，共 8 個）、`all`（24 個市場序列的 lag2、lag5）、另外 `stock_ret_lag2`、`stock_ret_lag5`。
- 組員說要 12 個序列 × lag1、lag2。2026-11-06 傳給組員確認的猜測：`key_lag2` 的 8 個，加 `XGB_TOP20` 裡排最前、又不在 key_lag2 的 gdaxi、n225、etf_0055、stoxx50e。備選是 gold。還不知道 `stock_ret` 算不算在這 24 欄裡。
