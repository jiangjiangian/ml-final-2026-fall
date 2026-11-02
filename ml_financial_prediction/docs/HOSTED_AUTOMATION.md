# 不靠學校主機的每日同步與模型流程

更新：2026-10-31，Asia/Taipei。這份文件說明已實作的hosted入口及啟用條件，**不以workflow檔存在宣稱排程已運行**。實際遠端run、分支與部署結果由[STATUS](STATUS.md)記錄。

2026-11-02更新：repo已恢復Private，手動rehearsal run41475878023成功；定時任務與正式提交尚未驗收。若使用者選擇公開程式／私人資料，本地已新增跨repo資料來源與獨立token支援，尚未建立資料repo或部署。下方2026-10-31 Public及恢復步驟為歷史紀錄。

## 可以用Codex排程嗎？

可以在具備該功能的ChatGPT／Codex介面建立scheduled task，但這個會話目前沒有建立或更新排程的工具。2026-10-30實讀[官方Automations文件](https://developers.openai.com/codex/app/automations)，原網址轉至`learn.chatgpt.com/docs/automations?surface=app`。現行文件區分：

| 執行方式 | 官方文件的條件 | 對本題的影響 |
|---|---|---|
| 桌面local project／worktree | 電腦開機、app運行，原目錄仍存在 | 不能當成不依賴個人電腦的部署 |
| Web scheduled task | 依可用方案／workspace啟用，可使用上傳內容及已連接工具 | 不直接繼承本雲端容器的私有目錄、環境變數或Python環境 |
| Team Tasks | 使用團隊service account及其已設定app connections在雲端執行 | 需要實際團隊功能及連線；本會話未設定 |
| CLI／IDE | 不提供Scheduled管理介面 | 可以開發／驗證程式，不能據此宣稱已建立每天排程 |

因此，本專案以可重跑Python CLI搭配GitHub-hosted runner實作確定的資料步驟；Codex排程若後續可用，適合巡檢、摘要或呼叫這份已驗證的工作流。無論哪個介面，都不能承諾排隊／延遲不會影響09:00硬截止。

## 已實作的資料流

```text
live-data的固定Git revision
    -> 驗證來源hash並還原私有raw
    -> 還原同一固定絕對路徑的模型／ledger狀態
    -> 取得跨workflow lease並以Git父commit驗證遠端未變
    -> collect：各來源獨立下載，產研究特徵，發布成功部分及缺口
       或 train / predict / submit / verify：沿用正式時鐘與資料／模型門檻
    -> 保存結果與釋放lease；未知提交狀態保留以供下次對帳
```

資料可放在同一個私人repository的`live-data`分支，或另一個私人資料repository的`live-data`；使用者也希望程式可公開並詢問僅讓組員讀資料，最後儲存方式尚待確認。啟動時驗證**資料repository**為private、Git origin對應它、checkout分支是`live-data`，且工作樹乾淨。公開程式repo與私人資料repo可以不同；不能用私人repo名稱掩蓋公開data origin，也不能把憑證寫入任一repo。

分離方案的程式已在本機實作：在程式repo設定變數`FINPRED_DATA_REPOSITORY=owner/private-data-repo`，並以GitHub Actions Secret `FINPRED_DATA_TOKEN`提供對該私人repo有必要讀寫權限的受限token；跨repo時不會默默降級用僅能存取程式repo的`GITHUB_TOKEN`。課程帳密另使用`COURSE_EMAIL`及`COURSE_PASSWORD` secrets。這些是設定名稱，不是已建立的repo、token或完成的部署；絕不將實際值貼入聊天。

兩份workflow共用`finpred-private-runtime` concurrency group。Git lease／遠端父commit檢查再處理本機CLI或其他runner：只接受fast-forward，沒有force push，也不在衝突後盲目重試POST。lease有效45分鐘，job最多35／40分鐘；逾期／失去所有權時拒絕POST。

## 入口與時程

| 檔案 | 行為 | 執行窗口 |
|---|---|---|
| `.github/workflows/live-data.yml` | 真實raw採集、內容去重、可攜catalog與研究特徵發布；一來源失敗保留舊版 | 提案台北04:17／05:17／06:17／07:17；UTC `17 20-23 * * *` |
| `.github/workflows/financial-daily.yml` | 還原狀態後執行當前合法stage；push只唯讀rehearsal | 提案07:20 train、08:10 predict、08:20 submit、08:35 verify |
| `deployment/hosted/run.sh` | 有界環境變數轉CLI參數，不把憑證放命令列 | 沿用真實時鐘，延誤不補跑過期submit |
| `scripts/run_hosted_pipeline.py` | `rehearsal`／`collect`／指定`stage`／`auto` | 純raw採集與官方session／模型是否合格分開 |

04:00～09:00是使用者要求的工作窗口，不是所有供應商都在04點完成更新。額外來源可能有尚未收盤bar；raw保留原值與取得時間，不能直接當已完成盤前特徵。

`collect`使用既有正常TLS下載器。教師憑證缺少時仍可取得公開來源，但結果會標`partial`，不冒稱教師也已更新；既有教師版本保留。研究特徵建置失敗也不阻止新raw發布。所有歷史vintage／發布時間假設仍標research，**不會為了每日更新而改成verified**。

## 啟用與可審查演練

**本輪真實遠端阻擋：** 程式提交`b39d516`的[資料同步run 41180208527](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41180208527)與[流程演練run 41180208487](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41180208487)均於private檢查停止。2026-10-31重新核對REST、GraphQL與未登入公開metadata，repository當時為`public`；這不是應繞過的程式錯誤，也不是成功採集。較早曾核對到private的狀態不能代替現在的檢查。兩份workflow另在checkout資料、安裝套件之前加入相同privacy preflight，runtime仍保留獨立檢查。

當時嘗試恢復private被API拒絕403；2026-11-02重新核對已為Private，手動rehearsal成功、手動collect部分成功。Actions Secrets設定仍受目前integration權限限制，需在GitHub安全介面配置；不要將帳密貼在聊天或提交到Git。資料repo的私人狀態、Secrets與default-branch cron入口是不同條件，全部落實後仍須查實際成功run。

1. 先推送私人`live-data`種子，核對來源與README；程式留`system-completion`，main保留空樹。
2. 推送含workflow的`system-completion`，以push事件取得真實rehearsal／collect run。這不需要先把workflow加入main。沒有course Secrets的push採集會明列partial。
3. 在repository Actions Secrets安全設定`COURSE_EMAIL`與`COURSE_PASSWORD`；`COURSE_LIVE_KEY`可選，既有下載器能由官方前端取得公開key。不要貼聊天、寫README或放命令列。自動化token是runner內建短期`GITHUB_TOKEN`，僅授予同repo內容寫權。
4. workflow曾執行／註冊後，依GitHub當前API／CLI文件嘗試手動dispatch指定branch，並以實際run確認。例如下列是入口，**不是已成功執行的紀錄**：

```bash
gh workflow run live-data.yml --repo jiangjiangian/ml-final-2026-fall \
  --ref system-completion --field mode=rehearsal
gh workflow run live-data.yml --repo jiangjiangian/ml-final-2026-fall \
  --ref system-completion --field mode=collect
```

5. **Cron仍只在default branch執行。** 目前既有main空樹與default-branch設定不能因新增這兩份檔案就算已啟用；需要明確落實default-branch入口或另一個實際scheduler，再查定時run。UI手動按鈕與API／CLI dispatch條件也不相同，不能只看YAML宣稱入口可用。
6. 接著驗收五個真實官方交易日、初始合格模型及第一筆有效回執。研究模型不能直接approved；`FINPRED_SUBMISSION_RELEASED`預設false，只有完整資料／模型及提交驗收達標後才開啟。這是部署門檻，不是重問已授權的競賽CSV上傳。

純本地驗證可以用`--mode rehearsal`讀取已checkout的私人`live-data`，前提是Git origin、private檢查及遠端父commit都通過。預設runtime固定`/tmp/finpred-hosted-runtime`；兩個runner必須相同絕對路徑，避免任意改寫模型／snapshot中的絕對路徑。

組員跨branch取用入口為`python scripts/fetch_live_data.py --repo jiangjiangian/ml-final-2026-fall --revision <固定40位commit> --runtime-dir /private/runtime --with-features`。這會核對raw與七個派生檔，將派生資料放自己的`shared-data/`；派生資料blocked時仍保留已核實raw並回報不同狀態，不把原始取得時間改為下載到組員電腦的時間。

## POST前的耐久狀態

現有提交器會先寫`post_in_flight`。hosted client在真正呼叫POST之前，再把該ledger及相容模型／預測狀態保存到私人Git、確認push成功，**之後重新讀官方state並查截止／配額與lease**，才送出請求。Git發布消耗的時間不會被忽略。

若checkpoint、CAS、Git push、fresh state或deadline失敗，不POST。若POST網路結果未知，保留in-flight／unverified，下次先比對目前有效CSV回執，不自動重送。job結束才上傳artifact或Actions cache無法提供這個POST前耐久性，所以本流程不用它們冒充ledger。

runtime只打包`approved.json`、`candidates`、`predictions`、`submission`、`verified`、`runs`及`tables`。raw另由portable catalog處理；環境、HTTP session、cookie、credential檔與鎖不打包。每個物件／索引驗hash、大小、允許路徑；拒絕symlink、FIFO、路徑穿越、重複成員、不同runtime根目錄及衝突的本地未解決狀態。每物件上限90MiB、邏輯runtime512MiB，超過時明確blocked；長期大模型／資料應遷移私有object store，不承諾Git無限容量。

## 本輪驗證與限制

新增測試涵蓋真正本機bare Git的lease／父commit競態、private與origin檢查、狀態hash／路徑／secret排除、deadline後不POST、checkpoint失敗不POST、raw與feature失敗分離，以及blocked模型仍保存結果。命令如下，完整結果由STATUS記錄：

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_hosted_pipeline.py' -v
ruff check scripts/run_hosted_pipeline.py deployment/hosted/runtime_store.py tests/test_hosted_pipeline.py
bash -n deployment/hosted/run.sh
```

這些本地合成／bare Git測試沒有更改遠端repo設定、填入Secrets或向競賽POST。歷史時間證據、模型勝出、真實定時run與真實回執仍各自驗收。

官方來源：[Codex Automations](https://developers.openai.com/codex/app/automations)、[Codex Cloud](https://developers.openai.com/codex/cloud/)、[GitHub workflow事件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)、[GITHUB_TOKEN](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)。2026-10-30取得的HTML／文字與SHA256證據在Git外`/workspace/shared/research/completion-20261030/automation-sources/`；文件閱讀不等於服務已啟用。
