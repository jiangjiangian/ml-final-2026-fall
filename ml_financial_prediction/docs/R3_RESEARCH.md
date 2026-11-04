# R3 研究計畫與實驗紀錄

狀態：**計畫已核准（2026-11-04），執行中**。建立：2026-11-04（Asia/Taipei）。
換 session 或 context 壓縮後，先讀本檔，再依「下一步」繼續。

## 0. 開始前核對（有來源才寫；查不到標「未知」）

| 項目 | 結果 | 來源 |
|---|---|---|
| Phase 1 目標 | 50 股 × 84 日，2026-06-01～09-30（6 月 21、7 月 22、8 月 21、9 月 20 日），全部在資料分支範圍內，不需延伸資料 | 官方模板 SHA256 `2081e92b…3f28`（live-data `objects/`），首欄有 UTF-8 BOM |
| Phase 1 排行榜 | 取隊伍所有已接受版本中的**最高分**；N＝4200，final.pdf 沒有描述公開／私人切分 | final.pdf p.2（SHA256 `e102f4c2…4810`，2026-11-04 重新下載核對） |
| Phase 1 配額 | 網站有每日 user／team 上傳配額（`uploadQuota.phase1`），**數值未知**（需登入，帳密只在 Actions Secrets） | `src/finpred/submission/phase1_submit.py` |
| Phase 1 已提交 | 已提交 1 次並核對回執：0.000968489142（R2 TCN M3-2 單次 fit，標籤 < 6/1） | live-data `catalog/phase1-result.json` |
| 助教基準 | 未知 | — |
| 配分 | 總 1920：Phase 1 120（超過助教基準即滿分）、Phase 2 競賽 360（依總分排名）、報告 1440（最重要，首要標準是可重現性） | final.pdf p.2、p.4 |
| Phase 2 競賽日 | 11/16–20、11/23–27、11/30–12/4、12/7–11、12/14–18、12/21–24，共 29 天；每日 09:00 截止；未交由系統自動全猜 0 | final.pdf p.3–4 |
| 方法要求 | 任何演算法都可以，**不要求深度學習**；報告至少比較 4 種可重現 approach，選 1 個並說明優缺點，最多 7 頁 | final.pdf p.3–4 |
| 外部資料 | 公開且可合理重現即可；付費或私人資料除非分享給全班，否則不能用 | final.pdf p.1 |
| 資料使用限制 | **NTU 資料保密暨使用限制同意書（115-1，林軒田／林守德課程）第三條：除課程明確允許的工具外，不得把資料或可還原資料的衍生內容上傳到 GitHub、Kaggle、公開雲端、生成式 AI 服務或 ML 平台。** 第四條涵蓋切分、清理、標籤等衍生檔 | 使用者 Google Drive 的 `Financial_Prediction_Data_NDA_115-1.pdf`（2026html@gmail.com 分享） |
| 守德老師簡報 | `Financial_Prediction_with_SDAI_Motivation.pdf` 不在公開課程頁、Drive 搜尋也找不到；本 session **未讀到原檔**。repo 先前摘要：pp.4–6 目標與資料、p.11 global 欄位與 TX_OI、p.14 可重現與資料分享、pp.20–21 洩漏與 walk-forward | `docs/SOURCES.md` |
| Kaggle GPU 配額 | 未知：Kaggle MCP 回傳 `Unauthenticated` | 2026-11-04 `get_accelerator_quota` |
| 本機運算 | 4 CPU、15 GB RAM；PyPI 可連線（套件尚未安裝） | 2026-11-04 實測 |

### 會改變研究方向的兩個發現

1. **Phase 1 的答案就在老師的訓練資料裡**（Training ZIP 到 8/31，Live 含 9 月），而排行榜取最佳版本、沒有隱藏切分。誰願意用答案就能拿到接近滿分的成績。誠實的方法**無法保證第一名**；滿分條件只是「超過助教基準」。
2. **雜訊很大**（只用 2020–2024 訓練期資料估計）：50 股平均盤中報酬的日標準差 0.0078。只賭大盤方向的策略，一年（250 日）平均分數的標準誤約 0.0005，29 個競賽日約 0.0014。過去在 2025 的差距（TCN 0.000869、Ridge 0.000817、全 0 0.000447）都在約 1 個標準誤內，**還不能說誰比較好**。個股相對部分（扣掉當日市場平均）的每日雜訊約只有市場部分的 1/3，比較容易驗證出真增益。

