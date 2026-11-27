# 全新 ML 研究 pipeline 狀態（RP 01 起）

使用者 2026-11-23 交辦建立可循環、可審計的全新 ML 研究 pipeline，並要求用量達上限重設後可自動接續。每輪自動喚醒或續跑前先讀這份檔案。正式實驗結果、數據、限制與下一個單一假設寫進 `memory/projects/22-ml-research-pipeline.md`。

## 接手紀錄（2026-11-26）

- 2026-11-23～11-26 由 Antigravity（session `6ea1e04e-9ab8-4383-8c77-11f7f7ce8c83`）跑完 `RP 01～RP 28`，結果都在 `22-ml-research-pipeline.md`。11-26 13:00 起 Antigravity 額度用完（`INSUFFICIENT_G1_CREDITS_BALANCE`），停在 `RP 29` 推上 Kaggle 之前。
- 2026-11-26 使用者用 `/goal` 交給 Claude Code 接手。這份狀態檔原本還寫 `RP 28` Stage 4 `IN_PROGRESS`，實際上 `RP 28` 已驗證並記錄，`output/` 也已刪，所以檢查點改到 `RP 29`。
- `RP 29` notebook（`notebooks/kaggle/2026-11-23_v1_research-pipeline/rp-29-online-expert-hedge/notebook.ipynb`，11-26 08:52 由 `gen_rp29.py` 產生）Claude 已做靜態檢查：6 個 code cell 都能 `ast.parse`；pyflakes 只有一個沒用到的 `inst_net`；`chronological_audit` 讀的三個 key 都有寫；聚合器先算第 t 天權重再加入第 t 天分數，時點正確。
- 正式程式的基準：接手時 `run_daily.py`、`src/pipeline/step4_submit.py` 已有別的 session 留下、未 commit 的改動（上傳 note 加 `model_name`），`git diff` 的 sha256 是 `ae498d14…`。這個 session 不碰這兩個檔，之後報告寫「這個 session 沒有改正式程式」，不寫「diff 為空」。
- 不再在 Mac 跑 `pytest`：會跑模型測試，違反「不在本機跑」的規則，而且這條研究線不改 `src/`。本機只做靜態檢查和下載 CSV 的重算。

## 當前階段與檢查點

