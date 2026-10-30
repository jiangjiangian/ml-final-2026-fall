# ML 系統建置與專案目錄

更新：2026-10-30，Asia/Taipei。這是專案的目錄與模組責任依據；實際完成狀態及可執行命令以 STATUS、README 為準。

這份文件把市場特徵工作放回完整系統。已有教師／外部來源adapter、不可變快照、標準化／時間對齊、研究訓練表、四類模型、候選比較、推論、提交／回執、每日五階段CLI及raw→daily表橋接。每日stage在未供表時會自動準備七個個股滯後特徵；今日取得證據不證明歷史可用性，因此strict訓練仍blocked，正式模型與持久排程未部署。不需先上微服務、Kubernetes或即時串流。

## 設計依據與使用者目標

採用兩個相容的參考：Chip Huyen《Designing Machine Learning Systems》（O'Reilly, 2022）的系統生命週期觀點，以及 DrivenData Cookiecutter Data Science v2 的目錄慣例。前者涵蓋資料工程、特徵、部署、監控與持續學習；後者將原始／中間／最終資料、可重用程式、notebook、模型與報告分開。**書沒有規定本專案必須使用下面這棵 tree**；這是依問題、時間限制與既有程式調整後的設計。使用者記得的書名尚未確認，不將上述書名冒充其原先指定的書。

