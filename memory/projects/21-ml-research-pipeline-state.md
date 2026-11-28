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
- `RP 38`（依名次調整押法）2026-11-27 做完：三個代價上限都判 `unreachable`，P00 進 OUT 前 10 0.0125%，上限 0.045 選中的列 0.287%；照登記維持 c2v2d 25/25。結果在 `22` 的「`RP 38` 實驗結果」。
- 使用者 2026-11-28 凌晨的決定（選擇題）：押法層這條（UB 03 到 RP 38）結案。下一步沒選列出的三個（`RP 39` 法人層樣本外確認、停止 RP 寫總結、Kronos-small 當第四個成員），自己寫：「我要超多資料（至少百萬）做微調大模型！」Claude 先查資料來源、可以微調的模型和評估方法，寫成設計草稿，再用選擇題問使用者定案，事先登記後才實作。編號用 `RP 40`（`RP 39` 仍留給 FinMind 法人層，本機草稿資料夾已用這個號碼）。
- 使用者 2026-11-28 01:50 對 `RP 40` 設計草稿的回答（選擇題）：測試期從 2025-07-01 起（Kronos 權重上傳之後）；過關標準放寬 11-26 的累計閘門規則，只對 `RP 40` 用 N1 式（事先凍結的單一候選，乾淨測試期 `c2v2d + 新成員 − c2v2d` 單邊 p < 0.05，而且和「過去 L 天平均盤中報酬」的名次相關 < 0.8，就提議影子跑；閘門照算照寫、不擋）。資料範圍和模型交給 Claude 決定，但要先用 deep research 查公開資料集和微調的好方法（使用者：「守德老師說可以微調那些預訓練模型，我認為重點是資料要夠多且符合我們題目」）。使用者想把幾個模型都跑看看，瓶頸是 GPU；說還有另一個 Kaggle 帳號，也問 Colab 能不能用 CLI 讓 Claude 連。設計草稿在 scratchpad `bigft/design_draft.md`（反駁修過 15 處），研究完再定資料和模型、寫事先登記。
- 候選 `RP 39`（還沒登記）：FinMind 2006～2019 的法人層樣本外確認。`RP 37` 的登記原本把 `RP 38` 留給它，2026-11-27 改給依名次調整押法。設計草稿在本機 `notebooks/kaggle/2026-11-23_v1_research-pipeline/rp-39-inst-layer-oos-finmind-2006-2019/design_draft.md`（11-27 從 `rp-38-…` 改名）。
- 使用者 2026-11-27 對 `RP 38` smoke 前的回答（選擇題）：同意把去名的名次快照上傳成私人 Kaggle 資料集；未來的波動照歷史慢慢變平靜（GJR-GARCH 回落）當主要情境，「一直維持現在的大小」只報告（第一次問時使用者說看不懂，Claude 用白話重講後才選）；前 10 照登記，只排除每天都被強制的 18 隊。問之前已告訴使用者預期最可能維持 25/25。
- 使用者 2026-11-27 看完 `RP 37` 後的決定（選擇題，四題都選推薦）：12-06 照兩條觸發規則（正式期累計 `c2v2d − rank_ensemble` 或 `c2v2d − c2` 低於 −2.33·σ·√天數才用選擇題提議換，否則維持）；接受 `RP 37` 讀 `116e5bd` 的例外；下一步做依名次調整押法；正式期的結束日由 Claude 從 Mac 登入讀一次 `/api/state`（只讀）。
- 使用者 2026-11-27 的決定（選擇題，看完網路研究 `memory/projects/23-recent-prediction-research.md` 之後）：下一步做「c2v2d 風格歸因」（沒選：照原計畫做法人層確認、依名次調整押法、Kronos-small 當第四個成員）。
- 使用者 2026-11-27 的決定（選擇題）：路線圖做完後，下一步做「樣本外確認法人層」（沒選：停止 RP 寫總結、兩個都做）；`RP 36` 的 collection 由 Claude 開新的 Safari 視窗加；11-24 08:18 從 Mac 送出的全部猜漲上傳（蓋掉 oop 07:29 的 `c2v2d`）補進 repo：`upload_log.jsonl` 和 `run_2026-11-24.log` 照時間插入那幾行，加上 `submission_2026-11-24_all1.csv` 和網站原本那份的備份。路線圖到 `RP 36` 結束，之後用選擇題問使用者（沒選過的方案：FinMind 2005～2019 法人資料的樣本外確認，或停止 RP 寫總結），不要自己加 `RP 37`。
- 使用者 2026-11-26 對 `RP 31` 起的決定（選擇題）：照 Antigravity 的路線圖探索新架構（PCA 殘差、低秩 VAR、HMM／卡爾曼、路徑簽名、小型深度學習、決策導向學習），仍用看過的 `WF_Test`，結果只當探索。每個新候選加進 `RP 30` 的 93 個候選池，累計 `SPA_c`（區塊長 20）`< 0.05` 才算過。沒選的方案：用 FinMind 2005～2019 法人資料做法人層的樣本外確認（已查證可行：`TaiwanStockInstitutionalInvestorsBuySell` 2005-01-01 起、免費版每小時 300～600 次；自營商 2014-12-01 前是合併的 `Dealer`），以及停止 RP 寫總結。
- Collection：使用者 2026-11-26 要 Claude 用 Safari 建 `ML 2026 Fall｜17 全新研究管線（RP）`，加入 `RP 01～30` 共 31 本（含沒有輸出的 `rp-05-institutional-flow-and-state-shrinkage-c2v2d`）。
- Git：使用者 2026-11-26 同意 commit 並 push 研究檔。`notebooks/kaggle/` 照 `notebooks/README.md` 只在本機，不進 Git；只 commit `memory/projects/20～22`、`CLAUDE.md` 的索引列、`README.md` 檔案樹的兩處。本機落後遠端 40 個 commit，而且 `README.md`、`run_daily.py`、`data/submission/upload_log.jsonl`、`run_2026-11-24.log` 兩邊都有改，所以在暫存 worktree 從遠端最新版 commit 再 push，主工作樹不動。之後在主工作樹 pull 時，這三個 memory 檔會以「未追蹤檔會被覆蓋」擋下，內容和遠端一樣，先移開再 pull。
- N1 核對（2026-11-26）：遠端 `6feb1dd` 就是 N1 影子跑的 commit；`RP 01` 查到「本機沒有 N1」是因為本機 checkout 停在 `f02b89d`，落後遠端 40 個 commit。
- Kaggle 途徑：claude.ai Kaggle 連接器回 `Unauthenticated`，`authorize` 300 秒沒回應。使用者 2026-11-26 決定這次接手改用 Kaggle 官方 CLI（`.venv/bin/kaggle`，帳號 `modelnovice`），走 repo 原本的 `notebooks/kaggle/push_all.sh --dir 2026-11-23_v1_research-pipeline --only <slug> [--smoke]`。這是交接規則「MCP 不能用就停」的例外，只限這次接手。
- 下一輪：使用者 2026-11-26 決定 `RP 30` 先做資料窺探校正，Antigravity 的 `RP 30～35` 路線圖（PCA 殘差、低秩 VAR、HMM、路徑簽名、小型深度學習、決策導向學習）往後排，編號順延。
- Kaggle Collection：`ML 2026 Fall｜17 全新研究管線（RP）`（id 19687957，2026-11-26 Claude 用 Safari 視窗 25140 建立）。`RP 01～38` 加上沒輸出的 RP 05 舊版共 39 本，都用抽屜檢查確認在裡面（第一輪有 RP 01、12、13、17 沒加成功，重加後確認；RP 36～38 在 2026-11-27 用 Safari 視窗 84 加入）。之後每本跑完就加。
- Kaggle slug 和資料夾名不同的四本：`rp-05-inst-flow-and-state-calibration-c2v2d`、`rp-07-rich-online-adapter-and-bounce-soft-tail`、`rp-11-inst-reg-and-smooth-ov-stress`、`rp-22-trdl-asymmetric-weights-and-gap-ema`（Kaggle 用標題產生 slug）。另有一本沒有輸出的 `rp-05-institutional-flow-and-state-shrinkage-c2v2d`。

