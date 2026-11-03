# 台股盤中方向預測：ML系統與工作指南

更新：2026-11-03，Asia/Taipei。程式與`live-data`依使用者決定公開，預設分支已為`system-completion`。Actions課程帳密由41584330745完整採集驗證生效；[後續採集41593199735](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41593199735)亦取得全部16類來源並匯出研究特徵，沒有來源失敗，資料revision為`c3f36239c699a1ab2ecafb17eb68eaff13c8fb9f`。公開讀取須明確加`--allow-public-data`，組員不需要網站帳密。

資料cron的入口條件已滿足，下一個名義時點為台北2026-11-04 04:17；**第一個真實schedule事件、正式模型與競賽提交仍待驗收**。研究模型採明示歷史可用性假設，不能直接當正式模型。最新證據見[STATUS](docs/STATUS.md)。

核心實作源自dev，目前整合與預設分支為`system-completion`；`deep-research`保留來源研究，`live-data`保存公開快照與衍生資料，main依要求保留空檔案樹與歷史。專案依Chip Huyen《Designing Machine Learning Systems》與Cookiecutter Data Science分層，見[ARCHITECTURE](docs/ARCHITECTURE.md)。程式分支不混入raw，所有分支及log均不放憑證。

早期來源研究（80ac804階段）入口：[金融競賽、四種架構、跨branch共用資料與Lauren Tan工作流](docs/deep-research/README.md)。該階段整理63筆來源證據與11筆書目，當時四架構只是設計；後續實作／實跑狀態以下節及STATUS為準。由repo根目錄執行`python tools/validate_research_bundle.py`可離線檢查研究交付；私有證據目錄存在時再加`--evidence-root /workspace/shared/research/deep-research-20261030`核對原始內容hash。

## 每日共享、四模型與Notebook的新入口

GitHub各branch共用repository可見性；本專案目前採全部公開。可攜catalog、來源hash及原始取得時間已驗證，匿名讀取最新catalog亦通過hash核對。私人資料repo仍是可選替代，無須為目前部署另建repo。正式模型／提交的剩餘條件見[Phase 2流程](docs/PHASE2_GUIDE.md)。

| 要做什麼 | 實際入口與狀態 |
|---|---|
| 組員取得同一資料版本 | 公開`live-data`的README含file tree、每欄公式／lag／單位；以固定40碼commit取用，來源取得時間與接收時間分開 |
| 每天更新raw與研究特徵 | `data/sharing.py`＋`data/shared_features.py`；最新50股×1660觀測日＝83000格，labels獨立；[欄位與驗證](docs/LIVE_DATA_FEATURES.md) |
| 比較新四架構 | Ridge／HistGBDT／causal TCN／市場引導跨股attention已完成48-fit R2研究及獨立重播，未升級正式模型 |
| 擴充特徵消融 | `scripts/build_research_expansion.py`及`run_feature_ablation.py`；R1／E04共32個真實fits與負結果，完整產業F3仍blocked |
| 多模型Notebook／Kaggle | [KAGGLE_TRAINING](docs/KAGGLE_TRAINING.md)；Notebook與官方私人bundle已本地驗證，缺本人Kaggle帳戶憑證，未遠端訓練 |
| 不靠學校主機的排程 | [HOSTED_AUTOMATION](docs/HOSTED_AUTOMATION.md)；hosted流程／持久鎖與pre-POST ledger已有程式，遠端run及cron以STATUS實際證據為準 |

隔離research shadow與固定cron-stage修正已隨`05eb17e`推送並通過CI；shadow還原演練41593711368、正式入口還原演練41593199708 attempt2成功，沒有預測POST。shadow固定研究recipe、不寫approved、不提交；實際盤前前瞻日、正式模型與五日服務仍待驗收，詳見STATUS。

從業務目錄取用遠端資料；第一次可用`live-data`解析成明確commit，實驗後續固定該40碼版本：

~~~bash
uv run --locked --no-sync python scripts/fetch_live_data.py \
  --repo jiangjiangian/ml-final-2026-fall --revision live-data \
  --runtime-dir /private/finpred-runtime --with-features --allow-public-data
