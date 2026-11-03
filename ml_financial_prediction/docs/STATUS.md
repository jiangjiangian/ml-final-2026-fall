# 當前狀態與交接

更新：2026-11-03，Asia/Taipei。程式／研究、資料採集、正式模型與競賽提交分別驗收；整體尚未全部完成。較早Private／main／缺Secrets的阻礙已由使用者設定與新run解決，不再列為待辦。

## 當前部署與真實資料

| 項目 | 已核實狀態 | 證據／界線 |
|---|---|---|
| Repository與分支 | Public，default=`system-completion`；main空樹與歷史保留 | 使用者明確選擇全部公開，API已核對；資料只進`live-data`，程式分支不混raw |
| 課程Actions Secrets | 已生效 | `COURSE_EMAIL`／`COURSE_PASSWORD`由Training／Live實際下載驗證；不需再設Public／default／Secrets或重貼Live key |
| 雲端完整採集 | 全部16來源成功 | 最新手動[41593199735](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41593199735)為`collected`、16 acquired、`failures=[]`、研究特徵`exported`，資料revision=`c3f36239c699a1ab2ecafb17eb68eaff13c8fb9f` |
| 資料共享與乾淨消費 | 已通過固定版本驗收 | 較早固定`live-data@8c8f18495c01b80d02dd9b90093a8afe322c79ef`還原16來源、134 manifests及7個derived檔，原時間與hash均保留；[rehearsal41584847865](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41584847865)成功，不冒稱已乾淨消費最新revision |
| 每日資料cron | 入口條件已滿足，首個定時事件待驗收 | 下一個名義時點為台北2026-11-04 04:17（UTC11/03 20:17）；尚無首個event=`schedule`成功證據，GitHub可能延遲 |
| 正式模型／預測／提交 | blocked，尚無合格approved模型 | 歷史發布／vintage及供應商前一官方交易日覆蓋仍需證據；沒有真實預測POST、有效回執或五交易日正式演練 |

15個採集job共產16來源：training同時產course-template；另外有Live、四個外部來源、八個Yahoo序列及TWSE產業快照。兩FRED來源已用相同官方CSV、curl IPv4與正常TLS在runner成功，保留原CSV／單位檢查，不使用關閉TLS或鏡像來冒充修復。

Training SHA256仍為`7433b27103107c630e293708a7ca4b7bfcec524e91ea6dc5be3e9b7d885b90e2`。Live SHA256為`48b16f68beb92f679250a22d6e314f230e675d9d619b45c52048251aa25b78ed`，42日期09/01～11/03、100股4000完成／200pending，後續完整採集的Live內容hash未變。帳密驗證run41584330745於05:31:16Z＝台北13:31取得此版，不能回填今日08:10證據；後續取得另留各自manifest真時間。共享Top50表為83000格＝50股×1660觀測日期，100pending／26缺觀測label另列，features與labels分離，觀測聯集不冒稱官方完整交易日曆。

先前13:31採集版本的匿名catalog核對成功，SHA256為`b7308d5821670fba6616d1f922400231c304c1ce0a3dae769eda4757b4f3f0b0`；不把此舊catalog hash當最新revision。原取得時間與隊友接收時間分開，共享更新不改寫舊研究。帳密驗證run41584330745為手動dispatch，05:30:46Z～05:31:40Z，其精簡證據在Git外`/workspace/shared/research/completion-20261030/credential-enabled-collection-41584330745.json`。

## 每日流程與已通過還原演練的研究隔離模式

正式流程已有collect→train→predict→submit→verify、持久Git lease／CAS、POST前耐久ledger、fresh官方state／配額／deadline重查與未知結果先對帳。daily未供表時會自動準備七個個股lag；研究假設模型不改標verified、不寫approved、不提交。既有正式時程為07:20訓練、08:10凍結／推論、08:20提交、08:35核對、09:00硬停止。

隔離research shadow入口與workflow已隨`05eb17e`推送，[遠端還原演練41593711368](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41593711368)為`shadow_rehearsal_passed`、`submitted=false`。排程設定為台北07:25以固定`linear / weighted_classification / seed42` recipe研究fit，08:13產shadow；沿用全部來源／值重建、真時鐘、官方session／template與截止檢查，不搜尋新winner、不升級模型、不POST預測。hosted登入僅為正常TLS讀取state/template；離線shadow核心無網路。證據與模型只進獨立`shadow/`，保留研究狀態、不可變預測、來源／模型／CSV hash及本地與Git發布deadline證據。此還原演練未執行真實盤前訓練／前瞻日，不能當正式模型或五日驗收。

