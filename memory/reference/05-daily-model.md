# 每天交件的模型

`configs/config.yaml` 的 `daily_model` 選模型（名字和檔案的對照在 `src/models/__init__.py`，選和換備援的程式在 `src/pipeline/step3_train_predict.py`）：`kind` 是主模型，`fallback` 是它算不出來時照順序改用的備援。改完 push，oop 下一次執行就生效。2026-11-12 早上起用 `persist`；同一天晚上使用者決定換成 `rank_ensemble`。2026-11-15 晚上使用者決定換成 `c2v2d`，備援是 `[c2, rank_ensemble, persist, online_lr]`，11-16 07:10 起生效；12-06 再看要不要改成 `c2`。決定的經過和驗證在 `memory/context/02-pipeline.md` 的「每天交件的模型」。

## c2v2d：排名集成加上大盤方向的傾斜（現在用的）

`src/models/m4_c2_tilt.py`，組員的 C2（`c2_tilt_backtest.ipynb`），Kaggle notebook 44 照它重做過。每天先算 `rank_ensemble` 的三個模型，再看「今天 50 檔平均會不會漲」的機率 p，換一些高 β 或低 β 的股票（β 是這檔跟著大盤動的程度）：

1. combined：ridge、kernel ridge、LightGBM 各自在 50 檔裡的名次 − 0.5，取平均。
2. β̃：每檔過去 120 個有答案的交易日，盤中報酬對 100 檔平均盤中報酬的斜率，換成 50 檔裡的名次 − 0.5。
3. p：邏輯迴歸，用 20 個台北 07:10 前就有的狀態：前一夜美股和 VIX、台股和韓股前一天的報酬、台指期未平倉的變化、50 檔前幾天的盤中報酬和跳空、長表的 9 個 `*_ret_lag1`（台指期夜盤、費半、台積電 ADR、道瓊、美元台幣、美債、油、金等前一天的報酬）。每月重訓一次，訓練資料從 2020-03 起累積。
4. 分數 = combined + 2·(2p − 1)·β̃，前 25 名猜 1。猜漲檔數不變，p 大於 0.5 時高 β 的往前，小於 0.5 時低 β 的往前。p = 0.5 時和 `rank_ensemble` 一模一樣。

沒有用日韓當天的開盤：`kospi_open_gap`、`n225_open_gap` 不能當狀態，程式裡有檢查。韓股只用前一天的收盤。

回測（notebook 44，2025-01-02～2026-10-08）：每天比 `rank_ensemble` 多 +0.000324（t 2.54），`c2`（14 個狀態，沒有長表那 9 欄）多 +0.000285。MT 24 拆開來看：一部分等於「依大盤預測換高低 β」的押注，另外每天約 +0.00018 跟著 p 走，是個股層級的效應。

2021 的確認沒過（Kaggle notebook 42，2021-01-11～12-30 共 239 天）：C2v2d 每天比原版少 0.000228（t −1.11），虧在換高低 β 的那塊。2026-11-15 晚上約 21:55 使用者在特徵組的 session 看過後選維持 C2v2d（特徵組轉述，見 `memory/context/02-pipeline.md`「2026-11-15 晚上換成 C2v2d」）。在正式流程每天重訓的排名上重量（notebook 46c，2025-01-02～2026-10-08 的 428 天）：每天多 +0.000279（t 2.29），和 notebook 44 是同一批日子，只說明換成正式的排名結果不變，不算新的證據。

分數從哪來（Kaggle `rp-37-c2v2d-style-attribution`，2026-11-27）：每天把 50 檔的盤中報酬對 β、動能、反轉、波動、成交金額和產業做迴歸，把分數拆成各風格和剩下的選股。2024-01～2026-10 每天 +0.00130 裡，β 佔 +0.00071（55%），反轉 +0.00015、產業 +0.00012、波動 +0.00008，真正的選股 +0.00024（18%）。也就是說，c2v2d 主要賺「低 β 股盤中比較強」這個風格，2022～2026 每年都是正的；傾斜層多賺的 +0.00029 裡 +0.00024 來自依大盤方向換 β。在大盤波動大的日子縮小低 β 的押注，回測只會少賺，所以不縮。2026-11-17～11-26 虧的 −0.0186 拆開後主要是反轉 −0.0117 和產業 −0.0096，β 是 +0.0077；依當時的波動縮放後，落在回測第 11 百分位。細節在 `memory/projects/22-ml-research-pipeline.md` 的 `RP 37` 結果。