~~~

完整raw核對後還原至本機runtime；已驗證的衍生features／labels放`shared-data/`。缺失或stale衍生資料會另報blocked，不將原始取得時間回填成接收時間。共享研究表不會自動變成正式verified訓練表。所有工作對照[COMPLETION_CHECKLIST](docs/COMPLETION_CHECKLIST.md)，歷史規範與下面較早基準繼續保留。

## 目標與正式規範

每天台北04:00～09:00取得教師及額外市場資料，產生特徵、訓練驗證候選模型，輸出50檔0/1預測，09:00前自動上傳並確認目前有效回執。04點是工作窗口起點，不是資料供應商更新保證。

~~~text
y = 1{adj_close > adj_open}
score = mean((2 * prediction - 1) * (adj_close - adj_open) / adj_open)
~~~

| 項目 | 正式規範 |
|---|---|
| Phase 1 | 2026-06-01～09-30，50檔×84日期，共4200預測 |
| Phase 1截止 | 2026-12-24 23:59 UTC+8，保留最高分版本 |
| Phase 2 | 官方每個session50檔，09:00 UTC+8截止，採最後有效提交 |
| 計分競賽階段 | 2026-11-16～12-24，以官方指定session為準 |
| 報告 | 至少四種可重現ML approaches，最多七頁A4；2026-12-30 13:00 UTC+8截止 |
| 原始碼保存 | 至2027-01-31 23:59 UTC+8 |

以上依2026-10-24 final規範，優先於較早簡報。報告占1440/1920，實驗紀錄與每日操作都要保留。團隊既有分工：蘇負責爬蟲／文字、顏負責時序／Transformer、戴負責rank／meta、楊協助外部序列；實際責任仍由團隊協調。

## 安裝與檢查

從repository根目錄執行；預設安裝requests、scikit-learn、exchange_calendars及Ruff，依uv.lock固定版本：

~~~bash
bash tools/setup_project.sh
~~~

四模型研究需要PyTorch CPU，從根目錄改用以下安裝。不要在實驗運行中重新同步共用環境：

~~~bash
FINPRED_WITH_NEURAL=1 bash tools/setup_project.sh
~~~

以下命令從業務目錄ml_financial_prediction執行：

~~~bash
uv run --locked --no-sync ruff check src scripts tests
uv run --locked --no-sync python -m unittest discover -s tests -q
~~~

最後整合結果以STATUS為準。根目錄CI有Python3.10／3.12設定；不能以設定存在宣稱遠端CI已通過。MLflow、Ray、KubeRay、Kubeflow未加入，現階段無須它們。

## 資料取得與時間對齊

Training與Live皆已由GitHub runner重新下載。固定包提供截至2026-08-31的歷史，Live提供後續日期、未完成值及修訂，兩者分開保存。2026-11-03T05:31:16Z取得的Live涵蓋09-01～11-03共42日期、100股共4000個完成／200個pending標籤，Training內容未變。此時為台北13:31，不能回填當日08:10輸入證據。共享Top50表保留83000個feature格、100個pending及26個缺觀測label；較早研究快照保留不動。`y=-1`不能訓練，有號部位的`-1`另需有效性證據。

沿用COURSE_EMAIL／COURSE_PASSWORD環境憑證；Live公開金鑰可由已核實前端在記憶體取得，不把值填入命令或Git：

~~~bash
uv run --locked --no-sync python scripts/download_course_data.py --source both --out-dir /workspace/shared/downloads/course/snapshots
uv run --locked --no-sync python scripts/download_external_data.py --source cboe_vix --source twse_twii --source fred_us10y --source fred_usd_twd --out-dir /workspace/shared/downloads/external
~~~

正常TLS、ZIP／股票全集／欄位及標籤檢查通過才保存不可變快照。課程與助教Live新網域已實測，不需重新提供既有帳密或key。差異、快照及既有API見[DATASET_INVENTORY](docs/DATASET_INVENTORY.md)與[API_INVENTORY](docs/API_INVENTORY.md)。