`RP 40`（微調 Kronos 當 c2v2d 的第四成員；研究結論和登記在 `22` 最後兩節，2026-11-28）：

| Stage | 內容 | 狀態 | 備註 |
|---|---|---|---|
| 套件 | `src/twfm/`（commit `22b9abd`） | `PASS` | workflow 寫、11 個審查發現修 10 個（出場遇漲跌停的遮罩延後，README 有寫）；加 A100 用的 bf16 |
| RP 40s smoke | `modelnovice/rp-40s-twfm-pipeline-smoke` | `PASS` | v1（smoke）100 秒：150 個測試全過，端到端都 `done`；v2 速度實測 1,207 秒，T4 凍結主幹 678 視窗／秒（一個 epoch 1.0 小時），結果在 `22` 的「`RP 40s` 結果」 |
| 登記 | `22` 的「`RP 40` 事先登記」 | `PASS` | 使用者 01:50 的四個回答加 Claude 定的資料和模型；真資料訓練前 commit |
| RP 40a 下載 | `modelnovice/rp-40a-finmind-tpex-prices-and-chip` | full 跑中 | smoke v1 `PASS`；full v2（CPU）上櫃價格約 3.3 小時，籌碼照進前 500 的年數抓到 11.3 小時，預計台北 11-28 16:45 左右結束 |
| RP 40b 面板 | `modelnovice/rp-40b-twfm-panel-and-audit` | smoke `PASS`，full 等 40a | 官方每季檔放私人資料集 `rp40-official-quarter-files`；smoke v3 錨點過（參考價改用交易所的除權息表）；v4（smoke）加第 11 節「50 檔在股票池的比例」，只記錄不擋。40a 跑完就推 full，先看這節再推 40c full |
| RP 40c LP | `modelnovice/rp-40c-kronos-linear-probe-validation` | smoke `PASS`，full 等 40b | smoke v1 37 秒：`head` 1 epoch、IC 表、`best_L`、第四成員、S1 判讀都有輸出，重算的 c2v2d 和 UB 01 每格一樣。full 約 4.5～9 小時（L 64、128 各 2 個 epoch） |
| RP 40d 變體 | `modelnovice/rp-40d-kronos-last2-and-lora-validation` | smoke `PASS`，full 等 40c | smoke v1 70 秒。產生時要給 40c 選的 L：`python3 bigft_tools/gen_rp40d.py <L>`。`find("report.json", "rp40c/report.json")` 修過（40c 的輸出有兩個 `report.json`） |
| RP 40e 重訓 | `modelnovice/rp-40e-kronos-final-refit-hidden-test` | smoke `PASS`，S1 過才跑 full | twfm 加 `final_fit`、`score_test`、`stop_after`（`22` 的「`RP 40c`～`40e` smoke」）；smoke v1 203 秒：151 個測試全過，十個工作都 `done`，測試期檔只有分數欄。Kaggle 跑 `FT_s0,LP,FT_SMALL,PATCH_val,PATCH_final`，Colab 跑 `SC_val_2e-4,SC_val_1e-3,SC_final,FT_s1,FT_s2`（`bigft_tools/out/rp40e_colab.py`） |
| RP 40f 測試期 | `modelnovice/rp-40f-kronos-test-period-once`（CPU） | smoke `PASS`，40e 全部做完才跑 full | smoke v2 274 秒（讀 40e smoke 的預測）：錨點對 RP 36、UB 01 都 < 1e-15，N1 重算 100% 一樣，`X4_PLACEBO` 重播和 `s41` 每天名次相關 0.9999。full 前要先把 Colab 的輸出包成私人資料集，`python3 gen_rp40f.py --colab-dataset <owner/slug>` 重產（Colab 的 `report.json` 改名 `report_colab.json`，免得和 Kaggle 那份撞） |
| 算力 | Kaggle 設定頁（Safari 視窗 84，2026-11-28 10:30） | | Kaggle GPU 這週用了 0.03 小時（上限 30）；40c、40d full 合計約 17 小時放 Kaggle，40e 的 `SC` 和種子 1、2 放 Colab A100（標準版，不開高 RAM） |

