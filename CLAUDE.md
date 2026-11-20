# 給 Claude Code 的規則

這是課程 ML 期末專案（2026 秋）的比賽主程式，分支 `claude/stock-market-challenger`，repo `jiangjiangian/ml-final-2026-fall`。每個台股交易日的台北 09:00 前，預測 50 檔股票當天會不會「收盤高於開盤」（`y = 1` 代表 `adj_close > adj_open`），把 0/1 寫成 CSV 上傳課程網站。

`src/crawler.py`、`src/features.py` 已實作，離線測試通過。2026-11-06 第一次連網試跑（研究模式，t = 11/06，沒有上傳）：老師 Training／Live（Live 用原本的網址、只信任 `configs/live_ca.pem`）、yfinance、期交所台指期都抓到，特徵表 32 個模型欄，兩輪獨立檢查沒有 blocker，`data/raw/`、`data/processed/` 已推上去給組員。2026-11-07：`run_daily_test.py` 串起爬蟲、特徵、組員的邏輯迴歸（`src/online_lr.py`）和上傳（`src/submit.py`、`src/site_api.py`）。排程在學校的 oop.cs.nccu.edu.tw（台北 07:10、07:25、07:40、07:55、08:05，使用者 2026-11-07 從 GCP 改過來、11-08 加到五次；11-11 加 08:25，只補日韓當天的開盤；11-17 加傍晚打分，11-18 起 16:10、20:00），使用者 Mac 08:15 起的備援寫好了但沒有裝（2026-11-09 查到 launchd 沒有這個工作，使用者決定先不裝），現在只有 oop。`submit.enabled` 是 true，`submit.phase` 決定交 Phase 1 還是 2（細節在 `memory/context/02-pipeline.md`）。當時 `train.py`、`predict.py`、`run_daily.py` 是骨架（2026-11-15 刪掉骨架，`run_daily.py` 換成正式的主程式）。2026-11-09：證交所、櫃買回補完（2020-01-02～2026-11-06）；長表加 17 欄給組員研究（交易所估值和委買賣、日韓開盤跳空、老師 S&P 500／Nasdaq 用 t 那列的版本、`kospi`），都不進 `model_columns`；每天抓交易所的 `exchange.enabled` 使用者 2026-11-10 打開，11-11 第一次跑成功。2026-11-11：VIXTWN、CNN 恐懼貪婪（使用者 2026-11-09 要的）推上去，爬蟲多兩步、長表多 4 欄變 84 欄，也都不進 `model_columns`，11-12 07:10 第一次正式跑。2026-11-11：使用者要台股開盤前拿到日韓當天的開盤，選了 yfinance、08:25 抓、只寫進長表：`crawler.open_today()` 從 Yahoo 一分鐘K棒抓，存 `data/raw/open_today/`，`run_daily_test.py` 抓到後重寫特徵表，t 那列的 `kospi_open_gap`、`n225_open_gap` 才有值；每日模型和上傳不變，11-12 08:25 第一次正式跑（細節在 `memory/projects/01-crawler.md`、`03-features.md`）。2026-11-11：使用者要一個網址給組員拿所有原始資料的每個欄，`src/merge_raw.py` 把 `data/raw/` 併成 `data/merged/` 的個股表和市場表，每格是來源的原字串、不對齊 t，排程每次上傳後更新，失敗不擋上傳，不碰 `data/processed/`（細節在 `memory/context/05-data-rules.md`、`02-pipeline.md`）。2026-11-09 那批程式和重建的 `data/processed/`（80 欄）、交易所原始檔、`kospi.csv` 在 11-09 下午一起推上去。2026-11-11 晚上組員把特徵表改成 107 欄、模型欄 55 欄（個股自己的 lag、盤中報酬、跳空、成交股數、前一天 OHLC），只推了程式；11-12 01:05 在 oop 重建 `data/processed/` 補推。2026-11-12 18:35 組員又加 3 個產業欄（110 欄，模型欄不變）、一樣只推程式，23:09 在 oop 重建補推（`memory/context/02-pipeline.md`）。2026-11-12：使用者要每天交件的模型暫時換成目前回測最穩定的，早上先用 `persist`（`src/persist_rule.py` 的持續性規則，每天 25 檔猜漲、25 檔猜跌，不看大盤方向）；同一天晚上使用者決定換成排名集成，`configs/config.yaml` 的 `daily_model.kind` 是 `rank_ensemble`（`src/rank_ensemble.py`，Kaggle notebook 16 的 `X_price`，每天早上重訓三個模型，也是 25 漲 25 跌），`fallback` 是 `[persist, online_lr]`，算不出來時照順序換；換模型改 `kind` 和 `fallback` 兩行（細節在 `memory/context/02-pipeline.md`、`memory/reference/05-daily-model.md`）。2026-11-15 晚上使用者決定換成 `c2v2d`（`src/c2_tilt.py`，排名集成再依大盤方向換高低 β，狀態都是 07:10 前就有的），`fallback` 是 `[c2, rank_ensemble, persist, online_lr]`，11-16 起生效，12-06 再看要不要改成 `c2`。2026-11-16 使用者要每天影子跑：`daily_model.shadow` 的五個模型（2026-11-20 加第六個只記不交的 `overnight_up`：前一晚美股大跌就全猜漲，`src/models/m5_overnight_up.py`，BT 研究的前 10% 規則）交件後都算一遍，存 `data/submission/shadow_<t>.csv`、不上傳，組員先手動交的日子也做；同一天也決定請組員別再先手動交（細節在 `memory/context/02-pipeline.md`）。2026-11-17：排程不上傳的日子（組員先交、已經交好、上次送出沒核對完成、網站讀不到），t 還沒爬過也補爬（`run_daily.py` 的 `ensure_crawled`）；SD 01 回測看不出 t 當天開盤前的資料有用，08:47 不做模型重算（`memory/projects/12-same-day-features.md`）。同一天使用者決定：排程交的那份資料不完整（用了備援，或方向模型的狀態有缺）時，之後的時段補齊後預測變了就重交，一天最多多交一次（`complete_<t>.json`）；GitHub 連不上時重試約 2 分鐘再用本機的程式照爬照交（`submit.require_push_before_post: false`，裝第二台排程前改回 true）；傍晚打分（`src/pipeline/step6_evening_score.py`，oop 16:10、20:00 跑 `run_daily.py --sync --evening`）只下載老師 Live，當天就替影子跑和網站上我們那份打分，寫 `shadow_scores.csv`、`site_scores.csv`，不上傳、不重建特徵表（細節都在 `memory/context/02-pipeline.md` 的「2026-11-17 的決定」）。2026-11-15 晚上使用者要照一般機器學習專案整理 `src/`（細節交給 Claude）：每天的流程照順序放 `src/pipeline/step1_crawler.py`～`step5_merge_raw.py`（加 `site_api.py`、`utils.py`），模型照日期放 `src/models/m1_online_lr.py`～`m4_c2_tilt.py`，排程跑 `run_daily.py`（`run_daily_test.py` 只轉過去），`models/` 只放訓練好的模型檔、現在是空的；這段之前寫的舊檔名對照在 `memory/context/02-pipeline.md` 的「檔案結構為什麼這樣」。之後特徵欄位再變，程式和 pull 之後 `--rebuild` 的 `data/processed/` 一定要同一次推，少一樣每天的特徵會因為欄位不同停下；先 pull 再重建、避開台北 07:00～08:40 推，步驟在 `memory/context/02-pipeline.md` 的「特徵欄位變了怎麼推」。

