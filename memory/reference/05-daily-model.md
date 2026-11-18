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

使用者 2026-11-16 決定：每天交件之後，`daily_model.shadow` 列的模型（現在是 `c2v2d`、`c2`、`rank_ensemble`、`persist`、`online_lr`）都預測 t，存檔但不上傳。這樣比的是上線後的真實日子，不是回測。組員已經手動交了的日子也做。

### 檔案

- `data/submission/shadow_<t>.csv`：每檔一列。每個模型兩欄，`pred_<模型>`（0/1）和 `prob_<模型>`（當天名次換成 0～1；`online_lr` 是機率）。`c2`、`c2v2d` 另有 `p_up_<模型>`（大盤方向的機率）。算不出來的模型那幾欄空白，原因在 `run_<t>.log`。
- `data/submission/shadow_scores.csv`：每天每個模型一列。`score` 是官方分數（每格 (2·pred − 1)·盤中報酬的平均），另有 `accuracy`（猜對的比例）、`pred_up`（猜漲的比例）、`cells`（格數）、`source`（答案從哪裡來）。t 當天 18:00 的傍晚打分用老師 Live 的 t 那列先算（`source` 是 `live`）；隔天早上用特徵表的答案再算一次（`features`），兩邊不一樣時 log 有 WARNING。早上算不到的日子留著傍晚的分數。
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
- 打分：t 當天 18:00 的傍晚打分（`src/pipeline/step6_evening_score.py`），老師 Live 還沒填好 t 那列就 20:00 再試。只下載 Live，不上傳、不重建特徵表；Live 寫進 `data/raw/teacher/live/`，組員傍晚就拿得到。
- 算不出來只記一行 WARNING，不影響交件。
- 關掉：`shadow: []`。

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
