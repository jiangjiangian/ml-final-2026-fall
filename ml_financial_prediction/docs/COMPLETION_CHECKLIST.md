# 全量工作驗收清單

更新：2026-11-03，Asia/Taipei。Public、default=`system-completion`及Actions課程Secrets均已落實，41584330745及後續41593199735手動採集16來源全部成功、研究特徵已匯出；05eb17e的CI與影子／正式入口還原演練成功，無預測POST。下一個名義資料cron為台北11/04 04:17，首個event=`schedule`待驗收；不把完整手動採集等同正式模型或每日提交服務完成。

## 本輪任務契約

- **目標：** 依使用者最新「暫時全部公開」選擇，`live-data`供版本化真實資料；每天早上更新、產特徵、訓練驗證、50股預測與提交核對；完成四模型研究與可重跑Notebook。
- **驗收：** 乾淨checkout讀指定revision並驗hash；README有實際file tree與return／lag／單位／可用時點；模型按相同日期股票鍵與官方score比較；排程、回執及連續交易日以真實紀錄證明。
- **限制：** main保留空樹與歷史，正式metric／截止／時間證據／試驗上限不放寬。raw／derived只進明確公開opt-in的`live-data`，程式分支不混raw，所有branch及log不放帳密／cookie／token；不把使用者公開決定冒充來源再散布授權。

## 必要交付與驗收