上線前的檢查（2026-11-15，Kaggle `c2-tilt-production-code-check`，用 commit `748db97` 的程式）：

- p：重算 1,177 天，和 notebook 44 最大差 1.5e-12；11 月重訓的係數和組員的一樣（差 ≤ 0.0005）；`tests/test_rank_ensemble.py`、`tests/test_persist_rule.py` 24 個都過。
- 重放 10-12～11-13 的正式流程：每天都是 25 檔猜漲；11-13 的原版選股和那天實際交的 100% 一樣。
- 和組員 Phase 2 的表比：p 只有 11-11、11-12 不一樣。11-11 是 yfinance 在 07:10 之後修正了油和金的收盤（正式流程用的是 07:10 的值），11-12 是組員那天的長表檔沒更新。換的組數和分數也有幾天不一樣，因為組員的原版排名是自己的回測，和正式的 `rank_ensemble` 每天分數差到 0.0027。β 的算法和 notebook 44 逐行一樣。
- 重放 22 天加總：`c2v2d` 0.098、`rank_ensemble` 0.091、`c2` 0.090。只有 22 天，只能參考。

算不出來時改用 `c2`，再不行用 `rank_ensemble`，當天照樣交件：

- 老師 global 表 t 那列沒有美股。美國休市的隔天（下一次是感恩節後的 11-27）大概會這樣，那天 `c2` 也算不出來，會交 `rank_ensemble`。
- t 的狀態缺超過 `max_missing_states`（3）個，例如長表的市場欄沒更新。
- 方向模型的訓練天數不到 250，或 `rank_ensemble` 本身算不出來。

每天的 log 有一行「模型 c2v2d：大盤方向 p = …，傾斜 …，和 rank_ensemble 換了 N 組，狀態缺 N 個，重訓日 …」。每檔的分數在 `scores_<t>.csv`：`base_pred` 是 `rank_ensemble` 的選法，`pred` 是交出去的，另外有 `combined`、`beta_rank`、`p_up`、`tilt`、`score`、`variant`。

## 資料不完整時重交（使用者 2026-11-17）

排程交好之後，`data/submission/complete_<t>.json` 記下那份用的資料完不完整。不完整有兩種：

- 用了備援：模型不是 `daily_model.kind`（現在是 `c2v2d`）。
- 方向模型的狀態有缺：預測表的 `missing_states` 大於 0。yfinance、期交所的序列沒抓到時會這樣，缺的狀態補成訓練期的平均。

不進模型的序列（CNN、VIXTWN、證交所、`stoxx50e`、`kospi` 等）沒抓到，預測不會變，不算不完整。檔案的欄：`model`、`missing_states`、`complete`、`reasons`（不完整的原因）、`site_id`（網站上那份的 id）、`redo`（重做了幾次）等。

不完整時，之後的時段（07:25、07:40…）重爬、重算：

- 還是不完整：不重交，下一個時段再試。
- 補齊了，50 檔的猜法一樣：不重交，紀錄改成完整。
- 補齊了，猜法不一樣：原本的檔改名成 `submission_<t>_first.csv`，新的 `submission_<t>.csv` 取代網站上那份，`scores_<t>.csv`、`shadow_<t>.csv` 跟著重寫。

不重做的情況：網站上那份是組員手動交的、已經重交過一次、08:44 以後、上傳次數用完、有一次送出後還沒核對完。開關是 `configs/config.yaml` 的 `submit.redo_incomplete`，最晚的時間是 `submit.redo_latest`。

美國休市的隔天 `c2v2d` 本來就會換備援（見上一節），那天之後的時段會一直重算到 08:44，不會補齊。

## rank_ensemble：排名集成（第二個備援）

`src/models/m3_rank_ensemble.py`，Kaggle notebook 16 的 `X_price`。每天早上用 t 之前 500 個有答案的交易日重新訓練，約 30 秒：

