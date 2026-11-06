# 交接：爬資料搬到 claude/stock-market-challenger

寫給 `claude/stock-market-challenger` 的 session，2026-11-06 寫在 `claude/data-collection`。內容以 data-collection `a806959`、stock-market-challenger `2e78b5e` 為準，行號都是這兩個 commit 的。下面的數字除了標「推論」的，都在暫存區實際量過。

## 使用者的決定（2026-11-06）

- 爬資料全部交給 stock-market-challenger。data-collection 之後不再爬，資料也不再更新，只留著當對照。
- data-collection 的 `data/` 集中搬到 stock-market-challenger，做法見「搬資料」。
- lag 只用 lag1 和 lag2，不用 lag5。使用者和組員都這樣說。
- 還沒確認的兩件事：
  - lag2 的意思。2026-11-04 定的是「到 i 為止兩天累積的報酬」。另一種讀法是「i 前一天的單日報酬」。使用者已經傳訊息問組員。
  - 組員要哪 12 個序列（12 × lag1、lag2 ＝ 24 欄）。猜的清單見「組員的特徵」。

## 搬資料

### 放到哪裡

| data-collection | stock-market-challenger | tree hash |
|---|---|---|
| `a806959:data/teacher/` | `data/raw/teacher/` | `61da1df7f5d016525649992e50d6eaba46ff426b` |
| `a806959:data/teacher_live/` | `data/raw/teacher_live/` | `50225f19d9c9da9abf2eaf2f63e5bf6026e33bf6` |
| `a806959:data/teacher_live/` | `data/reference/data-collection/teacher_live/` | `50225f19d9c9da9abf2eaf2f63e5bf6026e33bf6` |
| `a806959:data/extra/` | `data/reference/data-collection/extra/` | `281446bd8636d1aa7afcb568d80f0bfe67f06ac9` |
| `a806959:data/features/` | `data/reference/data-collection/features/` | `08b5cb3e52f9434e07a923df50cdfa97ea246119` |
| `a806959:data/transform/` | `data/reference/data-collection/transform/` | `9747c7bc81aa69097c1f3882d408d60f3b6eb935` |
| `a806959:schema.json` | `data/reference/data-collection/schema.json` | blob `19b27071ac8983812080831a276f3c86633bc770` |
| `0820473:data/extra/yfinance/` | `data/reference/data-collection/yfinance_raw_0820473/` | `d22577781283d4032b5c6264cf53346afc01d29a` |

為什麼這樣放：
- 老師資料可以直接當 `data/raw/`。`data/teacher/` 的 102 個檔（LF 換行）和 Training ZIP `7433b271…` 的成員逐位元組相同，`data/teacher_live/` 的 101 個檔（CRLF 換行）和 Live ZIP `eea89fce…` 也相同，比對時拿掉成員名稱開頭的 `data/`。
- `data/extra/yfinance/` 是清理過的，不能放進 `data/raw/yfinance/`。那裡規定放 Yahoo 原樣，`features.py` 會再清理一次，0052 分割前的價格會被除兩次 7。爬蟲下一次執行也會把它整個蓋掉。
- `data/raw/teacher_live/` 每次帶金鑰連網跑都會被新的 Live 蓋掉。對照測試要用長表當時的版本（`eea89fce`，9/1～11/5），所以 reference 另存一份。兩份是同樣的 blob，GitHub 上不多佔空間。
- `0820473` 的 19 個 yfinance 檔是還沒清理的 Yahoo 原樣：2026-11-04 07:35 UTC 抓的，資料到 8/31。拿來測 `features.py` 的清理。
- `data/reference/` 是凍結的快照。只有對照測試會讀，每天的流程不讀，爬蟲也不寫。

### 指令

在 stock-market-challenger 的 checkout、`claude/stock-market-challenger` 分支上跑。這組指令在暫存 clone 跑過一次：每個 tree hash 都對，`python -m pytest` 是 52 passed、4 skipped，和搬之前一樣。

