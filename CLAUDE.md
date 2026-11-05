# 給 Claude Code 的規則

這是課程 ML 期末專案（2026 秋）的比賽主程式，分支 `claude/stock-market-challenger`，repo `jiangjiangian/ml-final-2026-fall`。每個台股交易日的台北 09:00 前，預測 50 檔股票當天會不會「收盤高於開盤」（`y = 1` 代表 `adj_close > adj_open`），把 0/1 寫成 CSV 上傳課程網站。

`src/crawler.py` 已實作，離線測試通過，還沒連網試跑。`src/` 其他檔案是骨架：寫好用途、輸入、輸出和函式介面，函式本體是 `NotImplementedError`。下一步是第一次連網試跑爬蟲（先問使用者），再補 `src/features.py`。

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

`README.md` 只放檔案樹，給組員看。新增、搬動或刪除檔案時，改 `README.md` 的檔案樹；`memory/` 多了或少了檔案時，也改上面的表。`memory/` 裡的路徑都從 repo 根目錄算。

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

- 用 t 當天的價格、成交量、法人、技術指標或 `y` 當 t 的特徵。老師 global 的 `^TWII`、`^KS11`、`TX_OI` 只能用日期早於 t 的最後一列。
- 在台北 22:30 之後抓美股來做隔天的特徵。
- 隨機拆列做驗證（要按日期切）。
- 過了 t 當天的截止時間還上傳，或 POST 失敗後自動重試。
- 沒跟使用者確認舊系統的排程已經停了，就把 `submit.enabled` 改成 `true`。
- 把帳號密碼寫進程式、設定檔或 log。
- yfinance 請求間隔少於 2 秒。
