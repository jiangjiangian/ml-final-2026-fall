# Graph Report - ml_financial_prediction  (2026-10-30)

## Corpus Check
- Corpus is ~36,386 words - fits in a single context window. You may not need a graph.

## Summary
- 1400 nodes · 3174 edges · 98 communities (51 shown, 47 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 102 edges (avg confidence: 0.88)
- Token cost: unavailable (host-agent usage metadata not exposed)

## Community Hubs (Navigation)
- 基石：16講研究筆記 / 技法：16講研究筆記
- intraday.py / build_intraday_labels()
- fit.py / fit_model()
- market.py / math
- DATA_ALIGNMENT：原生歷史、位移實測與strict／research入口 / SOURCE_ALIGNMENT：Fixed／Live位移已有實測；歷史vintage仍阻擋正式接入
- MarketFeaturesTests / .build()
- pathlib / os
- daily_tables.py / prepare_prediction_table()
- IMPLEMENTATION_PLAN：2026-10-28歷史起點與候選介面，現況由RESEARCH_PLAN／STATUS取代 / README：台股盤中方向預測ML系統入口與實際可執行範圍
- alignment / features.yaml
- DATASET_INVENTORY：10/30最新runtime與10/27凍結研究快照分開保存 / 10/30 runtime Live：541298bytes，08:58:49.072701Z取得，09/01～10/30共40日期
- hashlib / io
- RETURN_RATIO：官方目標推導、四家族三目標結果、公平候選比較與正式限制 / 以abs(r)加權的方向分類目標
- SOURCES：規範、團隊與官方來源索引 / DATA_SOURCES：候選來源與待核實限制
- DailyTests / clock()
- AUTOMATION：提交API、鎖與回執、部署設定已實作驗證，沒有啟用排程或真實POST / 正常TLS登入後前端JavaScript與唯讀GET state提供路由證據；來源JS hash保存在私有evidence
- external.py / parse_external_payload()
- CourseIngestionTests / CourseClient
- STATUS：研究／五階段與資料橋接完成；正式資料模型、部署、五日演練及真實回執未完成 / 未供表時從cutoff前最新合法私有manifest自動建七lag；82674列重建表與hash一致
- TOOLS：成熟工具採用、官方技能固定來源與Kaggle邊界 / systemd與Actions入口已準備未啟用，使用者希望不靠學校主機
- daily.py / run_stage()
- make_zip() / CourseSchemaTests
- EXPERIMENTS：E00–E03真實研究結果、負消融、凍結來源與追溯限制 / 市場消融同配置score皆低E00與全0；E03雖高E01仍未過個股基準
- market_history.py / download_market_history()
- OPERATIONS：已實作每日五階段與資料橋接，尚未正式部署 / train於07:20～07:50完成候選訓練、比較與原子升級
- RESEARCH_PLAN：每日自動ML系統與Return-ratio的現行研究執行計畫 / 每日04:00～09:00教師＋市場資料→特徵→候選驗證→50檔CSV→自動提交及回執
- json / sys
- submission/course.py / execute_submission()
- Client / execute()
- ingestion/course.py / snapshots.py
- 08:10前實際取得的bytes可證明今日特徵已可用 / 下載／對齊／研究訓練／四族／候選／推論／提交回執／daily CLI已實作；正式排程與實際提交未完成
- CourseSubmissionClient / Session
- MARKET_FEATURES：已實作 M0 API／CLI 與資料政策 / 每系列 session、available_at、age、missing、fresh 追溯欄
- DATA_CONTRACT：版本化觀測與特徵交接契約 / 觀測 schema：source／series／session／各種時間／版本與 availability_evidence
- E00完成2025四季48次fit，固定winner後僅一次2026年1～5月保留檢查 / 研究市場表按08:10對齊，再以目標日期left join個股；保留缺值與目標鍵
- 研究導航：可追溯代理查核筆記、結果限制與最新狀態入口 / E00 mlp／classification：2025合併score 0.000854985259
- PROJECT_GRAPH：官方 Graphify 專案圖與重建方法 / 互動 HTML、完整 JSON、社群報告、semantic 與 health 稽核
- MarketCLITests / .run_cli()
- D010：正式M0只收有證據的版本化觀測與明示原生日曆；研究另標readiness / 只使用available_at不晚於feature_cutoff的版本；禁止當日盤後輸入與未來回填
- Phase2每日09:00 UTC+8截止，採最後有效提交 / targets CSV 明示日期與 aware cutoff；一日一 cutoff，09:00 上界
- build_market_features(observations,native_sessions,targets)已整合availability與固定八欄M0 / 已有ingestion／data／features／labels／models／training／evaluation／inference／submission／pipelines與CLI
- B/C研究與E00／市場消融已完成；D尚缺歷史證據、正式模型、持久runner及五日演練 / D001–D005：盤中目標／09:00、方向乘報酬score、11/16競賽、六序列淨OI與112日期差
- E00原report缺實驗腳本hash、載入buffer hash與完整耗時；現存表hash及模型checksum不能證明48個舊fit版本鏈 / E01起記七份程式首尾一致hash、原input buffer與canonical table、每fold鍵／缺值／排除、逐月日分數與耗時
- build_market_features.py / main()
- 來源登錄、取得成功、可回測、模型有增益是不同狀態 / 額外市場來源已採集與消融；E01～E03未顯示增益，未自動納入正式daily表
- 截止前快照＋完成標籤→時間對齊／日期切分→候選fit與同條件評估→通過才升級 / 取得→新快照／修訂→完成與可用性→特徵標籤→候選驗證→模型推論與CSV
- D023：提交／五stage CLI／部署設定已實作，尚未部署或真實POST／回執 / D028：daily未供表自動私有raw→七lag；observed_fetch的available_at=fetched_at且皆不晚08:10
- FEATURE_SPEC：市場轉換與 point-in-time 對齊 / s_j(t) 為 cutoff 前最新可用來源 session
- csv_bytes() / CsvTests
- 依ingestion→data→features／labels→models／training／evaluation→inference／submission→pipelines分責 / DrivenData Cookiecutter Data Science v2：原始／中間／最終資料、程式、notebook、模型、報告分開
- 每日教師＋額外資料、特徵、模型驗證、50股CSV自動提交與回執核實已授權 / 已確認目標：擴充經濟市場序列、04～09更新、候選訓練、適當報酬差分與50股自動提交
- 生產approved模型載入須通過執行套件版本相容檢查 / 歷史調整價發布未核實，strict訓練blocked；research opt-in只產研究表
- predict自08:10凍結特徵並固定模型推論，禁止fit / train／predict未供表時自動從私有課程快照準備七個個股滯後特徵
- MarkItDown0.1.9與K-Dense技能已裝；32份998頁抽取文字讀至EOF，原PDF仍權威 / tools/setup_markitdown.sh重建工具，markitdown以本地PDF輸出Markdown
- 正式啟用仍缺歷史時間／vintage證據、正式模型／fallback、持久執行器恢復測試、五日dry run及真實回執 / 使用者希望不靠學校主機，正式執行器與持久儲存仍待落實
- 主代理由已保存預測／labels重新計分與共同鍵核對，未重fit或再用holdout選參 / E00凍結Training＋10/27 Live：82674完成Top50鍵、50 pending，四族×三目標×四季48次fit
- D013：在dev工作；main空檔案樹並保留提交歷史 / D025：評估GitHub-hosted＋私有持久儲存與備援；未改main或default branch、未啟cron
- 單隱藏層MLP家族：32hidden、最多80iter / E00 mlp／regression：2025合併score 0.000179339973
- _Scripts / HTMLParser
- Response / .close()
- LectureCorpusTests / .test_refuses_git_checkout_but_allows_external_store()
- Response / .close()
- Response / .close()
- model-bundle-v1保存權重、前處理、schema順序／版本、train end、fit cutoff、readiness證據及hash／環境 / 實驗保留資料／程式hash、欄位版、參數、seed、切分、環境與官方score
- 公開基石16份495頁＋技法16份503頁；來源hash／頁碼證據見研究文件 / D021：32份基石技法抽取文字全部讀至EOF；公式圖像僅關鍵頁核對
- E00共82674完成Top50鍵、七個前觀測列特徵；非保證相鄰native session，亦非PIT／投資淨利 / Fixed＋凍結Live：Top50完成82674股票日期鍵，50個10/23 pending另列排除
- 操作門檻：07:50前比較升級、08:10特徵、08:20提交、08:35核實、09:00硬停止 / configs/daily.json是政策計畫，不是scheduler執行設定
- 已核實同配置在新完成歷史、相容schema／政策及同fold不退步時可refresh / 候選公平重fit；換配置strict改善，同verified配置新歷史可同fold不退步refresh；cache綁incumbent／資料／程式／套件
- 四族三目標、daily橋接／推論／提交已實作，前端契約與唯讀模板已核；無真POST／正式模型／常駐 / 使用者希望雲端排程不依賴學校主機；無Tasks，runner／持久存儲待落實
- 固定美股前一global列與台韓同日close、Live兩美股前一session是數值匹配觀察 / 已產1655目標日市場表與SOX／TSM／NVDA報酬，OI缺證據留空
- daily未供表時自動準備七個個股lag；今日08:10前取得只證明今日可用 / 歷史vintage／發布未核實使strict訓練blocked；opt-in研究表與E00模型不得升級或提交
- run-stage.sh / run-stage.sh script
- D007：08:10凍結、08:20初交、08:35核對是操作提案 / D011：一目標日一cutoff，不晚於該日09:00 Asia/Taipei，跨時區比實刻
- Q007：Google AI Mode分享頁內容無法取得，不推測清單 / Docs的美國利多等發想不是可寫死預測規則或已證明因果；AI Mode頁無法讀取
- finpred / requests
- 最新10/30 Live541298bytes：40日期、3900完成label與100個10/23 pending，Training未變 / 教師／Live與官方外部來源CLI保存通過TLS、ZIP、欄位／股票與標籤檢查的不可變快照
- 支援短版／教學版／詳細版／展開第N點；教學每次聚焦一概念
- features.yaml為公式對照，sources.json為來源登錄，daily.json為未部署時間／資料政策
- D015：Live用助教新網域與正常TLS，curl -k只作當次診斷不保存設定
- K-Dense markitdown、Graphify與OpenAI gh-fix-ci／security-best-practices技能已安裝並保留版本授權

## God Nodes (most connected - your core abstractions)
1. `RETURN_RATIO：官方目標推導、四家族三目標結果、公平候選比較與正式限制` - 58 edges
2. `MarketFeaturesTests` - 45 edges
3. `STATUS：研究／五階段與資料橋接完成；正式資料模型、部署、五日演練及真實回執未完成` - 40 edges
4. `DATASET_INVENTORY：10/30最新runtime與10/27凍結研究快照分開保存` - 40 edges
5. `基石：16講研究筆記` - 39 edges
6. `技法：16講研究筆記` - 39 edges
7. `OPERATIONS：已實作每日五階段與資料橋接，尚未正式部署` - 38 edges
8. `IMPLEMENTATION_PLAN：2026-10-28歷史起點與候選介面，現況由RESEARCH_PLAN／STATUS取代` - 36 edges
9. `EXPERIMENTS：E00–E03真實研究結果、負消融、凍結來源與追溯限制` - 36 edges
10. `AUTOMATION：提交API、鎖與回執、部署設定已實作驗證，沒有啟用排程或真實POST` - 32 edges

## Surprising Connections (you probably didn't know these)
- `sessions JSON：每系列單來源、完整有序原生 session 與 calendar_evidence` --semantically_similar_to--> `先在完整原生交易序列計算，再按可用時間對齊台股目標日`  [INFERRED] [semantically similar]
  docs/MARKET_FEATURES.md → AGENTS.md
- `工具採用分建議採用、已安裝、已整合並驗證三種狀態` --semantically_similar_to--> `來源登錄、取得成功、可回測、模型有增益是不同狀態`  [INFERRED] [semantically similar]
  AGENTS.md → docs/ARCHITECTURE.md
- `main()` --uses--> `ExternalDataError`  [INFERRED]
  scripts/download_external_data.py → src/finpred/ingestion/external.py
- `main()` --calls--> `CourseSubmissionClient`  [INFERRED]
  scripts/submit_predictions.py → src/finpred/submission/course.py
- `main()` --calls--> `execute_submission()`  [INFERRED]
  scripts/submit_predictions.py → src/finpred/submission/course.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **同特徵引擎連接候選研究與每日推論；正式升級另受門檻控制** — docs_architecture_shared_feature_engine, docs_architecture_daily_candidate_training, docs_architecture_daily_submission_goal, docs_architecture_candidate_compatible_fallback [EXTRACTED 1.00]
- **相同linear加權配置與12140共同鍵的E00–E03消融** — docs_experiments_e00_linear_control, docs_experiments_e01_m0, docs_experiments_e02_sox, docs_experiments_e03_adr_nvda, docs_experiments_shared_validation_keys [EXTRACTED 1.00]
- **取得快照、時間證據與獨立反例驗證共同形成adapter交付** — docs_implementation_plan_role_a, docs_implementation_plan_role_b, docs_implementation_plan_role_c, docs_implementation_plan_role_d [EXTRACTED 1.00]
- **已實作但未部署的每日五階段流程** — docs_operations_collect_stage, docs_operations_train_stage, docs_operations_predict_stage, docs_operations_submit_stage, docs_operations_verify_stage [EXTRACTED 1.00]
- **原始版本、原生日曆、發布證據共同限制正式歷史對齊** — docs_research_data_alignment_provider_not_vintage, docs_research_data_alignment_exchange_calendars, docs_research_data_alignment_documented_vintage_gate, docs_research_data_alignment_production_gaps [EXTRACTED 1.00]
- **固定全集下score、加權錯分與條件均值決策** — docs_research_foundations_official_score, docs_research_foundations_weighted_error_identity, docs_research_foundations_conditional_mean_decision [EXTRACTED 1.00]
- **E00四家族共享三目標、時間切分與官方score** — docs_research_return_ratio_linear, docs_research_return_ratio_hist_gbdt, docs_research_return_ratio_mlp, docs_research_return_ratio_gru, docs_experiments_e00_matrix [EXTRACTED 1.00]
- **時間有效研究協定** — docs_research_techniques_point_in_time_features, docs_research_techniques_date_grouped_validation, docs_research_techniques_train_only_preprocessing, docs_research_techniques_time_valid_oof, docs_research_techniques_feature_group_ablation [EXTRACTED 1.00]
- **正式每日執行仍需workflow註冊、持久狀態與真實演練** — docs_research_tools_github_default_branch, docs_research_tools_github_delay_persistence, docs_research_tools_five_day_acceptance_pending, docs_research_tools_scheduler_not_deployed [EXTRACTED 1.00]
- **M0 可交接表：八欄、唯一鍵與品質追溯** — docs_data_contract_m0_schema, docs_data_contract_feature_key, docs_data_contract_provenance_quality, docs_feature_spec_first_delivery, docs_market_features_provenance_report [EXTRACTED 1.00]
- **raw自動七lag、今日實取證據、歷史strict阻擋與晚到拒絕共同構成daily資料門檻** — readme_automatic_seven_stock_lags, readme_current_prediction_evidence, readme_strict_training_history_block, readme_late_snapshot_block [EXTRACTED 1.00]
- **可重現研究：時間切分、OOF、score 與 manifest** — docs_feature_spec_walk_forward, docs_architecture_time_valid_oof, readme_official_score, docs_experiments_experiment_manifest [INFERRED 0.85]
- **不依賴學校主機的目標需default branch入口、持久私有狀態及雲端備援落地** — docs_decisions_d024_no_school_host, docs_decisions_d025_hosted_runner_proposal, docs_decisions_d013_dev, docs_decisions_q005_repo_runtime [INFERRED 0.95]
- **正式啟用依賴歷史資料證據、模型與序列相容、持久執行器及五日／回執驗收** — docs_operations_historical_training_gate, docs_operations_production_gru_history_gate, docs_status_runtime_choice, docs_research_plan_five_day_acceptance, docs_operations_release_acceptance_remaining [INFERRED 0.95]
- **Point-in-time：時間證據、修訂與原生 session 共同約束特徵** — agents_point_in_time_guard, docs_data_contract_revision_asof, docs_data_contract_session_not_availability, docs_feature_spec_available_asof, agents_native_sessions, docs_market_features_revision_selection, docs_market_features_previous_session [INFERRED 0.95]

## Communities (98 total, 47 thin omitted)

### Community 0 - "基石：16講研究筆記 / 技法：16講研究筆記"
Cohesion: 0.07
Nodes (42): 頁文字hash保留收集器v1語意, 基石：16講研究筆記, The Learning Problem, Learning to Answer Yes/No, Types of Learning, Feasibility of Learning, Training versus Testing, Theory of Generalization (+34 more)

### Community 1 - "intraday.py / build_intraday_labels()"
Cohesion: 0.07
Nodes (19): evaluate_predictions(), _index(), official_score(), ScoreResult, build_intraday_labels(), finite_number(), LabelResult, positive_price() (+11 more)

### Community 2 - "fit.py / fit_model()"
Cohesion: 0.07
Nodes (22): code_hashes(), diagnostics(), main(), run_experiments(), predict_rows(), aware_datetime(), fit_estimator(), GRUEstimator (+14 more)

### Community 3 - "market.py / math"
Cohesion: 0.08
Nodes (22): availability_for_session(), aware_instant(), build_history_market_features(), _calendar(), history_calendar(), _iso_date(), normalize_course_market(), normalize_history_snapshots() (+14 more)

### Community 4 - "DATA_ALIGNMENT：原生歷史、位移實測與strict／research入口 / SOURCE_ALIGNMENT：Fixed／Live位移已有實測；歷史vintage仍阻擋正式接入"
Cohesion: 0.07
Nodes (49): TSM ADR／NVDA是海外個股歷史close，不冒稱指數或已核實總報酬, 未來bar／假日缺口／雙移／hash改動／signed -1／Yahoo schema／TWSE schema反例, DATA_ALIGNMENT：原生歷史、位移實測與strict／research入口, documented歷史模式要求vintage核實；strict拒絕未核實假設, exchange_calendars 4.13.2：XNAS／XNYS／XTAI／XKRX排程, FinMind部分查詢403；不能推論所有dataset匿名可用, Fixed美股欄1505/1505匹配前一global列，僅1418/1506匹配前一US session, Fixed TWII／KS11各1506/1506同日close，盤前不可用 (+41 more)

### Community 5 - "MarketFeaturesTests / .build()"
Cohesion: 0.13
Nodes (5): calendars(), MarketFeaturesTests, observation(), target(), utc()

### Community 6 - "pathlib / os"
Cohesion: 0.09
Nodes (9): _write(), collect_one(), fetch_pdf(), lecture_urls(), LectureLinks, main(), private_write(), validate_output_root() (+1 more)

### Community 7 - "daily_tables.py / prepare_prediction_table()"
Cohesion: 0.10
Nodes (19): _blocked(), _cutoff(), DailyTableError, prepare_prediction_table(), prepare_training_table(), _private_bytes(), _root(), _save() (+11 more)

### Community 8 - "IMPLEMENTATION_PLAN：2026-10-28歷史起點與候選介面，現況由RESEARCH_PLAN／STATUS取代 / README：台股盤中方向預測ML系統入口與實際可執行範圍"
Cohesion: 0.07
Nodes (35): AGENTS：繁中溝通、時間安全、授權與驗證工作規則, ARCHITECTURE：模組化Python批次ML生命週期、責任分層與交接契約, DECISIONS：有證據accepted、建議proposed、未決／阻擋分流；不是部署宣告, ingestion/course.py已實作已核實登入下載、記憶體cookie與正常TLS, 目前已完成adapter、研究市場表、四類模型、候選比較、daily橋接、推論及提交回執；正式訓練／部署仍未就緒, training/splits.py按target_date分組切分；同日股票不跨fold，前處理只train fit, IMPLEMENTATION_PLAN：2026-10-28歷史起點與候選介面，現況由RESEARCH_PLAN／STATUS取代, EXPERIMENTS記錄code／data hashes、欄位、參數、seed、切分、score、accuracy、逐月與missing (+27 more)

### Community 9 - "alignment / features.yaml"
Cohesion: 0.05
Nodes (39): alignment, complete_native_sessions_required_for_1s_return, compute_returns_before_alignment, method, no_bfill, on_missing, original_global_already_shifted, preserve_all_target_dates (+31 more)

### Community 10 - "DATASET_INVENTORY：10/30最新runtime與10/27凍結研究快照分開保存 / 10/30 runtime Live：541298bytes，08:58:49.072701Z取得，09/01～10/30共40日期"
Cohesion: 0.09
Nodes (31): Live40日期列只是下載內容觀察，尚未獨立證明完整官方交易日曆, DATASET_INVENTORY：10/30最新runtime與10/27凍結研究快照分開保存, 早前Live494300bytes、hash292643…：37日期3700列，10/23與10/27各100個y=-1, global1506列、六序列，較2330少112日期, 161746筆y均符合adj_close>adj_open；11610筆平價為0, 10/30資料台北16:58才取得，晚於08:10；真實prediction table CLI正確blocked, 10/27修訂：相同3700股鍵／37global日期，100個10/27股列與1個global列改值，無新增移除, 舊下載根live/latest_verified仍指10/27研究版本，並非10/30 runtime最新索引 (+23 more)

### Community 11 - "hashlib / io"
Cohesion: 0.15
Nodes (14): main(), read_rows(), main(), main(), main(), audit_course_zip(), CourseSchemaError, _number() (+6 more)

### Community 12 - "RETURN_RATIO：官方目標推導、四家族三目標結果、公平候選比較與正式限制 / 以abs(r)加權的方向分類目標"
Cohesion: 0.11
Nodes (24): 普通方向分類目標, RETURN_RATIO：官方目標推導、四家族三目標結果、公平候選比較與正式限制, 林軒田基石第08講Noise and Error：ideal target頁9–14、weighted classification頁21–24, stock-specific CPU GRU家族：5lookback、16hidden、8epoch, E00 gru／classification：2025合併score 0.000832172751, E00 gru／regression：2025合併score 0.000564604555, E00 gru／weighted_classification：2025合併score 0.000838222003, HistGradientBoosting家族：60輪、15leaf (+16 more)

### Community 13 - "SOURCES：規範、團隊與官方來源索引 / DATA_SOURCES：候選來源與待核實限制"
Cohesion: 0.10
Nodes (33): Cboe VIX官方CSV實得9302列，1990-01-02～2026-10-26；指數點水準／差分，非持有VIX報酬, 同學API紀錄已找回TWSE／TAIFEX／FinMind／MIS／GDELT；token存在與權限不假設，SOX／ADR／NVDA接入待驗證, API_INVENTORY：既有同學API清單、4官方raw adapters及額外市場序列；raw成功與歷史可用分開, 新增FRED DEXTAUS：11235列、727缺值，1983起；一美元兌台幣，紐約中午買入匯率，非台北收盤, 新增FRED DGS10：16909列、721缺值，1962起；年率百分比，變化100×百分比差為bp, 四個官方來源正常TLS實下載；保留缺值日期，published_at／available_at未知，raw成功不是歷史vintage／完整原生日曆證明, TWSE MI_5MINS_HIST實得當月15列10/01～10/22；非已核實任意歷史回補，原生日曆待查, DATA_SOURCES：候選來源與待核實限制 (+25 more)

### Community 14 - "DailyTests / clock()"
Cohesion: 0.10
Nodes (9): bounded_training(), _fit_child(), Client, clock(), DailyTests, run(), worker(), replace_after_read() (+1 more)

### Community 15 - "AUTOMATION：提交API、鎖與回執、部署設定已實作驗證，沒有啟用排程或真實POST / 正常TLS登入後前端JavaScript與唯讀GET state提供路由證據；來源JS hash保存在私有evidence"
Cohesion: 0.11
Nodes (24): 根目錄daily.yml只有manual workflow_dispatch，無schedule，使用self-hosted／linux／finpred持久runner, GET /api/submissions/{id}?record=current：從目前state取ID下載有效CSV核對, GET /api/state：activePhase2Day／phase2Days、目前mySubmissions、歷史submissionHistory與uploadQuota, POST /api/submissions前端JSON契約已核實，但未實際POST, GET /api/sample-submission?phase=2&tradingDate=YYYY-MM-DD：官方id,日期及50股模板, cache綁incumbent manifest／metadata、實際訓練表、程式及套件；模型表CSV以實用buffer綁完整性, CourseSubmissionClient沿用HTTPS及記憶體登入，提供state()及daily_template(), validate_prediction_csv驗exact日期、50唯一字串ID、模板順序與文字0／1 (+16 more)

### Community 16 - "external.py / parse_external_payload()"
Cohesion: 0.12
Nodes (9): download_external(), ExternalDataError, _number(), parse_external_payload(), summarize_external(), _unique_object(), DownloadTests, ParseTests (+1 more)

### Community 17 - "CourseIngestionTests / CourseClient"
Cohesion: 0.13
Nodes (7): CourseClient, CourseDownloadError, LiveClient, VerifiedSession, CourseIngestionTests, response(), daily_template()

### Community 18 - "STATUS：研究／五階段與資料橋接完成；正式資料模型、部署、五日演練及真實回執未完成 / 未供表時從cutoff前最新合法私有manifest自動建七lag；82674列重建表與hash一致"
Cohesion: 0.10
Nodes (27): 歷史發布／vintage、OI逐欄有效性、正式訓練表與持久執行器仍是門檻, private repo、default仍main且main空樹；dev有設定不等於workflow_dispatch或cron已註冊, 普通回報結論／完成／下一步、300中文字內且最多三重點；成熟工具及獨立subagent分工, 已完成來源collect、1655日研究市場表、七lag自動表、四家族三目標及候選／提交保護, 公開基石16份495頁＋技法16份503頁，共32份998頁抽取文字讀至EOF, 未供表時從cutoff前最新合法私有manifest自動建七lag；82674列重建表與hash一致, STATUS：研究／五階段與資料橋接完成；正式資料模型、部署、五日演練及真實回執未完成, E04匯率利率與E05產業／age／互動尚未完成；已看2026年1～5月不能再當全新holdout (+19 more)

### Community 19 - "TOOLS：成熟工具採用、官方技能固定來源與Kaggle邊界 / systemd與Actions入口已準備未啟用，使用者希望不靠學校主機"
Cohesion: 0.13
Nodes (23): 技能清單為歷史候選；已安裝狀態以最新TOOLS為準，不沿用舊未安裝宣告, TOOLS：成熟工具採用、官方技能固定來源與Kaggle邊界, 五個真實交易日dry run與正式提交回執尚未驗收, OpenAI官方gh-fix-ci下載6原始檔，未執行腳本或登入, workflow_dispatch和schedule皆需default branch workflow；main空樹尚未改設定, GitHub排程可能延遲／丟棄；hosted runner需外部私有持久儲存與跨工作鎖, Graphify已安裝；變動文件須實質重新閱讀萃取，不能只更新hash, 目前無可呼叫Kaggle MCP；特定官方路徑404不代表全球不存在 (+15 more)

### Community 20 - "daily.py / run_stage()"
Cohesion: 0.21
Nodes (17): main(), _approved(), _at(), _collect(), _hash(), _json(), PipelineBlocked, _predict() (+9 more)

### Community 21 - "make_zip() / CourseSchemaTests"
Cohesion: 0.19
Nodes (8): compare_course_archives(), difference(), keyed_tables(), partition_stock_row(), CourseSchemaTests, csv_bytes(), make_zip(), stock_row()

### Community 22 - "EXPERIMENTS：E00–E03真實研究結果、負消融、凍結來源與追溯限制 / 市場消融同配置score皆低E00與全0；E03雖高E01仍未過個股基準"
Cohesion: 0.16
Nodes (19): 研究假設：個股前筆／label於來源日23:59台北可用，市場native close＋2h；OI兩欄全缺, E02 SOX與E03 TSM ADR／NVDA消融已完成；E04匯率利率與E05產業仍未計分, EXPERIMENTS：E00–E03真實研究結果、負消融、凍結來源與追溯限制, E00個股七欄對照E01＋M0已執行，E01相同linear加權配置下降, E00-LW相同配置基準：linear abs(r)加權分類score0.000482249960, E01個股＋M0：score0.000356441216，比E00-LW下降0.000125808745, E02個股＋M0＋SOX：score0.000249487724，比E01下降0.000106953492, E03個股＋M0＋TSM ADR／NVDA：score0.000388784462，較E01略升但仍低E00-LW (+11 more)

### Community 23 - "market_history.py / download_market_history()"
Cohesion: 0.13
Nodes (8): main(), download_market_history(), download_twse_sector_snapshot(), parse_chart_history(), parse_twse_sector_snapshot(), MarketHistoryTests, payload(), Session

### Community 24 - "OPERATIONS：已實作每日五階段與資料橋接，尚未正式部署 / train於07:20～07:50完成候選訓練、比較與原子升級"
Cohesion: 0.15
Nodes (18): 候選失敗／超時或未通過時沿用相容已核實approved，沒有則blocked, collect於04:17／05:17／06:17／07:17補抓來源並保存快照, OPERATIONS：已實作每日五階段與資料橋接，尚未正式部署, 每次run有唯一ID、來源版本與輸出hash；持久POSIX鎖防並行覆蓋, 每日CLI已實作collect→train→predict→submit→verify，預設dry run, 初始模型嚴格勝train-majority；換配置嚴格勝同fold現有配置, 額外市場來源已採集及消融，未自動提升為正式daily特徵, 本對話沒有Tasks／排程工具，不能承諾聊天關閉後代理常駐 (+10 more)

### Community 25 - "RESEARCH_PLAN：每日自動ML系統與Return-ratio的現行研究執行計畫 / 每日04:00～09:00教師＋市場資料→特徵→候選驗證→50檔CSV→自動提交及回執"
Cohesion: 0.15
Nodes (19): 快照→標準化與可用性報告→版本特徵／獨立labels→訓練表→模型包→CSV→回執, 每日04:00～09:00教師＋市場資料→特徵→候選驗證→50檔CSV→自動提交及回執, 公開32份998頁抽取文字已完成；不宣稱全部圖片或未提供當期教材已讀, 五階段及raw→daily七個股票lag已實作；今日可用不證明歷史vintage, RESEARCH_PLAN：每日自動ML系統與Return-ratio的現行研究執行計畫, 本對話無Tasks；保留systemd及Actions手動入口，雲端正式executor仍未設定, 個股滯後基準→M0→逐組額外來源；lag／累積、波動、missing／age與產業互動分別消融, 五個官方交易日dry run與真實session回執是持續運行驗收，尚不可宣稱完成 (+11 more)

### Community 26 - "json / sys"
Cohesion: 0.15
Nodes (6): main(), main(), main(), main(), main(), read_prediction_file()

### Community 27 - "submission/course.py / execute_submission()"
Cohesion: 0.23
Nodes (9): _aware(), _csv(), _day(), execute_submission(), _guard(), _readiness(), _session(), SubmissionError (+1 more)

### Community 28 - "Client / execute()"
Cohesion: 0.23
Nodes (3): Client, execute(), WorkflowTests

### Community 29 - "ingestion/course.py / snapshots.py"
Cohesion: 0.22
Nodes (5): _exclusive_write(), _private_dir(), snapshot_bytes(), audit_template(), download_course_sources()

### Community 30 - "08:10前實際取得的bytes可證明今日特徵已可用 / 下載／對齊／研究訓練／四族／候選／推論／提交回執／daily CLI已實作；正式排程與實際提交未完成"
Cohesion: 0.15
Nodes (8): CLI 讀入 buffer 一次並記錄輸入／程式／CSV hash；防同時更新造成錯配, 固定 M0 八欄；YAML 只作規格，M1–M4／join／fit／提交未實作, workflow_dispatch與schedule皆要求workflow在default branch；main空樹時dev檔案不產生入口, train／predict未供表時自動從私有raw準備七個個股滯後特徵, run_daily_pipeline.py已有collect→train→predict→submit→verify，驗真實時鐘與官方session, dev為工作分支；main空樹且保留歷史；架構圖位於上層graphify-out, 下載／對齊／研究訓練／四族／候選／推論／提交回執／daily CLI已實作；正式排程與實際提交未完成, JSON提交介面前端核實、session／模板唯讀實測；尚無真實POST或成功回執

### Community 31 - "CourseSubmissionClient / Session"
Cohesion: 0.24
Nodes (3): CourseSubmissionClient, Session, TransportTests

### Community 32 - "MARKET_FEATURES：已實作 M0 API／CLI 與資料政策 / 每系列 session、available_at、age、missing、fresh 追溯欄"
Cohesion: 0.25
Nodes (7): 每系列 session、available_at、age、missing、fresh 追溯欄, MARKET_FEATURES：已實作 M0 API／CLI 與資料政策, 休市攜帶最新可用 session；fresh 僅新 session 為真，修訂不算新 session, 最新值為 null 不回退舊有效值；差分缺值仍可保留 VIX／OI 水準, 取最新 session 的明示日曆前序；分母用同 cutoff 版本，不跳缺口, 報告保存 current／previous 證據、應有前序、缺值原因、來源狀態, 10/30重抓固定包未變，最新Live40日期3900完成／100 pending；10/27研究版本不變

### Community 33 - "DATA_CONTRACT：版本化觀測與特徵交接契約 / 觀測 schema：source／series／session／各種時間／版本與 availability_evidence"
Cohesion: 0.25
Nodes (9): 非空 availability_evidence 與 calendar_evidence 為 M0 輸入契約, DATA_CONTRACT：版本化觀測與特徵交接契約, 市場表唯一鍵：target_date、feature_cutoff、feature_version, M0 八欄：四指數報酬、VIX 水準／差分、TX_OI 水準／差分, 觀測 schema：source／series／session／各種時間／版本與 availability_evidence, 每 cutoff 選各 session 當時已可用的最後版本, 提交需 exact header／ID 順序／50 檔／整數 0 或 1, observations JSON：全部契約欄位、有限值、單位與時間證據 (+1 more)

### Community 34 - "E00完成2025四季48次fit，固定winner後僅一次2026年1～5月保留檢查 / 研究市場表按08:10對齊，再以目標日期left join個股；保留缺值與目標鍵"
Cohesion: 0.22
Nodes (7): 半導體 dummy×SOX 或因果 beta×IXIC 交互作用, 研究四族：正則化線性、梯度提升樹、MLP、小型GRU, 研究市場表使用最新歷史vintage與close＋2小時假設；strict拒絕未核實歷史發布, build_course_market_features.py以原生歷史與targets產研究market CSV／報告, 研究市場表按08:10對齊，再以目標日期left join個股；保留缺值與目標鍵, uv.lock固定requests／scikit-learn／exchange_calendars／Ruff；四模型另選PyTorch CPU, 每族比較普通分類、abs(return)加權分類、報酬回歸取正負

### Community 35 - "研究導航：可追溯代理查核筆記、結果限制與最新狀態入口 / E00 mlp／classification：2025合併score 0.000854985259"
Cohesion: 0.20
Nodes (8): E00四家族×三目標×四季度：48次fit＋12筆baseline，validation winner為MLP普通分類, 固定E00 MLP winner後只評一次2026年1–5月4750鍵：0.001275711605低於全0的0.001549845039, MLP80iter未收斂原警告保留，未依holdout再調參, 2025Q1–Q4只fit更早資料，驗證共12140鍵，四季2750／3050／3242／3098；seed42, 研究導航：可追溯代理查核筆記、結果限制與最新狀態入口, 研究筆記已由代理查核，尚無人類投稿審閱簽核；STATUS才是最新整合狀態, E00 2025全0／train-majority score0.000447093446，全1為相反數, E00 mlp／classification：2025合併score 0.000854985259

### Community 36 - "PROJECT_GRAPH：官方 Graphify 專案圖與重建方法 / 互動 HTML、完整 JSON、社群報告、semantic 與 health 稽核"
Cohesion: 0.24
Nodes (8): 本代理 usage 未提供，token／成本未知；零 placeholder 不是零消耗, PROJECT_GRAPH：官方 Graphify 專案圖與重建方法, 僅刪完全相同 JSON 重複邊；不同來源/context/relation 證據保留, 互動 HTML、完整 JSON、社群報告、semantic 與 health 稽核, 先完成文件＋AST 圖，再開始 M0 實作, 實際市場消融負結果仍保留於研究記憶, graphifyy 0.9.95；Codex skill/reference 與固定來源 provenance, 32份公開講義閱讀與四類研究模型已有結果

### Community 38 - "D010：正式M0只收有證據的版本化觀測與明示原生日曆；研究另標readiness / 只使用available_at不晚於feature_cutoff的版本；禁止當日盤後輸入與未來回填"
Cohesion: 0.20
Nodes (4): 必要驗證涵蓋未來／晚發布、休市、缺原生日期、零分母、負OI、重複鍵、修訂與跨時區, 教師 global_data.csv：六序列已下載稽核，時間與原生日期接入仍 blocked, 第一版需市場表、公式、時間來源、缺值、版本與防洩漏測試, 10/30新快照台北16:58取得，不能重建當日08:10輸入；真實準備正確blocked

### Community 39 - "Phase2每日09:00 UTC+8截止，採最後有效提交 / targets CSV 明示日期與 aware cutoff；一日一 cutoff，09:00 上界"
Cohesion: 0.25
Nodes (8): 每目標日一個 aware cutoff，最晚該日 09:00 Asia/Taipei, targets CSV 明示日期與 aware cutoff；一日一 cutoff，09:00 上界, final.pdf（2026-10-24）為正式 final 規範, 04～09取得教師外部資料、驗證候選、50股CSV自動提交並核實有效回執, Phase2每日09:00 UTC+8截止，採最後有效提交, 2026-10-24 final規範優先；競賽11/16～12/24，Phase1 12/24 23:59截止, 報告至少四種可重現ML approaches，最多七頁A4，12/30 13:00 UTC+8截止, Phase1共50股×84日=4200預測；Phase2每官方session50股

### Community 40 - "build_market_features(observations,native_sessions,targets)已整合availability與固定八欄M0 / 已有ingestion／data／features／labels／models／training／evaluation／inference／submission／pipelines與CLI"
Cohesion: 0.22
Nodes (5): 每列觀測在該次cutoff前可知，保留版本、missing／age／fresh；泛用YAML builder未實作, 每日推論產50股CSV／manifest／提交與回執；自動提交已授權，程式已實作但未部署, build_market_features(observations,native_sessions,targets)已整合availability與固定八欄M0, 已有ingestion／data／features／labels／models／training／evaluation／inference／submission／pipelines與CLI, 提交validator使用exact ID／header；dry_run、POST acknowledgement與目前有效CSV回執分開

### Community 41 - "B/C研究與E00／市場消融已完成；D尚缺歷史證據、正式模型、持久runner及五日演練 / D001–D005：盤中目標／09:00、方向乘報酬score、11/16競賽、六序列淨OI與112日期差"
Cohesion: 0.22
Nodes (6): B/C研究與E00／市場消融已完成；D尚缺歷史證據、正式模型、持久runner及五日演練, GitHub只讀repo根.github/workflows；業務目錄舊example不是啟用排程, D001–D005：盤中目標／09:00、方向乘報酬score、11/16競賽、六序列淨OI與112日期差, 按預測日期 walk-forward；同日股票不跨 train/validation, 官方score=mean((2*prediction-1)*(adj_close-adj_open)/adj_open), y=1{adjusted_close>adjusted_open}，輸出每檔0／1

### Community 42 - "E00原report缺實驗腳本hash、載入buffer hash與完整耗時；現存表hash及模型checksum不能證明48個舊fit版本鏈 / E01起記七份程式首尾一致hash、原input buffer與canonical table、每fold鍵／缺值／排除、逐月日分數與耗時"
Cohesion: 0.25
Nodes (8): E00原report缺實驗腳本hash、載入buffer hash與完整耗時；現存表hash及模型checksum不能證明48個舊fit版本鏈, E01起保存七份程式hash、input buffer／canonical table、fold鍵、缺值、環境與時間；E00缺項保留, GRU研究四家族比較完成，但正式daily缺舊模型中間日期context而阻擋approval, E01起記七份程式首尾一致hash、原input buffer與canonical table、每fold鍵／缺值／排除、逐月日分數與耗時, E01–E03七份原程式hash對應source objects事後保存；fit.py逆轉後續patch重建後驗hash，舊report不改, report與predictions保留fold／配置／baseline、OOF／holdout同鍵預測、警告與選擇；輸出不可覆寫, 正式模型仍待歷史時間證據、verified訓練／預測表與常駐排程；研究模型不提交競賽, GRU正式daily approval阻擋：只供今日50列且缺中間日期已核實context，序列不同研究驗證

### Community 43 - "build_market_features.py / main()"
Cohesion: 0.39
Nodes (5): code_manifest(), load_json(), main(), stage(), unique_object()

### Community 47 - "FEATURE_SPEC：市場轉換與 point-in-time 對齊 / s_j(t) 為 cutoff 前最新可用來源 session"
Cohesion: 0.46
Nodes (6): s_j(t) 為 cutoff 前最新可用來源 session, FEATURE_SPEC：市場轉換與 point-in-time 對齊, M0 八欄已實作與合成驗證；教師資料正式訓練表仍 blocked, 原生單 session 報酬 (P_s−P_prev)/P_prev, 三種索引：台股目標 t、來源 session s、cutoff(t), VIX 水準與點數差；不是可交易 VIX 報酬

### Community 50 - "每日教師＋額外資料、特徵、模型驗證、50股CSV自動提交與回執核實已授權 / 已確認目標：擴充經濟市場序列、04～09更新、候選訓練、適當報酬差分與50股自動提交"
Cohesion: 0.33
Nodes (3): 已確認目標：擴充經濟市場序列、04～09更新、候選訓練、適當報酬差分與50股自動提交, 已實作下載快照／隔離／對齊、M0與海外研究特徵、四族三目標、模型包、五stage與daily橋接, 圖只索引專案程式與文件，排除技能自身、憑證與課程 raw

### Community 52 - "predict自08:10凍結特徵並固定模型推論，禁止fit / train／predict未供表時自動從私有課程快照準備七個個股滯後特徵"
Cohesion: 0.40
Nodes (3): 2026-10-30新快照台北16:58取得，當日08:10 prediction正確blocked, predict自08:10凍結特徵並固定模型推論，禁止fit, train／predict未供表時自動從私有課程快照準備七個個股滯後特徵

### Community 53 - "MarkItDown0.1.9與K-Dense技能已裝；32份998頁抽取文字讀至EOF，原PDF仍權威 / tools/setup_markitdown.sh重建工具，markitdown以本地PDF輸出Markdown"
Cohesion: 0.40
Nodes (3): tools/setup_markitdown.sh重建工具，markitdown以本地PDF輸出Markdown, Microsoft MarkItDown0.1.9 PDF工具已安裝，PDF／Graphify／ML環境分開, 技能0.1.8範例與本機已驗證0.1.9差異保留安裝紀錄

### Community 54 - "正式啟用仍缺歷史時間／vintage證據、正式模型／fallback、持久執行器恢復測試、五日dry run及真實回執 / 使用者希望不靠學校主機，正式執行器與持久儲存仍待落實"
Cohesion: 0.40
Nodes (5): 使用者希望不靠學校主機，正式執行器與持久儲存仍待落實, strict歷史訓練因publication／vintage未核實仍blocked, 快照／模型／ledger需私有持久狀態；GitHub cache與短命runner不是資料庫, 正式啟用仍缺歷史時間／vintage證據、正式模型／fallback、持久執行器恢復測試、五日dry run及真實回執, 尚無正式模型、常駐排程、真實POST或五個交易日演練

### Community 55 - "主代理由已保存預測／labels重新計分與共同鍵核對，未重fit或再用holdout選參 / E00凍結Training＋10/27 Live：82674完成Top50鍵、50 pending，四族×三目標×四季48次fit"
Cohesion: 0.50
Nodes (4): E00凍結Training＋10/27 Live：82674完成Top50鍵、50 pending，四族×三目標×四季48次fit, E00驗證MLP普通分類winner的2026年1～5月一次保留檢查低於同鍵全0, 主代理由已保存預測／labels重新計分與共同鍵核對，未重fit或再用holdout選參, 同linear／abs(return)配置E01～E03市場擴充未勝E00，不升級

### Community 57 - "單隱藏層MLP家族：32hidden、最多80iter / E00 mlp／regression：2025合併score 0.000179339973"
Cohesion: 0.50
Nodes (4): 單隱藏層MLP家族：32hidden、最多80iter, E00 mlp／regression：2025合併score 0.000179339973, E00 mlp／weighted_classification：2025合併score 0.000498627855, scikit-learn MLPClassifier官方API

### Community 66 - "E00共82674完成Top50鍵、七個前觀測列特徵；非保證相鄰native session，亦非PIT／投資淨利 / Fixed＋凍結Live：Top50完成82674股票日期鍵，50個10/23 pending另列排除"
Cohesion: 0.67
Nodes (3): Fixed＋凍結Live：Top50完成82674股票日期鍵，50個10/23 pending另列排除, E00共82674完成Top50鍵、七個前觀測列特徵；非保證相鄰native session，亦非PIT／投資淨利, E00研究推論CLI對最新完整日50檔輸出0/1，production_eligible=false且未上傳競賽

## Knowledge Gaps
- **130 isolated node(s):** `schema_version`, `timezone`, `feature_cutoff_local`, `availability_status`, `method` (+125 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 364 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **47 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `RETURN_RATIO：官方目標推導、四家族三目標結果、公平候選比較與正式限制` connect `RETURN_RATIO：官方目標推導、四家族三目標結果、公平候選比較與正式限制 / 以abs(r)加權的方向分類目標` to `E00共82674完成Top50鍵、七個前觀測列特徵；非保證相鄰native session，亦非PIT／投資淨利 / Fixed＋凍結Live：Top50完成82674股票日期鍵，50個10/23 pending另列排除`, `研究導航：可追溯代理查核筆記、結果限制與最新狀態入口 / E00 mlp／classification：2025合併score 0.000854985259`, `E00原report缺實驗腳本hash、載入buffer hash與完整耗時；現存表hash及模型checksum不能證明48個舊fit版本鏈 / E01起記七份程式首尾一致hash、原input buffer與canonical table、每fold鍵／缺值／排除、逐月日分數與耗時`, `EXPERIMENTS：E00–E03真實研究結果、負消融、凍結來源與追溯限制 / 市場消融同配置score皆低E00與全0；E03雖高E01仍未過個股基準`, `單隱藏層MLP家族：32hidden、最多80iter / E00 mlp／regression：2025合併score 0.000179339973`?**
  _High betweenness centrality (0.002) - this node is a cross-community bridge._
- **What connects `schema_version`, `timezone`, `feature_cutoff_local` to the rest of the system?**
  _130 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `基石：16講研究筆記 / 技法：16講研究筆記` be split into smaller, more focused modules?**
  _Cohesion score 0.07099099099099099 - nodes in this community are weakly interconnected._
- **Why does `STATUS：研究／五階段與資料橋接完成；正式資料模型、部署、五日演練及真實回執未完成` connect `STATUS：研究／五階段與資料橋接完成；正式資料模型、部署、五日演練及真實回執未完成 / 未供表時從cutoff前最新合法私有manifest自動建七lag；82674列重建表與hash一致` to `IMPLEMENTATION_PLAN：2026-10-28歷史起點與候選介面，現況由RESEARCH_PLAN／STATUS取代 / README：台股盤中方向預測ML系統入口與實際可執行範圍`, `已核實同配置在新完成歷史、相容schema／政策及同fold不退步時可refresh / 候選公平重fit；換配置strict改善，同verified配置新歷史可同fold不退步refresh；cache綁incumbent／資料／程式／套件`, `DATA_ALIGNMENT：原生歷史、位移實測與strict／research入口 / SOURCE_ALIGNMENT：Fixed／Live位移已有實測；歷史vintage仍阻擋正式接入`, `主代理由已保存預測／labels重新計分與共同鍵核對，未重fit或再用holdout選參 / E00凍結Training＋10/27 Live：82674完成Top50鍵、50 pending，四族×三目標×四季48次fit`?**
  _High betweenness centrality (0.002) - this node is a cross-community bridge._
- **Should `intraday.py / build_intraday_labels()` be split into smaller, more focused modules?**
  _Cohesion score 0.06885758998435054 - nodes in this community are weakly interconnected._
- **Why does `EXPERIMENTS：E00–E03真實研究結果、負消融、凍結來源與追溯限制` connect `EXPERIMENTS：E00–E03真實研究結果、負消融、凍結來源與追溯限制 / 市場消融同配置score皆低E00與全0；E03雖高E01仍未過個股基準` to `E00共82674完成Top50鍵、七個前觀測列特徵；非保證相鄰native session，亦非PIT／投資淨利 / Fixed＋凍結Live：Top50完成82674股票日期鍵，50個10/23 pending另列排除`, `研究導航：可追溯代理查核筆記、結果限制與最新狀態入口 / E00 mlp／classification：2025合併score 0.000854985259`, `DATA_ALIGNMENT：原生歷史、位移實測與strict／research入口 / SOURCE_ALIGNMENT：Fixed／Live位移已有實測；歷史vintage仍阻擋正式接入`, `DATASET_INVENTORY：10/30最新runtime與10/27凍結研究快照分開保存 / 10/30 runtime Live：541298bytes，08:58:49.072701Z取得，09/01～10/30共40日期`, `E00原report缺實驗腳本hash、載入buffer hash與完整耗時；現存表hash及模型checksum不能證明48個舊fit版本鏈 / E01起記七份程式首尾一致hash、原input buffer與canonical table、每fold鍵／缺值／排除、逐月日分數與耗時`, `RETURN_RATIO：官方目標推導、四家族三目標結果、公平候選比較與正式限制 / 以abs(r)加權的方向分類目標`, `STATUS：研究／五階段與資料橋接完成；正式資料模型、部署、五日演練及真實回執未完成 / 未供表時從cutoff前最新合法私有manifest自動建七lag；82674列重建表與hash一致`?**
  _High betweenness centrality (0.002) - this node is a cross-community bridge._
- **Should `fit.py / fit_model()` be split into smaller, more focused modules?**
  _Cohesion score 0.06915113871635611 - nodes in this community are weakly interconnected._
## Build provenance

Built using graphifyy 0.9.95: AST extraction plus host-agent document extraction.
Clustering uses Graphify's installed NetworkX Louvain fallback.
Token usage/cost is **unavailable**, not zero: this host's agent API does not expose usage metadata. The tool's zero placeholders above are not measured usage.
`graphify-out/` is in the working tree; only shareable artifacts are retained by Git.
The graph is a map of documented plans and code, not evidence of model performance.

Normalization removed 9 exact duplicate edges and added 53 verified external import stubs using Graphify's own API. Added 1 external package nodes only for dependencies explicitly declared in pyproject.toml. Distinct evidence is retained. The raw extractor diagnostics and normalization audit are in `raw_health.json` and `normalization.json`. Repeated YAML list-field keys are a structural abstraction; individual market meanings are represented by the document extraction.

Clustering analyzes simple directed connectivity, so same-endpoint relations are counted as topology collapse in the diagnostic below. The JSON and HTML exports retain **all distinct parallel evidence edges** via Graphify's `original_links` export API; this count is not export evidence loss.

[graphify] MultiDiGraph edge-collapse diagnostic
input: <in-memory>
input_stage: provided JSON (normal graph.json is post-build)
effective_directed: <direct-call>
nodes: 1400
unverified_code_nodes: 0
raw_edges: 3198
valid_candidate_edges: 3198
missing_endpoint_edges: 0
dangling_endpoint_edges: 0
external_reference_edges: 0
self_loop_edges: 0
exact_duplicate_edges: 0
directed_unique_endpoint_pairs: 3174
directed_same_endpoint_collapsed_edges: 24
undirected_unique_endpoint_pairs: 3173
undirected_same_endpoint_collapsed_edges: 25
same_endpoint_group_count: 24
relation_variant_groups: 22
source_file_variant_groups: 0
source_location_variant_groups: 0
context_variant_groups: 2
post_build_graph_type: DiGraph
post_build_edges: 3174
producer_suppression_sites: 12
producer_suppression_examples:
  - L1814 seen_ids arity=unknown
  - L2378 seen_ids arity=unknown
  - L2380 seen_doc_refs arity=unknown
  - L3047 seen_ids arity=unknown
  - L3194 seen_ids arity=unknown
  - L4223 seen_keys arity=unknown
  - L4409 seen_keys arity=unknown
  - L7740 seen_ids arity=unknown
examples:
  - src_finpred_data_course_schema_compare_course_archives -> src_finpred_data_course_schema_compare_course_archives_keyed_tables edges=2 relations=['calls', 'contains'] locations=['L200', 'L232'] contexts=['', 'call']
  - src_finpred_data_course_schema_compare_course_archives -> src_finpred_data_course_schema_compare_course_archives_difference edges=2 relations=['calls', 'contains'] locations=['L213', 'L236'] contexts=['', 'call']
  - src_finpred_evaluation_init -> src_finpred_evaluation_official_score edges=2 relations=['imports_from', 're_exports'] locations=['L3'] contexts=['export', 'import']
  - src_finpred_evaluation_official_score_evaluate_predictions -> src_finpred_evaluation_official_score_scoreresult edges=2 relations=['calls', 'references'] locations=['L28', 'L86'] contexts=['call', 'return_type']
  - src_finpred_features_init -> src_finpred_features_market edges=2 relations=['imports_from', 're_exports'] locations=['L3'] contexts=['export', 'import']
note: normal graph.json is post-build; raw producer loss must be measured earlier.