```bash
git fetch origin +refs/heads/claude/data-collection:refs/remotes/origin/claude/data-collection
SRC=origin/claude/data-collection
R=data/reference/data-collection
git cat-file -t 0820473         # 要印出 commit；淺層 clone 可能沒有，先 git fetch --unshallow
git status --porcelain          # 要是空的；同一個資料夾可能有別的 session
test ! -e data/raw/teacher && test ! -e data/raw/teacher_live && test ! -e data/reference
printf '%s\n' '# data/reference/ 是 data-collection 的凍結快照，原樣保存，不改換行' 'data/reference/** -text' >> .gitattributes
git add .gitattributes
git read-tree --prefix=data/raw/teacher/      -u "$SRC:data/teacher"
git read-tree --prefix=data/raw/teacher_live/ -u "$SRC:data/teacher_live"
for sub in extra features transform teacher_live; do git read-tree --prefix=$R/$sub/ -u "$SRC:data/$sub"; done
git read-tree --prefix=$R/yfinance_raw_0820473/ -u 0820473:data/extra/yfinance
git cat-file blob "$SRC:schema.json" > $R/schema.json && git add $R/schema.json
git diff --cached --name-only | grep -Ev '^(\.gitattributes|data/raw/teacher/|data/raw/teacher_live/|data/reference/data-collection/)'   # 要沒有輸出
```

commit 之後核對（期望值見上表）：

```bash
for p in data/raw/teacher data/raw/teacher_live $R/teacher_live $R/extra $R/features $R/transform $R/yfinance_raw_0820473 $R/schema.json; do echo "$p $(git rev-parse HEAD:$p)"; done
python -m pytest -q
```

要注意的事：
- `git read-tree --prefix` 遇到目標路徑已經存在，或那裡有沒追蹤的檔，會失敗（exit 128），所以先跑 `test ! -e`。
- commit 前想取消：`git rm -r -q --cached --ignore-unmatch data/raw/teacher data/raw/teacher_live data/reference && rm -rf data/raw/teacher data/raw/teacher_live data/reference && git restore --staged --worktree .gitattributes`。資料夾是共用的，不要用 `reset --hard`。
- 大小：`data/raw/` 約 45.6 MB，`data/reference/data-collection/` 約 31 MB。最大的檔是 `panel_lag.csv.gz`，6.9 MB。
- push 會上傳約 32～35 MB。這些 blob 雖然已經在 data-collection 分支上，git 只把父 commit 的內容當成遠端已有。
- commit 照這個分支自己的規則：不加 `Co-Authored-By`，只 `git add` 自己動的檔。

### 搬完之後爬蟲第一次跑會怎樣

- `data/raw/manifest.json` 還不存在，所以第一次會下載 Training 一次，再整包換進去。內容一樣，`git diff data/raw/teacher` 應該是空的。兩邊用新爬蟲的算法算出的 `files_sha256` 都是 `1c17e27f…`，Live 是 `4675ae4d…`。第二次就會跳過 Training。
- 研究模式沒有 `COURSE_LIVE_KEY` 時會跳過 Live，`data/raw/teacher_live/` 不動。帶金鑰跑時會換成新的 Live，diff 應該只有新增的列。
- 新舊兩套指紋的算法不同，不能拿來互相比。舊的 `members_sha256` 路徑帶 `data/`，而且先把 CRLF 換成 LF（舊 `crawler.py:659-661`）。新的 `files_sha256` 路徑不帶 `data/`，用原始位元組（`src/crawler.py:114-117`）。Training 舊的是 `31bbdc99…`、新的是 `1c17e27f…`。
- `schema.json` 和 `extra/manifest.json` 裡的路徑是相對舊 repo 根目錄的（例如 `data/extra/…`）。對照測試要先換路徑：`data/teacher` → `data/raw/teacher`，`data/{extra,features,transform,teacher_live}` → `data/reference/data-collection/…`。換完之後 19 個 manifest 指紋、schema 的 268 個檔案指紋和長表的指紋都對得上。

### 搬完要改的文件（stock-market-challenger）

- `README.md:24`、`:29-35`：檔案樹加上 `data/reference/data-collection/`，說明 `teacher/`、`teacher_live/` 一開始是從 data-collection 搬來的。
- `memory/context/data-rules.md:39-47`：資料放在這個分支的那段要加 `data/reference/` 的規則（凍結、只讀、`-text`、只給對照測試用），大小改成約 77 MB。
- `memory/context/environment.md:15`（現在是 52 passed、4 skipped）、`:25`、`:49`（長表範圍是 2020-01-02～2026-11-04）。
- `notebooks/README.md:12`：現在叫人去用 data-collection 的 `data/teacher/` 而且不要 commit，要改成讀 `data/raw/teacher*`。
- `memory/projects/kaggle-models.md:20-32`、`:199`：資料來源、BASE 網址（還是舊分支名 `claude/peaceful-babbage-09xeie`）、範圍（寫到 9/30，實際到 11/4）。這份可能是另一個 session 在用，改之前先問使用者。
- `CLAUDE.md:5`（狀態）、`:11-19`（memory 表，`kaggle-models.md` 本來就漏列）。
- `.gitignore:33` 的註解、`src/features.py:44`（清理紀錄改到 `data/reference/data-collection/extra/manifest.json`）、`memory/projects/crawler.md:13`、`:157`、`:195-199`。