1. 41 個價量欄（`rank_ensemble.columns`）：老師個股檔每天收盤後算得出的欄退一天，加長表的 `stock_ret_lag1`、`stock_ret_lag2`，和 4 個持續性欄（這檔過去比同伴強多少）。
2. 每一欄換成當天在 100 檔裡的排名（−1～1），沒有值的格子給 0。
3. 目標：(這檔的盤中報酬 − 當天平均) ÷ 當天標準差，也就是同一天裡誰比較強。
4. 三個模型：ridge、Nyström kernel ridge（近似的核方法）、小的 LightGBM，後兩個各用 3 個種子平均。三個預測各自換成 50 檔裡的排名再平均，前 25 名猜 1、後 25 名猜 0。

每天猜漲和猜跌各一半，分數只看 50 檔之間誰強誰弱，不押大盤。回測用官方分數（每天 50 檔的 mean((2·pred − 1)·盤中報酬)），每月重訓一次：

| 期間 | 排名集成 | 持續性規則 |
|---|---|---|
| 2024-01～2026-10 的 11 季，每天平均 | +0.00101（t 6.0，11 季都是正的） | +0.00069 |
| 2022～2023 的 8 季，每天平均 | +0.00080（t 4.9） | +0.00057 |
| Phase 2 的 10-12～11-10，20 天加總 | +0.070 | +0.052 |

集成減持續性規則，同一天的差：11 季每天 +0.00032（95% 區間 +0.00004～+0.00061），2022～2023 每天 +0.00023（區間 −0.00013～+0.00060，含 0）。oop 用這份程式重播 1,175 天，0／1 有 99.45% 的格子和 notebook 一樣。2026-11-12 的紙上預測（沒有交）拿 +0.0206，同一天交的持續性規則是 +0.0116。

算不出來時改用 `persist`，再不行用 `online_lr`，當天照樣交件。log 寫「rank_ensemble 算不出來（原因），改用 persist」。`c2v2d`、`c2` 也用它的三個模型，所以它算不出來時三個一起換。會算不出來的情況：

- 爬蟲記下前一個交易日在老師 Live 整天還沒填（`data/raw/manifest.json`）。只有幾檔沒填時不停，那幾檔 t 那列當成空白。
- 要預測的 50 檔少了，或它們 t 那列空白的格子超過 10%，或有一欄全部空白。
- 有答案的交易日不到 250 天、表裡 t 之前有還沒答案的日子，或模型的預測不是有限的數。
- `src/models/m3_rank_ensemble.py` 不見或載入失敗。

換模型後第一個早上，看 `data/submission/run_<t>.log` 的「模型」那行用了哪個。有「算不出來」就是那天用了備援，流程不會停，要看 log 才知道。

## persist：持續性規則（第三個備援）

`src/models/m2_persist_rule.py`。不用訓練，只讀特徵表的 `label_intraday_return`（盤中報酬，收盤 ÷ 開盤 − 1）：

1. 只看要預測的 50 檔。每個有答案的交易日，e = 這檔的盤中報酬 − 當天 50 檔的平均，也就是這檔那天比同伴強多少。
2. t 的分數 = 這檔股票在 t 之前 120 個有答案的交易日的 e 的平均。
3. 當天分數高的 25 檔猜 1，低的 25 檔猜 0。

回測在 Kaggle notebook 14：670 天每天平均 +0.00069（95% 區間 +0.00040～+0.00101），11 季每季都是正的，最差的一季 +0.00021；同期全猜 0 是 +0.00046。2026-11-12 在 oop 用正式流程的函式重播這 690 天，分數和 notebook 一樣。2026-11-12 是它交件的第一天，網站分數 +0.011575。

兩種情況算不出來，log 寫「persist 算不出來（原因），改用 online_lr」：最新的答案和 t 中間隔超過 3 個交易日，或 50 檔裡有分數的不到 40 檔。設定在 `persist_rule`。

## online_lr：組員的邏輯迴歸（第四個備援）

