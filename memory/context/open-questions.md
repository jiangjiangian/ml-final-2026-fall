# 還沒決定的事

需要時問使用者。有答案後，把結果和日期寫進對應的檔，再從這裡刪掉那一節。

## 每天用什麼方式自動觸發

- 現況：觸發方式決定之前先不放 `.github/workflows/`。目前沒有任何東西每天在跑這個分支。
- GitHub Actions（GitHub 的雲端機器）的排程不準：11/04 晚了 3 小時 42 分到 6 小時 17 分；11/05 07:20～07:35 的排程到 11:31～11:39 才開始，16 個時點只觸發 5 個。
- GitHub 的排程和 `workflow_dispatch`（用 API 或網頁手動觸發），都只認預設分支上的 workflow 檔。
- 2026-11-05 給使用者的提議（還沒決定）：
  - 觸發：cron-job.org 在台北 07:15、07:45、08:15 呼叫 GitHub API 的 `workflow_dispatch`，Cloudflare Workers Cron 當第二個鬧鐘。
  - 執行：GitHub 的機器跑 `python run_daily.py`，帳密放 GitHub Secrets，用 `concurrency` 擋住同時跑兩次。前一次成功的話，後面幾次查到網站上已經有一樣的提交就結束。
  - 監控：Healthchecks.io 在開始和成功時各收一次回報，08:40 前沒收到成功就通知。
  - 要使用者決定：workflow 檔放在空的 `main`（由它 checkout 這個分支），還是把預設分支設成這個分支；外部排程用的 GitHub token；通知管道；用誰的帳號。
  - 其他選項：GCP Cloud Scheduler 加 Cloud Run Job（最準時，要綁卡）；Mac 的 launchd（Mac 要醒著）。
- 舊研究的細節：`../ml-final-archive/archive/old-research/deploy-README-2026-11-04.md`。

## 舊系統的排程停了沒

- 2026-11-05：GitHub 預設分支已經是空的 `main`，使用者因為 GitHub Actions 一直延遲而換掉。`system-completion` 最後一次排程是 11/05 台北 11:39，之後沒有再跑。使用者之後想用下面「外部排程叫 GitHub 執行」的做法。
- 換之前的狀況：`system-completion` 的 `course-benchmark.yml` 每天照排程跑，上傳開關寫死成開，舊模型也通過了上傳前的檢查。台北 08:20、08:27 這兩個排程準時觸發時，它會真的上傳。
- 這個分支把 `submit.enabled` 改成 `true` 之前，要先跟使用者確認舊排程已經停了。不然兩套程式會搶著交答案、用掉上傳次數。
- `system-completion`、`dev`、`deep-research` 使用者 2026-11-05 已在 GitHub 刪掉；`live-data` 還在。

## 每天的資料誰 commit、push

- 現在沒有任何步驟會 commit 或 push `data/raw/`、`data/processed/`。README 給組員的網址要等有人 push 之後才讀得到。
- 排程或 `run_daily.py` 要在 features 之後 commit、push 這兩個資料夾（只加這兩個路徑），寫到排程那一步再問。

## 組員的腳本要改讀新資料

- 組員的 `build_dataset.py` 和 Kaggle 的 `notebooks/kaggle/data/twfeat.py` 還在讀 data-collection 的 `panel_lag.csv.gz`（欄名 `ticker`、lag2 和 lag5、日K的 `usd_twd`）。
- 要改成 README 的網址，欄名是 `stock_id`、lag1 和 lag2、`usd_twd_am`，模型欄看 manifest 的 `model_columns`。第一次連網試跑、push 特徵表之後再通知組員。

## 正式流程用哪位組員的帳號

還沒決定。帳號密碼只放 `.env` 或執行環境的 secret。

## 排程設定檔放哪裡

- 選項：空的 `main` 只放一個 `.github/workflows/daily.yml`（去拿這個分支的程式來跑），或把預設分支改成這個分支。
- 使用者 2026-11-05 擔心延遲。已說明：延遲來自 GitHub 的 `schedule`，和設定檔放哪裡無關；外部呼叫 `workflow_dispatch` 平常是分鐘內，2026-01-20 事故時平均晚 11 分鐘。上線前試跑一週，記錄「呼叫到開始」的秒數。寫到排程那一步再問。

## Phase 2 用哪個模型

- `configs/config.yaml` 先寫 LightGBM，之後依驗證結果換。
- Phase 1 的模型見 `memory/context/competition.md`。
- `claude/hopeful-brahmagupta-wikys1` 有 11/04 的 R4 模型研究，commit 訊息寫選了 E1 線性模型、LightGBM 沒贏 E1。選模型時可以參考。