## 1. 驗證設計（待確認）

| 區段 | 期間 | 用途 |
|---|---|---|
| 暖身訓練 | 2020-01-02～2021-12-31 | 只當訓練資料 |
| 選模（開發）期 | 2022-01～2025-12，逐月測試區塊，expanding window | 所有模型與特徵的比較；2025 曾在 R1／R2 探索過，另外單獨列出 |
| 已用保留期 | 2026-01～05 | **只當訓練資料**，不再拿來選模型 |
| Phase 1 目標期 | 2026-06-01～09-30 | Phase 1 模型不訓練、不評分、不選模 |
| 最終保留期 | 2026-10-01～11-13（約 30 交易日，Live 資料） | 研究期間不看；最後只對 1～2 個方案＋基準用一次 |
| Phase 2 前瞻 | 11/04 起每日盤前 shadow 預測 | 真正的樣本外紀錄 |

- 按日期切，train 結束到 test 開始留 **5 個交易日 embargo**；同一天的股票不跨 fold。
- 篩選階段每月重訓（成本較低）；入圍方案改用**每週重訓**（Phase 2 預定頻率）重跑，並加跑「訓練一次、預測 4 個月」測衰退（對應 Phase 1）。
- 報告：整體分數、逐月分數、最差月份、逐年趨勢；與基準的**成對差**用依日期的 block bootstrap（區塊 5 日、2000 次）算 95% 信賴區間。
- 前處理只在 train fold fit；固定 seed；最終多 seed／多模型平均。
- 最終保留期 SE 約 0.0013，只能檢查「沒有崩壞」，不能區分方案；這點會在模型卡寫明。

## 2. 基準（每個新結果都在同一組鍵上並列）

全 0、全 1、前一日同股方向、Ridge（panel 50 欄）、LightGBM（panel 50 欄、固定小參數）。另在 2025 四季 fold 重現既有參考：TCN 0.000868847322、R1 F2 Ridge 0.000816754184、全 0 0.000447093446，確認評分框架一致。

## 3. 可驗證假設（每條附來源；都只用每天 09:00 前拿得到的老師 Live ZIP＋yfinance）

| ID | 假設 | 特徵 | 來源 |
|---|---|---|---|
| H1 | 台股盤中報酬平均為負（隔夜／盤中拉鋸），所以預設猜跌有正期望；模型價值在於何時翻成猜漲 | 無（基準與截距） | Lou, Polk & Skouras (2019), JFE 134(1):192–213, doi:10.1016/j.jfineco.2019.03.011；本資料 2020–2024 有 4/5 年平均為負 |
| H2 | 最近一晚美股漲跌 → 台股開盤跳空 → 盤中反轉；panel 的 lag2 把第 1、2 晚混在一起而互相抵銷 | 最近 1 個 session 的 SOX／NVDA／TSM／指數報酬，以及個股 beta × 美股報酬 | Tsai, Lih & Ko (2012), Physica A 391(24):6497–6505（TWSE 日間與隔夜報酬符號負相關）；資料分支 `data-decisions.md`：GSPC 最近一晚對當日盤中 −0.130、第 2 晚 +0.096 |
| H3 | 個股的盤中／隔夜報酬各自有持續性 | 前 1／5／20 日盤中報酬、隔夜跳空（老師個股檔前移一列） | Lou et al. (2019)；Heston, Korajczyk & Sadka (2010), JF 65(4):1369–1407 |
| H4 | 橫斷面標準化特徵（當日排名／z-score）比原始值穩定 | Alpha158 類價量因子的 CSRank | Microsoft Qlib Alpha158／benchmarks（github.com/microsoft/qlib） |
| H5 | GBDT 是表格資料的主力；冠軍方案靠 GBDT＋序列 NN 集成與定期重訓 | LightGBM／CatBoost／XGBoost；GRU／TCN | ML Contests 2025 報告（mlcontests.com）；Optiver Trading at the Close 第 1 名：CatBoost＋GRU＋Transformer 加權集成、共用約 300 特徵、線上重訓（Kaggle discussion 487446 的二手整理：zhuanlan.zhihu.com/p/689864294、docswell 簡報） |
| H6 | 目標對齊評分：回歸 r 後取正負，或以 \|r\| 加權分類，優於一般分類 | loss 設計 | 本專案 `FINANCIAL_METHODS.md` 推導 |
| H7 | 星期、長假後第一天等日曆效應 | 星期、距前一交易日天數 | 待驗證（低先驗） |
| H8 | 時間序列基礎模型零樣本輸出可當特徵 | Chronos-Bolt／TimesFM 對市場序列的預測 | 低先驗；必須證明有增益才保留 |