## 交易日和 i

現在有三套規則互相矛盾：
- data-collection 用寫死的 `LIVE_CLOSED_DAYS` 把 10/23 從日曆拿掉（舊 `crawler.py:70-73`），所以 t = 10/27 的 i 是 10/22。
- 新爬蟲取 `phase2Days` 裡早於 t 的最後一天。那天在 Live 裡還沒填好，就退回最後一個填好的日子（`src/crawler.py:450-471`）。
- `src/features.py:19-22` 的說明打算把 `phase2Days` 裡有的 Live 待定列也算成交易日。如果 `phase2Days` 有 10/23，訓練特徵的 i 會是 10/23，每天預測時的 i 卻是 10/22，兩邊對不上。

建議統一成一條規則，爬蟲和 `features.py` 呼叫同一個函式：
- 某天算台股交易日的條件：老師個股資料那天已經填好。也就是 100 檔裡至少 `crawler.min_stocks_filled` 檔的 `y` 是 0 或 1，而且 `etl:adj_open`、`etl:adj_close` > 0。
- i 是 t 之前最後一個這樣的日子。
- 還是 `-1` 的列（10/23、當天早上 t 那列）不當 i，往回數 i−k 時也不算。那天 global 表的列也不用。
- 單一檔股票那天是 `-1` 或沒有列（停牌），就當這檔沒有那一列。
- `phase2Days` 只用來決定 t，不會讓日曆多出日子。
- 可以在 config 加 `closed_days: [2026-10-23]`。那天如果之後出現數值就停下來，和舊程式一樣。

這條規則下，長表的日曆剛好是 1,660 天（2020-01-02～2026-11-04，沒有 10/23），和舊程式相同。

Live 的 `-1`：`eea89fce` 的 global 表裡只有兩列有 `-1`。10/23 是 `^TWII`、`TX_OI`；11/05（t 那列，08:55 下載）是 `^TWII`、`^KS11`、`TX_OI`。07:10 時 `^VIX` 是不是 `-1` 沒量過，所以建議 6 欄（`^VIX ^IXIC ^GSPC ^TWII ^KS11 TX_OI`）的 `-1` 都當缺值，一格一格判斷。

## lag 的公式

符號：
- i：t 之前最後一個台股交易日。
- close：股票和 ETF（TSM、NVDA、0050、0052、0055、006201、老師個股）用還原收盤價 `adj_close`，其他用 `close`。
- i−1、i−2：往回數這個序列自己的列。

公式：
- lag_k(t) = (close_i − close_{i−k}) / close_{i−k}，k = 1、2。
- 序列在 i 那天沒有K棒就留空白，不往前找。兩個端點任一是空的或 ≤ 0 也留空白（例如 WTI 2020-04-20 是 −37.63，^IRX 2020-03 有負值）。

要寫成 `(cur − base) / base`。用 `cur / base − 1`（pandas `pct_change` 的寫法）時，76,675 個有值的市場格裡有 74,262 個最後一位不同，最大差 4.4e-16。用 pct_change 的話，對照測試的容差設成絕對值 1e-15。

lag1 的測試值（data-collection 的凍結資料，算過兩次）：

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

要知道的副作用：
- 老師 global 的 `^GSPC`、`^IXIC`、`^VIX` 每一列已經是前一個美股交易日的值，所以 `teacher_gspc` 的 lag1 比 yfinance 美股的 lag1 晚一天。實測 `teacher_gspc` lag1 和前一列的 `dji` lag1 相關 0.867，和同一列只有 −0.176。
- 只用 lag1、lag2 時，台股連休中間那幾天的美股報酬不會出現在任何一列。例如 SOX 10/23 的 +0.44%。以 SOX 來說，這種日子從 20 天變成 57 天。
- 停牌或休市之後，lag1 會跨過整段空檔，分布會有長尾。

## yfinance 清理規則

