# 台股盤中方向預測：安裝與技術入口

更新：2026-11-04，Asia/Taipei。組員先讀[根目錄操作指南](../README.md)：流程圖、資料／特徵表、三步操作及目前狀態都在該頁。本頁保留技術入口與規範，避免維護兩套不同說明。

**交到競賽網站的是0／1預測CSV。模型、前處理與來源紀錄另外保存，供重現及下一次推論。**

## 1. 目標、兩階段與分支

```text
y = 1{adjusted_close > adjusted_open}
score = mean((2 * prediction - 1) * (adjusted_close - adjusted_open) / adjusted_open)
```

| 項目 | 規範／本專案做法 |
|---|---|
| Phase 1 | 官方50股 × 84日期，2026-06-01～09-30，共4,200個預測 |
| Phase 1訓練 | 固定既有R2的TCN設定，只用 `target_date < 2026-06-01` 的完成標籤；各預測日只用更早觀測作特徵 |
| Phase 1截止 | 2026-12-24 23:59台北時間；網站的目前有效版本與歷次最佳排行榜分開核對 |
| Phase 2 | 每個官方session預測50股，當日09:00台北時間截止，採最後有效提交 |
| 計分競賽階段 | 2026-11-16～12-24，以官方session為準 |
| 報告 | 至少四種可重現ML approaches，最多七頁A4；2026-12-30 13:00台北時間截止 |
| 保存義務 | 原始碼／必要重現紀錄保存至2027-01-31 23:59台北時間 |