`src/models/m1_online_lr.py`，2026-11-07～11-11 每天交件用的模型：每週重訓、每天用前一天的答案微調，每天早上重新 fit。特徵是組員的 26 個個股特徵加特徵表的 55 欄（`manifest.json` 的 `model_columns`）。11-09、11-10 它 50 檔全猜 0，分數和網站的 `Always down` 基準一樣（−0.028121、−0.000071）。

`online_lr` 在流程一開始就載入，所有模型的輸入表也是用它的 `load_data` 讀的（`step3_train_predict.load_model_input`），所以這個檔壞掉時整次停下，不會換備援。

## 影子跑：每個模型每天都算，不上傳

使用者 2026-11-16 決定：每天交件之後，`daily_model.shadow` 列的模型（現在是 `c2v2d`、`c2`、`rank_ensemble`、`persist`、`online_lr`，2026-11-20 加 `overnight_up`、`rank_inst`）都預測 t，存檔但不上傳。這樣比的是上線後的真實日子，不是回測。組員已經手動交了的日子也做。

### 檔案

- `data/submission/shadow_<t>.csv`：每檔一列。每個模型兩欄，`pred_<模型>`（0/1）和 `prob_<模型>`（當天名次換成 0～1；`online_lr` 是機率）。`c2`、`c2v2d` 另有 `p_up_<模型>`（大盤方向的機率）。`c2v2d` 再多四欄（2026-11-23 起，N1 影子跑讀）：`ridge_c2v2d`、`kridge_c2v2d`、`lgbm_c2v2d`（三個成員的分數）、`beta_rank_c2v2d`（β 的當天名次 − 0.5）。`overnight_up` 另有四欄，見下面「隔夜大跌全猜漲」；`rank_inst` 另有兩欄，見下面「法人組」。算不出來的模型那幾欄空白，原因在 `run_<t>.log`。
- `data/submission/shadow_scores.csv`：每天每個模型一列。`score` 是官方分數（每格 (2·pred − 1)·盤中報酬的平均），另有 `accuracy`（猜對的比例）、`pred_up`（猜漲的比例）、`cells`（格數）、`source`（答案從哪裡來）。t 當天 16:10 的傍晚打分用老師 Live 的 t 那列先算（`source` 是 `live`）；隔天早上用特徵表的答案再算一次（`features`），兩邊不一樣時 log 有 WARNING。早上算不到的日子留著傍晚的分數。
- `data/submission/site_scores.csv`（2026-11-18 起）：網站上我們那份每天一列。`file`（排程的檔名 `submission_<t>.csv`；組員取的其他檔名一律寫 `other`，不存）、`same_as`（和影子跑哪個模型的 50 檔一樣）、`site_score`（網站給的分數）、`rescored`（用老師 Live 重算，應該和網站一樣；差超過 1e-6 時 log 有 WARNING）、`all_zero`（全猜 0 的分數）、`day_rank`／`day_teams`（當天名次／有分數的隊數）、`total_score`、`total_rank`（累計分數和網站的名次）、`teams`、`all_forced_teams`（每天都是網站強制繳交的隊數）、`self_rank`（扣掉那些隊以後的累計名次）、`read_at`。只存我們這隊，不存任何隊名。

```python
import pandas as pd
s = pd.read_csv("data/submission/shadow_scores.csv")
s.pivot(index="date", columns="model", values="score").cumsum()   # 每個模型的累計分數
```

### 什麼時候算

- 排程自己交的那次：上傳之後，用交件那次的特徵表。交件的模型直接拿交出去的猜法，所以那一欄和 `submission_<t>.csv` 一樣。`rank_ensemble` 從 `c2v2d` 輸出的 `base_pred` 拿，`c2` 和 `c2v2d` 共用同一次訓練，不多花時間。
- 組員先交了：排程先補爬（t 當天還沒爬過才爬），再算，約多 3 分鐘。
- 資料不完整、補齊後重交的那次：用補齊後的特徵表重寫（見「資料不完整時重交」）。
- 一天只算一次，`shadow_<t>.csv` 已經有就跳過（重交時例外）；過了 09:00 不算（之後的資料可能被改過）。
- 打分：t 當天 16:10 的傍晚打分（`src/pipeline/step6_evening_score.py`），老師 Live 還沒填好 t 那列就 20:00 再試。只下載 Live，不上傳、不重建特徵表；Live 寫進 `data/raw/teacher/live/`，組員傍晚就拿得到。
- 傍晚補算（2026-11-23 起）：`rank_inst` 早上沒算出來的日子，16:10 打分前用剛下載的老師 Live 再算一次，寫回 `shadow_<t>.csv`，當天一起打分。其他模型不補算。
- 算不出來只記一行 WARNING，不影響交件。
- 關掉：`shadow: []`。