`src/features.py:39-44` 和 `memory/projects/crawler.md:15` 只寫了 4 條，而且有幾處寫法和舊程式不同。下面是舊程式實際做的，照順序執行（舊 `crawler.py:493-625`）。紀錄裡的價格是 Yahoo 原始單位，還沒做分割修正。

### R0 先篩掉不能用的列（全部序列，`validate_rows`，舊 `:493-512`）

- None、bool、NaN、inf 都當空值。
- close 是空的列整列拿掉。新爬蟲把 NaN 存成空字串（`src/crawler.py:631-649`），所以 `features.py` 要自己做這一步。
- 期貨和殖利率以外的序列出現 close ≤ 0：整個序列失敗，沿用舊檔。日期重複也一樣。
- 依日期排序。

### R1 壞報價（全部 19 個序列，舊 `:579-583`）

low、high 都有值而且 low ≤ high 時才檢查。close < low − 0.005 × |low|，或 close > high + 0.005 × |high|（嚴格不等式），就刪掉這一列。只看 close。

### R2 債市假日的平盤K棒（只有 ^TNX、^IRX，舊 `:584-586`、`:535-547`）

開高低收四個價格相同（不看 adj_close 和成交量），而且日期是哥倫布日（10 月、週一、8～14 號）或退伍軍人節（11/11；碰到週六提前到 11/10，碰到週日延到 11/12），就刪掉。下一個符合的日子是 2026-11-11（週三），在 Phase 2 期間。

### R3 佔位K棒（只有股票和 ETF：TSM、NVDA、0050、0052、0055、006201，舊 `:590-602`）

依日期掃 R1、R2 留下的列。第一列一定保留。只看開高低收相同的K棒：
- 成交量是 0 或空的，而且 close 和前一個「保留下來的」列的 close 完全相等，就刪掉。比的是保留下來的那列，所以連續停牌時，每一根都和停牌前最後一根比。
- 其他情況：取前 21 個保留下來的列裡不是 0 的成交量，排序後取 `recent[len // 2]`（偶數個時取上中位數，和 `statistics.median` 不同）。成交量不是 0 而且小於這個數的 1%，就刪掉。這是不完整的K棒。
- 成交量是 0 但 close 和前一列不同的平盤K棒，兩條都不成立，保留。

### R4 台股分割（股票和 ETF，舊 `:603-623`、`:515-524`）

看相鄰兩個保留下來的列 (prev, cur)：
- ratio = prev.close / cur.close，n = round(ratio)。2 ≤ n ≤ 50 而且 |ratio − n| / n < 0.03，factor 就是 n。不成立時用 1/ratio 再檢查一次，成立的話 factor 是 1/n（反向合併）。任一價格是空的或 ≤ 0 就不算。
- adj_close 的比值也要算出一模一樣的 factor。
- 代號不是 `.TW`、`.TWO` 結尾（TSM、NVDA）時只記錄，不改資料。
- 台股：分界那列之前的每一列，open、high、low、close、adj_close 都除以 factor，成交量乘以 factor。分界那列和之後不動。迴圈繼續往下掃時，用的是修正過的值。

### R5 分割前的股利調整乘回去（舊 `:550-566`）

R4 修正台股之後立刻做。Yahoo 對分割前的除息只調了約 1/n。
- r_t = adj_close / close（用已經除過 factor 的值），範圍是分界之前的列。分界前不到 2 列，或有空值、0、≤ 0，就直接結束。
- level 從分界前一列的 r 開始，那一列的 adj_close 不改。
- 從分界前第二列往回到第一列：step = 1 − r_t / r_{t+1}。step > 1e-5 時，fixed = min(step × factor, 0.95)，level 乘上 (1 − fixed)，記一筆 {ex_date = 下一列的日期, yahoo_fraction = step, rescaled_fraction = fixed}。否則 level 乘上 r_t / r_{t+1}，保留 Yahoo 原本的比值。
- 每一列的 adj_close 設成 close × level。

### 刪掉的列要整列拿掉

刪掉的列不能留成空白的一列。實測如果把 R1～R3 刪的 55 列留成空白位置，7 個序列會有 295 個 lag2、lag5 格和長表不同。

### 測試資料

