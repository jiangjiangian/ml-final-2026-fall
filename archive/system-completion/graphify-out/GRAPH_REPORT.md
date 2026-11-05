# Graph Report - ml_financial_prediction  (2026-11-03)

## Corpus Check
- 143 files · ~72,417 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 13 file(s) not represented in the graph (top: .timer 5, (none) 2, .example 2)

## Summary
- 2268 nodes · 5349 edges · 116 communities (78 shown, 38 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 187 edges (avg confidence: 0.88)
- Token cost: unavailable (host-agent usage metadata not exposed)

## Community Hubs (Navigation)
- sharing.py / re
- 基石：16講研究筆記 / 技法：16講研究筆記
- STATUS：公開設定與完整採集已驗證；研究／正式模型／排程與回執分開驗收 / 41593199735為collected、16 acquired、failures=[]、features exported，資料revision c3f36239c699a1ab2ecafb17eb68eaff13c8fb9f
- pathlib / tempfile
- hashlib / daily.py
- MarketFeaturesTests / .build()
- README：台股盤中方向預測ML系統入口與實際可執行範圍 / 08:10前實際取得的bytes可證明今日特徵已可用
- DailyTests / canonical_prediction_table()
- io / csv
- 來源與證據索引 / Lauren Tan與官方工程師：如何少盯流程，仍拿到可驗證的成果
- external.py / parse_external_payload()
- alignment / features.yaml
- AGENTS：繁中溝通、時間安全、授權與驗證工作規則 / 每日教師＋額外資料、特徵、模型驗證、50股CSV自動提交與回執核實已授權
- DATASET_INVENTORY：10/30最新runtime與10/27凍結研究快照分開保存 / 10/30 runtime Live：541298bytes，08:58:49.072701Z取得，09/01～10/30共40日期
- shared_features.py / build_shared_features()
- OPERATIONS：hosted完整採集已通過，每日五階段、正式模型與schedule／回執各自驗收 / train於07:20～07:50完成候選訓練、比較與原子升級
- fit.py / run_feature_ablation.py
- GitHub-hosted每日同步與模型流程：公開設定／完整採集和還原已驗，真正定時／正式提交待驗 / 本地completion.json只綁先前已fsync bytes，SIGKILL可留候選標記，不能單獨證明完成／雲端準時
- RETURN_RATIO：官方目標推導、四家族三目標結果、公平候選比較與正式限制 / 以abs(r)加權的方向分類目標
- temporal.py / TemporalRegressor
- json / argparse
- 金融領域知識如何改變ML問題 / M3提案causal TCN：lookback20、hidden32、kernel3、3 blocks／dilation1,2,4，未實作
- ingestion/course.py / snapshots.py
- CourseDownloadError / CourseIngestionTests
- AUTOMATION：提交API、鎖與回執、部署設定已實作驗證，沒有啟用排程或真實POST / 正常TLS登入後前端JavaScript與唯讀GET state提供路由證據；來源JS hash保存在私有evidence
- 全量驗收清單：設定／完整採集已完成，首個schedule及正式每日提交仍待驗 / 初始正式模型／歷史vintage缺證據；今日取得不能補舊歷史，不改研究模型為verified／approved
- 每天取得資料，讓不同branch成員使用相同版本 / 各模型branch用data_lock.json固定catalog commit與snapshot hash
- DataSharingTests / .snapshot()
- daily_tables.py / prepare_prediction_table()
- moment() / HostedShadowTests
- 依ingestion→data→features／labels→models／training／evaluation→inference／submission→pipelines分責 / 截止前快照＋完成標籤→時間對齊／日期切分→候選fit與同條件評估→通過才升級
- PROJECT_CONTEXT：NTU2026秋季final的穩定背景與來源權威順序 / 候選與現有配置在相同較早train重訓，再評相同validation鍵；通過才升級
- 金融預測競賽：能移植的是方法，評分與時點必須重建 / CMPAPI1索引證據：Jane Street Market Prediction — public metadata
- IMPLEMENTATION_PLAN：2026-10-28歷史起點與候選介面，現況由RESEARCH_PLAN／STATUS取代 / 歷史首批已完成工程、兩包下載快照、schema／版本差異、labels隔離、官方score及日期切分
- math / intraday.py
- 四種模型架構與實驗契約 / M4提案市場gate＋股內encoder／跨股attention：hidden32、2heads、1層，未實作
- EXPERIMENTS：E00–E03真實研究結果、負消融、凍結來源與追溯限制 / E02 SOX與E03 ADR歷史負結果保留；後續E04 FX／yield子集已另註冊並執行8 fits，E05產業仍未完成
- architecture_comparison.py / compare_architectures()
- normalization.py / CourseAlignmentTests
- raw() / test_evaluation.py
- TOOLS：成熟工具採用、官方技能固定來源與Kaggle邊界 / systemd與Actions入口已準備未啟用，使用者希望不靠學校主機
- 11/03進度報告：設定與16來源採集已通過，正式每日模型／提交未完成 / 617a09df的CI41594631696成功；Py3.12共326通過、Py3.10共322含3skip，Ruff／shell通過
- make_zip() / CourseSchemaTests
- native_feature_rows() / ResearchExpansionTests
- fit_model() / train_candidate()
- Phase 2：每天自動預測與提交 / 11/03目前選全部公開；下文組員限定／分離私人repo是先前可選方案
- MARKET_FEATURES：已實作 M0 API／CLI 與資料政策 / DATA_CONTRACT：版本化觀測與特徵交接契約
- DATA_ALIGNMENT：原生歷史、位移實測與strict／research入口 / 1655目標日期2020-01-02至2026-10-27，08:10台北cutoff研究表
- ARCHITECTURE：模組化Python批次ML生命週期、責任分層與交接契約 / live-data 每日衍生資料與 lag 定義
- RESEARCH_PLAN：每日自動ML系統與Return-ratio的現行研究執行計畫 / 每日04:00～09:00教師＋市場資料→特徵→候選驗證→50檔CSV→自動提交及回執
- submission/course.py / SubmissionError
- training_table.py / build_research_table()
- walk_forward_splits() / zoneinfo
- Client / execute()
- research_expansion.py / build_research_expansion()
- market.py / build_market_features()
- SOURCE_ALIGNMENT：Fixed／Live位移已有實測；歷史vintage仍阻擋正式接入 / 研究模型與市場消融已完成；正式normalized時間證據要求維持
- SOURCES：規範、團隊與官方來源索引 / OpenAI官方skills候選已查核，尚未加入本專案
- Phase2每日09:00 UTC+8截止，採最後有效提交 / 官方score=mean((2*prediction-1)*(adj_close-adj_open)/adj_open)
- KaggleBundleTests / .prepare()
- DECISIONS：有證據accepted、建議proposed、未決／阻擋分流；不是部署宣告 / deep-research源於dev@675d662；80ac804的四架構是設計，後續另行實作與研究比較
- PROJECT_GRAPH：官方 Graphify 專案圖與重建方法 / 圖新增金融競賽／期刊企業研究、四架構藍圖、資料共享與Lauren Tan工作流
- collect_lecture_corpus.py / main()
- os / build_market_features.py
- RuntimeStateTests / .put()
- CourseSubmissionClient / Session
- FEATURE_SPEC：市場轉換與 point-in-time 對齊 / s_j(t) 為 cutoff 前最新可用來源 session
- 金融競賽與agent工作流深度研究 / 深度研究範圍與證據規則
- HostedFlowTests / .test_collection_records_safe_actionable_categories_without_exception_text()
- D010：正式M0只收有證據的版本化觀測與明示原生日曆；研究另標readiness / D023：提交／五stage CLI／部署設定已實作，尚未部署或真實POST／回執
- 市場消融同配置score皆低E00與全0；E03雖高E01仍未過個股基準 / E01–E03均低於同鍵全0與E00-LW，沒有市場擴充增益或模型升級證據
- 研究導航：可追溯代理查核筆記、結果限制與最新狀態入口 / E00 mlp／classification：2025合併score 0.000854985259
- MarketCLITests / .run_cli()
- ScheduleDispatchTests / .run_wrapper()
- 課程報告與Phase1交付骨架 / 另登錄E04 FX／yield 8 fits未勝F0及全0；不替代blocked F3
- parse_chart_history() / MarketHistoryTests
- GitStoreTests / .clone_other()
- test_inference.py / fixture()
- Kaggle四模型研究與可重跑Notebook / 同一Notebook比較Ridge、HistGradientBoosting、因果TCN與市場引導跨股attention
- DATA_SOURCES：候選來源與待核實限制 / 來源接入需歷史、時區、發布依據、授權與日期抽查
- csv_bytes() / CsvTests
- API_INVENTORY：既有同學API清單、4官方raw adapters及額外市場序列；raw成功與歷史可用分開 / 四個官方來源正常TLS實下載；保留缺值日期，published_at／available_at未知，raw成功不是歷史vintage／完整原生日曆證明
- GRUEstimator / make_estimator()
- 主代理整合非重疊分工、證據、記憶與Graphify語意刷新 / adapter依賴A的schema／快照與B的時間證據；未齊先交parser及blocked報告
- documented歷史模式要求vintage核實；strict拒絕未核實假設 / Yahoo最新歷史close與provider時間戳不證明歷史發布／vintage
- frozen_schema() / .test_portable_ablation_cli_respects_blocked_slots_and_immutable_results()
- D013歷史核心在dev；main空樹並保留歷史；D030另授權deep-research研究分支 / D025：評估GitHub-hosted＋私有持久儲存與備援；未改main或default branch、未啟cron
- GRU正式daily approval阻擋：只供今日50列且缺中間日期已核實context，序列不同研究驗證 / GRU只用同股過去與當期輸入，邊界以最早已知向量padding；加更晚日期不能改更早預測
- Fixed美股欄1505/1505匹配前一global列，僅1418/1506匹配前一US session / Fixed IXIC／GSPC／VIX各1505/1505匹配前一教師global列日期close
- _Scripts / HTMLParser
- Response / .close()
- LectureCorpusTests / .test_refuses_git_checkout_but_allows_external_store()
- Response / .close()
- Response / .close()
- E00共82674完成Top50鍵、七個前觀測列特徵；非保證相鄰native session，亦非PIT／投資淨利 / Fixed＋凍結Live：Top50完成82674股票日期鍵，50個10/23 pending另列排除
- 操作門檻：07:50前比較升級、08:10特徵、08:20提交、08:35核實、09:00硬停止 / configs/daily.json是政策計畫，不是scheduler執行設定
- R2逐鍵評分與可信模型／前處理重播一致；R1／E04有固定共同12140鍵驗證 / submit_predictions CLI預設dry run，--submit才POST；同一開檔bytes及fstat mtime綁版本
- preflight.sh / preflight.sh script
- run.sh / run.sh script
- run-shadow.sh / run-shadow.sh script
- run-stage.sh / run-stage.sh script
- D007：08:10凍結、08:20初交、08:35核對是操作提案 / D011：一目標日一cutoff，不晚於該日09:00 Asia/Taipei，跨時區比實刻
- finpred / requests
- features.yaml為公式對照，sources.json為來源登錄，daily.json為未部署時間／資料政策
- D015：Live用助教新網域與正常TLS，curl -k只作當次診斷不保存設定

## God Nodes (most connected - your core abstractions)
1. `README：台股盤中方向預測ML系統入口與實際可執行範圍` - 84 edges
2. `STATUS：公開設定與完整採集已驗證；研究／正式模型／排程與回執分開驗收` - 80 edges
3. `來源與證據索引` - 72 edges
4. `RETURN_RATIO：官方目標推導、四家族三目標結果、公平候選比較與正式限制` - 59 edges
5. `EXPERIMENTS：E00–E03真實研究結果、負消融、凍結來源與追溯限制` - 47 edges
6. `MarketFeaturesTests` - 45 edges
7. `OPERATIONS：hosted完整採集已通過，每日五階段、正式模型與schedule／回執各自驗收` - 45 edges
8. `GitHub-hosted每日同步與模型流程：公開設定／完整採集和還原已驗，真正定時／正式提交待驗` - 42 edges
9. `DATASET_INVENTORY：10/30最新runtime與10/27凍結研究快照分開保存` - 41 edges
10. `AGENTS：繁中溝通、時間安全、授權與驗證工作規則` - 40 edges

## Surprising Connections (you probably didn't know these)
- `工具採用分建議採用、已安裝、已整合並驗證三種狀態` --semantically_similar_to--> `來源登錄、取得成功、可回測、模型有增益是不同狀態`  [INFERRED] [semantically similar]
  AGENTS.md → docs/ARCHITECTURE.md
- `fail_external()` --calls--> `ExternalDataError`  [INFERRED]
  tests/test_hosted_pipeline.py → src/finpred/ingestion/external.py
- `sessions JSON：每系列單來源、完整有序原生 session 與 calendar_evidence` --semantically_similar_to--> `先在完整原生交易序列計算，再按可用時間對齊台股目標日`  [INFERRED] [semantically similar]
  docs/MARKET_FEATURES.md → AGENTS.md
- `agent以目標／驗收／限制找上下文並自主執行，結束需可重跑證據` --semantically_similar_to--> `D033 accepted：短任務契約＋可重跑驗收；金融研究不無界追validation、外部技能不新增權限`  [INFERRED] [semantically similar]
  AGENTS.md → docs/DECISIONS.md
- `requests_diagnostic()` --uses--> `ExternalDataError`  [INFERRED]
  scripts/diagnose_external_sources.py → src/finpred/ingestion/external.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **同特徵引擎連接候選研究與每日推論；正式升級另受門檻控制** — docs_architecture_shared_feature_engine, docs_architecture_daily_candidate_training, docs_architecture_daily_submission_goal, docs_architecture_candidate_compatible_fallback [EXTRACTED 1.00]
- **工程／研究／實際運作三層證據不能互相替代** — docs_deep_research_agent_workflow_engineering_completion, docs_deep_research_agent_workflow_research_completion, docs_deep_research_agent_workflow_operation_completion [EXTRACTED 1.00]
- **一採集者與不可變物件／catalog／branch lock共享流程** — docs_deep_research_data_automation_one_collector_many_consumers, docs_deep_research_data_automation_immutable_objects, docs_deep_research_data_automation_data_catalog_proposal, docs_deep_research_data_automation_data_lock_pinning, docs_deep_research_data_automation_consumer_runtime [EXTRACTED 1.00]
- **四種同目標、同時序契約的研究架構** — docs_deep_research_model_architectures_m1_regularized_linear, docs_deep_research_model_architectures_m2_boosted_trees, docs_deep_research_model_architectures_m3_causal_tcn, docs_deep_research_model_architectures_m4_market_gated_attention [EXTRACTED 1.00]
- **相同linear加權配置與12140共同鍵的E00–E03消融** — docs_experiments_e00_linear_control, docs_experiments_e01_m0, docs_experiments_e02_sox, docs_experiments_e03_adr_nvda, docs_experiments_shared_validation_keys [EXTRACTED 1.00]
- **取得快照、時間證據與獨立反例驗證共同形成adapter交付** — docs_implementation_plan_role_a, docs_implementation_plan_role_b, docs_implementation_plan_role_c, docs_implementation_plan_role_d [EXTRACTED 1.00]
- **觀測列與原生交易日、可用時刻和缺值共同限定盤前特徵** — docs_live_data_features_previous_observation, docs_live_data_features_market_returns, docs_live_data_features_freshness_missing, docs_live_data_features_history_assumption [EXTRACTED 1.00]
- **每日採集、資料驗證、候選訓練、截止前推論、提交與回執** — docs_phase2_guide_daily_collection, docs_phase2_guide_features_validation, docs_phase2_guide_candidate_training, docs_phase2_guide_input_freeze, docs_phase2_guide_submission, docs_phase2_guide_receipt [EXTRACTED 1.00]
- **原始版本、原生日曆、發布證據共同限制正式歷史對齊** — docs_research_data_alignment_provider_not_vintage, docs_research_data_alignment_exchange_calendars, docs_research_data_alignment_documented_vintage_gate, docs_research_data_alignment_production_gaps [EXTRACTED 1.00]
- **固定全集下score、加權錯分與條件均值決策** — docs_research_foundations_official_score, docs_research_foundations_weighted_error_identity, docs_research_foundations_conditional_mean_decision [EXTRACTED 1.00]
- **E00四家族共享三目標、時間切分與官方score** — docs_research_return_ratio_linear, docs_research_return_ratio_hist_gbdt, docs_research_return_ratio_mlp, docs_research_return_ratio_gru, docs_experiments_e00_matrix [EXTRACTED 1.00]
- **時間有效研究協定** — docs_research_techniques_point_in_time_features, docs_research_techniques_date_grouped_validation, docs_research_techniques_train_only_preprocessing, docs_research_techniques_time_valid_oof, docs_research_techniques_feature_group_ablation [EXTRACTED 1.00]
- **正式每日執行仍需workflow註冊、持久狀態與真實演練** — docs_research_tools_github_default_branch, docs_research_tools_github_delay_persistence, docs_research_tools_five_day_acceptance_pending, docs_research_tools_scheduler_not_deployed [EXTRACTED 1.00]
- **M0 可交接表：八欄、唯一鍵與品質追溯** — docs_data_contract_m0_schema, docs_data_contract_feature_key, docs_data_contract_provenance_quality, docs_feature_spec_first_delivery, docs_market_features_provenance_report [EXTRACTED 1.00]
- **可重現研究：時間切分、OOF、score 與 manifest** — docs_feature_spec_walk_forward, docs_architecture_time_valid_oof, readme_official_score, docs_experiments_experiment_manifest [INFERRED 0.85]
- **不依賴學校主機的目標需default branch入口、持久私有狀態及雲端備援落地** — docs_decisions_d024_no_school_host, docs_decisions_d025_hosted_runner_proposal, docs_decisions_d013_dev, docs_decisions_q005_repo_runtime [INFERRED 0.95]
- **Point-in-time：時間證據、修訂與原生 session 共同約束特徵** — agents_point_in_time_guard, docs_data_contract_revision_asof, docs_data_contract_session_not_availability, docs_feature_spec_available_asof, agents_native_sessions, docs_market_features_revision_selection, docs_market_features_previous_session [INFERRED 0.95]

## Communities (116 total, 38 thin omitted)

### Community 0 - "sharing.py / re"
Cohesion: 0.08
Nodes (44): allowed_member(), bounded_bytes(), credential_values(), github_origin_identity(), HostedBlocked, no_symlink(), pack_runtime(), PrivateGitStore (+36 more)

### Community 1 - "基石：16講研究筆記 / 技法：16講研究筆記"
Cohesion: 0.07
Nodes (42): 頁文字hash保留收集器v1語意, 基石：16講研究筆記, The Learning Problem, Learning to Answer Yes/No, Types of Learning, Feasibility of Learning, Training versus Testing, Theory of Generalization (+34 more)

### Community 2 - "STATUS：公開設定與完整採集已驗證；研究／正式模型／排程與回執分開驗收 / 41593199735為collected、16 acquired、failures=[]、features exported，資料revision c3f36239c699a1ab2ecafb17eb68eaff13c8fb9f"
Cohesion: 0.03
Nodes (44): 歷史發布／vintage、供應商前一官方交易日覆蓋及初始合格正式模型仍未齊, Public且default=system-completion，main空樹保留；cron入口已滿足但首個schedule事件待驗收, 資料消費固定Git revision與來源hash，原取得時間和隊友接收時間分開, causal TCN已完成R2研究比較，但TCN探索分數不等於正式模型上線, 41593199735為collected、16 acquired、failures=[]、features exported，資料revision c3f36239c699a1ab2ecafb17eb68eaff13c8fb9f, 已實作collect→train→predict→submit→verify、七個個股lag、lease／CAS及POST前ledger, 42日期Live／4000完成／200pending，帳密驗證run於台北13:31取得，不能回填當天盤前, 從同一份核hash的Training／Live ZIP重建並核對schema／版本／50股順序／cutoff／七欄值／None mask (+36 more)

### Community 3 - "pathlib / tempfile"
Cohesion: 0.09
Nodes (3): curl_ipv4_diagnostic(), main(), requests_diagnostic()

### Community 4 - "hashlib / daily.py"
Cohesion: 0.12
Nodes (37): write_json(), bounded_research_fit(), _digest(), _fit_child(), main(), _now(), predict_shadow(), run_hosted_shadow() (+29 more)

### Community 5 - "MarketFeaturesTests / .build()"
Cohesion: 0.13
Nodes (5): calendars(), MarketFeaturesTests, observation(), target(), utc()

### Community 6 - "README：台股盤中方向預測ML系統入口與實際可執行範圍 / 08:10前實際取得的bytes可證明今日特徵已可用"
Cohesion: 0.07
Nodes (35): 半導體 dummy×SOX 或因果 beta×IXIC 交互作用, 固定 M0 八欄；YAML 只作規格，M1–M4／join／fit／提交未實作, system-completion已是含workflow的default，課程Secrets已實測，不需重設；cron實際觸發另驗收, train／predict未供表時自動從私有raw準備七個個股滯後特徵, deep-research 80ac804當時四架構尚未執行；後續runner已實作，實測狀態參STATUS, 固定40碼revision下載並核對raw／derived；保留來源取得時間，缺失／stale特徵另報blocked, run_daily_pipeline.py已有collect→train→predict→submit→verify，驗真實時鐘與官方session, system-completion是整合與default；dev保留核心基底、deep-research研究、main空樹，圖在repo根 (+27 more)

### Community 7 - "DailyTests / canonical_prediction_table()"
Cohesion: 0.08
Nodes (11): canonical_prediction_table(), Client, clock(), DailyTests, run(), worker(), replace_after_read(), feature_evidence() (+3 more)

### Community 8 - "io / csv"
Cohesion: 0.10
Nodes (22): main(), read_rows(), main(), _write(), main(), main(), prepare_bundle(), _read_json() (+14 more)

### Community 9 - "來源與證據索引 / Lauren Tan與官方工程師：如何少盯流程，仍拿到可驗證的成果"
Cohesion: 0.07
Nodes (40): 子代理限定檔案／問題或隔離worktree；builder交證據、reviewer新context挑反例、主代理重跑, 可驗收階段結束後，保存文件／下一步才壓縮context或開新會話, Anthropic官方：硬規則交hook／權限／CI；Google文件：context按目錄就近載入, Lauren Tan與官方工程師：如何少盯流程，仍拿到可驗證的成果, 工程完成：可重跑測試、乾淨checkout與真實輸入輸出hash, OpenAI Ryan Lopopolo：人提供意圖、環境、回饋，AGENTS導航及可執行不變條件, Lauren Tan／poteto身份及官方pstack可核對；React列Cursor而GitHub列xai，任職未獨立證實, Laziness Protocol：整合決策與縮小改動，lazy不省略驗證 (+32 more)

### Community 10 - "external.py / parse_external_payload()"
Cohesion: 0.09
Nodes (11): download_external(), download_fred_ipv4(), ExternalDataError, network_failure_category(), _number(), parse_external_payload(), summarize_external(), _unique_object() (+3 more)

### Community 11 - "alignment / features.yaml"
Cohesion: 0.05
Nodes (39): alignment, complete_native_sessions_required_for_1s_return, compute_returns_before_alignment, method, no_bfill, on_missing, original_global_already_shifted, preserve_all_target_dates (+31 more)

### Community 12 - "AGENTS：繁中溝通、時間安全、授權與驗證工作規則 / 每日教師＋額外資料、特徵、模型驗證、50股CSV自動提交與回執核實已授權"
Cohesion: 0.07
Nodes (20): 已確認目標：擴充經濟市場序列、04～09更新、候選訓練、適當報酬差分與50股自動提交, 金融試驗需有限預算與真正未看過的後續資料，不可無界hillclimb, 本對話沒有建立Codex排程工具；無Kaggle MCP／帳戶憑證，不稱已遠端執行, 41584330745與41593199735手動雲端採集均取得16來源並匯出研究特徵, daily未供表時自動準備七個個股lag；今日08:10前取得只證明今日可用, AGENTS：繁中溝通、時間安全、授權與驗證工作規則, 實驗保留資料／程式hash、欄位版、參數、seed、切分、環境與官方score, 已實作下載快照／隔離／對齊、M0與海外研究特徵、四族三目標、模型包、五stage與daily橋接 (+12 more)

### Community 13 - "DATASET_INVENTORY：10/30最新runtime與10/27凍結研究快照分開保存 / 10/30 runtime Live：541298bytes，08:58:49.072701Z取得，09/01～10/30共40日期"
Cohesion: 0.09
Nodes (31): Live40日期列只是下載內容觀察，尚未獨立證明完整官方交易日曆, DATASET_INVENTORY：10/30最新runtime與10/27凍結研究快照分開保存, 早前Live494300bytes、hash292643…：37日期3700列，10/23與10/27各100個y=-1, global1506列、六序列，較2330少112日期, 161746筆y均符合adj_close>adj_open；11610筆平價為0, 10/30資料台北16:58才取得，晚於08:10；真實prediction table CLI正確blocked, 10/27修訂：相同3700股鍵／37global日期，100個10/27股列與1個global列改值，無新增移除, 舊下載根live/latest_verified仍指10/27研究版本，並非10/30 runtime最新索引 (+23 more)

### Community 14 - "shared_features.py / build_shared_features()"
Cohesion: 0.13
Nodes (20): _aware(), _blocked(), build_shared_features(), _build_shared_features(), _catalog_identity(), _csv(), _json(), _latest() (+12 more)

### Community 15 - "OPERATIONS：hosted完整採集已通過，每日五階段、正式模型與schedule／回執各自驗收 / train於07:20～07:50完成候選訓練、比較與原子升級"
Cohesion: 0.10
Nodes (29): 候選失敗／超時或未通過時沿用相容已核實approved，沒有則blocked, 目前採用GitHub-hosted workflows、持久Git與lease；default／Secrets已落實，全16來源手動採集成功, hosted collect於04:17／05:17／06:17／07:17保存快照；原始採集不依賴競賽session，預測另查, OPERATIONS：hosted完整採集已通過，每日五階段、正式模型與schedule／回執各自驗收, 固定cron-stage修正已推送；還原演練成功不代表實際盤前日或五日完成, strict歷史訓練因publication／vintage未核實仍blocked, 每次run有唯一ID、來源版本與輸出hash；持久POSIX鎖防並行覆蓋, 每日CLI已實作collect→train→predict→submit→verify，預設dry run (+21 more)

### Community 16 - "fit.py / run_feature_ablation.py"
Cohesion: 0.12
Nodes (15): code_hashes(), diagnostics(), main(), run_experiments(), key_hash(), main(), run(), sha() (+7 more)

### Community 17 - "GitHub-hosted每日同步與模型流程：公開設定／完整採集和還原已驗，真正定時／正式提交待驗 / 本地completion.json只綁先前已fsync bytes，SIGKILL可留候選標記，不能單獨證明完成／雲端準時"
Cohesion: 0.06
Nodes (23): 部分Codex／ChatGPT介面可排程，本對話無建立或更新工具；GitHub是實際執行器, 資料cron台北04:17／05:17／06:17／07:17；首個真正schedule仍待驗收, 41593199735完整16來源collected／failures=[]／features exported，資料revision c3f36239c699a1ab2ecafb17eb68eaff13c8fb9f, COURSE_EMAIL／COURSE_PASSWORD Actions Secrets已由教師Training／Live下載驗證；與data token不同, 公開程式／私人資料跨repo方案仍支援，但目前全部公開，無需另建私人repo／token, 可選FINPRED_DATA_REPOSITORY指定另個私人資料repo，仍驗身份／origin與可見性，現同repo無需另設, default=system-completion且含workflow，main空樹保留；入口已滿足但不得用dispatch冒稱schedule成功, GitHub-hosted每日同步與模型流程：公開設定／完整採集和還原已驗，真正定時／正式提交待驗 (+15 more)

### Community 18 - "RETURN_RATIO：官方目標推導、四家族三目標結果、公平候選比較與正式限制 / 以abs(r)加權的方向分類目標"
Cohesion: 0.11
Nodes (28): 普通方向分類目標, RETURN_RATIO：官方目標推導、四家族三目標結果、公平候選比較與正式限制, 林軒田基石第08講Noise and Error：ideal target頁9–14、weighted classification頁21–24, stock-specific CPU GRU家族：5lookback、16hidden、8epoch, E00 gru／classification：2025合併score 0.000832172751, E00 gru／regression：2025合併score 0.000564604555, E00 gru／weighted_classification：2025合併score 0.000838222003, HistGradientBoosting家族：60輪、15leaf (+20 more)

### Community 19 - "temporal.py / TemporalRegressor"
Cohesion: 0.11
Nodes (7): CausalResidualBlock, CausalTCN, make_windows(), MarketGatedAttention, require_torch(), TemporalRegressor, TemporalModelTests

### Community 20 - "json / argparse"
Cohesion: 0.11
Nodes (12): _latest(), main(), main(), main(), main(), main(), main(), main() (+4 more)

### Community 21 - "金融領域知識如何改變ML問題 / M3提案causal TCN：lookback20、hidden32、kernel3、3 blocks／dilation1,2,4，未實作"
Cohesion: 0.07
Nodes (33): 通用TCN／深度預測方法可借用，但一般benchmark不證明金融增益, 競賽score未扣費稅滑價／成交與借券限制；不能冒稱已驗證實盤alpha, 估計E[r|X]後取正負；裁切／Huber會改變目標，須另立假設, 8萬股票列不是8萬獨立市場狀態；按日期切分與群聚報告, 金融領域知識如何改變ML問題, F0個股：現有7個lag；更長return／20日波動／量能為候選, F1跨市場：原生1／5／20-session return；SOX、ADR／NVDA，premium須另核實比例FX, F2狀態：VIX水準／點差、波動、age／休市mask及互動候選 (+25 more)

### Community 22 - "ingestion/course.py / snapshots.py"
Cohesion: 0.12
Nodes (10): main(), collect_raw(), _exclusive_write(), _private_dir(), snapshot_bytes(), download_course_sources(), download_market_history(), download_twse_sector_snapshot() (+2 more)

### Community 23 - "CourseDownloadError / CourseIngestionTests"
Cohesion: 0.13
Nodes (8): audit_template(), CourseClient, CourseDownloadError, LiveClient, VerifiedSession, CourseIngestionTests, response(), daily_template()

### Community 24 - "AUTOMATION：提交API、鎖與回執、部署設定已實作驗證，沒有啟用排程或真實POST / 正常TLS登入後前端JavaScript與唯讀GET state提供路由證據；來源JS hash保存在私有evidence"
Cohesion: 0.11
Nodes (24): 根目錄daily.yml只有manual workflow_dispatch，無schedule，使用self-hosted／linux／finpred持久runner, GET /api/submissions/{id}?record=current：從目前state取ID下載有效CSV核對, GET /api/state：activePhase2Day／phase2Days、目前mySubmissions、歷史submissionHistory與uploadQuota, POST /api/submissions前端JSON契約已核實，但未實際POST, GET /api/sample-submission?phase=2&tradingDate=YYYY-MM-DD：官方id,日期及50股模板, cache綁incumbent manifest／metadata、實際訓練表、程式及套件；模型表CSV以實用buffer綁完整性, CourseSubmissionClient沿用HTTPS及記憶體登入，提供state()及daily_template(), validate_prediction_csv驗exact日期、50唯一字串ID、模板順序與文字0／1 (+16 more)

### Community 25 - "全量驗收清單：設定／完整採集已完成，首個schedule及正式每日提交仍待驗 / 初始正式模型／歷史vintage缺證據；今日取得不能補舊歷史，不改研究模型為verified／approved"
Cohesion: 0.07
Nodes (19): G01已公開發布16來源完整採集，41593199735對應c3f36239c699a1ab2ecafb17eb68eaff13c8fb9f, Phase1 50股×84日截至12/24；至少四方法最多七頁報告12/30；證據保存至2027/1/31, 全量驗收清單：設定／完整採集已完成，首個schedule及正式每日提交仍待驗, E04另註冊9個FX／yield／age／missing欄與8fits，兩模型未勝F0／全0；七日quarantine只是研究假設, Public／default／Secrets已完成，下一cron台北11/04 04:17；首個schedule成功仍待驗, 較早private-only停止發布屬歷史；現在Public明確opt-in的live-data已完整雲端發布, lease／CAS／pre-POST checkpoint已有測試；shadow與固定stage已推送且研究／正式還原成功，原取消attempt不算成功, sharing／hosted與3.10獨立查核抓到payload記憶體／UTC Z／mock問題並修正，只以實際檢查更新狀態 (+11 more)

### Community 26 - "每天取得資料，讓不同branch成員使用相同版本 / 各模型branch用data_lock.json固定catalog commit與snapshot hash"
Cohesion: 0.09
Nodes (29): Guard Context Window：原文／長log留文件，主代理摘要與決策，分工給必要context, 第一階段建議private Actions artifacts：可按run ID共享，受TTL／配額／延遲限制, 導入驗收：第二個乾淨checkout下載固定版本，核對hash／可攜路徑／權限, 原始採集可先獨立運作，不因模型無增益或vintage不足停止保存新快照, S3 If-None-Match防覆寫與If-Match控制競態；Versioning預設未開且全版本完整物件計費, 各branch消費相同不可變快照，解析到各自Git外private runtime, 提案台北04:17／05:17／06:17／07:17重抓；UTC cron 17 20-23 * * *, data-catalog是尚未建立的metadata分支，不含raw／密鑰／signed URL (+21 more)

### Community 28 - "daily_tables.py / prepare_prediction_table()"
Cohesion: 0.16
Nodes (15): main(), _blocked(), _cutoff(), DailyTableError, live_fetch_in_prediction_window(), prediction_rows_from_history(), prepare_prediction_table(), prepare_training_table() (+7 more)

### Community 29 - "moment() / HostedShadowTests"
Cohesion: 0.16
Nodes (8): HostedShadowTests, late_fit(), publish(), slow_write(), inputs(), moment(), private_file(), ShadowForecastTests

### Community 30 - "依ingestion→data→features／labels→models／training／evaluation→inference／submission→pipelines分責 / 截止前快照＋完成標籤→時間對齊／日期切分→候選fit與同條件評估→通過才升級"
Cohesion: 0.07
Nodes (11): 每列觀測在該次cutoff前可知，保留版本、missing／age／fresh；泛用YAML builder未實作, 訓練僅使用截止前已完成且已可用歷史標籤；當日未收盤y與Live未完成-1禁用, DrivenData Cookiecutter Data Science v2：原始／中間／最終資料、程式、notebook、模型、報告分開, 截止前快照＋完成標籤→時間對齊／日期切分→候選fit與同條件評估→通過才升級, 每日推論產50股CSV／manifest／提交與回執；自動提交已授權，程式已實作但未部署, Chip Huyen《Designing Machine Learning Systems》（O’Reilly2022）：資料工程、特徵、部署、監控與持續學習, build_market_features(observations,native_sessions,targets)已整合availability與固定八欄M0, 已有ingestion／data／features／labels／models／training／evaluation／inference／submission／pipelines與CLI (+3 more)

### Community 31 - "PROJECT_CONTEXT：NTU2026秋季final的穩定背景與來源權威順序 / 候選與現有配置在相同較早train重訓，再評相同validation鍵；通過才升級"
Cohesion: 0.11
Nodes (14): Q007：Google AI Mode分享頁內容無法取得，不推測清單, PROJECT_CONTEXT：NTU2026秋季final的穩定背景與來源權威順序, hosted具Git lease／CAS、POST前ledger及fresh官方state／deadline檢查；真實運作另驗收, 11/03固定包重抓未變；Live42日期4000完成／200pending，13:31取得，原10/27研究版保持不動, 四族三目標、daily橋接／推論／提交已實作並有hosted採集；尚無真實預測POST或正式模型, 共享83000個50股日期格、100pending及26缺觀測label；取得與接收時間分開，R2全48fit已稽核, 使用者要求live-data每日同步、逐欄return／lag說明、多模型Notebook及不靠學校主機運行, 2026-10-30新增三要求：跨branch共享每日資料、金融競賽四架構研究、Lauren Tan agent workflow (+6 more)

### Community 32 - "金融預測競賽：能移植的是方法，評分與時點必須重建 / CMPAPI1索引證據：Jane Street Market Prediction — public metadata"
Cohesion: 0.08
Nodes (26): 時序驗證：較早train、同日同側、來源發布／修訂版本；GroupKFold不自動等於時間驗證, 正式09:00台北截止；08:10特徵凍結為專案操作提案, 金融預測競賽：能移植的是方法，評分與時點必須重建, G-Research Crypto：Weighted Correlation Coefficient；連續加密市場目標, Jane Street Market Prediction：Jane Street Trading；Code competition，公式尚未完整核對, Jane Street Real-Time：Jane Street Zero-Mean R2；同步重跑，非本課二元return, JPX Tokyo Stock Exchange：JPXSharpe；排名／投組目標非本課50股二元輸出, KDD Cup為年度資料探勘競賽，不是金融競賽同義詞；可讀archive只至2016 (+18 more)

### Community 33 - "IMPLEMENTATION_PLAN：2026-10-28歷史起點與候選介面，現況由RESEARCH_PLAN／STATUS取代 / 歷史首批已完成工程、兩包下載快照、schema／版本差異、labels隔離、官方score及日期切分"
Cohesion: 0.11
Nodes (24): ingestion/course.py已實作已核實登入下載、記憶體cookie與正常TLS, 目前已完成adapter、研究市場表、四類模型、候選比較、daily橋接、推論及提交回執；正式訓練／部署仍未就緒, training/splits.py按target_date分組切分；同日股票不跨fold，前處理只train fit, IMPLEMENTATION_PLAN：2026-10-28歷史起點與候選介面，現況由RESEARCH_PLAN／STATUS取代, EXPERIMENTS記錄code／data hashes、欄位、參數、seed、切分、score、accuracy、逐月與missing, 歷史首批已完成工程、兩包下載快照、schema／版本差異、labels隔離、官方score及日期切分, M0交付驗收須八欄、完整目標鍵、來源／欄位版本、時間與品質及分子分母manifest, 歷史規劃比較至少四種可重現ML approaches；目前四類實作已由頁首更新 (+16 more)

### Community 34 - "math / intraday.py"
Cohesion: 0.15
Nodes (7): evaluate_predictions(), _index(), ScoreResult, build_intraday_labels(), finite_number(), LabelResult, positive_price()

### Community 35 - "四種模型架構與實驗契約 / M4提案市場gate＋股內encoder／跨股attention：hidden32、2heads、1層，未實作"
Cohesion: 0.11
Nodes (24): ML噪音驗證不可無限試到贏；完成條件為有限預算、可重現與含負結果比較, source_fetched_at、catalog_published_at、consumer_received_at分開；不可為strict改寫fetched_at, 共同市場方向與個股成分並存；不能只保留相對排名, 部署前要求相同context的批次／逐日推論一致；新增未來資料不改舊輸出, 輸入[date_batch,50,20,feature]，20目標session含當次cutoff，缺期保留位置／mask／age, M4需保留日期50股feature，label_available_mask只控制loss；E00完整label平表非完整張量, 四種模型架構與實驗契約, 第五步融合用時間有效OOF及同raw-return尺度，另立有限預算 (+16 more)

### Community 36 - "EXPERIMENTS：E00–E03真實研究結果、負消融、凍結來源與追溯限制 / E02 SOX與E03 ADR歷史負結果保留；後續E04 FX／yield子集已另註冊並執行8 fits，E05產業仍未完成"
Cohesion: 0.10
Nodes (24): 研究假設：個股前筆／label於來源日23:59台北可用，市場native close＋2h；OI兩欄全缺, E02 SOX與E03 ADR歷史負結果保留；後續E04 FX／yield子集已另註冊並執行8 fits，E05產業仍未完成, EXPERIMENTS：E00–E03真實研究結果、負消融、凍結來源與追溯限制, E00原report缺實驗腳本hash、載入buffer hash與完整耗時；現存表hash及模型checksum不能證明48個舊fit版本鏈, 早期E04 E01＋FX／利率提案未計分；後續另註冊F0＋FX／yield子集8 fits，不能混同原配置, E04事先另註冊F0＋九個FX／yield／age／missing欄，兩模型×四季8 fits；不冒稱F3完整, E05台灣產業／交互作用未計分：三類單日水準已取，完整歷史報酬／消融未完成, 研究CPU環境：Python3.12.14、sklearn1.9.1、NumPy2.5.4、joblib1.6.0、PyTorch2.8.0+cpu (+16 more)

### Community 37 - "architecture_comparison.py / compare_architectures()"
Cohesion: 0.16
Nodes (12): build_sequence_panel(), candidate_configurations(), _code_hashes(), compare_architectures(), default_config(), digest(), _folds(), PanelPreprocessor (+4 more)

### Community 38 - "normalization.py / CourseAlignmentTests"
Cohesion: 0.16
Nodes (8): availability_for_session(), build_history_market_features(), _calendar(), _iso_date(), normalize_course_market(), _value(), calendar(), CourseAlignmentTests

### Community 39 - "raw() / test_evaluation.py"
Cohesion: 0.21
Nodes (6): official_score(), labels(), LabelTests, OfficialScoreTests, pred(), raw()

### Community 40 - "TOOLS：成熟工具採用、官方技能固定來源與Kaggle邊界 / systemd與Actions入口已準備未啟用，使用者希望不靠學校主機"
Cohesion: 0.13
Nodes (23): 技能清單為歷史候選；已安裝狀態以最新TOOLS為準，不沿用舊未安裝宣告, TOOLS：成熟工具採用、官方技能固定來源與Kaggle邊界, 五個真實交易日dry run與正式提交回執尚未驗收, OpenAI官方gh-fix-ci下載6原始檔，未執行腳本或登入, workflow_dispatch和schedule皆需default branch workflow；main空樹尚未改設定, GitHub排程可能延遲／丟棄；hosted runner需外部私有持久儲存與跨工作鎖, Graphify已安裝；變動文件須實質重新閱讀萃取，不能只更新hash, 目前無可呼叫Kaggle MCP；特定官方路徑404不代表全球不存在 (+15 more)

### Community 41 - "11/03進度報告：設定與16來源採集已通過，正式每日模型／提交未完成 / 617a09df的CI41594631696成功；Py3.12共326通過、Py3.10共322含3skip，Ruff／shell通過"
Cohesion: 0.08
Nodes (17): 617a09df的CI41594631696成功；Py3.12共326通過、Py3.10共322含3skip，Ruff／shell通過, 無本對話Codex排程工具，日常採GitHub Actions；GCP尚未建立且目前無需開通, 15下載jobs產16來源，training另產template；含四外部／八Yahoo／TWSE產業, 41584330745及41593199735均16來源collected／failures=[]／features exported；後者資料revision c3f36239c699a1ab2ecafb17eb68eaff13c8fb9f, Live42日期、100股4000完成／200pending，台北13:31取得，不能回填今日08:10證據, 核hash的Training／Live ZIP重建canonical schema／版本／50股順序／cutoff／七欄值與None mask, 共享表83000格＝50股×1660觀測日期，保留100pending與26缺觀測label，features／labels分離, 11/03進度報告：設定與16來源採集已通過，正式每日模型／提交未完成 (+9 more)

### Community 42 - "make_zip() / CourseSchemaTests"
Cohesion: 0.19
Nodes (8): compare_course_archives(), difference(), keyed_tables(), partition_stock_row(), CourseSchemaTests, csv_bytes(), make_zip(), stock_row()

### Community 43 - "native_feature_rows() / ResearchExpansionTests"
Cohesion: 0.20
Nodes (7): fred_feature_rows(), native_feature_rows(), price_return(), values(), fixture(), ResearchExpansionTests, target()

### Community 44 - "fit_model() / train_candidate()"
Cohesion: 0.17
Nodes (7): fit_model(), ModelBundle, save_model_bundle(), train_candidate(), ExperimentTests, table(), TrainingTests

### Community 45 - "Phase 2：每天自動預測與提交 / 11/03目前選全部公開；下文組員限定／分離私人repo是先前可選方案"
Cohesion: 0.09
Nodes (23): 11/03目前選全部公開；下文組員限定／分離私人repo是先前可選方案, 所有branch共用repo可見性；公開程式且資料僅組員可用需另私人repo／object storage, 07:20～07:50用已完成歷史標籤訓練，依日期與現有模型及簡單基準比較, 2026-11-02手動採集部分成功：11來源成功，教師Training／Live及兩個FRED來源失敗且保留前版, 教師ZIP公開再散布授權尚未核實，不假稱已禁止或已授權, 台北04:17、05:17、06:17、07:17採集來源，驗格式hash與實際取得時間, Phase 2：每天自動預測與提交, 外部傳入預測表尚未完成數值與來源bytes的重算驗證 (+15 more)

### Community 46 - "MARKET_FEATURES：已實作 M0 API／CLI 與資料政策 / DATA_CONTRACT：版本化觀測與特徵交接契約"
Cohesion: 0.15
Nodes (17): 非空 availability_evidence 與 calendar_evidence 為 M0 輸入契約, 每目標日一個 aware cutoff，最晚該日 09:00 Asia/Taipei, DATA_CONTRACT：版本化觀測與特徵交接契約, 市場表唯一鍵：target_date、feature_cutoff、feature_version, M0 八欄：四指數報酬、VIX 水準／差分、TX_OI 水準／差分, 觀測 schema：source／series／session／各種時間／版本與 availability_evidence, 每系列 session、available_at、age、missing、fresh 追溯欄, 每 cutoff 選各 session 當時已可用的最後版本 (+9 more)

### Community 47 - "DATA_ALIGNMENT：原生歷史、位移實測與strict／research入口 / 1655目標日期2020-01-02至2026-10-27，08:10台北cutoff研究表"
Cohesion: 0.14
Nodes (22): TSM ADR／NVDA是海外個股歷史close，不冒稱指數或已核實總報酬, 未來bar／假日缺口／雙移／hash改動／signed -1／Yahoo schema／TWSE schema反例, DATA_ALIGNMENT：原生歷史、位移實測與strict／research入口, exchange_calendars 4.13.2：XNAS／XNYS／XTAI／XKRX排程, FinMind部分查詢403；不能推論所有dataset匿名可用, Fixed TWII／KS11各1506/1506同日close，盤前不可用, Live IXIC／GSPC各37/37前一US session；VIX僅28/37, 八欄M0＋SOX／TSM ADR／NVDA ret_1s；兩欄OI全缺 (+14 more)

### Community 48 - "ARCHITECTURE：模組化Python批次ML生命週期、責任分層與交接契約 / live-data 每日衍生資料與 lag 定義"
Cohesion: 0.10
Nodes (19): build_shared_features將個股輸入、labels與市場表分開並綁同一raw catalog／lineage；research不標verified, ARCHITECTURE：模組化Python批次ML生命週期、責任分層與交接契約, hosted runner採跨workflow concurrency與Git lease／CAS；POST前持久in-flight ledger，再核對官方state與deadline, producer絕對payload路徑不能當跨機器可攜資料契約, export_snapshot_bundle以hash去重並保留真實fetched_at、修訂與portable catalog；import先核對hash路徑, 80ac804的design-only設定現可被architecture_comparison凍結與執行；不改寫當時歷史, 使用者曾授權私有live-data分享raw與衍生資料；portable Git catalog已實作，部署依STATUS, live-data 每日衍生資料與 lag 定義 (+11 more)

### Community 49 - "RESEARCH_PLAN：每日自動ML系統與Return-ratio的現行研究執行計畫 / 每日04:00～09:00教師＋市場資料→特徵→候選驗證→50檔CSV→自動提交及回執"
Cohesion: 0.15
Nodes (19): 快照→標準化與可用性報告→版本特徵／獨立labels→訓練表→模型包→CSV→回執, 每日04:00～09:00教師＋市場資料→特徵→候選驗證→50檔CSV→自動提交及回執, 公開32份998頁抽取文字已完成；不宣稱全部圖片或未提供當期教材已讀, 五階段及raw→daily七個股票lag已實作；今日可用不證明歷史vintage, RESEARCH_PLAN：每日自動ML系統與Return-ratio的現行研究執行計畫, 本對話無Tasks；保留systemd及Actions手動入口，雲端正式executor仍未設定, 個股滯後基準→M0→逐組額外來源；lag／累積、波動、missing／age與產業互動分別消融, 五個官方交易日dry run與真實session回執是持續運行驗收，尚不可宣稱完成 (+11 more)

### Community 50 - "submission/course.py / SubmissionError"
Cohesion: 0.23
Nodes (9): _aware(), _csv(), _day(), execute_submission(), _guard(), _readiness(), SubmissionError, validate_prediction_csv() (+1 more)

### Community 51 - "training_table.py / build_research_table()"
Cohesion: 0.18
Nodes (7): build_research_table(), number(), positive(), stock_lags(), build_course_sequence_table(), row(), TrainingTableTests

### Community 52 - "walk_forward_splits() / zoneinfo"
Cohesion: 0.20
Nodes (5): DateSplit, walk_forward_splits(), cutoffs(), DateSplitTests, split_rows()

### Community 53 - "Client / execute()"
Cohesion: 0.23
Nodes (3): Client, execute(), WorkflowTests

### Community 54 - "research_expansion.py / build_research_expansion()"
Cohesion: 0.14
Nodes (7): aware_instant(), history_calendar(), normalize_history_snapshots(), build_research_expansion(), _numeric(), _records_by_series(), _targets()

### Community 55 - "market.py / build_market_features()"
Cohesion: 0.27
Nodes (11): build_market_features(), _calendars(), _date(), _feature_values(), FeatureResult, _instant(), _Observation, _observations() (+3 more)

### Community 56 - "SOURCE_ALIGNMENT：Fixed／Live位移已有實測；歷史vintage仍阻擋正式接入 / 研究模型與市場消融已完成；正式normalized時間證據要求維持"
Cohesion: 0.19
Nodes (18): 正常日、週末／長假及台美不同休市日的原始值核對, SOURCE_ALIGNMENT：Fixed／Live位移已有實測；歷史vintage仍阻擋正式接入, 首輪blocked表與IMPLEMENTATION_PLAN是歷史起點，須併讀本輪更新, IMPLEMENTATION_PLAN保留首輪歷史，非本輪進度權威, 研究模型與市場消融已完成；正式normalized時間證據要求維持, 群組更新狀態缺逐欄mask；有號-1保留未知與真值歧義, Live其他系列不能直接套用兩美股欄的位移政策, Live已正常TLS取得；下載成功尚不等於歷史可用性核實 (+10 more)

### Community 57 - "SOURCES：規範、團隊與官方來源索引 / OpenAI官方skills候選已查核，尚未加入本專案"
Cohesion: 0.18
Nodes (18): 授權 GET /downloads/fin_pred_data.zip 與 /api/sample-submission?phase=1 成功, 課程網站 POST /api/auth/login：Email／密碼與同源 Origin／Referer, 使用者指定curl -k對照：原IP仍HTTP503，proxy上游TLS失敗；不持久化insecure, SOURCES：規範、團隊與官方來源索引, 網站 ZIP hash 與既有 DATA_AUDIT 相同；仍無發布／原生日期／shift metadata, fin_pred_data.zip：本次網站下載 hash 與舊版相同，未新增時間證據, gh-fix-ci：實際GitHub Actions PR check除錯, jupyter-notebook：EDA及可重現notebook原型 (+10 more)

### Community 58 - "Phase2每日09:00 UTC+8截止，採最後有效提交 / 官方score=mean((2*prediction-1)*(adj_close-adj_open)/adj_open)"
Cohesion: 0.13
Nodes (12): B/C研究與E00／市場消融已完成；D尚缺歷史證據、正式模型、持久runner及五日演練, GitHub只讀repo根.github/workflows；業務目錄舊example不是啟用排程, D001–D005：盤中目標／09:00、方向乘報酬score、11/16競賽、六序列淨OI與112日期差, 按預測日期 walk-forward；同日股票不跨 train/validation, final.pdf（2026-10-24）為正式 final 規範, 04～09取得教師外部資料、驗證候選、50股CSV自動提交並核實有效回執, Phase2每日09:00 UTC+8截止，採最後有效提交, 2026-10-24 final規範優先；競賽11/16～12/24，Phase1 12/24 23:59截止 (+4 more)

### Community 60 - "DECISIONS：有證據accepted、建議proposed、未決／阻擋分流；不是部署宣告 / deep-research源於dev@675d662；80ac804的四架構是設計，後續另行實作與研究比較"
Cohesion: 0.13
Nodes (14): deep-research源於dev@675d662；80ac804的四架構是設計，後續另行實作與研究比較, D030 accepted：新增deep-research，基底dev@675d662，研究金融競賽／四模型／Lauren Tan, D031單採集者／portable catalog方案由D035私人live-data實作，定時運作仍待驗收, D032固定線性／提升樹／TCN／市場引導跨股attention與預註冊預算；80ac804時是藍圖, D034：使用者授權私人live-data保存raw／derived與lag文件；帳密不可入Git, D035：內容hash物件、portable catalog與固定Git revision已實作；實際運作以STATUS核對, D036：R1有24 fits和8產業blocked；另註冊E04 8 fits；R2最終結果以STATUS更新, D037：本會話無排程工具及Kaggle MCP／本人憑證；官方CLI私有bundle不等於遠端kernel (+6 more)

### Community 61 - "PROJECT_GRAPH：官方 Graphify 專案圖與重建方法 / 圖新增金融競賽／期刊企業研究、四架構藍圖、資料共享與Lauren Tan工作流"
Cohesion: 0.18
Nodes (12): 本代理 usage 未提供，token／成本未知；零 placeholder 不是零消耗, 圖需實際覆蓋sharing／derived lineage、原生return／FX研究、TCN／attention、Notebook與hosted pre-POST狀態, 圖新增金融競賽／期刊企業研究、四架構藍圖、資料共享與Lauren Tan工作流, 圖中的設計或實作節點不等於正式模型批准、排程每天成功或真實回執, PROJECT_GRAPH：官方 Graphify 專案圖與重建方法, 僅刪完全相同 JSON 重複邊；不同來源/context/relation 證據保留, 互動 HTML、完整 JSON、社群報告、semantic 與 health 稽核, 先完成文件＋AST 圖，再開始 M0 實作 (+4 more)

### Community 62 - "collect_lecture_corpus.py / main()"
Cohesion: 0.22
Nodes (7): collect_one(), fetch_pdf(), lecture_urls(), LectureLinks, main(), private_write(), validate_output_root()

### Community 63 - "os / build_market_features.py"
Cohesion: 0.23
Nodes (7): code_manifest(), load_json(), main(), stage(), unique_object(), main(), read_prediction_file()

### Community 65 - "CourseSubmissionClient / Session"
Cohesion: 0.22
Nodes (4): post_predictions(), CourseSubmissionClient, Session, TransportTests

### Community 66 - "FEATURE_SPEC：市場轉換與 point-in-time 對齊 / s_j(t) 為 cutoff 前最新可用來源 session"
Cohesion: 0.27
Nodes (9): 必要驗證涵蓋未來／晚發布、休市、缺原生日期、零分母、負OI、重複鍵、修訂與跨時區, 教師 global_data.csv：六序列已下載稽核，時間與原生日期接入仍 blocked, s_j(t) 為 cutoff 前最新可用來源 session, FEATURE_SPEC：市場轉換與 point-in-time 對齊, 第一版需市場表、公式、時間來源、缺值、版本與防洩漏測試, M0 八欄已實作與合成驗證；教師資料正式訓練表仍 blocked, 原生單 session 報酬 (P_s−P_prev)/P_prev, 三種索引：台股目標 t、來源 session s、cutoff(t) (+1 more)

### Community 67 - "金融競賽與agent工作流深度研究 / 深度研究範圍與證據規則"
Cohesion: 0.17
Nodes (9): deep-research研究分支：由dev@675d662建立，Git名稱不含空白, 金融競賽與agent工作流深度研究, 共用自動資料、金融競賽與四架構、Lauren Tan agent工作流, citation-management腳本不可讀，實際使用公開書目來源與專案離線檢查, 早期文獻代理限額失敗後主代理接手；後期恢復獨立子代理查核, 深度研究範圍與證據規則, 支撐性來源保存URL、實際時間、SHA256、閱讀範圍與原文位置, 來源優先：官方規則與主辦者、作者／出版者原文、具名工程師 (+1 more)

### Community 70 - "市場消融同配置score皆低E00與全0；E03雖高E01仍未過個股基準 / E01–E03均低於同鍵全0與E00-LW，沒有市場擴充增益或模型升級證據"
Cohesion: 0.33
Nodes (9): E00個股七欄對照E01＋M0已執行，E01相同linear加權配置下降, E00-LW相同配置基準：linear abs(r)加權分類score0.000482249960, E01個股＋M0：score0.000356441216，比E00-LW下降0.000125808745, E02個股＋M0＋SOX：score0.000249487724，比E01下降0.000106953492, E03個股＋M0＋TSM ADR／NVDA：score0.000388784462，較E01略升但仍低E00-LW, E00–E03逐鍵相等驗證，12140共同排序validation鍵hash c69c1fa7…, E01–E03固定linear／abs(r)加權／seed42／原四季與82674完成鍵，12140 validation逐鍵相同且不重看holdout, 四季消融score完整保留，所有配置Q3負分；整體結論依共同鍵合併score (+1 more)

### Community 71 - "研究導航：可追溯代理查核筆記、結果限制與最新狀態入口 / E00 mlp／classification：2025合併score 0.000854985259"
Cohesion: 0.20
Nodes (8): E00四家族×三目標×四季度：48次fit＋12筆baseline，validation winner為MLP普通分類, 固定E00 MLP winner後只評一次2026年1–5月4750鍵：0.001275711605低於全0的0.001549845039, MLP80iter未收斂原警告保留，未依holdout再調參, 2025Q1–Q4只fit更早資料，驗證共12140鍵，四季2750／3050／3242／3098；seed42, 研究導航：可追溯代理查核筆記、結果限制與最新狀態入口, 研究筆記已由代理查核，尚無人類投稿審閱簽核；STATUS才是最新整合狀態, E00 2025全0／train-majority score0.000447093446，全1為相反數, E00 mlp／classification：2025合併score 0.000854985259

### Community 74 - "課程報告與Phase1交付骨架 / 另登錄E04 FX／yield 8 fits未勝F0及全0；不替代blocked F3"
Cohesion: 0.20
Nodes (10): 課程報告與Phase1交付骨架, 另登錄E04 FX／yield 8 fits未勝F0及全0；不替代blocked F3, 既有E00實跑線性、HistGradientBoosting、MLP、GRU，研究狀態, R1中F2 Ridge在已看過2025驗證期較高，不代表正式模型效果, 最終報告只能填入已實際驗證成果並由人工確認規範與頁數, E01至E03在固定線性加權配置未勝E00；結果不能概括全部訊號, Phase1須50股×84官方日期，不能以已知label回填預測, 此文件是報告骨架，並未提交或完成七頁PDF (+2 more)

### Community 75 - "parse_chart_history() / MarketHistoryTests"
Cohesion: 0.27
Nodes (4): parse_chart_history(), MarketHistoryTests, payload(), Session

### Community 77 - "test_inference.py / fixture()"
Cohesion: 0.42
Nodes (3): fixture(), future_rows(), InferenceTests

### Community 78 - "Kaggle四模型研究與可重跑Notebook / 同一Notebook比較Ridge、HistGradientBoosting、因果TCN與市場引導跨股attention"
Cohesion: 0.22
Nodes (9): Kaggle四模型研究與可重跑Notebook, 同一Notebook比較Ridge、HistGradientBoosting、因果TCN與市場引導跨股attention, 資料／程式bytes與SHA固定，kernel pin manifest以偵測dataset latest漂移, 選到validation第一名不等於正式模型，仍需歷史可用性與未見資料, Kaggle排隊、runtime與額度不保證09:00前完成，不能作唯一每日提交執行器, 目前沒有Kaggle MCP／使用者token，尚無遠端登入、資料上傳或kernel執行證據, Notebook demo／compare／report；demo是合成smoke、report不重訓, 可審查離線bundle分開50股完整features與labels，私人kernel、CPU、無網路 (+1 more)

### Community 79 - "DATA_SOURCES：候選來源與待核實限制 / 來源接入需歷史、時區、發布依據、授權與日期抽查"
Cohesion: 0.39
Nodes (8): DATA_SOURCES：候選來源與待核實限制, FinMind Free：逐資料集核對權限；禁止原始資料再散布, 已有Cboe／TWSE／FRED兩新增序列raw adapters；實際覆蓋與API紀錄見API_INVENTORY，時間查證仍必要, GDELT：新聞去重、公司辨識、發布與收錄時間, 來源接入需歷史、時區、發布依據、授權與日期抽查, TAIFEX 日夜盤與交易歸屬日必須分開, TWSE 有歷史命名端點；2020 完整回補未證實, TWSE／TAIFEX／FinMind／Nasdaq／Cboe 官方來源

### Community 81 - "API_INVENTORY：既有同學API清單、4官方raw adapters及額外市場序列；raw成功與歷史可用分開 / 四個官方來源正常TLS實下載；保留缺值日期，published_at／available_at未知，raw成功不是歷史vintage／完整原生日曆證明"
Cohesion: 0.48
Nodes (7): Cboe VIX官方CSV實得9302列，1990-01-02～2026-10-26；指數點水準／差分，非持有VIX報酬, 同學API紀錄已找回TWSE／TAIFEX／FinMind／MIS／GDELT；token存在與權限不假設，SOX／ADR／NVDA接入待驗證, API_INVENTORY：既有同學API清單、4官方raw adapters及額外市場序列；raw成功與歷史可用分開, 新增FRED DEXTAUS：11235列、727缺值，1983起；一美元兌台幣，紐約中午買入匯率，非台北收盤, 新增FRED DGS10：16909列、721缺值，1962起；年率百分比，變化100×百分比差為bp, 四個官方來源正常TLS實下載；保留缺值日期，published_at／available_at未知，raw成功不是歷史vintage／完整原生日曆證明, TWSE MI_5MINS_HIST實得當月15列10/01～10/22；非已核實任意歷史回補，原生日曆待查

### Community 83 - "主代理整合非重疊分工、證據、記憶與Graphify語意刷新 / adapter依賴A的schema／快照與B的時間證據；未齊先交parser及blocked報告"
Cohesion: 0.60
Nodes (5): 歷史分工A：取得及快照，保留Live群組狀態與逐欄歧義, 歷史分工B：逐來源date／shift／時區／發布修訂與完整原生日曆證據, 歷史分工C：schema與時間證據驅動normalized adapter及M0，未知語意fail closed, 歷史分工D：獨立cutoff、假日、修訂、缺值與全集反例驗證, 主代理整合非重疊分工、證據、記憶與Graphify語意刷新

### Community 84 - "documented歷史模式要求vintage核實；strict拒絕未核實假設 / Yahoo最新歷史close與provider時間戳不證明歷史發布／vintage"
Cohesion: 0.33
Nodes (5): documented歷史模式要求vintage核實；strict拒絕未核實假設, strict同快照實跑exit2、blocked報告且不產生正式市場CSV, Yahoo八系列真實快照；正常TLS、無key、Git外不可變保存, 1655日期研究M0＋SOX／TSM ADR／NVDA已產出，OI仍缺, strict缺證據blocked；research明示日曆與close加2小時假設

### Community 87 - "GRU正式daily approval阻擋：只供今日50列且缺中間日期已核實context，序列不同研究驗證 / GRU只用同股過去與當期輸入，邊界以最早已知向量padding；加更晚日期不能改更早預測"
Cohesion: 0.50
Nodes (3): GRU研究四家族比較完成，但正式daily缺舊模型中間日期context而阻擋approval, 正式模型仍待歷史時間證據、verified訓練／預測表與常駐排程；研究模型不提交競賽, GRU正式daily approval阻擋：只供今日50列且缺中間日期已核實context，序列不同研究驗證

### Community 88 - "Fixed美股欄1505/1505匹配前一global列，僅1418/1506匹配前一US session / Fixed IXIC／GSPC／VIX各1505/1505匹配前一教師global列日期close"
Cohesion: 0.50
Nodes (3): Fixed美股欄1505/1505匹配前一global列，僅1418/1506匹配前一US session, Fixed長假落後多session，2020-01-30匹配2020-01-17, Fixed IXIC／GSPC／VIX各1505/1505匹配前一教師global列日期close

### Community 95 - "E00共82674完成Top50鍵、七個前觀測列特徵；非保證相鄰native session，亦非PIT／投資淨利 / Fixed＋凍結Live：Top50完成82674股票日期鍵，50個10/23 pending另列排除"
Cohesion: 0.67
Nodes (3): Fixed＋凍結Live：Top50完成82674股票日期鍵，50個10/23 pending另列排除, E00共82674完成Top50鍵、七個前觀測列特徵；非保證相鄰native session，亦非PIT／投資淨利, E00研究推論CLI對最新完整日50檔輸出0/1，production_eligible=false且未上傳競賽

## Knowledge Gaps
- **333 isolated node(s):** `schema_version`, `timezone`, `feature_cutoff_local`, `availability_status`, `method` (+328 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 701 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **38 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GitHub-hosted每日同步與模型流程：公開設定／完整採集和還原已驗，真正定時／正式提交待驗` connect `GitHub-hosted每日同步與模型流程：公開設定／完整採集和還原已驗，真正定時／正式提交待驗 / 本地completion.json只綁先前已fsync bytes，SIGKILL可留候選標記，不能單獨證明完成／雲端準時` to `STATUS：公開設定與完整採集已驗證；研究／正式模型／排程與回執分開驗收 / 41593199735為collected、16 acquired、failures=[]、features exported，資料revision c3f36239c699a1ab2ecafb17eb68eaff13c8fb9f`?**
  _High betweenness centrality (0.001) - this node is a cross-community bridge._
- **What connects `schema_version`, `timezone`, `feature_cutoff_local` to the rest of the system?**
  _333 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `sharing.py / re` be split into smaller, more focused modules?**
  _Cohesion score 0.07723855092276145 - nodes in this community are weakly interconnected._
- **Why does `run_stage()` connect `hashlib / daily.py` to `CourseSubmissionClient / Session`, `submission/course.py / SubmissionError`, `ingestion/course.py / snapshots.py`, `daily_tables.py / prepare_prediction_table()`, `os / build_market_features.py`?**
  _High betweenness centrality (0.001) - this node is a cross-community bridge._
- **Should `基石：16講研究筆記 / 技法：16講研究筆記` be split into smaller, more focused modules?**
  _Cohesion score 0.07099099099099099 - nodes in this community are weakly interconnected._
- **Why does `STATUS：公開設定與完整採集已驗證；研究／正式模型／排程與回執分開驗收` connect `STATUS：公開設定與完整採集已驗證；研究／正式模型／排程與回執分開驗收 / 41593199735為collected、16 acquired、failures=[]、features exported，資料revision c3f36239c699a1ab2ecafb17eb68eaff13c8fb9f` to `R2逐鍵評分與可信模型／前處理重播一致；R1／E04有固定共同12140鍵驗證 / submit_predictions CLI預設dry run，--submit才POST；同一開檔bytes及fstat mtime綁版本`, `11/03進度報告：設定與16來源採集已通過，正式每日模型／提交未完成 / 617a09df的CI41594631696成功；Py3.12共326通過、Py3.10共322含3skip，Ruff／shell通過`, `ARCHITECTURE：模組化Python批次ML生命週期、責任分層與交接契約 / live-data 每日衍生資料與 lag 定義`, `GitHub-hosted每日同步與模型流程：公開設定／完整採集和還原已驗，真正定時／正式提交待驗 / 本地completion.json只綁先前已fsync bytes，SIGKILL可留候選標記，不能單獨證明完成／雲端準時`, `全量驗收清單：設定／完整採集已完成，首個schedule及正式每日提交仍待驗 / 初始正式模型／歷史vintage缺證據；今日取得不能補舊歷史，不改研究模型為verified／approved`, `DECISIONS：有證據accepted、建議proposed、未決／阻擋分流；不是部署宣告 / deep-research源於dev@675d662；80ac804的四架構是設計，後續另行實作與研究比較`?**
  _High betweenness centrality (0.001) - this node is a cross-community bridge._
- **Should `STATUS：公開設定與完整採集已驗證；研究／正式模型／排程與回執分開驗收 / 41593199735為collected、16 acquired、failures=[]、features exported，資料revision c3f36239c699a1ab2ecafb17eb68eaff13c8fb9f` be split into smaller, more focused modules?**
  _Cohesion score 0.03379416282642089 - nodes in this community are weakly interconnected._
## Build provenance

Built using graphifyy 0.9.95: AST extraction plus host-agent document extraction.
Clustering uses Graphify's installed NetworkX Louvain fallback.
Token usage/cost is **unavailable**, not zero: this host's agent API does not expose usage metadata. The tool's zero placeholders above are not measured usage.
`graphify-out/` is in the working tree; only shareable artifacts are retained by Git.
The graph is a map of documented plans and code, not evidence of model performance.

Normalization removed 32 exact duplicate edges and added 58 verified external import stubs using Graphify's own API. Added 1 external package nodes only for dependencies explicitly declared in pyproject.toml. Distinct evidence is retained. The raw extractor diagnostics and normalization audit are in `raw_health.json` and `normalization.json`. Repeated YAML list-field keys are a structural abstraction; individual market meanings are represented by the document extraction.

Clustering analyzes simple directed connectivity, so same-endpoint relations are counted as topology collapse in the diagnostic below. The JSON and HTML exports retain **all distinct parallel evidence edges** via Graphify's `original_links` export API; this count is not export evidence loss.

[graphify] MultiDiGraph edge-collapse diagnostic
input: <in-memory>
input_stage: provided JSON (normal graph.json is post-build)
effective_directed: <direct-call>
nodes: 2268
unverified_code_nodes: 0
raw_edges: 5492
valid_candidate_edges: 5492
missing_endpoint_edges: 0
dangling_endpoint_edges: 0
external_reference_edges: 0
self_loop_edges: 2
exact_duplicate_edges: 0
directed_unique_endpoint_pairs: 5349
directed_same_endpoint_collapsed_edges: 143
undirected_unique_endpoint_pairs: 5346
undirected_same_endpoint_collapsed_edges: 146
same_endpoint_group_count: 120
relation_variant_groups: 44
source_file_variant_groups: 0
source_location_variant_groups: 74
context_variant_groups: 2
post_build_graph_type: DiGraph
post_build_edges: 5349
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
  - docs_deep_research_financial_methods_document -> docs_deep_research_sources_document edges=11 relations=['references'] locations=['Markdown link at line 17', 'Markdown link at line 25', 'Markdown link at line 29', 'Markdown link at line 3', 'Markdown link at line 31', 'Markdown link at line 35', 'Markdown link at line 39', 'Markdown link at line 43', 'Markdown link at line 47', 'Markdown link at line 51', '文件Markdown連結'] contexts=['']
  - docs_deep_research_competitions_document -> docs_deep_research_sources_document edges=7 relations=['references'] locations=['Markdown link at line 27', 'Markdown link at line 29', 'Markdown link at line 3', 'Markdown link at line 33', 'Markdown link at line 57', 'Markdown link at line 9', '文件Markdown連結'] contexts=['']
  - docs_deep_research_agent_workflow_document -> docs_deep_research_sources_document edges=7 relations=['references'] locations=['Markdown link at line 11', 'Markdown link at line 26', 'Markdown link at line 30', 'Markdown link at line 31', 'Markdown link at line 32', 'Markdown link at line 5', '文件Markdown連結'] contexts=['']
  - docs_deep_research_data_automation_document -> docs_deep_research_sources_document edges=5 relations=['references'] locations=['Markdown link at line 19', 'Markdown link at line 45', 'Markdown link at line 80', 'Markdown link at line 82', '文件Markdown連結'] contexts=['']
  - docs_deep_research_model_architectures_document -> docs_deep_research_sources_document edges=3 relations=['references'] locations=['Markdown link at line 33', 'Markdown link at line 37', '文件Markdown連結'] contexts=['']
note: normal graph.json is post-build; raw producer loss must be measured earlier.

## Reviewed semantic retirements

Graphify’s semantic-retirement guard requires an explicit reviewed rebuild. After complete source rereading and a private backup, this audited rebuild retired exactly 35 stale or superseded semantic nodes listed with individual reasons in normalization.json. Current content, complete source coverage and every distinct current evidence edge are preserved.

## 2026-11-03 semantic refresh audit

Two extraction subagents completely reread the eight changed documents (679 lines total); 33 unchanged document extractions were reused. Source SHA256 and EOF coverage were checked before merging. Semantic output contains 1,074 nodes and 1,877 evidence relations. Thirty-five superseded node IDs were explicitly reviewed and retired. Two old budget references were retargeted to the existing frozen-budget node in MODEL_ARCHITECTURES.md after checking its line 65; they were not changed into claims about actual fit counts. The complete edge adjustment records are in normalization.json. Agent token usage is unavailable; numeric zeros in schema placeholders are not measured usage.