### 隔夜大跌全猜漲（`overnight_up`，2026-11-23 起）

使用者 2026-11-20 決定加進影子跑。它只能填在 `daily_model.shadow`，填在 `kind` 或 `fallback` 會被擋下，所以不會被交出去。程式在 `src/models/m5_overnight_up.py`，設定在 `configs/config.yaml` 的 `overnight_up`。

- 規則：前一晚台積電 ADR、費城半導體指數、S&P 500 三個「從上一個台股交易日開盤前到 t 開盤前」的漲跌，各除以自己前 250 個台股交易日的標準差，再平均，得到隔夜訊號 O。O 是負的，而且絕對值排進前 250 天的前 10%，t 的 50 檔全猜漲。其他日子和 `rank_ensemble` 一樣。
- 為什麼只影子跑：回測只有一點跡象（Kaggle BT 05、07、09）。測試期 37 個觸發日一共多 0.137，但 39% 來自 2025-04-11 一天，拿掉最好的三天只剩 0.016。要靠之後每天的紀錄才分得出真假，一年大約觸發 15 天。
- 和研究用的版本差在哪：研究用四個成分，多一個美國掛牌的台灣 ETF（EWT），每天的爬蟲沒有抓。三個成分的版本在 2024-01-02～2026-10-08 觸發 43 天，研究的版本 37 天，兩邊都有的 32 天。
- S&P 500 來自老師 global 表。美國或韓國休市的台股交易日老師沒有那一列（約 13% 的日子），那天和隔天 O 只用另外兩個成分。
- `shadow_<t>.csv` 多的四欄：`o_overnight_up`（隔夜訊號 O）、`o_absq_overnight_up`（|O| 在前 250 天的分位，0～1）、`o_parts_overnight_up`（用了幾個成分，2 或 3）、`us_last_bar_overnight_up`（用到的最後一根美股K棒的日期）。同一天每檔都一樣。`pred_overnight_up` 50 檔都是 1 的日子就是觸發日。

### 法人組（`rank_inst`，2026-11-23 起）

使用者 2026-11-20 決定加進影子跑。和 `overnight_up` 一樣只能填在 `daily_model.shadow`，不會被交出去。程式在 `src/models/m6_rank_inst.py`，設定在 `configs/config.yaml` 的 `rank_inst`。

- 做法：`rank_ensemble` 的 41 個價量欄，加法人 23 欄，共 64 欄。三個模型、參數、前 500 天訓練、每天早上重訓、25 檔猜漲 25 檔猜跌都和 `rank_ensemble` 一樣。這是 Kaggle notebook 33 的 `X_inst`。
- 法人 23 欄：都從老師個股檔的外資、投信、自營商買賣超股數和外資持股比率算，每一格是 t 的前一個交易日收盤後的值。
  - `c_foreign_pct`、`c_trust_pct`、`c_dealer_pct`：外資、投信、自營商當天買賣超 ÷ 當天成交股數。
  - `c_foreign_pct5`、`c_foreign_hold_chg5`：外資 5 天累計買賣超 ÷ 5 天成交股數；外資持股比率 5 天的變化。
  - `f_foreign_pct20`、`f_trust_pct5`、`f_trust_pct20`：外資 20 天、投信 5 天和 20 天累計買賣超 ÷ 同期成交股數。
  - `f_inst_pct`：三大法人合計當天買賣超 ÷ 當天成交股數。
  - `f_foreign_streak`、`f_trust_streak`：連續買超（正）或賣超（負）的天數，截在 ±20。
  - `f_foreign_z60`：外資當天買賣超占比和自己前 60 天比的 z 分數。
  - `f_foreign_hold`、`f_foreign_hold_chg20`：外資持股比率；20 天的變化。
  - `f_foreign_ema5_gap` 等 9 欄：外資、投信、三大法人各自的「當天買賣超 − 自己的 5／10／20 天 EMA（指數移動平均）」÷ 20 天平均成交股數。
