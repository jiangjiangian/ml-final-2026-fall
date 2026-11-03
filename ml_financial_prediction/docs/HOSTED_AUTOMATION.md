# 不靠學校主機的每日同步與模型流程

更新：2026-11-03，Asia/Taipei。實際執行器採GitHub-hosted Actions，repo為Public、default branch為`system-completion`，main空樹保留。Actions課程Secrets由41584330745驗證有效，[後續完整採集41593199735](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41593199735)亦取得16來源並匯出研究特徵，資料revision為`c3f36239c699a1ab2ecafb17eb68eaff13c8fb9f`。最新CI、研究與正式入口還原演練均成功；第一個event=`schedule`、真實盤前前瞻日與正式模型／競賽提交仍待驗收，不以手動成功冒稱每天準時運作。

兩份workflow依使用者「暫時全部公開」決定設定`FINPRED_ALLOW_PUBLIC_DATA=true`；CLI須`--allow-public-data`，未opt-in仍拒絕公開資料發布。來源identity、hash、credential排除、Git鎖與模型／截止門檻不變。教師ZIP／Yahoo再散布授權尚未核實，不冒稱來源方已授權或禁止。

## 可以用Codex排程嗎？

具備該功能的ChatGPT／Codex介面可以建立scheduled task，但本會話沒有建立或更新排程的工具。2026-10-30實讀[官方Automations文件](https://developers.openai.com/codex/app/automations)，原網址轉至`learn.chatgpt.com/docs/automations?surface=app`。當時文件的能力邊界如下：

| 執行方式 | 官方文件的條件 | 對本題的影響 |
|---|---|---|
| 桌面local project／worktree | 電腦開機、app運行，原目錄仍存在 | 不能當不依賴個人電腦的部署 |
| Web scheduled task | 依方案／workspace啟用，可使用上傳內容及已連接工具 | 不直接繼承本容器私有目錄、環境變數或Python環境 |
| Team Tasks | 團隊service account及其已設定app connections | 需要實際團隊功能與連線，本會話未設定 |
| CLI／IDE | 不提供Scheduled管理介面 | 可開發／驗證程式，不能據此宣稱已建每天排程 |

本專案以確定的Python步驟搭配GitHub-hosted runner；聊天關閉不影響已部署的GitHub cron。Codex排程日後若可用，可巡檢或呼叫既有workflow，不應取代真實排程／截止與回執證據。GitHub可能排隊或延遲，不能保證09:00前一定完成。

## 已實作的資料流與儲存

```text
live-data的固定Git revision
    -> 驗證來源hash，還原runner內0700私有runtime
    -> 還原同一固定絕對路徑的模型／ledger狀態
    -> 取得跨workflow lease，以Git父commit驗證遠端未變
    -> collect：各來源獨立下載、研究特徵、成功部分與缺口
       或 train / predict / submit / verify：正式時鐘與資料／模型門檻
    -> 保存允許的狀態並釋放lease；未知提交結果留待對帳
```

目前同一公開repository的`live-data`保存portable raw、catalog、derived及允許的持久狀態；程式分支不混入raw。啟動時核對實際可見性與公開opt-in、repository identity、Git origin、`live-data`分支及乾淨工作樹。任何分支／log都不放帳密、token或cookie。匿名catalog已核對內容hash成功，組員取用資料無須網站帳密。

正式與collect共用GitHub concurrency group `finpred-private-runtime`，名稱沿用早期實作，不代表repo仍私人。研究shadow採獨立queue `finpred-research-shadow`，避免取代正式pending job；三者寫回仍共用durable Git lease／CAS，獨立queue不繞過資料鎖。只接受fast-forward、不force push、不在衝突後盲目重試POST。lease有效45分鐘，job最多35／40分鐘，逾期或失去所有權時拒絕POST。

若日後改選公開程式／私人資料，可設定`FINPRED_DATA_REPOSITORY=owner/private-data-repo`及受限的Actions Secret `FINPRED_DATA_TOKEN`。這是仍支援的替代方案，目前無需另建repo／token。同repo自動化使用runner內建短期`GITHUB_TOKEN`，workflow只授予必要的contents寫權。

## 入口與時程

| 檔案 | 行為 | 台北時程 |
|---|---|---|
| `.github/workflows/live-data.yml` | 真實raw採集、去重、catalog／研究特徵發布，一來源失敗保留舊版 | 04:17／05:17／06:17／07:17；UTC `17 20-23 * * *` |
| `.github/workflows/financial-daily.yml` | 還原狀態，執行目前合法stage；push只唯讀rehearsal | 07:20 train、08:10 predict、08:20 submit、08:35 verify |
| `.github/workflows/research-shadow.yml` | 固定recipe研究fit與隔離shadow；push只還原rehearsal，永不POST預測 | 07:25研究fit、08:13 shadow，實際前瞻日尚待驗收 |
| `deployment/hosted/run.sh` | 有界環境變數轉CLI，不把憑證放命令列 | 沿用真時鐘，延遲不補送過期submit |
| `scripts/run_hosted_pipeline.py` | rehearsal／collect／stage／auto | raw採集獨立於官方session與模型；正式stage另驗session |

08:10／08:20等是本專案操作時程，老師硬截止為09:00。04:00～09:00是工作窗口，不保證供應商04點已更新；當日未收盤bar不得直接當盤前特徵。

下一個資料cron名義時點為台北2026-11-04 04:17（UTC11/03 20:17）。default branch入口與憑證已落實，但仍須核對真正的event=`schedule`、來源狀態及取得時間，不能以手動dispatch代替。資料採集每日可運行；競賽訓練／預測／提交另外依官方session與真時鐘決定，不能只用星期推定開放。

collect有15個下載job但產16來源：training同時產course-template。單一來源失敗會保留舊版並標partial，研究特徵失敗亦不阻止raw發布。兩個FRED來源目前指定`curl_ipv4`正常TLS傳輸，CSV／單位／大小檢查不變；其他來源維持原adapter。所有歷史發布／vintage假設仍標research，不因每天重抓而改為verified。

## 已完成設定與重跑入口

| 設定／驗證 | 現況 |
|---|---|
| Repository可見性 | Public，使用者已決定並設定 |
| Default branch | `system-completion`，含兩份workflow；main空樹仍保留 |
| Actions課程Secrets | `COURSE_EMAIL`、`COURSE_PASSWORD`已設定，Training／Live實際下載成功；不需再次提供 |
| Live key | `COURSE_LIVE_KEY`可選，下載器能由官方前端取得公開key；不需另貼聊天 |
| 同repo寫回 | 使用內建短期token，手動採集已成功發布`live-data` |
| 正式提交開關 | `FINPRED_SUBMISSION_RELEASED`仍預設false；合格模型／dry run／提交驗收未齊，不手動略過 |

下列入口已可執行；最新實際結果以STATUS與Actions run為準：

```bash
gh workflow run live-data.yml --repo jiangjiangian/ml-final-2026-fall \
  --ref system-completion --field mode=rehearsal
gh workflow run live-data.yml --repo jiangjiangian/ml-final-2026-fall \
  --ref system-completion --field mode=collect
```

本機rehearsal須有已checkout的`live-data`、正確origin與遠端父commit；公開模式加`--allow-public-data`。hosted runtime固定`/tmp/finpred-hosted-runtime`，跨runner保持相同絕對路徑，避免任意改寫模型／snapshot中的路徑。

組員從業務目錄取用：

```bash
python scripts/fetch_live_data.py --repo jiangjiangian/ml-final-2026-fall \
  --revision <固定40位commit> --runtime-dir /private/runtime \
  --with-features --allow-public-data
```

會核對raw及七個派生檔，將派生資料放自己的`shared-data/`；派生blocked仍保留已核實raw並分別回報，不把原取得時間改為隊友下載時間。

## POST前的耐久狀態

提交器先寫`post_in_flight`，hosted client在真正POST之前，把ledger及相容模型／預測狀態保存到持久Git並確認push，**再讀fresh官方state與截止／配額、驗lease**，才送請求。Git發布消耗的時間不會被忽略。

checkpoint、CAS、push、fresh state或deadline失敗均不POST。網路結果未知則保留in-flight／unverified，下次先比對目前有效CSV回執，不自動重送。job結束才上傳artifact或Actions cache無法提供POST前耐久性，本流程不用它們冒充ledger。

runtime只打包`approved.json`、`candidates`、`predictions`、`submission`、`verified`、`runs`、`tables`及獨立研究用`shadow`；raw另走portable catalog。環境、HTTP session、cookie、credential檔與鎖不打包。每個物件／索引驗hash、大小及允許路徑，拒絕symlink、FIFO、路徑穿越、重複成員、runtime根路徑不符與未解決狀態衝突。runner內runtime各層目錄0700、檔案0600，不能只保護leaf。物件上限90MiB、邏輯runtime512MiB；超過明確blocked，長期大資料可再遷object store，不承諾Git無限容量。

## 已推送且通過還原演練的隔離研究入口

`research-shadow.yml`、`run_hosted_shadow.py`與離線`run_shadow_forecast.py`已隨`05eb17e`推送，[研究還原41593711368](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41593711368)為`shadow_rehearsal_passed`、`submitted=false`。研究workflow設定於台北07:25固定linear／weighted_classification／seed42 fit，08:13 shadow推論；採獨立GitHub queue但共用durable Git lease／CAS。`shadow`只保存獨立研究模型、來源／template證據、不可變預測與真實完成／Git發布截止證據，不寫approved或正式prediction指標、不POST預測。還原演練沒有執行真實盤前fit或前瞻日。

hosted預測會以正常TLS登入並讀官方state／template，最小session證據排除帳號與cookie；離線核心不建網路client，重用來源hash／值重建、當日04:00～08:10取得、08:10凍結與09:00前持久化檢查。最新官方state有10/12～11/03共15 sessions、尚無11/04，不能用星期補造日期或把shadow當五個正式交易日驗收。正式workflow已推送每個cron固定到原stage的修正，避免排隊延遲後auto改跑其他stage；[正式還原41593199708 attempt2](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41593199708/attempts/2)為`rehearsal_passed`、`prediction_posted=false`，原attempt1曾被concurrency取消，不當作成功。

本地`completion.json`只綁定先前已fsync的預測與manifest，不能單獨證明完成標記或雲端準時寫入；SIGKILL可能留下候選標記。hosted前瞻證據還須核對`hosted-publication.json`中的Git commit、CSV hash及`hosted_persistence_before_deadline=true`。可捕捉的中斷會清除標記；固定recipe另綁定套件與模型程式hash。最後修正`617a09d`的研究還原演練[41594631484](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41594631484)亦成功，並非真實盤前預測。

## 驗收與歷史紀錄

帳密驗證採集41584330745的證據在Git外`/workspace/shared/research/completion-20261030/credential-enabled-collection-41584330745.json`；後續41593199735亦為16來源`collected`／`failures=[]`／特徵`exported`。程式`617a09df597e7e03ee7d121ca2d1ff03ab5765a8`的[CI41594631696](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41594631696)成功；本機Python3.12共326項全部通過、3.10共322項含3skip其餘通過，Ruff（src／scripts／tests）、兩個hosted wrapper的bash語法與diff檢查通過。初次CI發現umask022下中間目錄755，已修逐層0700並強制022測試。這些測試與還原演練不等於真實盤前預測、正式提交或回執。

| 歷史時點 | 當時結果 | 現在的解讀 |
|---|---|---|
| 10/31 runs41180208527／41180208487 | 當時僅授權私人模式，Public被private gate拒絕；代改private回403 | 歷史安全檢查，不是目前公開模式故障 |
| 11/02 rehearsal41475878023／collect41476226337 | 當時恢復Private；rehearsal成功、collect部分成功 | 之後已另獲全部公開授權 |
| 11/03 collect41571756896 | FRED修復，13來源成功，教師帳密缺少 | 已由使用者設定Secrets及41584330745完整採集取代 |

目前仍須首個定時run、歷史PIT／供應商更新證據、初始合格正式模型、五個真實官方交易日dry run與有效競賽回執。研究模型不得直接approved，也不為完成任務放寬門檻。

官方來源：[Codex Automations](https://developers.openai.com/codex/app/automations)、[Codex Cloud](https://developers.openai.com/codex/cloud/)、[GitHub workflow事件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)、[GITHUB_TOKEN](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)。2026-10-30取得的HTML／文字及SHA256證據在Git外`/workspace/shared/research/completion-20261030/automation-sources/`；文件閱讀不等於服務已驗收。
