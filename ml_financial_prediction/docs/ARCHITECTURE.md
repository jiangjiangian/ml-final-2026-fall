# ML 系統建置與專案目錄

這份文件把市場特徵工作放回完整系統。下面的模組與執行介面是建置規格；目前尚未實作模型、爬蟲、推論或提交服務。先交付規格與可執行資料稽核，不需要一開始就上微服務、Kubernetes或即時串流。

## 1. 核心設計

用一個私人Git repository管理程式、設定與實驗紀錄；受限原始資料及模型存受控的持久儲存空間。先用模組化Python批次系統，每日執行一次主流程，取得來源有延遲時再重試。運算量真的需要時，訓練可獨立放GPU主機，日常推論維持CPU小任務。

資料流分成兩個使用同一套特徵引擎的流程：

| 流程 | 輸入 | 主要操作 | 產物 |
|---|---|---|---|
| 研究訓練 | 歷史快照、歷史發布時間、目標日曆 | 時間對齊、特徵、時間切分、fit、評估 | 固定模型版本、OOF預測、實驗結果 |
| 每日預測 | 截止前最新快照、當期模板、固定模型 | 同套時間對齊與特徵、predict、檢查格式 | 50檔CSV、執行manifest、提交回執 |

每日推論不重新fit scaler、imputer或特徵選擇器。需要重訓時啟動獨立的train流程，確認新模型後明確升級model version。

## 2. 目錄分類

以下是**建議完整目錄**。這次文件套件只包含README、AGENTS、docs、config、範本與audit工具；執行性模組逐階段新增，避免空檔案看起來像已完成系統。

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

`data/`、`artifacts/`、`logs/`是執行時儲存路徑，預設不入Git；放哪台磁碟或受控物件儲存由團隊決定。各資料夾內可再按來源、日期與版本分類，例如 `data/raw/taifex/2026-11-17/<fetch_id>/`。這是路徑示意，不表示目前已有那些資料。

## 3. 每層如何交接

| 層 | 核心介面（待實作） | 保證 |
|---|---|---|
| ingestion | `fetch(source, range, fetched_at)` | 原始回應、來源、hash；不悄悄改值 |
| normalization | `normalize(snapshot)` | typed value、unit、session_date、版本 |
| availability | `resolve_asof(records, target_dates, cutoff)` | 每列值在該次cutoff前可知；保留證據 |
| features | `build_features(asof_data, feature_config)` | 明確欄位順序、版本、missing/age |
| labels | `build_labels(stock_prices)` | y與open-to-close return，與輸入隔離 |
| training | `fit(train, validation, config)` | 不跨日期洩漏，打包前處理與模型 |
| evaluation | `evaluate(pred, label, return)` | 官方score及輔助指標；日期/股票明確 |
| inference | `predict(model_bundle, feature_table)` | 禁止fit，驗證schema與cutoff |
| submission | `render_validate_submit(pred, template, mode)` | exact ID/header；dry_run與回執分開 |

第一個實際市場特徵交付為 `market_features` 一日一列。模型組把它接到所有股票列；不需要每個人各自抓一份全球指數。新聞也可先交市場級一日一列，再擴充公司級 `(stock_id,date)` 表。

## 4. 設定與版本

`configs/features.yaml`定義欄位與公式。後續新增`configs/sources.yaml`記錄來源介面與免費權限，`configs/splits.yaml`記錄日期fold，`configs/models/<name>.yaml`記錄參數，`configs/production.yaml`指定啟用模型與cutoff。先用清楚的設定檔，暫不引入複雜的模型註冊平台。

每個model bundle必須一起保存：權重、前處理器、feature schema及順序、feature version、train end date、availability policy、參數、套件版本、seed、code commit與data hashes。推論若欄位缺少、順序不同或模型所需版本不符就停止該次預測並走已驗證備援，不自動補出看似合理的欄位。

每次run manifest至少包括run_id、job_type、session_date、cutoff、started/finished_at、code_commit、來源快照、feature_version、model_version、輸出hash與狀態。manifest寫入持久儲存，不依賴聊天記憶。

## 5. 分階段建置

| 階段 | 做什麼 | 完成標準 |
|---|---|---|
| A 規格與資料 | 核實目標、日曆、每個欄位可用時間、官方模板 | 能重現schema audit；來源時間表有證據 |
| B 最小可行系統 | 個股基準 + M0；一個簡單模型；官方score；手動CSV | 一個命令能從已授權本地快照得到可驗證CSV |
| C 可信研究 | 四種ML approaches、walk-forward、消融、時間OOF | 相同切分比較，能說明市場特徵增益或無增益 |
| D 每日操作 | 來源增量更新、固定模型推論、重試、回執 | 連續多個普通session成功演練，失敗也可重跑 |
| E 進階擴充 | 海外指數、新聞、meta模型、漂移與重訓策略 | 新增功能有回測證據，未破壞B-D |

先把B做通，再併行推進研究與日常操作。不要等Transformer完成才測試網站CSV。meta model使用時間有效OOF，不用base model在自己的訓練集預測的結果來訓練融合器。

## 6. 團隊協作

蘇負責ingestion/news與市場特徵規格；楊協助外部時間序列和日曆；顏負責模型及序列介面；戴負責官方score、切分、OOF/meta與比較。實際工作量由團隊確認，這裡是建議，不新增未經同意的責任。

共用DATA_CONTRACT.md為交接契約，每個PR說明欄位、時間含意、驗證與相容性。所有人用同一個submission validator及score函式。API token與網站帳密由選定執行環境提供，避免在組員電腦間複製登入狀態。

## 7. Git與執行主機

私人GitHub保存程式與docs，原始資料留在授權儲存空間。Actions每次runner通常為短命環境，必須明確下載快照與模型並把新結果寫回持久位置。已有伺服器時可以用systemd timer跑相同CLI，不需改寫pipeline；GPU訓練也可以在另一主機執行同一版本程式。

目前不需先連電腦來完成設計。日後選Codex Cloud時配置repo與資料存取；選本機／SSH時再配置該資料夾與Python環境。登入中的瀏覽器不會自動讓Actions或Cloud取得網站存取權。