產生器在 scratchpad 的 `bigft_tools/`（`nbkit.py`、`gen_rp40a.py`～`gen_rp40f.py`），本機備份在 `notebooks/kaggle/2026-11-23_v1_research-pipeline/rp-40-tools/`（不進 Git）。40b～40d 的 twfm 釘在 `bigft_tools/twfm_frozen_40cd/`（sha `f2f7dca4a0af`，產生器裡有 assert），40e 用 wt-rp 的新版。

`RP 38`（`modelnovice/rp-38-rank-chasing-bet-layer`，依名次調整押法，只做決策模擬；登記在 `22` 最後一節）：

| Stage | 角色 | 狀態 | 備註 |
|---|---|---|---|
| Stage 1 Scope & Tooling Gate | `ml-research-lead` | `PASS` | 2026-11-27 使用者選的；Kaggle CLI 照舊；不加候選、不跑 `SPA_c` |
| Stage 2 Audit & Preregistration | `literature-and-data-researcher` | `PASS` | 三個審查（草案過時、對手模型、剩餘天數和上線）加一個評審；Claude 重算起點；使用者回答三題後登記，smoke 前單獨 commit |
| Stage 3 Kaggle Smoke Run | `kaggle-experiment-runner` | `PASS` | 去名資料集 `ml-final-phase2-board-anon-1127`（私人）建好；smoke v1 40 秒、檢查都過；日曆改成 12-25 休市（`22` 的「smoke 後的更正」，`b320028`）；smoke v2 26 秒 |
| Stage 4 Kaggle Full Run | `kaggle-experiment-runner` | `PASS` | full v3 1,017.86 秒 `complete`；三個上限都 `unreachable` |
| Stage 5 Independent Verification | `independent-verifier` | `PASS` | `verify_rp38_claude.py` 217 項 ALL PASS（REML 的容許值改過，notebook 沒動） |
| Stage 6 Memory & Collection | `memory-and-docs-maintainer` | `PASS` | 結果寫進 `22`（三個 agent 從數字、登記、寫作檢查過）；collection ｜17 已加（抽屜檢查確認）；三個上限判讀相同，不用使用者挑 |