- 書籍與作者：[O'Reilly 書頁及目錄](https://www.oreilly.com/library/view/designing-machine-learning/9781098107956/)、[作者書目](https://huyenchip.com/books/)。公開資料可核實書名、作者與主題，未假稱閱讀付費全文。
- 業界目錄範本：[Cookiecutter Data Science v2](https://cookiecutter-data-science.drivendata.org/)。沿用資料分層與模組化原則，不在已有專案上重新執行產生器覆蓋檔案。

使用者已重申三個交付目標：增加經濟／市場序列；每天台北時間04:00～09:00自動更新教師及外部資料，並產生經驗證的候選模型；把適合的價格序列報酬計算成特徵。04:00是要求的工作窗口起點，不是已證明所有來源更新完成的時間。自動更新、自動訓練、自動替換正式模型及自動對外提交是四個不同步驟；使用者本輪已明確要求自動提交，完成端點／格式／截止／回執驗證後沿用本授權執行；目前尚未部署。

## 1. 核心設計

用一個私人Git repository管理程式、設定與實驗紀錄；受限原始資料及模型存受控的持久儲存空間。先用模組化Python批次系統，每日執行一次主流程，取得來源有延遲時再重試。運算量真的需要時，訓練可獨立放GPU主機，日常推論維持CPU小任務。

資料流分成兩個使用同一套特徵引擎的流程：

| 流程 | 輸入 | 主要操作 | 產物 |
|---|---|---|---|
| 研究／每日候選訓練 | 截止前已可用的快照、已完成且已可用的歷史標籤、目標日曆 | 時間對齊、按日期切分、fit、評估；與目前模型同條件比較 | 候選模型、OOF預測、實驗結果；通過條件後才升級 |
| 每日預測 | 截止前最新快照、當期模板、已驗證模型 | 同套時間對齊與特徵、predict、檢查格式 | 50檔CSV、執行manifest、提交與回執；程式已實作，正式運作未部署 |

每日推論不重新fit scaler、imputer或特徵選擇器。每日重訓是獨立的候選模型job，不等於模型每收到一列就必須線上更新；先使用成熟套件的可重現批次fit。訓練只含該次截止前已完成、已可用的標籤，不能用當日尚未收盤的y，也不能以未完成的Live `-1`列訓練。候選模型須在預先設定的時間預算內完成資料與驗證檢查，通過升級條件後才改正式版本；未完成、失敗或未通過時沿用先前已驗證且相容的模型，並記錄原因。沒有可用正式模型時明確回報blocked，不能假稱已完成當日預測。

## 2. 目錄分類

以下是**完整設計目錄**。已有ingestion、data、features、labels、models、training、evaluation、inference、submission、pipelines、CLI與測試；monitoring獨立模組仍待按需建立。目前健康／失敗資訊由各stage manifest記錄，不把完整設計誤當服務已部署。

```text
ml-final-2026-fall/                  # 核心dev；獨立研究在deep-research
├── .github/workflows/              # repository根目錄的CI；部署排程另管理
├── .agents/skills/graphify/         # 已安裝的架構圖技能
├── graphify-out/                   # 已有：可分享的架構圖與來源追溯
├── tools/                         # 已有：Graphify安裝／建圖工具
└── ml_financial_prediction/        # Python業務專案根目錄
    ├── pyproject.toml / uv.lock    # 套件、開發工具與鎖定版本
    ├── AGENTS.md / README.md       # 工作規則／實際上手命令
    ├── configs/                   # 來源、欄位、時間窗口、模型與切分設定
    ├── src/finpred/
    │   ├── ingestion/             # 教師／外部來源adapter與原始下載
    │   ├── data/                  # 快照、schema、時間與版本標準化
    │   ├── features/              # 已有M0；後續個股、外部指數等特徵
    │   ├── labels/                # y與真實報酬；與輸入特徵隔離
    │   ├── models/                # 已有：線性、GBDT、MLP、小型CPU GRU
    │   ├── training/              # 日期切分、fit、候選模型與升級
    │   ├── evaluation/            # 官方score、消融與比較
    │   ├── inference/             # 已有：載入固定模型、schema與時間檢查，不fit
    │   ├── submission/            # 已有：CSV、deadline、提交ledger及回執核對
    │   ├── monitoring/            # 待建：新鮮度、缺值、漂移與失敗狀態
    │   └── pipelines/             # 串接研究訓練／每日工作流
    ├── scripts/                   # 已有CLI；入口薄、邏輯留在src
    ├── tests/                     # 已有合成測試；依模組逐步增加
    ├── notebooks/                 # 按需建立：EDA與可匯出的圖表
    ├── deployment/                # 已有：systemd service／timers；尚未啟用
    └── docs/                      # 規格、來源、決策、實驗與進度

受控執行時儲存（不進Git；下列是邏輯分層，按使用時建立）：
FINPRED_RUNTIME_ROOT/               # 例如/workspace/shared/finpred
├── data/
│   ├── raw/                       # 不可變原始快照與manifest
│   ├── interim/                   # 標準化、保留時間與來源版本的觀測
│   ├── features/                  # 版本化的模型輸入
│   ├── labels/                    # 完成的y與報酬，獨立儲存
│   └── templates/                 # 官方目標股票／日期模板
├── artifacts/
│   ├── models/{candidates,approved}/ # 候選與已驗證模型，禁止直接覆寫
│   ├── experiments/               # 同切分比較、參數與結果
│   ├── predictions/               # 模型／日期／cutoff對應預測
│   └── receipts/                  # 自動提交後的回執
└── logs/                          # 不含憑證的執行與失敗紀錄
```

這是完整責任分層，**不是所有節點都已建立或部署的宣告**。套件、CI及測試以STATUS為準。既有教師下載保留於`/workspace/shared/downloads/course/`，不為統一目錄而覆寫。每日CLI以`--runtime-dir`接收Git外私有持久根目錄；實際使用raw、candidates、approved.json、predictions、runs與提交ledger等路徑。上圖data／artifacts是邏輯分層，不冒稱與實際stage根目錄逐字相同。

| 路徑 | 放什麼 | 不放什麼 |
|---|---|---|
| `README.md` | 上手方式、專案目標、實際可用命令、目錄入口 | 大量重複會議紀錄 |
| `AGENTS.md` | Codex固定工作規則、必讀文件、驗證要求 | 帳密或未確認事實 |
| `configs/` | 來源、特徵、模型、切分、推論與執行設定 | token或個人電腦絕對路徑 |
| `src/finpred/ingestion/` | 教師資料、TWSE、TAIFEX、FinMind、新聞等adapter | 模型訓練或特徵選擇邏輯 |
| `src/finpred/data/` | schema、來源版本、交易日曆、available_at與as-of對齊 | 事後回填的未來資料 |
| `src/finpred/features/` | 個股、market、籌碼、新聞特徵及共同builder | 同一特徵在notebook另寫第二份 |
| `src/finpred/labels/` | y與intraday return的生成與隔離 | 把當日label接回特徵 |
| `src/finpred/models/` | 模型介面、logistic、樹、MLP、時序與meta模型 | 資料抓取與網站登入 |
| `src/finpred/training/` | 時間切分、fit、選參、OOF、模型打包 | 對外提交 |
| `src/finpred/evaluation/` | 官方score、accuracy、逐日逐月報告、消融 | 用靜態排行榜當唯一驗證 |
| `src/finpred/inference/` | 載入固定模型、檢查欄位、生成每日預測 | 現場重新fit前處理 |
| `src/finpred/submission/` | 模板、CSV驗證、dry_run、提交與回執 | 未檢查就直接覆蓋已接受版本 |
| `src/finpred/monitoring/` | freshness、missing、輸入drift、模型表現與截止 | 把缺資料視為正常零值 |
| `src/finpred/pipelines/` | 串接各模組的研究／每日工作流 | 把所有邏輯塞在一個main檔 |
| `scripts/` | 薄CLI入口、一次性遷移或稽核 | 複製src裡的演算法 |
| `tests/` | 時間洩漏、來源格式、模型輸入、提交格式測試 | 真實帳密、完整課程資料 |
| `notebooks/` | EDA、圖表、有限實驗原型 | 唯一可重現的正式pipeline |
| `deployment/` | 選定主機／執行器後的服務、timer與執行環境設定 | 把尚未啟用的範本稱為部署完成 |
| `docs/` | 定義、決策、進度、來源、runbook與報告大綱 | 原始資料鏡像 |
| `.github/workflows/` | CI、已審查啟用的排程 | 假裝已完成的模板 |
| `data/raw/` | 不變更的原始下載快照，按來源和下載時間分開 | 清洗後覆寫原始檔 |
| `data/interim/` | 清洗後、保留來源時間語意的長表 | 無法追溯來源的拼表 |
| `data/features/` | 按feature_version、cutoff、目標日版本化的特徵 | label與prediction混在一起 |
| `data/labels/` | 真實y與報酬，權限和feature分離 | 未來標籤混進訓練特徵 |
| `data/templates/` | 當期官方模板及其雜湊 | 自行改順序的股票清單 |
| `artifacts/models/` | 模型、前處理、欄位順序、訓練範圍與metadata | 只有權重、沒有環境或欄位 |
| `artifacts/experiments/` | 每fold結果、OOF、參數、環境與實驗manifest | 人工手填的最佳分數而無執行紀錄 |
| `artifacts/predictions/` | 目標日期、模型版本、cutoff對應的預測 | 不知道哪天產生的final_final.csv |
| `artifacts/receipts/` | 接受狀態、提交時間、session與CSV hash | 帳密或cookie |
| `logs/` | 無密鑰的結構化執行紀錄 | 完整來源回應與敏感session |

`data/`、`artifacts/`、`logs/`是上述受控儲存根目錄之下的邏輯路徑，預設不入Git；若在checkout內另設本機路徑，必須先確認已忽略。各資料夾內可再按來源、日期與版本分類，例如 `data/raw/taifex/2026-11-17/<fetch_id>/`。這是路徑示意，不表示目前已有那些資料。GitHub只會讀取repository根目錄的`.github/workflows/`，業務目錄內的舊`.yml.example`不因此成為啟用排程。

## 3. 每層如何交接

| 層 | 核心介面（實作狀態依列註明） | 保證 |
|---|---|---|
| ingestion | `download_course_sources`／`download_external`／市場歷史下載 | 原始回應、來源、hash；不悄悄改值 |
| normalization | `normalize_course_market`及availability政策 | typed value、unit、session_date、版本；未核實來源可blocked |
| daily tables | `prepare_prediction_table`／`prepare_training_table` | 私有快照hash／TLS／取得cutoff；七個股票lags共用stock_lags。今日觀測可用性與歷史vintage分開 |
| availability | 第一版整合於 `build_market_features(observations, native_sessions, targets)` | 每列值在該次cutoff前可知；保留版本證據 |
| features | 同一M0核心；泛用 `build_features(asof_data, feature_config)` 尚待實作 | 固定八欄M0、版本、missing/age/fresh；不讀YAML |
| labels | `build_intraday_labels` | y與open-to-close return，與輸入隔離 |
| training | `fit_model`／`train_candidate`／model-bundle-v1 | 按日期切分、train-only前處理；現有配置在同一過去fold重訓後公平比較 |
| evaluation | `evaluate_predictions` | 官方score及輔助指標；日期/股票全集明確 |
| inference | `predict_rows` | 禁止fit，驗證schema、model fit時點與cutoff |
| submission | `validate_prediction_csv`／`execute_submission` | exact ID/header；dry_run、POST acknowledgement與目前有效CSV回執分開 |
| daily | `run_stage` | collect／train／predict／submit／verify；私有runtime、鎖、真實時鐘、官方session |

第一個實際市場特徵交付為 `market_features` 一日一列。模型組把它接到所有股票列；不需要每個人各自抓一份全球指數。新聞也可先交市場級一日一列，再擴充公司級 `(stock_id,date)` 表。

新增來源先走`raw -> interim -> features`：原始值保留，再核實原生日曆、單位、版本及可用時間，在完整原生序列計算轉換，最後按台股目標cutoff向後對齊。價格指數、ETF／股票與匯率可依明確報價和調整政策計算報酬；SOX不是SOXX／SMH，TSM ADR與NVDA不是經濟指數。VIX先用水準／點數變化，TX_OI用有號部位水準／差分，殖利率用水準／基點變化；不把每種序列一律套百分比報酬。月／季總經資料若納入，另需首次發布與修訂版本證據，不能只按觀測月份對齊。

來源adapter優先重用官方介面及成熟HTTP／資料處理套件；目前紀錄有TWSE、TAIFEX、FinMind、GDELT等候選來源，逐資料集核對免費權限、歷史範圍與發布時間。來源登錄、取得成功、可回測與模型有增益是不同狀態。完整選擇與證據放DATA_SOURCES、SOURCE_ALIGNMENT及SOURCES，避免每個模組各維護一份API清單。

## 4. 設定與版本

`configs/features.yaml`是欄位公式對照；已有`configs/sources.json`來源清單及`configs/daily.json`未部署的時間／資料政策，目前不是可執行的通用工作流設定。後續按實際模型介面加入切分、參數與正式版本設定；先用清楚的設定檔，暫不引入複雜的模型註冊平台。

model-bundle-v1已保存權重、前處理器、feature schema／順序、feature version、train end date、fit cutoff、readiness／availability evidence、參數、套件版本、seed與資料／程式hash。推論若欄位、版本或時點不符便停止，不自動補出看似合理的欄位。joblib只載入本專案產生且明示可信的私有模型，雜湊不提供惡意序列化隔離。

獨立研究分支另有`configs/research/model_families.json`與[四架構設計](deep-research/MODEL_ARCHITECTURES.md)：這是未被runner讀取的設計，不改現有四類基準。跨branch共用資料方案見[DATA_AUTOMATION](deep-research/DATA_AUTOMATION.md)：Git保存metadata，私有共享儲存保存raw；producer的絕對payload路徑不能直接當可攜契約。尚未建立共享服務或catalog分支。

每次run manifest至少包括run_id、job_type、session_date、cutoff、started/finished_at、code_commit、來源快照、feature_version、model_version、輸出hash與狀態。manifest寫入持久儲存，不依賴聊天記憶。

## 04:00～09:00每日工作的依賴

依賴順序是「取得教師／外部來源 -> 保存新快照並檢查更新 -> 核實完成狀態與截止前可用性 -> 建特徵／更新已完成標籤 -> 候選訓練與驗證 -> 可用模型推論與CSV檢查」。同樣內容以hash識別，修訂另存版本，不重複append同一股票日期。資料取得可重試，但下游不能把抓取成功當成可訓練成功；一個來源未齊時明列blocked／missing及已驗證的替代政策。

台北04:00～09:00是使用者要求的自動化窗口。美股一般16:00 ET收盤對應台北夏令04:00、冬令05:00，還有提早收盤及供應商延遲，因此應在窗口內按來源重試，不宣稱04:00全齊。正式特徵截止不可晚於09:00；訓練必須有更早的停止／升級時間，保留推論和格式檢查餘裕。08:10／08:20等分配仍為操作提案，需以實測耗時與正式session確認。執行頻率、重試、鎖、失敗恢復及啟用狀態由OPERATIONS與實際pipeline設定維護；本文件不啟用daemon或排程，也不以Codex的一次性工作環境假裝持續執行。

## 5. 分階段建置

| 階段 | 做什麼 | 完成標準 |
|---|---|---|
| A 規格與資料 | 核實目標、日曆、每個欄位可用時間、官方模板 | 能重現schema audit；來源時間表有證據 |
| B 最小可行系統 | 個股基準 + M0；一個簡單模型；官方score；手動CSV | 一個命令能從已授權本地快照得到可驗證CSV |
| C 可信研究 | 四種ML approaches、walk-forward、消融、時間OOF | 相同切分比較，能說明市場特徵增益或無增益 |
| D 每日操作 | 來源增量更新、固定模型推論、重試、回執 | 連續多個普通session成功演練，失敗也可重跑 |
| E 進階擴充 | 海外指數、新聞、meta模型、漂移與重訓策略 | 新增功能有回測證據，未破壞B-D |

目前B／C已完成研究路徑、E00四族三目標與市場消融，但不是已核實PIT的正式服務。D已有stage、raw→當日表橋接與設定；仍缺歷史vintage／發布證據、正式模型、持久執行器與五日演練。最新快照實取晚於08:10時正確blocked，不能據此跳過時點檢查。額外指數E01～E03未顯示增益，未自動加入daily正式表；結果見EXPERIMENTS。meta model後續只用時間有效OOF，不用base model自己的train預測訓練融合器。

## 6. 團隊協作

蘇負責ingestion/news與市場特徵規格；楊協助外部時間序列和日曆；顏負責模型及序列介面；戴負責官方score、切分、OOF/meta與比較。實際工作量由團隊確認，這裡是建議，不新增未經同意的責任。

共用DATA_CONTRACT.md為交接契約，每個PR說明欄位、時間含意、驗證與相容性。所有人用同一個submission validator及score函式。API token與網站帳密由選定執行環境提供，避免在組員電腦間複製登入狀態。

## 7. Git與執行主機

私人GitHub保存程式與docs，原始資料留在授權儲存空間。Actions每次runner通常為短命環境，必須明確下載快照與模型並把新結果寫回持久位置。已有伺服器時可以用systemd timer跑相同CLI，不需改寫pipeline；GPU訓練也可以在另一主機執行同一版本程式。

使用者後續希望不依靠學校主機，可評估雲端執行器；本對話沒有Tasks排程工具，不能承諾代理離線自行常駐。Actions手動與schedule都要workflow存在default branch，main目前空樹；GitHub-hosted方案仍缺受控持久儲存／跨runner鎖與deadline備援。此處不改repo設定，不將SSH資訊當本地工作的前提。登入中的瀏覽器不會自動讓Actions或Cloud取得網站存取權。