## 先讀哪個檔

細節都在 `memory/`，一個主題一個檔。動手前讀相關的那幾份：

| 要做的事 | 讀 |
|---|---|
| 新增、搬動、刪除 memory 或 notebooks 的檔：放哪個資料夾、檔名怎麼編號、要一起改哪裡（2026-11-16） | `memory/README.md`、`notebooks/README.md`（子資料夾各有一份 README） |
| 查名詞 | `memory/reference/01-glossary.md` |
| 給組員查的說明（2026-11-12 從 README 移過來）：特徵表每一欄、合併表、每天交件的模型、排程主機、證交所和櫃買 | `memory/reference/` 的 `02-feature-table.md`、`04-merged-data.md`、`05-daily-model.md`、`06-runner-hosts.md`、`03-exchange-backfill.md` |
| 比賽規則、課程網站 API、上傳的規矩、Phase 1 結果 | `memory/context/01-competition.md` |
| 每天的流程、指令、失敗時怎麼手動交 | `memory/context/02-pipeline.md` |
| 寫爬蟲或特徵：時間對齊、美股日期、-1、交易日曆、資料存放 | `memory/context/05-data-rules.md` |
| 本機環境、分支、舊系統封存、skills、輸出風格 | `memory/context/04-environment.md` |
| 還沒決定的事和線索 | `memory/context/03-open-questions.md` |
| `src/pipeline/step1_crawler.py`（爬蟲）的設計和進度 | `memory/projects/01-crawler.md` |
| `src/pipeline/step2_features.py`（特徵）的規劃：清理規則、交易日、lag 公式、對照測試 | `memory/projects/03-features.md` |
| Kaggle 上平行訓練的模型研究（另一個 session 在用） | `memory/projects/02-kaggle-models.md` |
| 2026_1111 原始特徵實驗（Kaggle 01～37、07b、09b）的方法、結果、下一步 | `memory/projects/04-raw-feature-experiments.md` |
| 實驗設計的審稿（第三方 agent）、排行榜的事實、AutoML 和調參數、文獻、還沒決定的事 | `memory/projects/05-experiment-critique.md` |
| 特徵篩選和模型集成的文獻（2026-11-14 研究 workflow，查證過的 108 篇）和收斂的實驗計畫 | `memory/projects/10-literature-features-models.md` |
| Decider（開盤前猜當天大盤盤中方向的模型，Kaggle D01 起，使用者 2026-11-12 用 `/goal` 加 `/loop` 交辦）：先讀狀態檔的階段和下一步，定義、每本的數字、事先寫好的判斷在專案檔 | `memory/projects/06-decider-research-state.md`、`memory/projects/07-decider-market-direction.md` |
| 大盤擇時 MT（每天依大盤預測調猜漲的檔數，Kaggle MT 01 起，使用者 2026-11-13 用 `/goal` 交辦，和 Decider 分開）：先讀狀態檔，文獻辯論、評估規則、事先登記、每本的數字在專案檔 | `memory/projects/08-market-timing-research-state.md`、`memory/projects/09-market-timing.md` |
| 當天開盤前資料 SD（t 當天 09:00 前的日韓開盤、台指期 08:45 開盤能不能讓每個模型變好，Kaggle SD 01 起，使用者 2026-11-17 交辦；回測變好才做 08:47 重算重交）：事先登記、每本的結果 | `memory/projects/12-same-day-features.md` |
| 突破研究 BT（在模擬 Phase 2 超過第一名：第一名的分數解剖、選擇性擇時、HMM 和馬可夫切換、動態追蹤，Kaggle BT 01 起，使用者 2026-11-15 用 `/goal` 交辦，和 Decider、MT 分開）：狀態、主持人查到的事實、評估規則、每本的六段紀錄 | `memory/projects/11-breakthrough-research.md` |
| 解封研究 UB（不綁 25 漲 25 跌、自己決定每天猜幾檔漲的模型，Kaggle UB 01 起，使用者 2026-11-19 交辦；過關標準是回測贏 c2v2d 再影子跑 5 天，過關前每天照交 c2v2d）：目標、使用者的決定、以前測過的、規則 | `memory/projects/13-unbound-count-model.md` |