- `RP 29` 全部 `PASS`（2026-11-26）：smoke v1 74.16 秒、full v2 81.01 秒 `COMPLETE`，獨立重算誤差 `< 3.5e-14`，結果記在 `22-ml-research-pipeline.md`，`output/` 已刪。
- 目標實驗：`RP 37`，用 FinMind 2005～2019 的法人資料做法人層的樣本外確認。2026-11-27 設計草稿完成，還沒登記，放在本機 `notebooks/kaggle/2026-11-23_v1_research-pipeline/rp-37-inst-layer-oos-finmind-2006-2019/design_draft.md`（不進 Git）：H1 只有一個（`X_price` 加凍結的 `0.12·(on_tr + on_dl)`，Top50-H 2006-01-02～2019-12-31，3,460 天），兩本 kernel（RP 37a 只下載 FinMind 法人 346 個請求約 1.5～2 小時、RP 37 重用 UB 02 的預測只算分數），真實增量估計每天 +0.00003～+0.00006，通過機率約 43%～85%。要使用者決定：最低效果門檻、m = 1 或加只看投信的 H2、要不要 FinMind token、外資在 2017-12-18 前後的定義、測試起點。同一天使用者質疑 c2v2d 和研究框架，Claude 做了網路研究（`memory/projects/23-recent-prediction-research.md`），RP 37 要不要照跑等使用者看完再決定。`RP 30～36` 全部 `PASS`，不要重跑。
- 使用者 2026-11-27 的決定（選擇題）：路線圖做完後，下一步做「樣本外確認法人層」（沒選：停止 RP 寫總結、兩個都做）；`RP 36` 的 collection 由 Claude 開新的 Safari 視窗加；11-24 08:18 從 Mac 送出的全部猜漲上傳（蓋掉 oop 07:29 的 `c2v2d`）補進 repo：`upload_log.jsonl` 和 `run_2026-11-24.log` 照時間插入那幾行，加上 `submission_2026-11-24_all1.csv` 和網站原本那份的備份。路線圖到 `RP 36` 結束，之後用選擇題問使用者（沒選過的方案：FinMind 2005～2019 法人資料的樣本外確認，或停止 RP 寫總結），不要自己加 `RP 37`。
- 使用者 2026-11-26 對 `RP 31` 起的決定（選擇題）：照 Antigravity 的路線圖探索新架構（PCA 殘差、低秩 VAR、HMM／卡爾曼、路徑簽名、小型深度學習、決策導向學習），仍用看過的 `WF_Test`，結果只當探索。每個新候選加進 `RP 30` 的 93 個候選池，累計 `SPA_c`（區塊長 20）`< 0.05` 才算過。沒選的方案：用 FinMind 2005～2019 法人資料做法人層的樣本外確認（已查證可行：`TaiwanStockInstitutionalInvestorsBuySell` 2005-01-01 起、免費版每小時 300～600 次；自營商 2014-12-01 前是合併的 `Dealer`），以及停止 RP 寫總結。
- Collection：使用者 2026-11-26 要 Claude 用 Safari 建 `ML 2026 Fall｜17 全新研究管線（RP）`，加入 `RP 01～30` 共 31 本（含沒有輸出的 `rp-05-institutional-flow-and-state-shrinkage-c2v2d`）。
- Git：使用者 2026-11-26 同意 commit 並 push 研究檔。`notebooks/kaggle/` 照 `notebooks/README.md` 只在本機，不進 Git；只 commit `memory/projects/20～22`、`CLAUDE.md` 的索引列、`README.md` 檔案樹的兩處。本機落後遠端 40 個 commit，而且 `README.md`、`run_daily.py`、`data/submission/upload_log.jsonl`、`run_2026-11-24.log` 兩邊都有改，所以在暫存 worktree 從遠端最新版 commit 再 push，主工作樹不動。之後在主工作樹 pull 時，這三個 memory 檔會以「未追蹤檔會被覆蓋」擋下，內容和遠端一樣，先移開再 pull。
- N1 核對（2026-11-26）：遠端 `6feb1dd` 就是 N1 影子跑的 commit；`RP 01` 查到「本機沒有 N1」是因為本機 checkout 停在 `f02b89d`，落後遠端 40 個 commit。
- Kaggle 途徑：claude.ai Kaggle 連接器回 `Unauthenticated`，`authorize` 300 秒沒回應。使用者 2026-11-26 決定這次接手改用 Kaggle 官方 CLI（`.venv/bin/kaggle`，帳號 `modelnovice`），走 repo 原本的 `notebooks/kaggle/push_all.sh --dir 2026-11-23_v1_research-pipeline --only <slug> [--smoke]`。這是交接規則「MCP 不能用就停」的例外，只限這次接手。
- 下一輪：使用者 2026-11-26 決定 `RP 30` 先做資料窺探校正，Antigravity 的 `RP 30～35` 路線圖（PCA 殘差、低秩 VAR、HMM、路徑簽名、小型深度學習、決策導向學習）往後排，編號順延。
- Kaggle Collection：`ML 2026 Fall｜17 全新研究管線（RP）`（id 19687957，2026-11-26 Claude 用 Safari 視窗 25140 建立）。`RP 01～36` 加上沒輸出的 RP 05 舊版共 37 本，都用抽屜檢查確認在裡面（第一輪有 RP 01、12、13、17 沒加成功，重加後確認；RP 36 在 2026-11-27 用新開的 Safari 視窗 84 加入）。之後每本跑完就加。
- Kaggle slug 和資料夾名不同的四本：`rp-05-inst-flow-and-state-calibration-c2v2d`、`rp-07-rich-online-adapter-and-bounce-soft-tail`、`rp-11-inst-reg-and-smooth-ov-stress`、`rp-22-trdl-asymmetric-weights-and-gap-ema`（Kaggle 用標題產生 slug）。另有一本沒有輸出的 `rp-05-institutional-flow-and-state-shrinkage-c2v2d`。

`RP 36`（`modelnovice/rp-36-decision-focused-signature`，決策導向學習；登記在 `22` 最後一節）：

