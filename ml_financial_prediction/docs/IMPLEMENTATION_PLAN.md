# 下一階段實作與驗收流程

> 歷史計畫，已由[RESEARCH_PLAN](RESEARCH_PLAN.md)及[STATUS](STATUS.md)取代。下文保留2026-10-28首批起點與候選介面，不作目前完成狀態。現已完成原生日曆adapter、研究市場表、四類模型、候選比較、raw→daily表橋接、推論、提交／回執及每日stage。今日cutoff前觀測證據不證明歷史vintage，strict訓練／正式模型與持久排程仍未就緒。已安裝技能以[TOOLS](research/TOOLS.md)為準。

更新：2026-10-28；時區Asia/Taipei，工作分支`dev`。本文件保留開發runbook與驗收依賴；已完成狀態以本節及STATUS為準，後續介面仍有待實作部分。

## 第一批已完成

pyproject／uv.lock、Ruff及根目錄CI設定已建立，本機104測試與lint通過；CI未推送執行。教師／Live及四個官方外部來源可重跑下載、不可變快照、schema／全集核對、版本差異、標籤隔離、官方score與按日期切分已實作並驗證。新Live已補齊10/27，仍有10/23的100個待完成標籤；新舊快照保留。新增外部資料為FRED美10年殖利率及美元兌台幣，詳API_INVENTORY。下列候選檔名中的下載／schema／score／labels／splits已落地，腳本實名見README。

尚未完成normalized availability adapter、真實市場表、模型fit／驗證升級、消融與四模型、每日工作流部署；configs/daily.json只是計畫。下一批先補逐來源日曆與可用時間證據，再接既有M0及scikit-learn，不把已完成raw取得誤當整體系統完成。

## 首批前起點與延續阻礙（歷史快照）

- 已有八欄 M0 市場特徵核心、CLI、版本追溯與 49 個通過的合成測試。這些證明既定輸入契約下的程式行為，沒有證明教師資料的時間語意或模型增益。
- 固定 training ZIP 已取得並通過既有稽核；真實來源日期／既有 shift／原生日曆／發布證據仍未齊，正式 normalized observations 與可回測市場表尚未 ready。
- Live 已透過助教提供的新入口 `https://fin-pred-daily.jiangxuehaokeai.chatgpt.site/` 正常 TLS 下載；成功狀態在 `live/verified/download_manifest.json`。本次ZIP含100股＋global，各37個日期列、範圍2026-09-01～10-27，與固定歷史包互補，不作完整替換。舊IP blocked manifest保留為歷史；原IP `curl -k` 的診斷仍收到代理上游 TLS error HTTP503，常態流程使用新網域並保留驗證。
- Live 頁面已說明台北時間00:00新增列、兩美股指數用前一美國 session；仍缺完整原生日曆、逐欄有效mask／歷史發布證據。未知暫-1但真值也可能=-1；不得全域清洗。10/23與10/27各100個y=-1，不能因ZIP可讀就視作標籤／特徵齊全。來源差異與證據見 DATASET_INVENTORY、SOURCE_ALIGNMENT。
- 模型、每日推論、提交與排程尚未實作／啟用。Phase 1 已存在的目標區段標籤即使現在可下載，也不能成為當時預測的有效輸入。

每次開始先讀 `AGENTS.md`、README、ARCHITECTURE、PROJECT_CONTEXT、STATUS、DECISIONS；資料／特徵工作另讀 DATA_CONTRACT、FEATURE_SPEC、SOURCE_ALIGNMENT、MARKET_FEATURES。先查 Graphify 的相關概念與來源，再核對原文，不把圖的 inferred 關係當成已證明事實。

## 第一個可審查 batch

### 執行順序與工具採用

使用者於2026-10-27確認偏好成熟、常用且適合任務的現成工具，避免重複造輪子。以下保留執行順序；工程與資料底座已完成首批，模型相關依賴及流程尚待加入：

1. 工程底座：先整合Ruff程式檢查與GitHub Actions自動測試，沿用現有unittest及合成測試資料；不把課程原始資料或憑證放入CI。
2. 資料底座：A／B並行完成可重跑下載、不可變快照、欄位／label隔離及來源時間證據；官方score與按日期分組切分可獨立實作，不必等所有來源查完。
3. 真實特徵：時間證據齊備後接標準化adapter與既有M0，產出第一張可追溯真實市場表，D獨立驗證假日、修訂與截止時間，檢查是否使用了預測當時尚未知的資訊。
4. 模型驗收：採scikit-learn的現成模型及Pipeline建立基準，在同樣時間切分比較「個股」與「個股＋市場」；再擴充四類模型，實驗量增加時用MLflow記錄。不因工具可用就提早啟用提交或排程。