依[官方final.pdf](https://www.csie.ntu.edu.tw/~htlin/course/ml26fall/final/final.pdf)及官方模板。固定Training截至8/31，包含Phase 1的部分目標標籤，因此本次fit先排除6/1起全部標籤；不拿已知答案訓練後再回報預測。Phase 1是靜態回測，不套用Phase 2的每日09:00、正式模型認證或五日演練條件。歷史調整價／發布版本尚未核實的假設仍明記，不冒稱當時已取得。

| Branch | 放什麼 |
|---|---|
| `system-completion` | 預設分支：整合程式、文件、workflow與測試 |
| `live-data` | 共用raw快照、來源catalog、features／labels及允許持久保存的每日狀態 |
| `deep-research` | 外部研究來源與方法學；後續實作整合至程式分支 |
| `dev`／`main` | 保留核心開發歷史／依使用者要求保留空檔案樹與歷史 |

Repo目前為Public。帳密、cookie、token不進任何branch或log；程式分支不混raw。目錄依Chip Huyen《Designing Machine Learning Systems》生命週期及Cookiecutter Data Science分層，詳見[ARCHITECTURE](docs/ARCHITECTURE.md)。

## 2. 安裝與檢查

先安裝Git、Python 3.12及[uv](https://docs.astral.sh/uv/)。從repository根目錄執行：

```bash
export UV_CACHE_DIR="$HOME/.cache/uv"
bash tools/setup_project.sh
```

安裝器依 `uv.lock` 固定套件，並執行Ruff及測試。四架構或Phase 1的TCN另需CPU PyTorch，改用：

```bash
FINPRED_WITH_NEURAL=1 bash tools/setup_project.sh
```

不要在訓練進行中重新同步同一個Python環境。之後從 `ml_financial_prediction/` 執行：

```bash
uv run --locked --no-sync ruff check src scripts tests
uv run --locked --no-sync python -m unittest discover -s tests -q
```

CI支援Python 3.10／3.12；最新實際通過數及run見[STATUS](docs/STATUS.md)。MLflow、Ray、KubeRay及Kubeflow目前無必要，不為套件數量增加維運成本。

## 3. 組員：先拿共用資料，再訓練

完整可接續執行的命令集中於[根目錄「組員三步操作」](../README.md#4-組員三步操作)。組員取得已發布資料**不需課程帳密**。

| 入口 | 讀取 | 輸出／用途 |
|---|---|---|
| `scripts/fetch_live_data.py --with-features --allow-public-data` | 指定repo及 `live-data`／固定40碼revision | Git外runtime的 `raw/`、`shared-data/`；核對hash，保留來源取得時間 |
| `scripts/prepare_team_data.py --allow-research` | 同版raw，明確的排他性 `--train-before` | `training-table.json`、不含答案的 `features.json`、`lineage.json` |
| `scripts/train_model.py --allow-research` | 上一步的訓練JSON | 一次固定linear／HistGBDT fit；`model.joblib`、`manifest.json`、`training-run.json` |
| `notebooks/financial_model_comparison.ipynb` | 固定版本與固定日期切分 | 多模型比較、baseline、全部結果與來源，不另寫第二套特徵邏輯 |

`--train-before 2026-06-01` 代表只允許6/1之前的訓練標籤；`features.json`則保留同一日期範圍觀測日期聯集的50股研究輸入，不含答案，也不提供6～9月預測列。研究輸出目錄必須是新的、位於Git之外；失敗紀錄不覆寫成成功。此固定linear範例只驗證組員的資料→訓練鏈，不會自動得到正式提交模型或Phase 1答案。

11/04已從乾淨runtime實跑固定公開版 `fcd6810b132ac1c06f27daf5e880d36bd8386c50`：還原16來源／166個manifests／7個衍生檔，準備77,674筆完成標籤與77,700格特徵，最後標籤日期5/29；單次linear fit成功，沒有評分validation／holdout或提交。

`shared-data/features/stock_lags.csv.gz` 有七個個股特徵；`shared-data/features/market.csv` 是按可用時間對齊的市場表；`shared-data/labels/stock_outcomes.csv.gz` 是獨立答案。模型輸入與labels按 `(stock_id,target_date)` 對應，推論不載入labels。市場來源須先做原生序列轉換及時間對齊，再以目標日接到50股，不能對原始日期直接join。欄位、lag、單位與數值例子見[根目錄特徵表](../README.md#3-特徵表lag-到底是什麼)及[FEATURE_SPEC](docs/FEATURE_SPEC.md)。

### 維運者：直接下載教師資料

只有要重新採集來源的維運者需要安全注入 `COURSE_EMAIL`／`COURSE_PASSWORD`；一般組員沿用共用分支即可。Live公開金鑰由已核實前端在記憶體取得，不放命令列或Git。入口為 `scripts/download_course_data.py`、`download_external_data.py`，使用正常TLS並檢查ZIP、schema、hash與股票全集。網址與既有API見[DATASET_INVENTORY](docs/DATASET_INVENTORY.md)及[API_INVENTORY](docs/API_INVENTORY.md)。

目前已手動採集16類來源；這是採集成功數，不表示每個來源都有完整歷史、歷史發布證據或模型增益。Training與Live分開留版本；Live會修訂，`y=-1`為pending不能訓練。來源時間與目前覆蓋以當版catalog／lineage為準，不把今日下載時間填成歷史發布時間。

## 4. 模型研究與Phase 1入口

| 研究 | 模型／已完成範圍 | 解讀 |
|---|---|---|
| 較早E00 | linear、GBDT、MLP、GRU × 三目標 × 四季，共48 fits | 有一次已用過的2026年1～5月保留檢查，不再用該段挑winner |
| 新R2 | Ridge、HistGBDT、causal TCN、市場引導跨股attention，共48 fits | 2025探索fold已獨立逐鍵評分及模型重播；不是新的未見樣本外證據 |
| R1／E04 | 32個受控fits，含SOX／ADR／NVDA、FX／yield消融 | 保留負結果；完整產業歷史F3仍待接入，不用別組實驗冒充完成 |

官方主指標是方向乘盤中return；accuracy只是輔助。歷史版本假設下的回測分數，不稱為可執行且扣費後的投資淨利。全部數值與預註冊見[EXPERIMENTS](docs/EXPERIMENTS.md)、[RETURN_RATIO](docs/research/RETURN_RATIO.md)及[研究索引](docs/deep-research/README.md)。

| Phase 1步驟 | 專用入口 | 驗收 |
|---|---|---|
| 固定模型與回測 | `scripts/run_phase1_forecast.py` | 三個官方source manifests＋既有R2報告；先登記設定，只fit一次，不評分6～9月答案 |
| 建CSV | `scripts/build_phase1_predictions.py` | exact官方股票／日期順序、完整4,200格、每格僅整數0或1 |
| dry run／提交／對帳 | `scripts/submit_phase1_predictions.py` | 預設不POST；`--submit`實送，`--verify-only`只核對目前有效版本 |

各入口用 `--help` 查看參數。Phase 1固定TCN recipe為dropout 0.1、lookback 20、hidden 32、epochs 20、seed 42，沿用既有winner的15欄：七個個股lags＋八個M0市場欄。M0包含IXIC／GSPC／TWII／KS11四欄報酬、VIX水準／點差及外資淨部位水準／差分，精確八欄名稱見[MARKET_FEATURES](docs/MARKET_FEATURES.md)。市場欄保留時間／版本假設及缺值，不當成已認證歷史資料。專用回測會分離訓練標籤與各預測日可用特徵，保存前處理、權重、來源／程式hash及CSV。

一般 `scripts/predict.py` 服務的是固定模型對後續時點的推論，會檢查fit時點；不能拿今天才訓練的模型冒充過去已上線。Phase 1使用上述專用靜態回測路徑。joblib只載入團隊可信來源，不能把任意下載的模型當安全資料檔。

目前Phase 1尚待真實fit、上傳與4,200格回執驗收；以[STATUS](docs/STATUS.md)最新證據為準。網站收到CSV後還要下載「目前有效版本」逐格比對；HTTP 200或排行榜分數都不能替代這項驗收。

## 5. 每日Phase 2與實際執行位置

| 執行器 | 適合做什麼 | 目前證據／限制 |
|---|---|---|
| 本機／Codex雲端CPU | 固定模型、四架構研究、Phase 1 | 已實跑模型研究；不依賴Kaggle才能fit |
| GitHub-hosted Actions | 定時採集、候選訓練、每日推論、提交與回執 | workflow／跨工作排他鎖（lease）及提交前持久紀錄（ledger）已部署；11/04 08:05仍無 `schedule` 事件，觸發正在查核 |
| Kaggle Notebook | Notebook與選用GPU模型比較 | 本地Notebook／bundle已驗，尚無遠端訓練證據 |
| 官方Kaggle MCP | 讓agent操作Kaggle的連線 | 已找到註冊資訊；本會話尚無可呼叫的Kaggle RPC，MCP本身不提供算力 |

[Actions readiness 41645046599](https://github.com/jiangjiangian/ml-final-2026-fall/actions/runs/41645046599)回報 `credentials_missing`：該runner沒有Kaggle token／username／key，與個人MCP設定分開。課程帳密已實測有效，不需重新設定；Kaggle設定方法見[KAGGLE_TRAINING](docs/KAGGLE_TRAINING.md)。沒有Kaggle連線不阻止本機CPU工作；Kaggle排隊／額度不作每日09:00前完成的保證。

每日五階段入口是 `scripts/run_daily_pipeline.py`：下載（collect）→ 訓練（train）→ 預測（predict）→ 提交（submit）→ 核回執（verify）。詳細工作流、真時鐘、lease、未知POST先對帳及恢復方法見[OPERATIONS](docs/OPERATIONS.md)、[HOSTED_AUTOMATION](docs/HOSTED_AUTOMATION.md)、[PHASE2_GUIDE](docs/PHASE2_GUIDE.md)。聊天代理不是常駐執行器，也不需學校SSH。

當日08:10前確實取得的bytes，只證明今日可用，不能證明歷史調整價格當時已公開。Phase 2正式訓練仍缺歷史版本／發布證據及初始合格模型；獨立research shadow只能累積前瞻研究證據，不寫approved、不POST。候選失敗／超時保留既有合格模型；沒有就停止並明示原因，不假造成功。

`build_daily_tables.py`是每日時點驗證入口，**不是舊資料回填工具**；改 `--target-date` 不能把今天抓到的快照變成過去盤前已取得。組員離線研究改用第3節的prepare入口。額外市場資料已有採集與消融，尚未自動納入正式每日模型。

## 6. 文件與技能

| 文件 | 找什麼 |
|---|---|
| [STATUS](docs/STATUS.md)／[COMPLETION_CHECKLIST](docs/COMPLETION_CHECKLIST.md) | 最新真實結果、run、未完成條件 |
| [AGENTS](AGENTS.md)／[DECISIONS](docs/DECISIONS.md) | 工作規則、授權、已確認決策與歷史變更 |
| [ARCHITECTURE](docs/ARCHITECTURE.md)／[PROJECT_CONTEXT](docs/PROJECT_CONTEXT.md) | 系統分層、穩定背景 |
| [FEATURE_SPEC](docs/FEATURE_SPEC.md)／[DATA_CONTRACT](docs/DATA_CONTRACT.md) | 公式、單位、時間與輸入交接 |
| [LIVE_DATA_FEATURES](docs/LIVE_DATA_FEATURES.md) | 共用分支資料字典、來源與缺值 |
| [PROJECT_GRAPH](docs/PROJECT_GRAPH.md) | Graphify程式／文件圖與來源追溯 |
| [TOOLS](docs/research/TOOLS.md) | Graphify、Microsoft MarkItDown及固定版本技能 |

公開ML講義基石16份495頁與技法16份503頁的抽取文字已完整讀取，關鍵公式／圖像另核對；不是998頁圖片全部逐頁審閱。來源hash、頁碼與閱讀證據見[FOUNDATIONS](docs/research/FOUNDATIONS.md)、[TECHNIQUES](docs/research/TECHNIQUES.md)。工具不會自動提供ChatGPT Project其他未附上的聊天／檔案。