- 為什麼只影子跑：回測在另外 50 檔每天比 `X_price` 多 0.00019，過了多重檢定；但用 2021 年做的確認沒過（p 0.078），模擬期 22 天還少。增量這麼小，大約要 250 天才分得出有沒有用，影子跑是留紀錄。
- 早上法人資料沒到的日子：老師 Live 還沒填前一個交易日，或要預測的 50 檔裡法人欄有值的不到 45 檔（`min_filled_share: 0.9`），早上先不算，傍晚打分前補算。用的還是前一個交易日的資料，只是比早上晚拿到。
- `shadow_<t>.csv` 多的兩欄：`inst_filled_rank_inst`（50 檔裡前一個交易日的法人欄有值的檔數）、`late_rank_inst`（0 是早上算的，1 是傍晚補算的）。`late` 是 1 的日子代表資料到齊時模型會怎麼猜，不代表早上交得出來，評估能不能上線時要分開看。
- 和 notebook 33 對過：oop 重播 2026-08-03～2026-11-12 的 69 天，猜漲猜跌和 notebook 一樣的格子 Top50 98.9%、另外 50 檔 99.4%（同一段 `rank_ensemble` 對 notebook 是 98.7%、99.0%）。

## N1 影子跑（2026-11-23 起）

使用者 2026-11-23 同意，只記不交。N1 是 c2v2d 的排名集成多一個成員 JS_ONLINE（Kaggle KD 05 訓練好的小型神經網路，每天用前一個交易日的答案更新一步）。程式在 `src/models/m7_n1_js_online.py`，設定在 `configs/config.yaml` 的 `daily_model.n1`。研究的經過在 `memory/projects/13-unbound-count-model.md`。

### 怎麼算

- 分數：N1 = k_t·comb4 + 2(2p − 1)·β̃。comb4 是 ridge、kernel ridge、LightGBM、JS_ONLINE 四個當天名次 − 0.5 的平均；k_t = 三個成員平均的標準差 ÷ comb4 的標準差，把尺度拉回 c2v2d 的；p、β̃ 和 c2v2d 一樣。分數前一半猜漲，所以也是 25 漲 25 跌。
- 三個成員、p、β̃ 讀 `shadow_<t>.csv` 的 `c2v2d` 欄。那天 c2v2d 沒算出來時 N1 空白，JS_ONLINE 自己的猜法照記。
- JS_ONLINE 的 54 個輸入從老師個股檔和 4 個美股序列（`gspc`、`sox`、`tsm_adr`、`vix`）算，每天從 2020-01-02 整段重算，只用日期早於 t 的列。美股取日期早於 t 的最後一根K棒的漲跌（D06 規則）。`gspc` 是 Yahoo 的 ^GSPC，爬蟲另外抓（`yfinance.extra_tickers`），不進特徵表和合併表。
- 每天早上先補更新：狀態最後更新日之後、t 之前的每個交易日各更新一步，同一天不會更新兩次。t 的前一天有「新缺」的股票（前前天還有資料）時，先不更新那天，`stale_n1` 記 1，下一個交易日再照有的列更新。

### 什麼時候跑