## 4. 實驗順序與嘗試預算

R3 全部最多 **80 組設定**（每組＝一次完整 walk-forward），失敗也計數。

| 階段 | 內容 | 運算 |
|---|---|---|
| R3-0 | 評分框架、walk-forward＋embargo、bootstrap、嘗試紀錄；5 個基準；2025 重現檢查 | CPU |
| R3-1 | 分數拆解：市場擇時 vs 個股相對，看技能在哪 | CPU |
| R3-2 | H1–H4、H7 特徵消融（固定 LightGBM 與 Ridge），每組對 panel 基準算成對 CI | CPU |
| R3-3 | 模型家族：Ridge／logistic、LightGBM、CatBoost、XGBoost、AutoGluon（時間順序 tuning data，不用隨機 bagging）、MLP、小型 TCN／GRU；Optuna 只在 train 內部的時間切分調參，每家族上限 50 trials | CPU；NN 先用季重訓篩選 |
| R3-4 | H8 基礎模型特徵（低優先） | CPU |
| R3-5 | 入圍方案：每週重訓模擬、衰退、多 seed、集成；yfinance 失敗時的分數下降；重訓與推論時間 | CPU |
| R3-6 | 選 1～2 個方案＋備援 → 最終保留期（需同意）→ Phase 1 CSV（提交前需同意）→ 模型卡 | CPU |

時程：Phase 2 競賽 11/16 開始，所以 R3-0～R3-5 目標 11/12 前完成，11/13 用保留期定案，11/15 前部署。

## 5. Phase 2 可用性（硬條件）

- 特徵只用老師 Live ZIP＋yfinance；日線收盤時間依資料分支 `schema.json` 的 timing 紀錄；不用當日 ^TWII、^KS11、TX_OI 與任何 label_ 欄。
- 07:17 開始重訓、08:11 推論；LightGBM／Ridge 在 CPU 數分鐘內完成。NN 若需要，改成離線每週訓練、每日固定模型推論。
- 模型檔沿用 `predict.py` 的 feature_columns／feature_version／fit_cutoff 檢查；不一致就停止。
- 備援：只用老師資料的 Ridge 或小型 GBDT（須先勝過全 0）。切換規則草案：yfinance 缺值超過門檻 → 備援；主模型重訓失敗 → 沿用上週主模型；都失敗 → 全 0（歷史上期望值為正，也等於系統自動提交）。

## 6. Kaggle GPU

使用者確認課程允許後可用 Kaggle（dataset 一律 private）。GPU 只用於多 seed NN 與大量 Optuna，估計總計 10～15 GPU 小時；R3-0～R3-2 只用 CPU。

**2026-11-04 狀態：無法使用。** 本 session 的 Kaggle MCP 每個呼叫回 `Unauthenticated`，`authorize` 在雲端 session 60 秒超時；容器內沒有 Kaggle 憑證；GitHub Actions `kaggle-readiness.yml`（run 41645046599，11/03）因沒有 secrets 跳過探測。容器到 Kaggle API 的網路是通的（`kernels/list` 回 401）。使用者選擇到 claude.ai connectors 重新連接 Kaggle，**之後開新 session 才生效**。新 session 第一步：`get_accelerator_quota` 確認配額，記入本節。

## 7. 使用者決定（2026-11-04）

| 問題 | 決定 |
|---|---|
| 同意書衝突 | 使用者確認課程允許；可用 Kaggle，dataset 一律 private。repo 可見性不由代理更動 |
| Phase 1 目標 | 用誠實、預先登記的方法超過助教基準；主要心力放 Phase 2 與報告 |
| 驗證設計 | 最終保留期 2026-10-01～11-13，只用一次；Phase 1 模型絕不用 6/1–9/30 標籤；Phase 2 正式模型可把 6/1–9/30 當一般歷史訓練，但選模永不用 |
| 計畫 | 核准，從 R3-0 開始 |

## 7b. 老師技術指標的時間性核對（2026-11-04）