| Stage | 角色 | 狀態 | 備註 |
|---|---|---|---|
| Stage 1 Scope & Tooling Gate | `ml-research-lead` | `PASS` | 2026-11-27 路線圖最後一項；Kaggle CLI 照舊 |
| Stage 2 Audit & Preregistration | `literature-and-data-researcher` | `PASS` | 登記在 smoke 前單獨 commit；兩篇文獻用 Crossref 查證 |
| Stage 3 Kaggle Smoke Run | `kaggle-experiment-runner` | `PASS` | v1 146.91 秒全過；審查 1 個小問題（窗口不同），加同窗口診斷 |
| Stage 4 Kaggle Full Run | `kaggle-experiment-runner` | `PASS` | v2 345.51 秒，354 次 L-BFGS 全部收斂 |
| Stage 5 Independent Verification | `independent-verifier` | `PASS` | 誤差 `7.6e-14`；閘門 p 本機 0.10、notebook 0.0943；正式程式雜湊不變 |
| Stage 6 Memory & Collection | `memory-and-docs-maintainer` | `PASS` | 結果寫進 `22`；`daily_rp36.csv` sha256 `e2efb571653afbd7`；collection ｜17 已加（2026-11-27 視窗 25140 已關，改開新視窗 84 加入，抽屜檢查確認） |

`RP 35` 各 Stage 都 `PASS`（smoke v2、full v3 2,243.58 秒，3 個種子；閘門 p = 0.0931，沒過，小型深度學習淘汰；`daily_rp35.csv` sha256 `50579053bba4d5d6`）。
`RP 34` 各 Stage 都 `PASS`（審查修正後 smoke v3、full v4 124.70 秒；閘門 p = 0.0931，沒過；`daily_rp34.csv` sha256 `8afa1b6295ee6caf`）。
`RP 33` 各 Stage 都 `PASS`（smoke 110.42 秒、full 262.91 秒；閘門 p = 0.0877，沒過；`daily_rp33.csv` sha256 `2a27a26cdbeed42f`）。
`RP 32` 各 Stage 都 `PASS`（smoke 87.31 秒、full 122.39 秒；閘門 p = 0.0841，沒過；`daily_rp32.csv` sha256 `44c59f4cc3b408e9`）。
`RP 31` 各 Stage 都 `PASS`（smoke 72.64 秒、full 216.16 秒；閘門 p = 0.0825，沒過）。
`RP 30` 各 Stage 都 `PASS`（smoke v1 失敗後 v2 通過，full v3 8.47 秒）。

`RP 30` 結論：`SPA_c` p = 0.0796，沒有候選確定勝過 `c2v2d`；照登記，`RP 01～29` 不提議影子跑，`c2v2d` 主幹上疊小修正的路線停止。下一輪（`RP 31`）要先定新的評估方式，等使用者選方向。

## 方法上的保留（2026-11-26 接手時記下）

`RP 01～RP 28` 每輪都看 `WF_Test`（670 天）和 `Holdout`（28 天）的結果來選冠軍和下一個假設，`Holdout` 也每輪都報告。交接檔要求 holdout 凍結、只用一次。所以每本 notebook 內 Holm `m = 6` 的「勝過 `c2v2d`」已經不能當確認：28 輪、上百個設定都在同一段 `WF_Test` 上比過。`RP 29` 的專家也包含這樣選出的 `RP 17 M5`、`RP 23 M3`。`RP 29` 照登記跑完，但任何 RP 結果都不拿來提議影子跑或改正式模型，直到用沒看過的資料（往後的實際交易日，或跨全部 RP 候選的資料窺探校正）確認。

## 用量上限重設後之冪等續跑規則

1. 每次自動喚醒或續跑時，協調者 `ml-research-lead` 第一步必讀這份狀態檔，找出第一個狀態不是 `PASS` 的 Stage 接續。
2. 已標記 `PASS` 的 Stage 不重跑、不調換 pipeline 順序，避免快取或登記序號錯位。
3. 若中斷前已透過 Kaggle MCP 推上遠端運算，重設喚醒後先呼叫 `get_notebook_session_status` 檢查遠端是否已在等待期間變成 `COMPLETE`；若已完成就直接下載輸出進 Stage 5，不重複重推。
4. 若 Kaggle MCP 仍未啟用或未授權，保持 `BLOCKED_MCP_UNAVAILABLE` 並回報阻塞，沒有使用者同意不改用本機 CLI 或自製包裝。
5. 每完成一個 Stage，立即更新上表狀態與時間戳記。