最新讀到的官方state有15個session（2026-10-12～11-03），尚未列11/04；未來可能每日更新，不用星期或修改時鐘補造未來官方日期。日期證據在Git外`/workspace/shared/research/completion-20261030/official-session-dates-20261103.json`。正式workflow已推送每個cron固定對應原stage的修正，避免延遲train被auto改成submit；[正式入口41593199708 attempt2](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41593199708/attempts/2)為`rehearsal_passed`、`prediction_posted=false`，原attempt1被concurrency取消，沒有當作成功。

研究workflow採獨立GitHub queue `finpred-research-shadow`，避免取代正式pending job；正式與collect仍共用`finpred-private-runtime`。三者寫回持久資料時仍共用Git durable lease／CAS，獨立queue不代表可同時繞過資料寫入鎖。

## 來源與時間門檻

正式預測要求目標日台北04:00～08:10實際取得的course-live manifest、正常TLS、payload／manifest hash，且由同一份已核對Training／Live原始ZIP重建canonical表，核對schema、版本、50股順序、cutoff、七欄數值及None mask。舊Live、晚到來源、hash或值竄改都會拒絕。這補上舊10/30 Live可作11/03輸入，以及只綁正確來源hash卻可改值的兩個缺口。

當日observed-fetch的verified只證明當次bytes在cutoff前可得，不證明歷史調整價／發布vintage，亦不證明供應商內容涵蓋前一官方交易日；這些仍是正式缺口。不能以新快照回填過去、bfill或全資料標準化求通過。

固定包IXIC／GSPC／VIX各1505/1505可比值匹配前一教師global列日期，僅1418/1506匹配前一美國native session；固定TWII／KS11各1506/1506含同日close。Live兩美股指數37/37匹配前一來源session，VIX仍有例外。這是舊凍結快照的數值觀察，不是歷史發布證據，詳見[DATA_ALIGNMENT](research/DATA_ALIGNMENT.md)。完整原生序列先計算return再as-of對齊，不能把多國inner join後相鄰列當連續來源交易日。

研究市場表有1655目標日、M0與SOX／TSM ADR／NVDA；歷史close＋2小時與個股前筆23:59僅明示假設。TX_OI兩欄因逐欄有效性不足留缺，signed OI不用普通百分比報酬；VIX變化不當資產報酬。市場資料已採集與研究，尚未自動接入正式daily模型。

## 已完成的模型研究

新R2四架構為Ridge、HistGBDT、causal TCN與市場引導跨股attention，48fits完成；中斷前30次僅接續18次，獨立逐鍵評分與可信模型／前處理重播一致。2025已看過探索fold的TCN M3-2為`0.000868847322`，同鍵全0為`0.000447093446`。這是research_assumption下的結果，不是全新樣本外或扣交易費收益，2026年1～5月已用過的保留期未重用。

R1的F0／F1／F2×兩固定模型×四季度共24fits，E04 FX／yield另註冊8fits，合計32個真實fits。R1 F2 Ridge為`0.000816754184`，E04兩模型均未勝相同F0／全0；原F3產業缺完整歷史的8slots仍blocked，不換組冒充完成。所有負結果、固定共同12140鍵分數與預註冊見[EXPERIMENTS](EXPERIMENTS.md)及[COMPLETION_CHECKLIST](COMPLETION_CHECKLIST.md)。

較早E00四族linear／GBDT／MLP／GRU×三目標×四季完成48fits；MLP普通分類validation為0.000854985259，一次2026年1～5月保留檢查0.001275711605，低於同鍵全0的0.001549845039。E01～E03市場擴充未勝相同個股配置，保留負結果。已凍結82674完整label鍵／82750全feature格不因今天共享表增大而改寫；研究版本與評分稽核在Git外保留。

真實R2報告Notebook六個code cells已完整執行，只有彙總、未另fit。Kaggle官方CLI2.2.5及私人bundle已本地驗證，但無Kaggle MCP／本人username/token，尚無遠端訓練或上傳；不能把本機Notebook當遠端成功。

## 最終本機驗證與真實遠端驗收