另已取得IXIC、GSPC、TWII、KS11、VIX、SOX、TSM ADR、NVDA原生日序列，以及台灣三類產業當日水準。SOX是指數，TSM／NVDA是海外個股；產業序列尚無完整歷史，FRED匯率／利率已形成另註冊的E04研究子集並完成8 fits，未勝F0／全0；產業完整歷史仍不足。正式每日特徵不因研究完成而自動升級。

重要發現：固定教師美股欄位匹配前一個教師global列日期，未必是前一美國交易日；固定TWII／KS11含同日收盤。不可盲目shift(2)或將其直接當盤前資料。研究市場表先在完整原生序列算報酬，再按08:10 cutoff對齊，保留缺值與版本。1655個目標日及SOX／TSM／NVDA特徵已產出，OI兩欄因證據不足留缺值。

~~~bash
uv run --locked --no-sync python scripts/build_course_market_features.py --history-root /workspace/shared/downloads/market-history --targets /workspace/shared/research/alignment/targets.csv --mode research --allow-research --out /workspace/shared/research/alignment/market_features.csv --report /workspace/shared/research/alignment/market_report.json
~~~

這是research_assumption：最新歷史vintage與close＋2小時假設，不是量測到的歷史發布時間。strict模式拒絕缺乏證據的輸入。詳細匹配、假日例子與限制見[DATA_ALIGNMENT](docs/research/DATA_ALIGNMENT.md)。M0純Python核心仍有合成示範；八欄公式、missing／age／fresh與輸入契約見[MARKET_FEATURES](docs/MARKET_FEATURES.md)。不能在多國inner join後把相鄰列冒稱一個原生交易日。

## 模型研究與推論

研究訓練表將上一筆個股觀測與當日label隔離，以目標日期left join市場資料，不靜默刪除目標。已凍結E00／R1／R2使用82674個完成Top50樣本；新共享資料不回寫舊實驗。原始發布／歷史調整價尚不足以核實point-in-time，builder只輸出研究狀態。

四類模型為正則化線性、梯度提升樹、MLP與小型GRU；各比較普通分類、abs(return)加權分類及報酬回歸取正負。E00已完成2025四季48次fit；固定winner後只作一次2026年1～5月保留檢查。市場消融比較相同validation，不反覆挑保留期。含負結果的數值見[RETURN_RATIO](docs/research/RETURN_RATIO.md)及[EXPERIMENTS](docs/EXPERIMENTS.md)。

以下是新實驗範例，輸出目錄必須不存在或為空，既有結果不可覆寫：

~~~bash
uv run --locked --no-sync python scripts/run_experiments.py --table /workspace/shared/research/experiments/course-stock-m0-table.json --out-dir /workspace/shared/research/experiments/new-validation-run --families linear --objectives weighted_classification --research-if-unverified
~~~

模型包保存前處理、欄位／版本、資料與程式hash、時間及套件版本。推論不fit；只載入本專案產生、可信且私有的模型包。joblib可執行程式，不能載入任意下載模型。

生產approved載入須通過執行套件版本相容檢查；GRU還需已核實的中間序列歷史，目前缺這項交付時會blocked，不能因研究fit成功就直接每天上線。

## 每日工作流與排程

CLI已有collect、train、predict、submit、verify五階段，檢查真實時鐘與官方session。預設dry run只禁止POST，仍可能下載、訓練及寫入私有runtime：

~~~bash
uv run --locked --no-sync python scripts/run_daily_pipeline.py --runtime-dir /workspace/shared/finpred-runtime --stage collect --dry-run
~~~

此命令僅在目標日台北04:00～09:00及官方開放session可執行。train／predict未提供表路徑時，pipeline會從私有raw快照自動準備：目前僅七個個股滯後特徵。08:10前實際取得的bytes可證明**今日**特徵已可用；這不能證明歷史調整價當時已發布，因此strict訓練仍blocked，研究opt-in才自動產研究訓練表。顯式verified表仍支援，但推論還需相容approved模型。