其他MCP、技能與插件依具體任務缺口再採用；目前關鍵阻礙是資料時間證據，新增插件不能代替來源查核。

先完成「可重跑的授權下載＋不可變快照＋固定 ZIP 原始稽核＋schema／股票／label 隔離」，不把網站連通性、資料下載、資料可用時間與訓練 readiness 合併成一個成功狀態。

首批實作位置（已完成；目前可執行入口以README為準）：

- `src/finpred/ingestion/course.py`：使用既有個人 Secrets 的授權登入及已核實下載端點；cookie 僅存記憶體，輸出不得含帳密、token 或完整認證回應。
- `src/finpred/data/snapshots.py`：在 checkout 外或既有 ignored 路徑保存不可變原始快照；每次取得另記來源、取得時間、檔案大小、SHA256、資料版本／回應 metadata 及狀態，不覆寫舊檔。
- `src/finpred/data/course_schema.py`、`scripts/download_course_data.py`：從固定 ZIP 核對成員、欄位／型別、日期、股票全集、重複鍵、缺值、可生成 label 的欄位，以及兩資料版本的新增／改寫／刪除差異。
- `tests/test_course_ingestion.py`、`tests/test_course_schema.py`：用小型合成 ZIP／模擬 HTTP 回應測試登入失敗、下載失敗、格式錯誤、原始檔保留與資料全集；真實課程資料不放入測試或 Git。

這個 batch 的驗收：兩包可由可追溯快照重跑稽核；相同內容有相同 hash，更新不破壞歷史；股票代碼保留字串與全集；目標／label 區和特徵候選區明確分離。Live 已實測為9/1起的新區段，無 info.json，不可覆寫固定歷史或其股票清單；下載器應重現已核實的表單登入／下載並保留TLS驗證。失敗與未完成欄位必須有具體狀態；不以HTTP200、CRC或數值=-1單獨推斷ready。

## 平行分工、檔案與依賴

| 分工 | 擁有的檔案／交付 | 驗收與依賴 |
|---|---|---|
| A：資料取得與快照 | ingestion/course.py、data/snapshots.py、raw schema audit、下載／版本 manifest | 使用已核實的新網域、POST /login表單key與GET /data.zip；保持TLS驗證、cookie記憶體、無密鑰log；兩包分開快照，保存Live群組更新狀態與逐欄缺失／歧義限制 |
| B：時間與原生日曆 | `docs/SOURCE_ALIGNMENT.md`的逐系列證據；已有`configs/sources.json`來源清單，另需calendar artifacts | 確認 provider date、source session、已位移政策、時區、發布與修訂時間；正常日、台美不同休市日、週末／長假各至少一例，不由交集表倒推日曆 |
| C：標準化 adapter 與 M0 接入 | data/normalization.py、data/availability.py、scripts/build_course_market_features.py；必要時擴充現有 M0 介面 | 依賴 A 的 schema／快照及 B 的證據；產生契約要求的 normalized observations、完整原生日曆與明示 targets，再呼叫既有 M0；未知語意 fail closed |
| D：獨立測試與 review | tests/test_course_alignment.py、跨快照／修訂／洩漏回歸測試、review 記錄 | 以期望行為與反例驗證 A／C，不照抄實作；檢查 cutoff 後資料、來源假日、缺 session、修訂、缺值與股票／目標保留 |
| root：整合與記憶 | README、STATUS、DECISIONS、DATA_CONTRACT、EXPERIMENTS、Graphify 圖及整體驗收 | 分配不重疊的檔案範圍，確認依賴後整合；只將有證據的事項標 accepted，文件變更後刷新語意圖而非僅更新 hash |

各代理可先讀共用文件，但不要同時修改同一核心或記憶檔。A／B 可並行；C 可先完成 parser、schema 驗證及 blocked 報告，真正產生歷史特徵需等時間證據；D 與實作並行設計反例，最後獨立檢查。Live下載阻礙已解除，剩餘時間證據與欄位有效性限制仍不能略過。

## 時間與版本接入規則