程式提交`617a09df597e7e03ee7d121ca2d1ff03ab5765a8`已推送，[CI41594631696](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41594631696)成功；本機Python3.12共326項全部通過，Python3.10共322項、3項選用神經網路測試skip，其餘通過。Ruff（src／scripts／tests）、兩個hosted wrapper的bash語法與diff檢查均通過。合成ZIP fixture固定timestamps，模型指標跨07:50回復與研究模型路徑限制反例均已通過；初次CI41593199598發現umask022使中間目錄755，已修逐層0700並以022測試，沒有放寬production。影子及正式入口只通過還原演練，沒有真實預測POST。

## 已確認的儲存與協作決策

依使用者最新決定全部公開，取代早期private-only／另設私人資料repo偏好；公開opt-in不放寬hash、origin、secret排除、Git鎖或模型門檻。所有branch與log不放憑證，來源再散布授權未核實，不冒稱老師禁止或已授權。跨repo私人資料方案仍是替代，當前不需另建repo／token。

日常執行器是GitHub-hosted Actions，非聊天代理。此對話無Tasks工具，不承諾聊天關閉後Codex自行常駐；也不再把學校SSH當前提。GCP可用Cloud Run Jobs／Scheduler／Storage但目前未開通，無需為現有採集另設。普通回報採繁中「結論／完成／下一步」、300中文字內／最多3重點；成熟現成工具與可獨立子代理優先。

公開ML講義基石16份495頁＋技法16份503頁抽取文字已讀至EOF，關鍵公式／圖像另核對，不冒稱998頁全部圖片逐頁審閱或可讀ChatGPT Project其他未提供內容。Graphify0.9.95、Microsoft MarkItDown0.1.9與固定OpenAI技能已安裝，來源與hash見[TOOLS](research/TOOLS.md)；現階段無需Ray／KubeRay／Kubeflow。課程報告／Phase1正式期限及保存至2027-01-31義務見README。

## 歷史部署紀錄與追溯

下表描述當時狀態，不覆蓋上方現在已驗證的Public／default／Secrets。完整較早交接可查[ea4831e版STATUS](https://github.com/jiangjiangian/ml-final-2026-fall/blob/ea4831e/ml_financial_prediction/docs/STATUS.md)，80ac804研究設計與舊188項測試紀錄亦保留於Git，不用現程式hash回填舊run。

| 歷史時點 | 當時證據 | 後續狀態 |
|---|---|---|
| dev核心11d7614 | Python3.10／3.12 CI41031916837成功，188項本機基準 | 為核心歷史基底，後續套件數依實際凍結版本 |
| deep-research@80ac804 | 63來源查核紀錄、11去重書目、四架構與共享藍圖；未新fit | 後續system-completion才實作與執行R1／E04／R2；63筆不等於63篇論文 |
| 10/31 b39d516 | CI41180208434成功，hosted41180208527／41180208487在當時private-only規則下拒絕Public；代改private403 | 後續使用者另授權全部公開並新增明確opt-in |
| 11/02 | Private時固定31650da乾淨消費16來源／32 manifests／7 derived成功，rehearsal41475878023成功 | 較早私人版本保留，新公開版本亦已乾淨消費 |
| 11/02 collect41476226337 | 11來源成功，教師兩來源缺Secrets、FRED兩來源network_or_tls，舊版保留 | FRED修復後41571756896為13來源成功；使用者設Secrets後41584330745全部成功 |
| 11/03 人工刷新221875e | Training／Live／template及兩FRED更新，台北11:04取得Live42日期 | 此為人工5來源刷新；完整雲端更新另見41584330745，均晚於今日freeze |

## 下一個具體工作

1. 核對首個真正schedule採集，依官方session保存真實盤前版本、執行隔離研究訓練／前瞻預測，驗證準時持久化；不造未來session或回填晚到資料。
2. 補齊歷史發布／vintage與供應商前一官方交易日覆蓋，驗證初始正式模型；shadow只能提供隔離前瞻證據，不能取代嚴格歷史認證或正式approved。
3. 依真實官方session累積五交易日演練及有效回執，再標記每日服務完成。完整產業F3／E05仍待歷史來源，E04已完成且無增益，不重做已用holdout或無限搜尋validation。

詳細入口：[進度報告](PROGRESS_2026-11-03.md)、[全量清單](COMPLETION_CHECKLIST.md)、[每日共享特徵](LIVE_DATA_FEATURES.md)、[hosted](HOSTED_AUTOMATION.md)、[Kaggle](KAGGLE_TRAINING.md)、[報告骨架](REPORT_OUTLINE.md)。重跑命令見README；更新記憶／決策／Graphify後再壓縮context。