- `run_daily.py` 收尾時，合併原始資料之後、推資料之前。要全部成立：`enabled`、Phase 2、t 是今天、不是休市或傍晚、這次沒有停下、沒加 `--dry-run`、台北 08:45 前。
- 用自己的環境 `.venv-n1`（有 torch，`requirements-n1.txt`）開子程序，最多 150 秒，最晚 08:58。主程序不 import torch。逾時、當掉、資料還不是 t 的，都只記一行 WARNING，交件、重交、推資料照常。
- 下一個排程時段：n1 跑的時候 `run_daily` 的鎖還拿著，下一個時段拿不到鎖會整個跳過。所以逾時也不超過「到下一個時段的秒數減 210 秒」（`next_slots`、`slot_margin_seconds`，留給 commit、push：一次 git 呼叫卡到 180 秒的逾時、等 15 秒再推一次也夠），剩不到 30 秒就不叫，下一個時段再算。`next_slots` 要和 `deploy/crontab.txt` 一樣，測試會比。
- 一天最多算 2 批：`shadow_<t>.csv` 變了（重交後重寫）才算第 2 批，第 1 批留著。
- `gspc.csv` 還沒抓到過（上線第一天爬蟲抓 ^GSPC 失敗）：那天 n1 回傳碼 2、不算，隔天爬蟲再抓。不用空白的 gspc 照算，因為補更新會把空白寫進狀態，之後改不回來。抓到過一次以後，抓不到時沿用舊檔，照算並記 `stale_us_n1`。
- 裝法、測試、第一次的重現檢查在 `deploy/n1_setup.md`。

### 檔案

- `data/submission/n1/n1_<t>.csv`：一批 50 列。`run`（第幾批）、`pred_n1`、`prob_n1`（N1 分數的當天名次）、`pred_js_n1`、`js_n1`（JS_ONLINE 自己的猜法和分數）、`k_t_n1`、`c2v2d_same_n1`（用讀到的成員分數重算的 c2v2d 和影子跑那欄一樣是 1）、`note_n1`（N1 空白的原因）、`state_n1`、`state_sha_n1`（用的狀態最後更新到哪天、內容雜湊）、`updated_n1`（這次補更新的日子）、`stale_n1`、`stale_us_n1`（美股K棒比 t 之前最後一個美股交易日舊、值是空白，或爬蟲這次沒抓成那幾個序列、沿用舊檔）、`gspc_n1`、`sox_n1`、`tsm_n1`、`vix_n1`（4 個美股輸入）、`us_bar_n1`（用到的K棒日期）、`shadow_sha_n1`、`inputs_sha_n1`、`files_sha_n1`、`code_commit`、`made_at`。
- `data/submission/n1/inputs_<t>.npz`（第 2 批是 `inputs_<t>_run2.npz`）：這次每個更新日和 t 的 100 檔 54 個輸入、更新用的目標、K棒數、每次更新前後的狀態雜湊。Kaggle 核對和 `.cache/n1/` 不見時的重播都用它。
- `models/n1/ub04_v5/`：起始狀態（Kaggle UB 04 第 5 版），只讀。每天更新的狀態在 oop 的 `.cache/n1/`，不進 Git。

### 打分和停止規則

- 傍晚打分把 `n1_<t>.csv` 也算進 `shadow_scores.csv`：模型 `n1`、`js_n1` 用最後一批；有第 2 批時第 1 批另記 `n1_run1`、`js_n1_run1`。
- 停止規則（使用者 2026-11-23）：影子跑前 5 個交易日累計 n1 − c2v2d 少於 −0.0067 就停。log 每天寫目前的累計，第 5 天寫結論（低於停止線是 WARNING）。只記 log，要停時把 `daily_model.n1.enabled` 改成 `false`，同一個 commit 把 `tests/test_n1_shadow.py` 的 `test_the_n1_config_block` 裡 `conf["enabled"] is True` 改成 `is False`。
- `n1_<t>.csv` 有問題（少欄、pred 不是 0／1）時只記 WARNING，其他影子模型和網站上那份照常打分。
- 5 天後在 Kaggle 核對：讀 `shadow_<t>.csv` 要用 `pd.read_csv(..., float_precision="round_trip")`，和 n1 讀的方法一樣，N1 的分數才會逐位元一樣（預設讀法可能差最後一位）。

## 換模型

改 `kind` 和 `fallback` 兩行，例如換回持續性規則：

```yaml
daily_model:
  kind: persist
  fallback: online_lr
```

- `kind` 寫錯或寫 `none`：整次停下，當天不交。
- `fallback` 寫錯名字或和前面重複：記一行 ERROR 後跳過，其他照跑。`none` 代表沒有備援。
- 程式和設定同一次 push，避開台北 07:00～08:40。推之前在 oop 的測試 worktree 跑 `tests/test_persist_rule.py`、`tests/test_rank_ensemble.py`。