凍結的 `extra/manifest.json` 有 62 筆紀錄，每筆都有原始值，可以直接當測試資料：
- 壞報價 2 筆：usd_twd 2020-12-08、2024-08-28。
- 債市假日 24 筆：^TNX、^IRX 各 12 天，2020-10-12、2020-11-11、2021-10-11、2021-11-11、2022-10-10、2022-11-11、2023-10-09、2024-10-14、2024-11-11、2025-10-13、2025-11-11、2026-10-12。
- 佔位K棒 29 筆：成交量 0 的 26 筆（006201 10 筆、0050 7 筆、0052 7 筆、0055 2 筆，含 2026-10-23 颱風假的 4 筆），不完整的 3 筆（0050、0052、0055 都在 2024-11-20）。
- 分割 1 筆：0052，分界 2025-11-17，factor 7。2025-11-14 原始 (O 248.3000030517578, H 249.64999389648438, L 248.0500030517578, C 248.5, adj 242.5469207763672, V 5021929)，修正後 (35.47142900739397, 35.66428484235491, 35.43571472167969, 35.5, 34.6495601109096, 35153503)。
- 股利乘回 6 筆，都是 0052（yahoo_fraction → rescaled_fraction）：2020-04-22 0.0042352 → 0.0296467、2021-04-20 0.0011495 → 0.0080467、2022-04-20 0.0120857 → 0.0845996、2023-04-21 0.0053832 → 0.0376827、2024-04-18 0.0057143 → 0.0400004、2025-04-23 0.0030159 → 0.0211113。分割後的 2026-04-20 是 Yahoo 自己調的，不動。

要保留、不能刪的反例：
- usd_twd 2020-03-31、006201 2021-09-13：close 在高低區間外，但只超出 0.358%、0.368%，不到 0.5%。
- ^TNX 2023-11-10：日期符合退伍軍人節的規則，但不是平盤。
- 0050、0052 的 2025-04-07、04-10：跌停平盤，成交量正常。
- 006201 2023-11-01：平盤，成交量 1000，是中位數的 5%。
- 0055 2020-09-18：close 等於前一列，但成交量 10188，是中位數的 25%。

### 還沒決定的細節（問使用者）

- close ≤ 0 和日期重複時，要照舊讓整個序列失敗（當天這個特徵空白），還是只丟那一列。
- 中位數照舊用上中位數。新爬蟲的期貨低量防線用的是 `statistics.median`，兩個地方不要混用。
- adj_close 空的那一列，舊程式退回用 close，會讓同一序列混用兩種價格。凍結資料裡沒有這種列。
- 反向合併時 R5 會把股利比例乘上 1/n，意思有疑問，目前沒有任何實例。
- 如果 Yahoo 以後修好 0052 的歷史，R4 就不會觸發，紀錄數會對不上。

## 對照測試

新的 `features.py` 要通過三組比對。lag 的函式寫成通用的 k，用 k = 2、5 對長表，正式只產 k = 1、2。

### (a) 離線，搬完就能做

- 輸入：`$R/extra/yfinance/` 的 19 個凍結檔、`data/raw/teacher/`、`$R/teacher_live/`（只取 ≤ 2026-11-04，10/23 依上面的規則拿掉）。
- 清理開著跑，要 0 筆紀錄（實測凍結檔再清一次是 0 筆，位元組不變）。
- 日曆要剛好 1,660 天，沒有 10/23。
- `stock_ret` 和 24 個市場序列的 lag2、lag5，要和 `$R/transform/panel_lag.csv.gz` 逐格相同，空白的位置也要一樣。比的時候用 repr 字串，或用 `pandas.read_csv(..., float_precision="round_trip")` 讀。實測用舊公式重算 24 個市場序列 × 2 個 lag，加上 100 檔 × 2 個 lag 共 332,000 個個股格，0 個不符。
- lag2 有值的列數可以當快速檢查：sox 1603、usd_twd 1654、us13w 1585、etf_0050 1649、n225 1552、teacher_* 1545。
- lag1 沒有對照答案，用上面「lag 的公式」的測試值。

### (a2) 離線，測清理

- 輸入：`$R/yfinance_raw_0820473/`（Yahoo 原樣，到 2026-08-31）。
- 清理後和凍結檔 ≤ 2026-08-31 的部分比：日期、開高低收、成交量完全相同，adj_close 相對差 ≤ 2e-6（實測 8.2e-7）。
- 紀錄要 56 筆，日期和規則都相同：壞報價 2、債市假日 22、佔位 25、分割 1、股利 6。和 62 筆差的 6 筆是 2026-10-12 的兩筆債市假日和 2026-10-23 的四筆佔位K棒。
- 上面的反例寫成單元測試。