`README.md` 給組員看，只放四樣（使用者 2026-11-12）：流程（爬蟲 → 特徵 → 模型 → 上傳）、組員怎麼拿資料、特徵表的摘要和連結、檔案樹。其他細節寫在 `memory/reference/`，用組員看得懂的寫法，README 只放連結；特徵欄有增減或定義改了，改 `memory/reference/02-feature-table.md`。新增、搬動或刪除檔案時，改 `README.md` 的檔案樹；`memory/` 多了或少了檔案時，也改上面的表。`memory/` 裡的路徑都從 repo 根目錄算。

### memory/ 怎麼維護

- 整理原則在 `memory/README.md`（使用者 2026-11-16）：只有 `context/`（規則和環境）、`projects/`（每條工作線）、`reference/`（給組員查）三個資料夾，最上層只放 README。檔名 `NN-名字.md`，NN 是在那個資料夾建立的順序；新檔用下一個號碼，刪掉的號碼空著、不重新編號；自動研究的狀態檔用 `-state` 結尾，放在 `projects/`。搬動或刪除後，grep 舊路徑要找不到任何一行。
- 使用者做了決定，寫進對應的檔，標上日期（例如 2026-11-05）。
- `03-open-questions.md` 的問題有答案後，搬到對應的檔，再從清單拿掉。
- 這份 `CLAUDE.md` 只放索引和最重要的規則，細節寫在 `memory/`。