| ID | 交付／完成條件 | 查核時狀態 | 證據或待補事項 |
|---|---|---|---|
| G01 | 公開`live-data`保存真實Training／Live與額外來源，不混入憑證 | 已完整雲端採集／發布 | 最新41593199735為collected、16來源無失敗、研究特徵exported，資料revision為c3f36239c699a1ab2ecafb17eb68eaff13c8fb9f；Public與明確opt-in已核對，較早private-only停止發布為歷史 |
| G02 | 資料branch README展示實際file tree，逐欄說明公式、return窗口、lag索引、單位及已知限制 | 已寫入資料分支 | `lag1`不等於「公式用了兩個價」；observed-row return不冒稱native-session return |
| G03 | 可攜快照、不可變原始物件、修訂／未完成標籤、來源取得時間與跨branch固定版本 | 程式與反例已驗證 | `data/sharing.py`在3.10／3.12有sharing反例測試通過；含原時間／hash、修訂、symlink／路徑穿越、credential、同內容去重、UTC Z相容。避免每次acquisition保留同18MB buffer的長期記憶體問題已修正；跨遠端取用另見G04 |
| G04 | 第二個乾淨checkout下載指定revision，驗hash並重建自己的runtime | 已完成 | 較早固定公開8c8f18495c01b80d02dd9b90093a8afe322c79ef乾淨消費16來源、134 manifests與7 derived，原時間與hash均通過；舊私人31650da亦曾成功 |
| G05 | 實際每日04:00～09:00集中採集，來源失敗不覆寫歷史，模型失敗不阻止保存raw | 全部來源手動成功；定時待驗收 | 41584330745全16來源成功，rehearsal41584847865成功；Public／default／Secrets已落實，下一個名義cron台北11/04 04:17，尚無首個schedule成功證據 |
| G06 | 查明Codex排程能力，提供可用部署途徑 | 能力已核對，採GitHub-hosted執行 | 本對話無Automation／Tasks工具，日常執行靠Actions與live-data持久狀態；不承諾聊天代理常駐，官方來源見HOSTED_AUTOMATION |
| G07 | F0個股lag與原M0／SOX／ADR真實研究表，前處理／時間切分／labels隔離 | 已有核心成果 | [STATUS](STATUS.md)、[DATA_ALIGNMENT](research/DATA_ALIGNMENT.md)；研究狀態，非歷史PIT認證 |
| G08 | F1原生1／5／20-session return、F2波動／age／missing的凍結欄位與消融 | 研究實作與比較已完成 | 凍結82674鍵、F0/F1/F2各7/28/40欄；兩個固定模型×四季共24實際fits。源日曆、晚修訂、缺期、零分母與當日未來收盤反例通過。結果與8個blocked F3 slots見下方R1紀錄，不冒稱PIT認證 |
| G09 | E04匯率／殖利率特徵及受控比較；E05產業／交互作用可用性與消融 | E04研究比較完成；完整產業F3仍blocked | E04先另外註冊9個FX／yield／age／missing欄、兩固定模型×四季共8 fits，兩模型均未勝相同F0／全0。七日quarantine是研究假設；F3三產業native return缺完整歷史，不能以E04替補。E05之age部分已納F2；產業與另列交互作用比較尚未完成 |
| G10 | M1線性／M2提升樹／M3 causal TCN／M4市場引導跨股attention實作與因果測試 | 已實作並通過局部測試／遠端CI | 原始碼與因果／batch-day等價測試已交付；完整R2分數另見G11。舊四族linear／GBDT／MLP／GRU結果不能冒充新TCN／M4結果 |
| G11 | 新四架構在真實相同資料／fold的有限比較，報所有結果、baseline及winner選擇理由 | 已完成研究比較 | R1實際24 fits、8 blocked slots，E04另8 fits；R2完成48 fits，逐鍵重算和模型重播通過。TCN 0.000868847322、全0 0.000447093446，為已看過的2025探索fold與研究假設，不是新樣本外 |
| G12 | 完整50股時序feature panel、缺期mask與獨立label mask；批次／逐日推論等價 | 研究panel／因果測試已實作，正式日曆未認證 | 來源保留完整feature格與獨立label mask，不能把E00完整label平表冒充全量input。R2的1655個目標日是教師觀測日聯集；與第三方XTAI相比有4個calendar-only日期，可能為特殊休市，未經官方逐日核實，不自動填入或宣稱20個已認證台股session |
| G13 | Notebook從頭執行，包含多模型／官方score比較與實際結論 | 本機真實報告模式已完成 | 6個code cells完整執行並讀取48-fit報告；只展示彙總、不另fit。尚未在Kaggle遠端執行 |
| G14 | Kaggle私人遠端訓練與結果取回 | 外部條件未齊 | 沒有Kaggle MCP或Kaggle帳戶憑證；可完成官方CLI私人bundle與本地驗證，不能宣稱已遠端運算。憑證不得貼聊天或寫Git |
| G15 | 由證據充分的歷史／當日資料訓練初始合格模型，通過升級／相容回退 | blocked：證據與合格模型未齊 | 今日08:10前取得只證明今日bytes可用，不能替舊歷史補vintage。研究模型不得改標verified或approved |
| G16 | hosted持久資料／模型／pre-POST ledger、有效鎖、截止停止與失敗恢復 | 程式及遠端restore完成；提交待驗收 | lease／CAS／checkpoint／deadline已有測試，41584847865 rehearsal成功；新隔離shadow與固定stage已隨05eb17e推送；shadow41593711368與正式41593199708 attempt2還原成功、無預測POST，原attempt1取消不算成功 |
| G17 | 真實50股CSV在開放session準時提交，核對目前有效CSV回執 | 待真實時段與G15／G16 | 已有提交契約與mock測試；本輪尚無新的server接受與有效回執證據，HTTP200不足 |
| G18 | 五個真實官方交易日dry run，逐日可查版本／準時性／失敗回復 | 未完成，依真實session累積 | 11/03實讀state有10/12～11/03共15 sessions、尚無11/04；不造未來日期或回放冒充。shadow已推送且還原演練成功，但真實盤前前瞻日未完成，研究隔離證據不等於正式approved演練 |
| G19 | 根據實際完成項更新記憶、決策、實驗、Graphify與交接 | 本輪文件已更新，最終圖／交接待主代理 | 目前設定／完整採集與歷史403已分開，舊實驗與來源證據保留；新code／測試／remote facts凍結後刷新語意圖，不能只改hash |

所有必要交付皆完成或明確受外部條件阻擋前，不將整體標為「全部完成」。短期無增益或來源blocked也是研究結論，不能為完成任務修改驗收門檻。

