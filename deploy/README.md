# Phase 2 每日自動提交：怎麼做到準時、不延遲

更新：2026-11-04（台北）。
研究方式：deep-research 共 104 個 agent，查了 22 個來源；25 條宣稱各經 3 票對抗驗證，22 條確認、3 條駁回。另外讀了本 repo 的 Actions 紀錄和日誌。
**結論欄標「推論」的，是根據已驗證事實做的設計判斷，不是單一來源的說法。**

---

## 0. 一句話結論

**GitHub Actions 的 `schedule` 本身沒有準時保證，不能當主要觸發器。**
- **主要**：改用 Google Cloud Scheduler 準時呼叫 Cloud Run Job。容器映像鎖定版本，排程避開整點。
- **備援**：另一家供應商、另一個時點，用 GitHub `workflow_dispatch` 或 Claude 雲端排程任務。
- **監控**：Healthchecks.io 的 dead man's switch。
- **安全網**：每一次執行都先查「今天是否已有有效提交」，才決定要不要送。

成本估計每月 0 元左右；運算在 Cloud Run 免費額度內。

---

## 1. 為什麼 GitHub CI/CD 常常失敗又延遲

### 1.1 本 repo 2026-11-04 的實際紀錄

以下是 `financial-daily.yml` 的 4 個排程。時間來自 Actions API 與 job 日誌，日誌裡的 `FINPRED_SCHEDULE` 標明了是哪一個 cron。

| cron（UTC） | 應觸發（台北） | 實際開始（台北） | 延遲 | 結果 |
|---|---|---|---|---|
| `20 23 * * *` | 07:20 | 11:02 | 3 小時 42 分 | 失敗：`outside target-day 04:00-09:00 Taipei window` |
| `10 0 * * *` | 08:10 | 14:07 | 5 小時 57 分 | 同上 |
| `20 0 * * *` | 08:20 | 14:33 | 6 小時 13 分 | 同上 |
| `35 0 * * *` | 08:35 | 14:52 | 6 小時 17 分 | 同上 |

- `live-data.yml` 的 `17 20-23 * * *` 應該觸發 4 次，只出現 1 次，在 00:37 UTC（台北 08:37）。
- 所以「失敗」其實是程式的時鐘檢查正確地擋下遲到的執行，不是程式壞掉。**真正的問題是觸發本身沒有保證。**

### 1.2 官方文件怎麼說（已驗證，3-0）