### (b) 第一次連網之後

- `data/raw/yfinance/` 清理後，取 ≤ 2026-11-04 的部分和凍結檔比。
- 一定要相同：日期集合、19 個序列的開高低收和成交量（三次抓取之間實測 0 處不同）、≤ 11/04 的 (序列, 日期, 規則) 剛好是那 62 筆。
- adj_close 的水準不比，改比 lag2：絕對差 ≤ 5e-6（實測最大 9.85e-7）。跨過 11/04 之後新除息日的那幾格除外。Yahoo 每次抓都把到抓取當下為止的所有除息套到之前每一列，比例相同，所以不跨除息日的報酬不受影響。
- close 有任何不同，就當成 Yahoo 改了歷史，給人看，不放寬容差。
- 11/04 之後出現的新紀錄（例如 2026-11-11 退伍軍人節）可以接受，但要記下來。
- 接下來可能碰到的除息（推論，照 2025 年的日期）：0055、006201 約 11 月下旬，NVDA 約 12 月初，TSM 約 12 月中，0050 約 1 月下旬。

## src/crawler.py 要調整的地方

改之前照這個分支的規則，先跟使用者講清楚，等確認再寫。

1. 課程網站登入的 POST 只送一次（`:236`、`:240-241`、`:295-304`、`:867`）。一次逾時或 5xx，整次就停。每日模式讀不到 `/api/state` 也停（`:873-875`），Live 抓 3 次失敗丟 `CrawlerError`（`:508-527`）。登入不是上傳，可以考慮遇到暫時性錯誤重試 2 次，但和「POST 失敗不自動重試」的規則有關，要使用者決定。`/api/state` 失敗時，可以改用快取的 `data/raw/phase2_days.json`（裡面要有 t）。
2. 截止時間（08:30）在登入、`/api/state`、Training、Live 第一次嘗試之前都沒檢查（`:867`、`:869`、`:490`、`:515`、`:242`）。課程網站和 Live 是串流下載，(10, 90) 秒的逾時只限制兩塊資料之間的等待，整個下載沒有總時間上限（`:253`、`:272`）。從 config 推算，yfinance 開始前最壞要約 38 分鐘（推論）。如果 08:15 才觸發（`open-questions.md:11` 的提案），可能超過 08:50。建議每一步之前都檢查截止，每個請求加總時間上限。
3. 08:30 以後才開始跑時，19 個序列都標 `skipped_deadline`，舊檔留著（`:798-800`、`:778-781`）。檢查 i 那根只看 status 是 ok 的序列（`:816-819`），留著的舊檔不會被檢查。所以 `features.py` 一定要在每個序列檔裡找日期剛好是 i 的那一列，不管 manifest 寫什麼，不能用「最後一根 ≤ i」。爬蟲這邊建議每個序列都記 `has_bar_i`。
4. Yahoo cookie 的 bug：快取裡的 cookie 沒有叫 A3 的那一個時，yfinance 1.7.0 的 `data.py:211` 會丟 `KeyError`。它不算暫時性錯誤（`data.py:19-28`），重試 3 次結果都一樣（`src/crawler.py:737-738`），19 個序列全部失敗，光等就約 11 分鐘。壞掉的 cookie 存在 `.cache/yfinance/cookies.db`，之後每次都會壞，直到有人刪掉。已經用 yfinance 1.7.0 重現。修法：把 `YfData._load_cookie_curlCffi` 包一層，遇到 `KeyError` 回傳 False，再加一個離線測試。
5. 約六分之一的日子會有序列沒有 i 那根：1,660 天裡有 282 天（17.0%）至少一個序列缺，多半是外國放假。每次都等 60 秒重抓、標 `stale`、回傳 3（`:821-841`）。最近會遇到：t = 2026-11-24 缺 N225（日本 11/23 放假），t = 2026-11-27 缺 9 個美國相關序列（感恩節）。建議只有 `no_bar_i` 時不設 `stale`，另外記在 `run.no_bar_i`，回傳 3 留給真的失敗。`run_daily.py` 也要照這個處理。
6. `run.http_requests` 只算 Yahoo 的請求（`:893-895`）。建議改名 `yahoo_requests`，另外加 `site_requests`。
7. 兩個過時的註解：`configs/config.yaml:52` 寫「最後一根量太小就丟掉」，程式只記錄不丟（`:676-682`）。`configs/config.yaml:75` 是 `lags: [2, 5]`，要改成 `[1, 2]`，`src/features.py:6` 的例子和 `memory/glossary.md:23` 一起改。