1. 保留教師 `date` 的原始名稱與語意狀態；未核實前不直接填成原市場 session_date，更不把下載時間填成歷史發布時間。
2. 逐系列提供完整原生 session 日曆，在原生序列上計算報酬／差分，再按 available_at 對齊台股目標日。不能在多市場日期交集上把相鄰觀測當成一個 session。
3. 觀測須保留 source、series、原生 session、event、此版本 published_at、available_at、basis／evidence、fetched_at、revision、unit、原始快照 hash 與公開來源識別。
4. available_at 決定 cutoff 前資格；同 session 依此版本 published_at 選最新發布版，全部無發布時間才按可用時間排序。混合有／無發布 metadata 或平手歧義須拒絕，不能用 opaque revision_id 排序。
5. fetched_at 只記錄此次取得。歷史回補需另有發布證據／明列且有依據的保守假設；未來現場流程還須確認實際在 cutoff 前成功取得，不能只因來源理論上已發布就當作拿到了資料。
6. 每個轉換的分子、分母都使用同一 cutoff 前的版本；缺前一原生 session 不跳到更早值。目標日期、股票全集保留，缺來源透過 missing／age／fresh 與缺值原因表示。
7. 目前一目標日一明示 cutoff，不能晚於該日 09:00 Asia/Taipei；08:10 仍是提案。source condition 在缺預期發布排程時保持 unknown，不只用 24 小時 age 推斷停更。
8. Live兩美股已明示前一美國交易日收盤，不再無條件shift；其餘全球欄及固定包需各自核實。本站最後寫入／補抓時間不冒充原來源published_at。保存群組received／expected／status，對沒有逐欄mask的有號-1維持歧義；y=-1與未齊全價格不能進入已完成label集合。

## 已完成且可獨立驗證的評估模組

- `src/finpred/evaluation/official_score.py`：實作官方 `mean((2*p-1)*(close-open)/open)`；測試方向、分母、缺值／非法值、股票／日期對齊，不把 accuracy 當主指標。
- `src/finpred/labels/intraday.py`：核對實際價格欄是否為還原價，再建立 y 與盤中報酬；當日 open／close／high／low／volume／盤後資料進 label／evaluation 區，不混入當日盤前輸入。
- `src/finpred/training/splits.py`：按 target_date 分組的時間切分；同一天不同股票不得跨 train／validation。所有 imputer／scaler／feature selection 只用 train fit；以合成日期／股票集合測試不洩漏與全集政策。

這些模組已通過測試，但不等於整體真實回測ready；正式訓練仍需已核實的輸入時間與標籤可用時間。

## 從真實市場表走到模型比較

第一個真實市場表的交付必須含八欄 M0、欄位／來源版本、完整目標鍵、逐系列時間證據、缺值／age／fresh 摘要、分子分母追溯及可重跑 manifest。抽查正常日、假日和晚修訂後，才進時間回測。

先固定一個簡單模型及同一組日期、股票、資料版本與 walk-forward 切分，比較「個股基準」和「個股＋M0」。通過後再依正式規範比較至少四種有辨識度的 ML approaches，例如 logistic、梯度提升樹、MLP、TCN／RNN；Transformer 不必先做。每次有意義實驗記錄 EXPERIMENTS 的 code／data hashes、欄位版本、參數、seed、切分、官方 score、accuracy、逐月表現、missing 比例與結論。

Phase 1 既有標籤只可在符合歷史時點的訓練／評估範圍使用，不可由「現在已可下載」推論「當時即可用」。不可反覆以靜態排行榜挑超參數，也不可把無交易成本的官方 score 稱為投資策略淨利。這個階段不啟用網站提交或定時任務。

## 技能與插件選用

- 已安裝 Graphify：架構／依賴／文件導航與更新後的圖；不替代測試、來源查核或模型驗證。
- 已可用 cloud-environment-onboarding:setup：環境安裝、啟動及可重用設定；不替代 ML pipeline 實作。
- 已核實的官方候選技能（尚未安裝）：`jupyter-notebook` 適合 EDA／可重現 notebook，正式計算仍抽回模組；`gh-fix-ci` 用於實際 CI 失敗；`playwright` 用於必要的網站／操作介面驗證；`security-best-practices` 用於下載器、帳密與部署程式的有界安全審查。視工作需求採用，不為增加技能而安裝。
- 可選但尚未安裝的插件：Codex Security 做軟體安全檢查，Linear 管理任務／驗收。Graphify 目前不缺 API key，也無須為此增設憑證。
- 實驗追蹤可另評估 MLflow、受控資料版本可評估 DVC；它們是工程工具，不是目前已連接的插件。現階段保留unittest；Ruff及requests已安裝，scikit-learn是尚未安裝的models optional extra，開始模型實驗再啟用。
- mathbox 技能主要服務數學研究，不作為一般 coding／MLOps 通用流程；僅在研究結論承載特定數學計算時，才考慮適用的 computation-audit。
