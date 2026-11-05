# 當前狀態與交接

更新：2026-10-30，Asia/Taipei。本輪已執行研究、模型實驗與系統實作，尚未啟用正式排程或提交競賽預測。各模組「已實作」不等於每日服務「已部署」。

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