也可獨立檢查daily table準備；此CLI會依原始取得時間檢查，不會因改target-date把晚到資料塞回過去：

~~~bash
uv run --locked --no-sync python scripts/build_daily_tables.py --runtime-dir /workspace/shared/finpred-runtime --target-date 2026-10-30 --kind prediction
~~~

2026-10-30曾以台北16:58取得的真實快照驗證此入口，正確回報blocked；這是歷史負向檢查，不是五日演練。11/03新資料同樣晚於當日freeze。額外市場來源已採集與消融，但未自動納入正式daily表；E01～E03未顯示增益，見EXPERIMENTS。五階段CLI及橋接已實作，正式模型尚未合格；研究模型不能升級或提交。

候選訓練07:20～07:50，08:10凍結特徵，08:20提交、08:35核對，09:00停止。失敗／超時保留相容且已驗證模型，無此版本則blocked。提交JSON介面已由前端核實、session／模板已唯讀實測；尚無真實POST或成功回執。詳見[OPERATIONS](docs/OPERATIONS.md)及[AUTOMATION](docs/research/AUTOMATION.md)。

本對話沒有Tasks工具，日常執行器採GitHub-hosted Actions，不依賴聊天或學校主機。`system-completion`已是含workflow的default branch，課程Secrets已實際驗證；不需再次設定。持久Git狀態、跨runner lease及POST前checkpoint已實作，資料cron仍須首個真實schedule run證明觸發；完整每日服務還需正式模型與回執驗收。詳見HOSTED_AUTOMATION及STATUS。

## 教材、技能與專案記憶

已安裝Microsoft MarkItDown0.1.9 PDF工具、K-Dense markitdown技能、Graphify與OpenAI官方gh-fix-ci／security-best-practices技能，保留版本與授權。見[TOOLS](docs/research/TOOLS.md)。Kaggle只作比較，未登入或上傳課程資料。

林軒田公開基石16份495頁、技法16份503頁，共32份998個實體PDF頁抽取文字已讀至EOF，另抽查關鍵公式／圖像。這不是全部頁面視覺審閱，也不取代本學期規範。原PDF／轉換物在checkout外；頁碼／閱讀證據見[FOUNDATIONS](docs/research/FOUNDATIONS.md)及[TECHNIQUES](docs/research/TECHNIQUES.md)。

從repository根目錄重建PDF工具，再轉換本地檔案：

~~~bash
bash tools/setup_markitdown.sh
/workspace/.tools/markitdown/bin/markitdown /absolute/path/lecture.pdf -o /absolute/path/lecture.md
~~~

PDF工具、Graphify與ML環境分開。技能的0.1.8範例與已驗證0.1.9差異保留在安裝紀錄；原PDF仍為公式／圖表權威。工具不會讓Codex自動讀取ChatGPT Project其他聊天或檔案。

| 文件 | 用途 |
|---|---|
| [AGENTS](AGENTS.md) | 繁中短版回報、開發／驗證與儲存規則 |
| [ARCHITECTURE](docs/ARCHITECTURE.md)、[PROJECT_CONTEXT](docs/PROJECT_CONTEXT.md) | 系統分層與穩定背景 |
| [DATA_CONTRACT](docs/DATA_CONTRACT.md)、[FEATURE_SPEC](docs/FEATURE_SPEC.md) | 資料、可用時間、特徵與交接 |
| [STATUS](docs/STATUS.md)、[DECISIONS](docs/DECISIONS.md) | 最新證據、阻礙、已確認決策 |
| [RESEARCH_PLAN](docs/RESEARCH_PLAN.md)、[EXPERIMENTS](docs/EXPERIMENTS.md) | 研究／實作範圍與實驗登錄 |
| [PROJECT_GRAPH](docs/PROJECT_GRAPH.md) | 上層graphify-out圖與重建方法 |

AGENTS.md要求讀取的文件構成專案記憶，不假設聊天自動共享上下文。普通回報固定「結論／完成／下一步」、300中文字內、最多三個重點，完整證據留文件。
