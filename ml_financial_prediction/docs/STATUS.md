# 當前狀態與交接

## 2026-11-03最新決定與交付

續作最新雲端採集41571756896：13來源成功、教師Training／Live兩項因missing_course_credentials失敗。FRED已以相同官方CSV、curl IPv4正常TLS及原有資料解析實際修復；新data commit346f87d。公開／default／Secrets設定的403仍未解除，正式排程仍未啟用。新測試3.12共301項通過、3.10共297含3skip；詳見進度報告。

本次續作已推送`live-data@221875e`：人工刷新Training／Live／template及兩FRED來源；Live42日期4000完成／200 pending，台北11:04取得，不能作今日盤前證據。共享表83000格、100 pending labels、26缺觀測label。正式預測入口已從hash核對的原始ZIP重建並比對特徵值／schema／來源程式版本，補上只綁hash卻可改值的缺口；官方交易日覆蓋／供應商更新狀態仍需證據。新的外部來源診斷workflow已推送，沒有放寬TLS。299項3.12測試通過、3.10共295項含3skip；詳見報告的續作段落。

完整本輪進度與操作清單見[2026-11-03報告](PROGRESS_2026-11-03.md)。實際採集已確認：教師Training／Live缺GitHub Actions憑證，FRED兩來源為network_or_tls；舊版保留。公開與default branch修改均403，試圖安全寫入COURSE_EMAIL secret也403，因此repo仍Private、default仍main、cron未啟用。程式公開模式提交cf89ddb的遠端CI41558603125成功；Python3.12共294項通過、3.10共290項／3 skips。這不是正式每日服務全部驗收完成。

使用者決定「全部公開」，不再要求資料只給組員或另設私人repo。程式已加入明確公開資料opt-in，工作流配置依此選擇；CLI需`--allow-public-data`，hosted需`FINPRED_ALLOW_PUBLIC_DATA=true`。公開模式不放寬hash、來源identity、secret排除、Git CAS／lease、模型或deadline gate。GitHub可見性與default branch尚須實際套用／核對，不能把程式完成稱為設定已完成。

GCP是Google雲端平台，可用Cloud Run Jobs／Cloud Scheduler／Cloud Storage承接定時批次與持久資料，但尚未開通帳戶／建立資源；目前先沿用已實作的GitHub Actions。Codex本對話仍沒有建立排程工具。

## 2026-11-02最新更新

獨立稽核實際發現舊builder可將10/30 Live作11/03輸入；已在prediction builder及顯式預測表入口加入目標日04:00～08:10真實取得的course-live manifest／hash／TLS檢查，舊快照反例現在blocked。該檢查不證明供應商資料已涵蓋前一官方交易日，也不證明外部表內數值由來源bytes正確轉換；這兩項仍須正式驗證，不能據此宣稱freshness完整或模型可上線。

目前GitHub實查已恢復Private；使用者希望公開程式，但資料只給組員，正在選擇「整個repo私人」或「公開程式＋獨立私人資料repo」。GitHub branch無獨立可見性。教師ZIP的公開再散布授權尚未核實，沒有證據可宣稱老師明文禁止；FinMind條款不是本次16來源的授權依據。下方2026-10-31 Public／等待恢復Private為歷史紀錄，不代表目前狀態。

R2已完成48 fits：原30次中斷後只續跑18次；逐鍵重算與可信模型／前處理器重載重播皆通過。2025探索fold固定配置的TCN M3-2為0.000868847322；同鍵全0為0.000447093446。這些是已使用過的validation與歷史可用性研究假設，不是全新樣本外績效、已批准正式模型或實盤收益。時間窗口採教師觀測日期聯集，不是已認證完整台股日曆；2026年1～5月保留期未重新使用。Notebook已以真實R2報告模式完整執行；未在Kaggle遠端執行。

固定live-data commit `31650da87d5e37d856050425707cd75e73736d75`已由另一個乾淨遠端checkout下載驗證：16來源、32份manifest及7份特徵／標籤輸出均成功還原，保留真實取得時間。GitHub Actions手動rehearsal [41475878023](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41475878023)成功；手動collect [41476226337](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41476226337)工作結束但資料狀態為partial，11個來源成功、教師Training／Live與兩個FRED來源失敗；前版快照保留，實際錯誤原因尚待診斷。新資料commit `5b226c409fda84d9e28fdf68fe91c575c9f38a8d`。這不是全部來源更新成功，也不是定時排程已啟用。