用 2330、2881、1101 的還原收盤／高低價重算，老師欄位都只用到當列與更早的價格（中位絕對誤差 0）：
`SMA`＝30 日簡單均線；`BBANDS_*`＝5 日均線 ± 2σ（母體標準差），所以收盤一定在帶內、`bb_pos` 落在 [0,1]；`RSI`、`ATR`＝Wilder 14 日；`MACD`＝柱狀值（EMA12−EMA26 再減 9 日訊號線）。各指標日變化與次日報酬的相關係數絕對值都 < 0.08。R3 特徵一律再 `shift(1)`，所以沒有前視。Phase 2 若需要可以自行重算這些指標。

## 7c. R3-3 預先登記（2026-11-04，R3-2 尚未全部完成時寫下）

**基底特徵集 S\* 的選法**：取 R3-2 中開發期分數最高的 LightGBM 特徵集；若它對 `A_hist`（panel＋stock_hist，最簡單的有效集合）的成對差 95% CI 含 0，就用 `A_hist`。

**R3-3 設定（皆在 S\* 上，其他參數同 R3-2）**：
1. LightGBM `weighted_classification`（|r| 加權）
2. LightGBM `classification`
3. CatBoost 回歸（depth 4、300 iterations、learning_rate 0.05、l2 3）
4. XGBoost 回歸（max_depth 4、300 trees、learning_rate 0.03、min_child_weight 50、subsample／colsample 0.8）
5. LightGBM 回歸，只用 Top50 訓練
6. 兩頭模型 H9：市場頭 Ridge（alpha 10，用同日相同的市場欄）＋個股頭 LightGBM（對去市場平均的報酬）
7. Optuna：LightGBM 30 trials，只在 2022–2023（季重訓）評分；8. 用最佳參數跑完整開發期一次，2024–2025 為調參外的確認
9. MLP（PyTorch CPU，3 seeds）
10. 等權集成：最佳 GBDT＋最佳 Ridge 的標準化 decision 平均（用已存預測，不重訓）

## 8. 嘗試紀錄

機器可讀完整紀錄：`docs/r3/attempts.jsonl`（格式見 `docs/r3/README.md`）。下表為摘要；分數為 2022-01～2025-12 逐月 walk-forward（5 日 embargo、訓練 100 股、計分 Top50 共 48,475 鍵），全部經 `official_score.py` 重算一致。CI＝依日期 block bootstrap（5 日、2000 次）95% 信賴區間。

### R3-0 基準（2026-11-04）

| # | 設定 | 分數 [95% CI] | 市場擇時／個股相對 | 2022–24／2025 | 最差月 | 正分月 |
|---|---|---|---|---|---|---|
| 1 | 全 0 | 0.000279 [−0.000150, 0.000681] | 0.000279／0 | 0.000222／0.000447 | 2022-11 −0.00371 | 30/48 |
| 2 | 全 1 | −0.000279 [−0.000681, 0.000150] | −0.000279／0 | −0.000222／−0.000447 | 2022-06 −0.00394 | 18/48 |
| 3 | 前一日同股方向 | −0.000004 [−0.000298, 0.000273] | −0.000067／0.000063 | 0.000084／−0.000268 | 2025-04 −0.00368 | 27/48 |
| 4 | Ridge（panel 50 欄，alpha 1） | 0.000510 [0.000124, 0.000916] | 0.000499／0.000010 | 0.000366／0.000939 | 2024-08 −0.00370 | 27/48 |
| 5 | LightGBM（panel 50 欄，固定小參數） | 0.000430 [0.000010, 0.000828] | 0.000244／0.000187 | 0.000431／0.000427 | 2024-08 −0.00432 | 33/48 |

成對差（同鍵）：Ridge−全 0＝+0.000231 [−0.000274, 0.000747]；LightGBM−全 0＝+0.000151 [−0.000386, 0.000648]；Ridge−LightGBM＝+0.000079 [−0.000364, 0.000558]。

結論：
- 2025 全 0＝0.000447093446 與先前紀錄逐位一致（同 12,140 鍵），評分框架對帳通過。
- Ridge 與 LightGBM 的 CI 都不含 0，但**對全 0 的成對差都還在雜訊內**；兩者 2024 年都約為 0（同年全 0＝0.000338）。
- Ridge 幾乎全靠市場擇時；LightGBM 約 44% 來自個股相對部分。市場擇時的成對差雜訊很大，個股相對部分是較可能驗證出穩定增益的方向。

## 下一步

R3-2：12 組預先登記的特徵假設（`configs/research/r3/r32_*.json`，固定 LightGBM 與 Ridge）執行中；harness 獨立審查中。
