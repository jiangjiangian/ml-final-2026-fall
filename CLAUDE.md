# 給 Claude Code 的規則

這是課程 ML 期末專案（2026 秋）的比賽主程式，分支 `claude/stock-market-challenger`，repo `jiangjiangian/ml-final-2026-fall`。每個台股交易日的台北 09:00 前，預測 50 檔股票當天會不會「收盤高於開盤」（`y = 1` 代表 `adj_close > adj_open`），把 0/1 寫成 CSV 上傳課程網站。

`src/crawler.py`、`src/features.py` 已實作，離線測試通過。2026-11-06 第一次連網試跑（研究模式，t = 11/06，沒有上傳）：老師 Training／Live（Live 用原本的網址、只信任 `configs/live_ca.pem`）、yfinance、期交所台指期都抓到，特徵表 32 個模型欄，兩輪獨立檢查沒有 blocker，`data/raw/`、`data/processed/` 已推上去給組員。2026-11-07：`run_daily_test.py` 串起爬蟲、特徵、組員的邏輯迴歸（`src/online_lr.py`）和上傳（`src/submit.py`、`src/site_api.py`）。排程在學校的 oop.cs.nccu.edu.tw（台北 07:10、07:25、07:40、07:55、08:05，使用者 2026-11-07 從 GCP 改過來、11-08 加到五次），使用者 Mac 08:15 起的備援寫好了但沒有裝（2026-11-09 查到 launchd 沒有這個工作，使用者決定先不裝），現在只有 oop。`submit.enabled` 是 true，`submit.phase` 決定交 Phase 1 還是 2（細節在 `memory/context/pipeline.md`）。`train.py`、`predict.py`、`run_daily.py` 還是骨架。2026-11-09：證交所、櫃買回補完（2020-01-02～2026-11-06）；長表加 17 欄給組員研究（交易所估值和委買賣、日韓開盤跳空、老師 S&P 500／Nasdaq 用 t 那列的版本、`kospi`），都不進 `model_columns`；每天抓交易所的 `exchange.enabled` 還是 false。這些程式和重建的 `data/processed/`（80 欄）、交易所原始檔、`kospi.csv` 在 11-09 下午一起推上去。之後特徵欄位再變，程式和 pull 之後 `--rebuild` 的 `data/processed/` 一定要同一次推，少一樣每天的特徵會因為欄位不同停下；先 pull 再重建、避開台北 07:00～08:40 推，步驟在 `memory/context/pipeline.md` 的「特徵欄位變了怎麼推」。

## 先讀哪個檔

細節都在 `memory/`，一個主題一個檔。動手前讀相關的那幾份：

| 要做的事 | 讀 |
|---|---|
| 查名詞 | `memory/glossary.md` |
| 比賽規則、課程網站 API、上傳的規矩、Phase 1 結果 | `memory/context/competition.md` |
| 每天的流程、指令、失敗時怎麼手動交 | `memory/context/pipeline.md` |
| 寫爬蟲或特徵：時間對齊、美股日期、-1、交易日曆、資料存放 | `memory/context/data-rules.md` |
| 本機環境、分支、舊系統封存、skills、輸出風格 | `memory/context/environment.md` |
| 還沒決定的事和線索 | `memory/context/open-questions.md` |
| `src/crawler.py` 的設計和進度 | `memory/projects/crawler.md` |
| `src/features.py` 的規劃：清理規則、交易日、lag 公式、對照測試 | `memory/projects/features.md` |
| Kaggle 上平行訓練的模型研究（另一個 session 在用） | `memory/projects/kaggle-models.md` |

`README.md` 給組員看：每天的流程、組員怎麼拿資料、檔案樹。新增、搬動或刪除檔案時，改 `README.md` 的檔案樹；`memory/` 多了或少了檔案時，也改上面的表。`memory/` 裡的路徑都從 repo 根目錄算。

### memory/ 怎麼維護

- 使用者做了決定，寫進對應的檔，標上日期（例如 2026-11-05）。
- `open-questions.md` 的問題有答案後，搬到對應的檔，再從清單拿掉。
- 這份 `CLAUDE.md` 只放索引和最重要的規則，細節寫在 `memory/`。

## 工作方式

- 回覆用繁體中文。
- 補程式前，先把要寫的東西和定義講清楚，等使用者確認後才實作。
- 要使用者做決定時，用選擇題問（AskUserQuestion），推薦的選項放第一個。每題自己講清楚，不用 i、E 這類代號；金融名詞（K棒、成交量、指數）先用白話解釋。
- 同一個資料夾可能有別的 session 在工作（例如 `notebooks/kaggle/`、`memory/projects/kaggle-models.md`）。commit 時只 `git add` 自己改的檔，不用 `git add -A`。
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

- 用 t 當天的價格、成交量、法人、技術指標或 `y` 當 t 的特徵。老師 global 的 `^TWII`、`^KS11`、`TX_OI` 只能用日期早於 t 的最後一列。唯一的例外：日韓 t 日開盤跳空 `kospi_open_gap`、`n225_open_gap`（使用者 2026-11-08）可以放在長表 t 那列給組員研究，不能進 `model_columns`；台北約 08:30 才看得到，每天早上 t 那列是空白。
- 在台北 22:30 之後抓美股來做隔天的特徵。
- 隨機拆列做驗證（要按日期切）。
- 過了 t 當天的截止時間還上傳，或 POST 失敗後自動重試。
- 沒跟使用者確認舊系統的排程已經停了，就把 `submit.enabled` 改成 `true`。
- 把帳號密碼寫進程式、設定檔或 log。
- yfinance 請求間隔少於 2 秒。