## 第一次連網試跑要查的事

除了 `memory/projects/crawler.md:195-199` 原本列的：
- `run.http_requests`：沒有快取時約 40，有快取約 20。如果是 78，代表 cookie 沒存起來。
- TWD=X：07:10 存一份 1d 和最近 5 天的 1h，10:00 左右和隔天早上各再抓一次。看 i 那根的 close 三次是否相同、是否等於倫敦 i 日 00:00 那一小時的 close。data-collection 用小時K量過，日期 d 那根的 close 大約是倫敦 d 日 00:00～01:00 的報價（台北 d 日早上），這樣 07:10 時已經定了。這個分支寫的「台北 08:00 才收完」是保守的上限。三次不同的話，TWD=X 改用 i−1 那根，或拿掉。
- 07:10 時 Live t 那列的 `^VIX` 是不是 `-1`。
- `/api/state` 的 `phase2Days` 有沒有 10/23，過去日子的 `enabled` 是多少。
- `git diff data/raw/teacher` 要是空的；`data/raw/teacher_live` 只多新的列。

## 爬蟲要跑多久

- 時間主要花在限流：每個請求之間等 2 秒再加 0～1 秒。沒有快取時 40 個請求（每個代號查時區和抓日K各 1 個，加 cookie、crumb），等約 92～97 秒。保留 `.cache/yfinance` 時 20 個請求，約 48 秒。
- 只抓一小段日期省不了時間。一個代號就是一個請求，完整歷史 165 KB 花 0.71 秒，兩週 2.4 KB 花 0.33 秒，19 個代號加起來只省約 7 秒。
- 正常一次 1～2 分鐘，07:10 開始、07:12 前完成。Live 晚兩次多 6 分鐘。Yahoo 那段最壞會被 08:30 擋下，約 08:33 結束。這幾個數字是模擬的，網路延遲用假設值。
- 真正會遲交的是觸發時間（GitHub Actions 11/04 晚 3 小時 42 分到 6 小時 17 分，11/05 晚約 4 小時），以及上面第 1、2 點的單點失敗。

## 其他過時的說法（stock-market-challenger）

- `memory/context/data-rules.md:24`、`src/features.py:21`：10/23 寫「很可能是休市日」。使用者 2026-11-05 已確認是颱風假。
- `memory/context/data-rules.md:43`：寫「adj_close 每次重抓浮動小於 1e-6」，實測 0052 是 1.041e-6。同一行的「除息後整欄重算」也要改成：Yahoo 每次抓都把到抓取當下為止的除息套到之前每一列。
- `memory/context/open-questions.md:23`：還寫 system-completion、dev、deep-research 在 GitHub 上，這三個已經刪了。`:34-36` 的通知方式已經決定，照 CLAUDE.md 的規則搬走。
- `src/features.py:39-44`：清理只列 4 條，照上面的 R0～R5 補齊。

## 組員的特徵

組員的 notebook 是 `feature_switch_2.ipynb`，不在 repo 裡。它讀組員自己用 `build_dataset.py` 產生的 `train_data_v2.csv`，裡面的 lag 欄來自 GitHub 上 data-collection 的長表。資料搬過來之後，他的腳本要改讀新的位置。

notebook 裡的市場集合：
- `us_tech`：4 欄，sox、tsm_adr、nvda、teacher_ixic 的 lag2。
- `key_lag2`：8 欄，上面 4 個加 teacher_gspc、teacher_vix、etf_0050、usd_twd 的 lag2。
- `all`：48 欄，24 個市場序列的 lag2、lag5。
- 另外 `stock_ret_lag2`、`stock_ret_lag5`。

組員說要 12 個序列 × lag1、lag2 ＝ 24 欄。notebook 沒寫是哪 12 個。2026-11-06 傳給組員確認的猜測是 `key_lag2` 的 8 個，加上 `XGB_TOP20` 裡排最前面、又不在 key_lag2 的 4 個：gdaxi、n225、etf_0055、stoxx50e。備選是 gold（在 XGB_TOP20 出現兩次）。還在等組員回覆，也還不知道 `stock_ret` 算不算在這 24 欄裡。

`features.py` 可以先把 25 個序列的 lag1、lag2 都產出來，模型再挑欄。爬蟲照 2026-11-05 的決定繼續抓 19 個序列。