`RP 37`（`modelnovice/rp-37-c2v2d-style-attribution`，c2v2d 分數的風格歸因，只診斷；登記在 `22` 最後一節）：

| Stage | 角色 | 狀態 | 備註 |
|---|---|---|---|
| Stage 1 Scope & Tooling Gate | `ml-research-lead` | `PASS` | 2026-11-27 使用者看完網路研究（`23`）選的；Kaggle CLI 照舊；不加候選、不跑 `SPA_c` |
| Stage 2 Audit & Preregistration | `literature-and-data-researcher` | `PASS` | 三個設計者（計量歸因、決策規則、資料和時點）加一個評審；登記在 smoke 前單獨 commit；正式期讀 `116e5bd` 是評審決定的例外，使用者可以否決 |
| Stage 3 Kaggle Smoke Run | `kaggle-experiment-runner` | `PASS` | v1 97.1 秒全過；審查確認 1 個小問題（核對腳本），smoke 前修好 |
| Stage 4 Kaggle Full Run | `kaggle-experiment-runner` | `PASS` | v2 111.92 秒；smoke 之後 notebook 沒改 |
| Stage 5 Independent Verification | `independent-verifier` | `PASS` | ALL PASS（核對腳本改成 round_trip 讀檔後）；正式程式雜湊不變 |
| Stage 6 Memory & Collection | `memory-and-docs-maintainer` | `PASS` | 結果寫進 `22`；`daily_rp37.csv` sha256 `94cb414444a71639`；collection ｜17 已加；`05-daily-model.md` 補分數來源 |

`RP 36` 各 Stage 都 `PASS`（smoke v1、full v2 345.51 秒；閘門 p = 0.0943，沒過；`daily_rp36.csv` sha256 `e2efb571653afbd7`；collection ｜17 已加）。
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