- `schedule` 在高負載時會延遲，**每個整點都是高負載時段**；負載夠高時，排隊中的工作會被**直接丟棄**。文件唯一的建議是「排在整點以外的分鐘」，而且只會「降低機率」，**沒有延遲上限，也不保證送達**。
  來源：[GitHub Docs – schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)、[原始檔 schedule-delay.md](https://github.com/github/docs/blob/main/data/reusables/actions/schedule-delay.md)、[疑難排解](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows)
- `schedule` 只在預設分支執行；public repo 60 天沒有活動會自動停用排程（同上來源）。
- 我們的 cron 已經避開整點（:10／:20／:35／:17），仍然晚了好幾小時。社群也回報過 5～14 小時的延遲和整天沒觸發的情況（[討論 207346](https://github.com/orgs/community/discussions/207346)、[209331](https://github.com/orgs/community/discussions/209331)、[201738](https://github.com/orgs/community/discussions/201738)；屬次要來源）。

### 1.3 改用 `workflow_dispatch` 就好了嗎？只能改善，不能根治（已驗證，3-0）

- 由外部準時呼叫 `workflow_dispatch` API，可以避開 schedule 佇列，延遲從「小時級」降到「分鐘級」。
- 但 GitHub 託管 runner 的啟動時間仍然沒有保證。2026-01-20 的官方事故中，手動 dispatch 的 workflow 也延遲，高峰約 23% 的 run 受影響，平均晚 11 分鐘；根因是 scheduled jobs 塞滿了共用後端（[事故 fw294tth5m8y](https://www.githubstatus.com/incidents/fw294tth5m8y)）。
- 2026 年 8～10 月還有其他 runner 啟動延遲事故（只有一位驗證者找到，列為參考）。

→ **GitHub Actions 適合當備援，不適合當唯一執行器。**

---

## 2. 各種做法比較

| 做法 | 準時性 | 會不會漏跑 | 成本 | 建議角色 | 依據 |
|---|---|---|---|---|---|
| GitHub `schedule` | 小時級延遲，沒有上限 | 會被丟棄 | 免費 | 只當第三層的「順便」 | 官方文件＋本 repo 實測 |
| 外部 cron → GitHub `workflow_dispatch` | 推論為分鐘級；事故時平均晚約 11 分鐘 | 很少 | 免費 | **備援** | 官方事故報告 |
| **GCP Cloud Scheduler → Cloud Run Job** | 文件沒寫準點保證（SLA 只管可用性） | at-least-once，可能重複 | 約 0 元 | **主要** | 官方文件、SLA、定價 |
| AWS EventBridge Scheduler → Lambda／Fargate | 「彈性時間窗」**必須設 Off**；實測約 60 秒內（次要來源） | at-least-once | 便宜 | 不用 GCP 時的替代主要 | AWS 文件（搜尋摘要） |
| 自架 VPS／電腦＋systemd timer | 約 1 分鐘內（`AccuracySec` 預設 1 分鐘） | 主機關機就漏跑 | VPS 月費 | 另一家的備援 | systemd man page |
| Claude Code 雲端排程任務 | 整點可能晚幾分鐘，建議用偏移分鐘；最小間隔約 1 小時 | research preview，可能沒啟動 | 用你的方案額度 | **監控／備援**，不當主要 | Claude Code 文件 |
| Claude Code session 內 `/loop` | 每次固定晚 0～30 分鐘；7 天自動過期 | 程式關掉就停 | — | **不適合** | Claude Code 文件 |
| Kaggle Notebook | 排隊與額度不保證 09:00 前完成 | — | 免費 | 不當每日執行器 | 本 repo 既有結論 |

Cloudflare Workers Cron、Render、Railway、Fly.io、Modal 本次**沒有通過驗證的資料**，不納入推薦。

### 2.1 GCP 的細節（已驗證）

- **觸發**：Cloud Scheduler 用 HTTP POST 呼叫
  `https://run.googleapis.com/v2/projects/PROJECT_ID/locations/asia-east1/jobs/JOB:run`。
  - 以 OAuth service account 認證，建議專用 invoker SA、最小權限 `roles/run.invoker`。
  - RunJob 回傳 long-running operation，job 在背景執行，所以不受 Scheduler 的 `attemptDeadline` 限制（HTTP target 可設 15 秒～30 分鐘）。
  - 來源：[Run jobs on schedule](https://cloud.google.com/run/docs/execute/jobs-on-schedule)、[scheduler job.proto](https://github.com/googleapis/googleapis/blob/master/google/cloud/scheduler/v1/job.proto)、[run v2 job.proto](https://github.com/googleapis/googleapis/blob/master/google/cloud/run/v2/job.proto)、[Terraform 範例](https://github.com/terraform-google-modules/terraform-docs-samples/blob/main/run/jobs_execute_jobs_on_schedule/main.tf)
- **重要限制**：RunJobRequest 只有 `validateOnly`、`etag`、`overrides` 三個欄位，**沒有冪等鍵**，每呼叫一次就產生一次新的 execution。
- **SLA**：每月 99.5% 可用性，以伺服器端錯誤率計算，**完全沒有承諾準點**；遞送是 at-least-once，可能重複，官方要求 target 要冪等。
  來源：[SLA](https://cloud.google.com/scheduler/sla)、[overview](https://cloud.google.com/scheduler/docs/overview)
- **秘密**：課程帳密放 Secret Manager，用環境變數或 volume 掛進 Cloud Run Job（[文件](https://docs.cloud.google.com/run/docs/configuring/jobs/secrets)）。

### 2.2 可以用 Claude（我）來排程嗎？

可以，但**只當監控和備援**。

- **雲端排程任務**（本環境的 scheduled task／routine）：
  - 還在 research preview，行為和限制都可能改變，也沒有 SLA。
  - 狀態顯示 *Succeeded* 只代表 session 正常結束，**不代表提交成功**。
  - 執行中可能停下來等權限確認；連到允許清單以外的主機會被擋（`403 host_not_allowed`）。
  - 同時執行數或用量達到上限時，任務可能根本沒啟動。
  - `/fire` API 是實驗性的，**沒有冪等鍵**，也不回報執行結果。
  - 來源：[routines 文件](https://code.claude.com/docs/en/routines)、[/fire API](https://platform.claude.com/docs/en/api/claude-code/routines-fire)
- **session 內的 `/loop`**：只在程式開著而且閒置時觸發，每天固定晚 0～30 分鐘，錯過不補跑，7 天後自動過期（[文件](https://code.claude.com/docs/en/scheduled-tasks)）。**不適合 Phase 2。**

適合交給我的工作：
- 08:41 讀 ledger 和官方回執，有問題就推播通知你。
- 08:27 當備援：確認「還沒有有效提交」之後，觸發 GitHub `workflow_dispatch` 用前一版模型補交。

---

## 3. 推薦架構

```text
                     ┌─────────────── 主要（GCP，asia-east1）────────────────┐
 Cloud Scheduler ──▶ │ Cloud Run Job：同一個鎖定版本的容器                   │
 （偏移分鐘、UTC）   │   collect → train → predict → submit → verify          │
                     │   每一步先取 lease、讀 ledger 與 /api/state           │
                     └──────┬──────────────────────────────────┬─────────────┘
                            │ 狀態：ledger／lease／模型／回執   │ 成功後 ping
                            ▼                                  ▼
                  live-data 分支（現有 Git CAS）        Healthchecks.io
                  ；之後可改 Cloud Storage              （沒收到 ping 就告警）
                            ▲
 ┌──── 備援（另一家、另一個時點）────┐       ┌──── 監控 ────┐
 │ Claude 雲端排程任務 08:27          │       │ Claude 08:41 │
 │  → 沒有有效提交才 dispatch         │       │ 讀 ledger＋  │
 │    GitHub financial-daily.yml      │       │ 官方回執→推播 │
 │ GitHub 自己的 schedule（第三層）   │       └──────────────┘
 └────────────────────────────────────┘
```

| 元件 | 做什麼 | 為什麼這樣選 |
|---|---|---|
| Cloud Scheduler | 每天固定時點觸發 | 專門的排程服務，有 99.5% 可用性 SLA（但沒有準點保證，所以仍要備援）；排在偏移分鐘 |
| Cloud Run Job（asia-east1） | 跑完整流程 | 台灣區域、按秒計費、免費額度足夠；job 在背景執行，不受 HTTP 逾時限制 |
| Artifact Registry＋**以 digest 鎖定映像** | 每天跑同一份程式與套件（例如 `yfinance==1.7.0`） | 避免「昨天能跑今天不能跑」 |
| Secret Manager | `COURSE_EMAIL`、`COURSE_PASSWORD`、GitHub token、Healthchecks URL | 帳密不進 Git、不進 log |
| 狀態儲存 | **第一版沿用現有 `live-data` 分支的 Git lease／CAS 與 ledger**（system-completion 已實作） | 不重寫已驗證的鎖與帳本；之後可再搬到 Cloud Storage |
| 備援：GitHub `workflow_dispatch` | 主要層沒成功時，用前一版模型補交 | 不同供應商，故障模式不同 |
| Healthchecks.io | 沒收到「提交＋核對成功」的 ping 就告警 | 抓得到「根本沒開始跑」的故障（[about](https://healthchecks.io/about)） |
| Claude 雲端排程任務 | 08:27 備援觸發、08:41 監控報告 | 預期可直接用本環境的 GitHub 連線觸發 dispatch，不必另存 token（建立時驗證）；只當補救層 |

---

## 4. 每日時間表

台北＝UTC+8，沒有夏令時間。**cron 一律寫 UTC**；台北早上 08:00 以前的時點，在 UTC 是**前一天**，所以星期欄是 `0-4`。是否為官方交易日，一律以 `/api/state` 判斷，cron 的星期欄只是先過濾。

| 台北 | UTC cron | 誰觸發 | 做什麼 | 失敗時 |
|---|---|---|---|---|
| 05:17、06:17 | `17 21,22 * * 0-4` | 主要 | collect：老師 Live ZIP＋yfinance 19 序列（限流），寫入 manifest 與取得時間 | 第二次重試；單一來源失敗就沿用前一版並標 partial |
| 07:17 | `17 23 * * 0-4` | 主要 | train：用截止前已完成的標籤訓練候選模型，和現役模型比較 | 沿用前一版已驗證模型 |
| 07:47 | `47 23 * * 0-4` | 主要 | 補跑：ledger 沒有今天的 collect／train 完成紀錄才重跑，否則立即結束 | — |
| 08:11 | `11 0 * * 1-5` | 主要 | predict：凍結 08:10 前取得的輸入，產生 50 股 CSV | 資料或模型不合格就停，交給 08:27 的備援 |
| 08:17 | `17 0 * * 1-5` | 主要 | submit：先寫 ledger 再 POST，接著下載目前有效版本逐格核對；成功後 ping Healthchecks | 結果不明時先對帳，不盲目重送 |
| 08:27 | `27 0 * * 1-5` | **備援**（Claude → GitHub dispatch） | 查 ledger 與 `/api/state`：**今天還沒有有效提交**才用前一版模型補交 | — |
| 08:41 | `41 0 * * 1-5` | 監控（Claude） | 核對回執，推播「成功／失敗／原因」 | Healthchecks 08:45 沒收到 ping 就告警 |
| 08:45～08:55 | — | 你 | 人工介入窗口 | — |
| 09:00 | — | — | 硬截止，之後不送 | — |

- 08:10 凍結、08:20 提交是專案自己的時程提案，老師的硬截止是 09:00（`system-completion` 的 AGENTS.md）。實作時，時點要配合現有程式的時鐘門檻。
- 所有時點都避開 :00 和 :30（GitHub 和 Claude 文件都建議偏移分鐘）。

---

## 5. 「不延遲、不重複、不覆蓋」的規則（推論，實作必守）

所有觸發器都可能重複：Scheduler 是 at-least-once，Run API 和 `/fire` 都沒有冪等鍵，主備又是兩個觸發。所以**冪等性要在管線本身做**：

1. **每一步先取當日 lease**（現有 Git CAS）。拿不到就結束，不併發。
2. **POST 之前先寫 ledger**（現有設計）。結果不明時，先下載目前有效版本對帳，不盲目重送。
3. **有效提交優先**：`/api/state` 或 ledger 顯示今天已經有正確的有效提交，就只核對、不重送。
4. **回退不覆蓋**：前一版模型的備援提交，**只能在當天還沒有有效提交時送出**。否則舊模型會蓋掉新模型的結果，因為競賽以最後一次有效提交為準，而且有配額。
5. **截止前停手**：過了 09:00 一律不送（現有時鐘門檻已經做到，11/04 的日誌就是證據）。
6. **映像鎖定**：Cloud Run 和 GitHub 備援都用同一個 digest 的容器，相依套件鎖定版本。
7. **資料回退**：Yahoo 被限流或缺資料時，沿用前一日快取並標 partial（現有 crawler 已經這樣做）；限流參數不變，每個請求間隔 ≥2 秒。
8. **成功的定義**：「下載到目前有效版本、逐格比對一致」才算成功。HTTP 200 或排程顯示 Succeeded 都不算。

---

## 6. 成本（2026-11-04 的定價頁）

- **Cloud Run Jobs 免費額度**：每月 240,000 vCPU-秒、450,000 GiB-秒，同一個 billing account 合計；asia-east1 屬 Tier 1。
  - 計費以 instance 存活時間計，最少 1 分鐘（[定價](https://cloud.google.com/run/pricing)）。
  - 估算：2 vCPU／4 GiB、每天合計 30 分鐘、每月 22 個交易日 → 79,200 vCPU-秒（33%）、158,400 GiB-秒（35%）→ **0 元**。即使用原價計算，也只要約 1.75 美元／月。
  - 備援先查 ledger 再決定要不要跑完整流程，就不會超額。
- **Cloud Scheduler、Secret Manager、Artifact Registry、Healthchecks 方案**：本次**沒有查證**價格，實作前要再查官方頁面。預期是每月幾角到幾美元。
- **GitHub Actions**：public repo 免費。

---

## 7. 實作清單

### A. 先止血（不需要 GCP，約 1 天）
- [ ] **Claude**：建立 Claude 雲端排程任務。08:27 檢查並在需要時 dispatch `financial-daily.yml`（`stage=submit`），08:41 監控與推播。**需要你同意建立排程。**
- [ ] **你**：註冊 Healthchecks.io，建一個 check（台北 08:45 前要收到 ping），把 ping URL 設成 Actions secret `FINPRED_HEALTHCHECK_URL`。
- [ ] **Claude**：在 verify 成功後加 ping；保留 GitHub 自己的 schedule 當第三層。

### B. GCP 主要執行器（約 2～3 天）
- [ ] **你**：建 GCP 專案並綁定 billing（需要信用卡；預估 0 元），在自己的電腦 `gcloud auth login`。
- [ ] **你**：啟用 API：
  ```bash
  gcloud services enable run.googleapis.com cloudscheduler.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
  ```
- [ ] **Claude**：寫 `Dockerfile`。內容是 Python 3.12、uv lock、`yfinance==1.7.0`，入口包裝現有的 `scripts/run_hosted_pipeline.py`。
- [ ] **Claude**：寫 `gcp/setup.sh`：
  - 建立 Artifact Registry、runner SA 與 invoker SA，設定 IAM。
  - 建立 Cloud Run Job：`--region=asia-east1 --cpu=2 --memory=4Gi --task-timeout=40m --max-retries=0 --set-secrets=...`（旗標以實作時的 `gcloud run jobs create --help` 為準）。
  - 建立 6 個 Cloud Scheduler job（第 4 節的時間表），用 `overrides` 指定 stage。
- [ ] **你**：建立 secrets，值只在你的終端機輸入，不貼到聊天：
  - `COURSE_EMAIL`、`COURSE_PASSWORD`
  - `GITHUB_TOKEN`：fine-grained token，只給本 repo `contents:write`，用來寫回 live-data 的 lease／ledger
  - `FINPRED_HEALTHCHECK_URL`
- [ ] **你**：執行 `setup.sh`。**不建議**把 GCP 憑證交給我。
- [ ] **Claude＋你**：手動 `gcloud run jobs execute` 跑 rehearsal 模式，確認不會 POST。

### C. 演練與上線
- [ ] 連續 5 個官方交易日 dry run（`FINPRED_SUBMISSION_RELEASED=false`）。每天檢查各階段實際開始時間、資料取得時間和 ledger。
- [ ] 通過後由**你**決定打開 `FINPRED_SUBMISSION_RELEASED=true`。
- [ ] 上線後每天 08:41 由 Claude 回報結果；有異常時，在 08:45～08:55 人工介入。

### 程式放哪裡（需要你決定）
- 管線程式在 `system-completion`，Dockerfile 和 GCP 腳本**建議放在那裡**的 `deployment/gcp/`，和現有的 `deployment/hosted/` 並列。
- 本分支只放這份設計文件，以及之後的實作紀錄。

---

## 8. 需要你決定或提供的東西

1. **要不要開 GCP**（推薦）。若不開，次佳方案是 AWS EventBridge Scheduler（彈性時間窗設 Off），或自架 VPS＋systemd 當主要觸發，再呼叫 GitHub `workflow_dispatch`。
2. **實作的分支**：建議 `system-completion`（程式所在）。
3. **允許我建立 Claude 雲端排程任務**（08:27 備援、08:41 監控），以及告警要用什麼通道（email／手機推播／其他）。
4. **何時打開正式提交**（`FINPRED_SUBMISSION_RELEASED`）。

---

## 9. 還沒查證的事情與風險

- **競賽網站**：每天有多少提交配額？登入方式（cookie／CSRF）是否穩定支援程式上傳？能否取得「目前有效提交」的內容或 hash 來核對？現有程式有 `/api/state` 和 `/api/sample-submission`，正式 POST 還沒有實際回執。
- **資料幾點可用**：老師 Live ZIP 每天幾點更新？（「網站約 04 點更新」是未查證的說法。）這決定 collect 最早能排在幾點。
- **Yahoo 對雲端 IP 的限流**：GCP／GitHub 的 IP 可能更容易被 Yahoo 限流。需要實測；備案是沿用前一日快取。
- **Claude 雲端排程任務的網路權限**：能否連到 `final.html2026.csie.org`？如果不行，它只能透過 GitHub dispatch 間接補交，或只做告警。
- **沒有實測的觸發延遲數據**：Cloud Scheduler 與 Claude 雲端任務都查不到；AWS 的「60 秒內」來自次要來源。上線前的 5 日演練要記錄實際延遲。
- **被駁回的說法**（報告不採用）：
  - 「Cloud Scheduler／EventBridge 可以直接用台北時區，所以不用換算 UTC」。
  - 「Cloud Scheduler 預設不重試、上限 5 次」。
  - 重試設定要在實作時對照官方文件明確設定。
- 定價與 research preview 功能的內容都以 2026-11-04 為準，可能變動。

---

## 10. 主要來源

- GitHub：[schedule 文件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)、[schedule-delay.md](https://github.com/github/docs/blob/main/data/reusables/actions/schedule-delay.md)、[疑難排解](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows)、[2026-01-20 事故](https://www.githubstatus.com/incidents/fw294tth5m8y)
- Google Cloud：[Run jobs on schedule](https://cloud.google.com/run/docs/execute/jobs-on-schedule)、[Scheduler SLA](https://cloud.google.com/scheduler/sla)、[Scheduler overview](https://cloud.google.com/scheduler/docs/overview)、[重試設定](https://docs.cloud.google.com/scheduler/docs/configuring/retry-jobs)、[Cloud Run 定價](https://cloud.google.com/run/pricing)、[Jobs 秘密](https://docs.cloud.google.com/run/docs/configuring/jobs/secrets)
- AWS：[EventBridge Scheduler＋ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/tasks-scheduled-eventbridge-scheduler.html)
- systemd：[systemd.timer](https://manpages.debian.org/buster/systemd/systemd.timer.5.en.html)
- Claude Code：[routines](https://code.claude.com/docs/en/routines)、[scheduled tasks](https://code.claude.com/docs/en/scheduled-tasks)、[/fire API](https://platform.claude.com/docs/en/api/claude-code/routines-fire)
- 監控：[Healthchecks.io](https://healthchecks.io/about)、[GitHub 原始碼](https://github.com/healthchecks/healthchecks)
- 本 repo 證據：Actions run [41764521303](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41764521303)、[41783443959](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41783443959)、[41786356232](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41786356232)、[41788428307](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41788428307)（四個都是 `PipelineBlocked: outside target-day 04:00-09:00 Taipei window`）