更新：2026-10-31，Asia/Taipei。最新整合工作在`system-completion`；私人資料分支為`live-data`。正式PIT模型、競賽真實POST／有效回執及五個未來官方交易日演練仍未完成，不能將整體標為全部完成。最新外部阻礙：repository已變為PUBLIC；已停止發布與消費，等待恢復Private後再查核。

## 本輪系統交付：已完成、執行中與外部阻礙

| 使用者預期 | 現有證據 | 尚未完成／不能推定 |
|---|---|---|
| 每天抓資料、各branch取得相同版本 | 已推送私人`live-data`首版，16種真實來源；content-addressed raw、可攜manifest／catalog、固定revision取用與反例測試已實作 | 第二個乾淨遠端消費因repo已變Public而被正確拒絕；真正定時run未通過，不能把cron檔當排程已運作 |
| README file tree與每個return／lag含義 | `live-data/README.md`逐欄列七股lag、M0／SOX／ADR、單位、觀測列與原生session差別；每日匯出有schema／lineage | 研究歷史日期／vintage未認證；有raw不代表可正式回測 |
| 每次更新產生可用資料 | 本機真實16來源匯出82900列＝50股×1658觀測日期；features／labels分開，保留50 pending與26缺觀測label | 1658日期是教師觀測聯集，不稱已認證台股日曆；正式daily市場／歷史表仍守verified gate |
| 增加經濟資料與受控特徵比較 | R1有F0／F1／F2、兩模型、四季度24 fits；另預註冊E04 FX／yield子集8 fits；全部32份預測獨立重算一致 | 原F3產業歷史不足，8個slots仍blocked；完整產業／另列交互作用E05未完成 |
| 四種架構實作與比較 | Ridge／HistGBDT／causal TCN／市場引導跨股attention已實作；完整50股feature panel與獨立label mask、因果／批次逐日等價測試存在 | R2在30/48 checkpoint後環境中斷，由detached恢復流程接續固定剩餘18 fits（已核對至31/48）；最終report／分數稽核前不選winner |
| Notebook與Kaggle訓練 | Notebook本地6個code cells完整執行，demo僅4個合成fits；官方Kaggle2.2.5私人bundle與12反例測試完成 | 真實R2 report模式尚待；無Kaggle MCP／本人username／token，沒有遠端訓練或上傳 |
| 不依賴學校主機的每日流程 | GitHub-hosted collectors／模型stage入口、跨workflow lease＋Git父commit、POST前耐久ledger及失敗保存已實作；19項hosted測試在3.10／3.12通過 | Secrets API讀取回403；兩次真實hosted run因repo Public而正確blocked。嘗試恢復Private亦403，需使用者操作；真正cron／完整憑證尚未驗收 |
| 用Codex排程 | 現行官方文件有介面排程，桌面local project需電腦／app運行；web tasks不繼承本容器目錄／Python環境 | 本對話沒有建立／更新排程工具，不能冒稱聊天關閉後本代理自行常駐 |

本輪latest raw根目錄為`/workspace/shared/completion-runtime/raw/`。Training在2026-10-30T15:47:29Z取得18,278,354bytes，SHA256仍為`7433b27103107c630e293708a7ca4b7bfcec524e91ea6dc5be3e9b7d885b90e2`；Live在15:47:34Z取得542,872bytes，SHA256=`13ed3d7bf61fe39287098f79ed11776122d9fa56725c3195c2b8937eb43bc404`，100股×40日期、3900完成／100 pending。新快照與原10/27研究版、較早541298bytes快照分開保存，不用最新版本改寫舊實驗。

`live-data`本機catalog目前保存16來源、32次取得紀錄；derived lineage綁定實際catalog及來源hash／fetched_at。Git外原始版本與研究報告不因這次共享而刪除。此筆數是本次整合觀察，往後由catalog與Git revision為準，不把README當永久計數來源。

新入口：[全量驗收清單](COMPLETION_CHECKLIST.md)、[每日共享特徵](LIVE_DATA_FEATURES.md)、[hosted部署／Codex排程](HOSTED_AUTOMATION.md)、[Kaggle／Notebook](KAGGLE_TRAINING.md)、[課程報告骨架](REPORT_OUTLINE.md)。R1／E04實際分數與可重跑入口見[EXPERIMENTS](EXPERIMENTS.md)。新增的TCN／跨股模型只產研究包，不會繞過正式模型升級／相容性／deadline／回執檢查。

