# 台股盤中方向預測：ML系統與工作指南

更新：2026-10-30，Asia/Taipei。實際驗證紀錄見[STATUS](docs/STATUS.md)。

已實作資料下載與快照、時間對齊、研究訓練表、四類模型、候選比較、推論、提交／回執檢查及每日分階段CLI。**正式排程尚未啟用，也沒有實際提交競賽預測。** 研究模型採明示歷史可用性假設，不能直接當正式模型。

目前在dev工作，main依要求保留空檔案樹與歷史。專案依Chip Huyen《Designing Machine Learning Systems》與Cookiecutter Data Science分層，見[ARCHITECTURE](docs/ARCHITECTURE.md)。原始資料、模型與憑證不入Git。

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

Training與Live皆已下載。固定包提供歷史，Live提供後續日期、未完成值及修訂，兩者分開保存。最新Live於2026-10-30取得541,298bytes，涵蓋09-01～10-30共40日期、3900個完成標籤及100個10/23待完成標籤；固定包內容未變。最新raw在/workspace/shared/finpred-runtime/raw，較早研究快照保留不動；y=-1不能訓練，有號部位的-1另需有效性證據。

沿用COURSE_EMAIL／COURSE_PASSWORD環境憑證；Live公開金鑰可由已核實前端在記憶體取得，不把值填入命令或Git：

~~~bash
uv run --locked --no-sync python scripts/download_course_data.py --source both --out-dir /workspace/shared/downloads/course/snapshots
uv run --locked --no-sync python scripts/download_external_data.py --source cboe_vix --source twse_twii --source fred_us10y --source fred_usd_twd --out-dir /workspace/shared/downloads/external
~~~

正常TLS、ZIP／股票全集／欄位及標籤檢查通過才保存不可變快照。課程與助教Live新網域已實測，不需重新提供既有帳密或key。差異、快照及既有API見[DATASET_INVENTORY](docs/DATASET_INVENTORY.md)與[API_INVENTORY](docs/API_INVENTORY.md)。

另已取得IXIC、GSPC、TWII、KS11、VIX、SOX、TSM ADR、NVDA原生日序列，以及台灣三類產業當日水準。SOX是指數，TSM／NVDA是海外個股；產業序列尚無完整歷史，FRED匯率／利率目前是raw，不冒稱都已成模型特徵。

重要發現：固定教師美股欄位匹配前一個教師global列日期，未必是前一美國交易日；固定TWII／KS11含同日收盤。不可盲目shift(2)或將其直接當盤前資料。研究市場表先在完整原生序列算報酬，再按08:10 cutoff對齊，保留缺值與版本。1655個目標日及SOX／TSM／NVDA特徵已產出，OI兩欄因證據不足留缺值。

~~~bash
uv run --locked --no-sync python scripts/build_course_market_features.py --history-root /workspace/shared/downloads/market-history --targets /workspace/shared/research/alignment/targets.csv --mode research --allow-research --out /workspace/shared/research/alignment/market_features.csv --report /workspace/shared/research/alignment/market_report.json
~~~

這是research_assumption：最新歷史vintage與close＋2小時假設，不是量測到的歷史發布時間。strict模式拒絕缺乏證據的輸入。詳細匹配、假日例子與限制見[DATA_ALIGNMENT](docs/research/DATA_ALIGNMENT.md)。M0純Python核心仍有合成示範；八欄公式、missing／age／fresh與輸入契約見[MARKET_FEATURES](docs/MARKET_FEATURES.md)。不能在多國inner join後把相鄰列冒稱一個原生交易日。

## 模型研究與推論

研究訓練表將上一筆個股觀測與當日label隔離，以目標日期left join市場資料，不靜默刪除目標。現有Top50表82674個完成樣本，50個pending樣本另列。原始發布／歷史調整價尚不足以核實point-in-time，builder只輸出研究狀態。

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

本次真實新快照在台北16:58取得，晚於當日08:10，上述檢查正確回報blocked；這是負向驗證，不是五日演練。額外市場來源已採集與消融，但未自動納入正式daily表；E01～E03未顯示增益，見EXPERIMENTS。五階段CLI及橋接已實作，不代表每日服務已部署；研究模型不能升級或提交。

候選訓練07:20～07:50，08:10凍結特徵，08:20提交、08:35核對，09:00停止。失敗／超時保留相容且已驗證模型，無此版本則blocked。提交JSON介面已由前端核實、session／模板已唯讀實測；尚無真實POST或成功回執。詳見[OPERATIONS](docs/OPERATIONS.md)及[AUTOMATION](docs/research/AUTOMATION.md)。

目前沒有可將本對話設定為每天自動執行的Tasks工具；聊天結束後不能承諾本代理自行常駐。systemd服務／timers及Actions手動設定已準備，皆未啟用。workflow_dispatch與schedule都要求workflow存在default branch；main空樹時，只放dev不會自動取得入口。GitHub-hosted runner另需持久私有快照／模型／提交ledger、跨runner鎖及截止延遲備援；不以cache當資料庫，不擅自改main或default branch。

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