## 已有成果、後續期限與可選工具

| 範圍 | 分類 | 處理方式 |
|---|---|---|
| Graphify、Microsoft MarkItDown、固定官方技能、Ruff與CI、32份公開講義研究、七競賽／期刊／企業方法、Lauren Tan原文研究 | 既有已交付 | [TOOLS](research/TOOLS.md)、[研究入口](deep-research/README.md)；沿用，不為本輪重複安裝或宣稱全部外部全文已讀 |
| 課程Phase1 50股×84日期CSV、至少四方法／最多七頁A4報告 | 正式後續交付 | Phase1截至2026-12-24 23:59 UTC+8，報告2026-12-30 13:00；以[README](../README.md)及正式final規範為準。不把已見label當作當時預測，也不提前冒稱整學期報告已完成 |
| 原始碼／版本／執行證據保存至2027-01-31 | 持續義務 | 持久Git／授權儲存及保存政策須覆蓋此期限；artifact預設TTL不是永久封存 |
| TWSE／TAIFEX／FinMind／MIS／GDELT等既有API紀錄 | 來源候選與待接入清單 | [API_INVENTORY](API_INVENTORY.md)；「用過／提過API」不代表每個資料集都有權限、歷史或必須加入正式模型。OI有效性與新聞時點仍需獨立驗收 |
| DVC、MLflow、Ray／KubeRay／Kubeflow、Linear／Codex Security | 按實際需求選用 | DVC可協助大資料版本、MLflow可協助更多實驗；當前小型CPU批次不需K8s／Ray。使用者要成熟好工具，不是安裝所有曾提名稱 |
| Kaggle MCP | 介面偏好，非效能／部署保證 | 本會話不可用；以官方CLI／API作可審查備援。免費GPU額度、資格、排隊與時限都不能當09:00前必定完成保證 |

## 獨立審查紀錄

已完整讀取AGENTS、README、ARCHITECTURE、PROJECT_CONTEXT、STATUS、DECISIONS、IMPLEMENTATION_PLAN、RESEARCH_PLAN、EXPERIMENTS、OPERATIONS、FEATURE_SPEC、DATA_CONTRACT、API_INVENTORY及deep-research相關契約／設定。後續獨立查核sharing／hosted原始碼及跨3.10測試，抓到共享payload重複記憶體、UTC Z解析差異及兩個3.10 Mock名稱錯誤，交由所屬代理修正；只有實際通過的檢查才更新狀態。遠端workflow及整體最後驗證由主代理紀錄。

## 本輪R1／E04實際研究紀錄

原始結果在Git外`/workspace/shared/research/completion-20261030/R1-E04-comparison-v1/`；`registration.json`在新分數出現前固定設定與來源hash，`report.json`保存所有32 fits及負結果，`independent_score_audit.json`由保存的32份預測及原始open／close直接重算，12140共同validation鍵、最大分數差為0，沒有重新fit。

| 2025已看過的時間驗證分組 | Ridge alpha=1 | HistGBDT 15葉／100iter |
|---|---:|---:|
| F0個股7欄 | 0.000526636554 | 0.000531184462 |
| F0＋F1原生return | 0.000442502529 | 0.000713281846 |
| F0＋F2波動／age／missing | 0.000816754184 | 0.000084810345 |
| E04：F0＋FX／yield子集 | 0.000310985284 | -0.000012346337 |
| 同鍵全0／train-majority | 0.000447093446 | 0.000447093446 |

R1的F2 Ridge在這段validation較高；這是同一段已看過2025資料上的研究結果，不能稱新unseen test或正式模型升級證據。E04沒有增益；完整F3產業未齊的8個原R1 slots維持blocked，沒有改成別組冒充完成。原始執行腳本另保留，portable source CLI為`scripts/run_feature_ablation.py --expansion-dir ... --out-dir ... [--include-e04]`；適配CLI只另作synthetic行為測試，沒有重做實際研究fit。