主代理已推送程式提交`b39d516`，遠端[CI run 41180208434](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41180208434)的Python3.10／3.12檢查success。新增hosted push runs [41180208527](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41180208527)及[41180208487](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41180208487)實際執行後被privacy gate阻擋；不是正式資料同步成功，也不是workflow語法錯誤。本機中途log為3.12的278項通過、3.10的274項／3 skips；其後增加public guard測試，最後一致套件數待凍結後重跑，不冒稱兩次中途收集數相同。

主代理以REST與GraphQL確認repo為Public（updated_at 2026-10-31T02:20:19Z）；先前`live-data@31650da`是在private檢查通過後發布，不能因舊授權就向Public繼續送資料。恢復Private的API PATCH回403，結果證據`visibility-restoration.json`保存在Git外，已請使用者在GitHub介面恢復。直到新一次private／origin驗證通過，不發布資料或完成遠端消費，亦不放寬guard。

## 既有核心與deep-research歷史交接（截至80ac804）

以下保留較早提交的實測與限制，說明當時狀態；其中「後兩架構未實作／runner不讀藍圖／E04未完成／raw不入Git」不代表本輪最新狀態。新資料分支授權、程式與結果以上方及驗收清單為準。原始記錄亦可查[80ac804版本](https://github.com/jiangjiangian/ml-final-2026-fall/blob/80ac804/ml_financial_prediction/docs/STATUS.md)，不以現在的程式hash回填舊run。

## deep-research分支新增交付

使用者要求新增金融競賽／方法學／模型架構與Lauren Tan工作流研究，已從`dev@675d662`建立獨立`deep-research` worktree；Git分支名稱不能含空白。未移動dev／main、未更改default branch或Secrets。下述既有模型實驗與188測試屬核心基底成果，**本研究階段沒有執行新fit、正式POST或常駐排程**。

新增[研究入口](deep-research/README.md)、七場Kaggle官方公開metric metadata比較、期刊／作者稿／AQR與Jane Street企業原文、四架構藍圖與可攜資料共享方案。63筆查核證據包含重複論文的不同來源，不是63篇論文；11筆去重書目記錄閱讀範圍／缺欄／出版日期差異。原始HTML／PDF只存Git外；Kaggle使用匿名公開只讀RPC，沒有登入或提交資料。

四架構為正則化線性、提升樹、causal TCN、市場引導跨股attention；後兩者未實作，新特徵版本未訓練。初步設定JSON明標design-only、現有runner不載入。R1至多8個feature-family設定、R2至多12個模型設定，各4季度，合計最多80 fits；精確特徵尚須執行前凍結，不將已看過的2026年1～5月重稱全新test。MASTER原文的五日橫斷面target與本課不等價，作者repo的validation/test處理問題另記錄。

資料共享建議先private Actions artifacts、需要長期版本時用私有object store／DVC與portable catalog；這是具體設計，未建立bucket、catalog分支或啟用workflow。原始資料不直接放repo，各branch固定catalog commit＋snapshot hash；來源取得與消費端接收時間分開。

Lauren Tan原始來源為Cursor官方pstack，固定commit閱讀；採「目標／驗收／限制」、可跑檢查、分工與短回報。前段文獻子代理遇用量限制由主代理接手，後段已恢復子代理獨立查核；不將失敗分工算完成，也未安裝／啟動pstack外部操作。

已執行：repo根目錄`python tools/validate_research_bundle.py --evidence-root /workspace/shared/research/deep-research-20261030`通過63個實際來源內容hash、來源ID／本地連結、11筆書目、四種架構及R1／R2總預算一致性；不含私有原檔的離線檢查亦在預設Python與3.10通過，新檢查器Ruff通過。本分支尚無新的遠端CI結果，沒有因文件／藍圖變更重訓或重跑核心全套。技能附帶引用驗證腳本無法讀取，實際以公開metadata與本專案離線檢查核對，沒有冒稱執行該腳本。這不是新模型效能或部署驗證。

獨立子代理完整審閱主題文件、研究規則、模型設定及既有實驗紀錄，直接核對七份官方RPC、MASTER README／PDF第1–5頁、pstack README與驗證原則；發現的預算界線與任職頁面差異均已修正。這不表示全部63份外部全文均經獨立複審；語意圖另以兩個互不重疊文件片段萃取，由主代理核對後整合。

## 使用者預期與目前差距

普通回報固定「結論／完成／下一步」、300中文字內、最多三個重點；完整證據放文件。優先成熟工具，獨立研究／實作／審查由subagent分工。

| 使用者目標 | 已完成 | 尚缺 |
|---|---|---|
| 每日更新教師＋額外經濟／市場資料 | 教師／Live、四個官方外部adapter、八個Yahoo日序列、三類TWSE產業水準；每日collect已串接 | 常駐執行器／持久儲存；部分來源的完整歷史及發布政策 |
| 正確計算return／差分及時間對齊 | 真實1655目標日研究市場表，M0＋SOX／TSM ADR／NVDA；查明教師既有位移 | 歷史發布／vintage認證、OI逐欄有效性；FRED／產業尚未形成完整特徵消融 |
| 自動產生模型輸入 | 每日快照自動轉七個個股lag；共享研究與推論公式、保留pending／缺值／age | 正式歷史訓練表來源證據；市場特徵尚未自動接入正式每日模型 |
| 每天訓練驗證並更新模型 | 四家族×三目標研究、候選公平比較、同配置新歷史刷新、失敗／超時回退 | 初始合格正式模型；研究假設模型不升級 |
| 50檔CSV自動提交與核實回執 | 官方session／模板唯讀驗證、提交契約、CSV／配額／截止／版本／回執／重複保護 | 真實POST接受與回執、常駐排程、五個真實交易日dry run |

## 真實資料與時間證據

2026-10-30T08:58:44Z重抓Training成功：18,278,354bytes，SHA256仍為`7433b27103107c630e293708a7ca4b7bfcec524e91ea6dc5be3e9b7d885b90e2`。Live於08:58:49Z取得541,298bytes，SHA256=`038d1a0fe29f4377fe9e2161962fde9bb3eda5afbb05d4ac7d9fc205af9517a3`；100股×40日期，2026-09-01～10-30，3900完整label、100個10/23 pending。新快照在`/workspace/shared/finpred-runtime/raw/`，原10/27研究資料與更早版本保留。帳密／cookie／公鑰不寫Git或log，不需重新提供既有key。

固定教師IXIC／GSPC／VIX各1505/1505可比列匹配「前一教師global列日期」的來源close，僅1418/1506匹配前一美國native session；長假可落後多session。固定TWII／KS11各1506/1506匹配同日close，不能作同日盤前輸入。Live兩美股指數37/37匹配前一來源session；VIX不能直接沿用同規則。這些是對凍結快照的實測，不是歷史發布時間證明。完整證據見[DATA_ALIGNMENT](research/DATA_ALIGNMENT.md)。

研究市場表`/workspace/shared/research/alignment/market_features.csv`有1655個目標日，先在完整原生序列計算再as-of對齊；使用第三方exchange_calendars4.13.2與close＋2小時的明示假設。OI兩欄全缺，沒有猜值。strict對未核實歷史vintage明確blocked；research必須顯式opt-in。來源清單、可用性與原始hash隨報告保存。

## 模型研究實際結果

E00以凍結Training＋10/27 Live建立82674個完成Top50股票日期鍵，50個pending另列；四類模型×三目標×四季度共48次fit，前處理只fit更早訓練資料。同一日期股票不跨fold。

| 相同linear／abs(return)加權配置 | 2025共同12140鍵score |
|---|---:|
| E00個股七欄 | 0.000482249960 |
| E01＋M0 | 0.000356441216 |
| E02＋M0＋SOX | 0.000249487724 |
| E03＋M0＋TSM ADR／NVDA | 0.000388784462 |

目前市場擴充未勝相同個股配置或全0基準0.000447093446；保留負結果，不升級。E00驗證選到MLP普通分類0.000854985259，一次2026年1～5月保留檢查為0.001275711605，**低於同鍵全0的0.001549845039**。這些均為research_assumption，不能當正式PIT績效或交易淨利。MLP80iter未收斂警告保留。

主代理另直接由已保存預測及label重新計分／核對共同鍵，與報告一致，沒有重新fit或再用holdout選參；證據`/workspace/shared/research/experiments/independent-score-audit.json`。E01起保存實際input buffer／canonical table、七份程式hash、環境、逐月／日分數與耗時。E00原追溯缺項如實保留，不回填假歷史；七份舊source object另經hash核對保存在source-snapshots。詳細結果與重跑方式見[EXPERIMENTS](EXPERIMENTS.md)、[RETURN_RATIO](research/RETURN_RATIO.md)。E04／E05未完成，不能填成正結果。

## 每日流程與工程驗證

`run_daily_pipeline.py`已有collect→train→predict→submit→verify五階段。未指定表路徑時，train／predict自動從runtime/raw中選cutoff前最新合法教師快照。今日預測的observed_fetch證據綁定真實manifest／payload／hash／fetched_at，available_at必須等於實際取得時間；只證明當次輸入已可取得，不回填歷史。七個個股lag與研究表共用實作；82674列重建後整份表及hash完全一致。額外市場序列已採集／研究，未因負結果自動加進正式模型。

歷史訓練仍只能自動產research表，strict回報blocked；顯式verified表入口保留給有證據的歷史adapter。研究模型不正式升級或提交。候選與incumbent configuration在同一較早train／相同validation鍵重新fit公平比較；換配置須嚴格改善。相同已核實配置有新完成歷史、schema／政策一致且同fold不退步時可刷新，避免永遠與自己同分而停止更新。快取綁定incumbent、資料、程式與套件版本；推論不fit、hash以同一buffer計算。GRU缺中間日期的正式推論context，目前daily明確阻擋。

正式時鐘／官方session／04:00～09:00窗口、07:20～07:50候選預算、08:10特徵freeze、50股全集／順序／二元值、配額、舊job保護、未知POST結果先對帳及有效回執比對均有檢查。2026-10-30新runtime的真實prediction preparation已實跑：新資料16:58台北才取得，正確拒絕作當天08:10輸入。這是負向驗證，不是完成一個交易日演練。

最終本機驗證：Python3.12的188項測試全部通過，含GRU三目標；Python3.10共188項，187項通過、1項選用GRU因未裝torch跳過。兩環境Ruff通過。3.10曾抓到mock名稱解析差異，已以明確module物件修正後重跑。shell語法、systemd units／timers與兩份workflow YAML解析通過；技能31個原始檔及Graphify SKILL hash核對相符。已將主要實作提交`11d7614af64b410e8fca94c0b64a1f028d47b2da`推送dev；[GitHub Actions run 41031916837](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41031916837)的Python3.10／3.12安裝、Ruff及測試均success。此CI不安裝選用torch；本機3.12另已驗證GRU。

## 教材、技能、分支與排程

公開基石16份495頁＋技法16份503頁，共32份998個實體PDF頁抽取文字已讀至EOF，關鍵公式／圖像另核對，不冒稱全部圖片逐頁審閱或已取得ChatGPT Project其他檔案。筆記、原文頁碼與hash見[FOUNDATIONS](research/FOUNDATIONS.md)、[TECHNIQUES](research/TECHNIQUES.md)。MarkItDown0.1.9、Graphify0.9.95與OpenAI官方gh-fix-ci／security-best-practices技能已安裝並固定來源／授權；沿用成熟sklearn／PyTorch／uv／Ruff，尚無需Ray／KubeRay／Kubeflow。Kaggle只比較，不登入或上傳課程資料。

核心工作在dev，本研究checkout在deep-research；main維持空樹及原歷史。GitHub唯讀核對repository為private、default仍main。systemd／Actions手動入口已準備但未啟用；workflow_dispatch和cron都要workflow先在default branch，不能把dev檔案存在說成已可排程。此對話沒有Tasks工具，不能在關閉後自行常駐。使用者希望不靠學校主機，正式雲端執行器／私有持久儲存方案待選；不因缺SSH停止本地工作。程式／圖存Git，raw／模型／逐列預測／憑證在checkout外。

## 下一個具體工作

1. 決定無學校主機的正式執行器與私有持久儲存，確認default branch入口、跨runner有效鎖與deadline備援後部署。不能用Actions cache冒充模型／ledger資料庫。
2. 補齊歷史特徵的可用性／修訂證據或建立從現在起的實際版本資料，驗證初始模型；預測表能形成不等於正式訓練證據已足夠。
3. 預註冊E04匯率／利率及E05產業／age／交互作用比較；2026年1～5月已看過，不再當全新保留集。完成五個真實官方交易日dry run與第一筆有效提交回執，才標記每日服務驗收完成。

從業務目錄重跑：`uv run --locked --no-sync python -m unittest discover -s tests -q`；3.10加`UV_PROJECT_ENVIRONMENT=/workspace/.tools/finpred-py310`。安裝及其他CLI見README；研究資料不隨checkout搬移。交接前保存本檔、決策、實驗、來源與Graphify，再壓縮context。
