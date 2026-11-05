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
- `system-completion`、`live-data`、`dev`、`deep-research` 還在 GitHub 上，由使用者自己刪，Claude 不刪。

## 正式流程用哪位組員的帳號

還沒決定。帳號密碼只放 `.env` 或執行環境的 secret。

## 失敗時用什麼管道通知

還沒決定，例如 LINE 群組。LINE Notify 已在 2025 年停用，要用 LINE 得另外建 Messaging API 的 bot；Healthchecks 內建的 email 或 Discord 比較簡單。

## Live ZIP 怎麼下載

兩條線索都要先跟使用者確認再用：

- Phase 1 紀錄寫的來源：`https://fin-pred-daily.jiangxuehaokeai.chatgpt.site/data.zip`。
- 舊程式 `../ml-final-archive/archive/system-completion/ml_financial_prediction/src/finpred/ingestion/course.py`：
  - 金鑰：先讀 `COURSE_LIVE_KEY`。沒有的話，從課程網站首頁 `<script src>` 載入的 JS（前 20 個）裡，找字串 `"https://140.112.31.182:8444/"` 之後的下一個賦值 `名稱="…"`，金鑰是引號裡的值（英數、`_`、`-`）。
  - 登入：`POST {LIVE_BASE}/login`，表單帶 `key`，要用瀏覽器的 User-Agent；回應裡要有 `href="/data.zip"`。
  - 下載：`GET {LIVE_BASE}/data.zip`。`LIVE_BASE` 就是上面那個 chatgpt.site 網址。
- 兩個主機的關係（`../ml-final-archive/archive/system-completion/ml_financial_prediction/docs/SOURCES.md` 第 9～11 行）：課程網站的 Live 卡片寫「前往資料服務取得最新 training data，並使用下方公開金鑰存取」，連到 `https://140.112.31.182:8444/`，但 TLS 驗證失敗（憑證沒有 IP）。chatgpt.site 是助教後來給的新入口，一般 TLS 可以過，用同一把公開金鑰登入。
- 更新時間：t 那列的 `^IXIC`、`^GSPC` 在 t 當天 05:05 前填好，其他欄和 y 在 t 當天 22:05 前填完（細節見 `memory/projects/crawler.md`）。

## Phase 2 用哪個模型

- `configs/config.yaml` 先寫 LightGBM，之後依驗證結果換。
- Phase 1 的模型見 `memory/context/competition.md`。
- `claude/hopeful-brahmagupta-wikys1` 有 11/04 的 R4 模型研究，commit 訊息寫選了 E1 線性模型、LightGBM 沒贏 E1。選模型時可以參考。