## 工作方式

- 回覆用繁體中文。
- 補程式前，先把要寫的東西和定義講清楚，等使用者確認後才實作。
- 要使用者做決定時，用選擇題問（AskUserQuestion），推薦的選項放第一個。每題自己講清楚，不用 i、E 這類代號；金融名詞（K棒、成交量、指數）先用白話解釋。
- 同一個資料夾可能有別的 session 在工作（例如 `notebooks/kaggle/`、`memory/projects/02-kaggle-models.md`）。commit 時只 `git add` 自己改的檔，不用 `git add -A`。
- 審查或測試有發現問題時，等結果全部出來再一起修。
- 只在 `claude/stock-market-challenger` commit 和 push。沒有使用者同意，不推其他分支、不開 PR。commit 不加 `Co-Authored-By`。
- `../ml-final-archive` 是舊分支的唯讀 worktree，只讀不改。
- 使用者希望新流程不要被舊研究牽著走，舊資料只在需要時查。
- 不要碰 `hw6-jiangjiangian`（無關的舊作業）。

## 寫作規則

給人看的文字（回覆、README、docstring、報告）都照 `.claude/output-styles/team-docs.md`。subagent 讀不到輸出風格，所以這裡放短版：

- 短句，先講結論。第一次出現的術語用幾個字解釋。
- 回覆的讀者是使用者本人，不重講他已經知道的背景。文件的讀者是組員。
- 文件的結構：一個 H1，H2 分段，H3 給每個項目；列表各項有自己的主題時寫成「標籤：說明」；路徑和指令用反引號。短的回覆不加標題。
- 不用「不是…而是…」、破折號、總結式結尾句、硬湊三點、「值得注意的是」這類填充語、emoji。粗體很少用。
- 寫之前先決定讀者和標題，寫完刪掉讀者不會發現少了的句子。

## 絕對不要

- 用 t 當天的價格、成交量、法人、技術指標或 `y` 當 t 的特徵。老師 global 的 `^TWII`、`^KS11`、`TX_OI` 只能用日期早於 t 的最後一列。唯一的例外：日韓 t 日開盤跳空 `kospi_open_gap`、`n225_open_gap`（使用者 2026-11-08）可以放在長表 t 那列給組員研究，不能進 `model_columns`；t 那列要等台北 08:25 的排程從 Yahoo 抓到才有值（使用者 2026-11-11），07 點多預測時是空白。
- 在台北 22:30 之後抓美股來做隔天的特徵。
- 隨機拆列做驗證（要按日期切）。
- 過了 t 當天的截止時間還上傳，或 POST 失敗後自動重試。
- 沒跟使用者確認舊系統的排程已經停了，就把 `submit.enabled` 改成 `true`。
- 把帳號密碼寫進程式、設定檔或 log。
- yfinance 請求間隔少於 2 秒。
