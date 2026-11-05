# Kaggle 模型研究（notebooks/kaggle/）

## 狀態

- 2026-11-05：使用者用 `/goal` 要求：寫幾本可以在 Kaggle 平行訓練的 notebook，用 `claude/peaceful-babbage-09xeie` 的資料，結合金融和時序知識整理特徵，找出能在 Phase 1 回測拿高分的模型。使用者說直接做，不用再問。
- 2026-11-05：Kaggle MCP 在這個 session 無法授權（`authorize` 300 秒沒回應）。等使用者放 `~/.kaggle/kaggle.json`（API token）後用 `kaggle` CLI 推。沒有 token 之前，notebook 先在本機跑，附 `kernel-metadata.json`。
- 這份是給 subagent 的規格。下面每一節都是要照做的定義，不是建議。

## 目標和評分

- 每一格 = 一檔股票 × 一個台股交易日 t。答案 `r = adj_close_t / adj_open_t − 1`，`y = 1{r > 0}`。
- 官方分數 = mean over cells of `(2·pred − 1) · r`，只算 Top50 的格子。全猜 0 的分數是 `−mean(r)`，歷史上是正的（台股盤中平均下跌），所以 0 是預設答案，只有有把握時才猜 1。
- 最佳決策：`pred = 1 iff E[r | x] > 0`。所以模型要麼回歸 r，要麼用 |r| 當樣本權重做二元分類；兩種都在 0 處切。不要調門檻去迎合測試期。
- Phase 1 的參考：2026-06-01～09-30，84 個交易日。舊系統的 TCN 拿 0.000968（官方）。目標是明顯高於這個數字，而且 dev 期也要穩定高於全猜 0。

## 資料

### 來源和路徑

`twfeat.load_raw(root=None)` 依序找：參數 `root`；環境變數 `TW_DATA_ROOT`；`/kaggle/input/tw-intraday-data/raw`；`<repo>/notebooks/kaggle/data/raw`；`<repo>/../ml-final-archive/data`；都沒有就從 GitHub 下載到 `<repo>/notebooks/kaggle/data/raw`：

```
BASE = https://raw.githubusercontent.com/jiangjiangian/ml-final-2026-fall/claude/peaceful-babbage-09xeie
teacher/info.json                      Top50@Y、Top100@Y
teacher/global/global_data.csv         date,^VIX,^IXIC,^GSPC,^TWII,^KS11,TX_OI；1,506 列，缺 112 個台股日
teacher/market/<stock_id>.csv          100 檔，21 欄，2020-01-02～2026-08-31，LF 換行，y 是 0/1
teacher_live/global/global_data.csv    2026-09-01 起，每個台股日一列
teacher_live/market/<stock_id>.csv     100 檔，同 21 欄，CRLF 換行，y 是 0.0/1.0，待定格是 -1；本機 archive 版到 2026-11-04
extra/yfinance/<series_id>.csv         19 個序列，date,open,high,low,close,adj_close,volume，2020-01-02～2026-09-30，已清理（壞報價、佔位K棒、0052 分割）
```

本機的 `../ml-final-archive/data` 是唯讀 worktree，只讀不改。`notebooks/kaggle/data/raw/` 不進 Git（notebooks/README.md 的規定：老師資料不 commit 進這個分支）。

### 個股欄位改名

| 老師欄名 | 短名 |
|---|---|
| `etl:adj_close` / `etl:adj_open` / `etl:adj_high` / `etl:adj_low` | `adj_close` / `adj_open` / `adj_high` / `adj_low` |
| `price:成交筆數` / `price:成交金額` / `price:成交股數` | `n_trades` / `amount` / `volume` |
| `foreign_investors_shareholding:全體外資及陸資持股比率` | `foreign_hold_pct` |
| `institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)` | `foreign_net` |
| `institutional_investors_trading_summary:投信買賣超股數` | `trust_net` |
| `institutional_investors_trading_summary:自營商買賣超股數(自行買賣)` / `(避險)` | `dealer_self_net` / `dealer_hedge_net` |
| `RSI` `SMA` `MACD` `ATR` `BBANDS_upper` `BBANDS_mid` `BBANDS_lower` `y` | 小寫同名：`rsi` `sma` `macd` `atr` `bb_upper` `bb_mid` `bb_lower` `y_teacher` |

### 清理

- Training 和 Live 接起來：Training 全部，Live 只取 date > Training 最後一天（2026-08-31）。
- Live 待定列：`adj_close == -1` 或 `adj_open == -1` 的列整列丟掉。10-23 和 11-04 所有股票都是待定，丟掉後自然不在日曆裡。
- Live 其他欄的 `-1` 當 NaN（法人欄的真 -1 只在 Training，不動）。Live global 的 `-1` 也當 NaN。
- 答案 `r`、`y` 自己從 `adj_close`、`adj_open` 算，和 `y_teacher` 比對，不一致的格數要印出來（預期 0）。
- 台股日曆 = 清理後個股列出現過的日期（排序、去重）。不要用 global 表當日曆。
- yfinance 的 `volume` 不用，指數的成交量永遠是 0。

### 時間對齊（最重要）

t 那列的特徵只能用「t 開盤前已知」的資料：

- 個股和跨股特徵：只用該股 date ≤ i 的列，i = t 的前一個台股日。實作上在每檔股票自己的列上算 rolling，再 `shift(1)`；缺列（54 格）時 shift 會拿到更早的列，仍然安全。跨股（cross-sectional）特徵先在每個日期 d 對 100 檔算，再 shift(1)。
- 市場特徵（從老師個股算的）：在日期 d 對 Top50 算，用日曆對到 t 的前一個台股日 i。
- 老師 global：`^VIX` `^IXIC` `^GSPC` 用 date ≤ t 的最後一列（Training 的第 j 列放的是第 j−1 列日期的美股收盤，Live 的 d 列放的是 date < d 的最後一個美股收盤，兩種都在 t 開盤前已知）。`^TWII` `^KS11` `TX_OI` 是當日收盤，只能用 date < t 的最後一列。
- yfinance：用 session date ≤ t − 1 日曆天的最後一根K棒。報酬先在該序列自己的連續K棒上算，再對齊。TWD=X 的 d 日 close 其實是台北 d 日早上的報價，用 ≤ t − 1 一樣安全。
- 絕對不用：t 當天任何欄位、`y_teacher`、`r`、`y`，也不能用 t 當天的 global 列（`^TWII` 等）。
- 不需要 embargo：row d 的答案在 d 收盤就知道，1 天後的目標沒有 overlap 問題。

## 特徵（twfeat.build_features）

輸出長表：`date, stock_id, is_top50, r, y` + 特徵欄。100 檔全部算（訓練可以用 100 檔，評分只算 Top50）。回傳 pandas DataFrame，依 date、stock_id 排序；`stock_id` 是字串。缺值留 NaN，不補（補值是模型 notebook 的事，而且只能用訓練期的統計）。

報酬一律用簡單報酬 `p_i / p_{i−k} − 1`，除非下面另外寫。「at i」表示 shift(1) 之後的值。

### 個股（前綴 `s_`）

| 欄 | 定義 |
|---|---|
| `s_ret1` `s_ret2` `s_ret5` `s_ret10` `s_ret20` | adj_close 往回 k 列的累積報酬，at i |
| `s_intra1` | `adj_close / adj_open − 1` at i（昨天的盤中報酬） |
| `s_intra_mean5` `s_intra_mean20` | `s_intra1` 往回 5、20 列的平均 |
| `s_intra_tstat20` | `mean(intra, 20) / (std(intra, 20) / sqrt(20))`，持續性的盤中偏向 |
| `s_up_frac20` | 往回 20 列 `y` 的平均（at i，也就是用 ≤ i 的 y） |
| `s_gap1` | `adj_open_i / adj_close_{i−1} − 1`（昨天的開盤跳空） |
| `s_gap_mean5` | 往回 5 列平均 |
| `s_range1` | `(adj_high − adj_low) / adj_close` at i |
| `s_atr_pct` | `atr / adj_close` at i |
| `s_clv1` | `(adj_close − adj_low) / (adj_high − adj_low)` at i，分母 0 時 NaN |
| `s_vol5` `s_vol20` | `s_ret1` 往回 5、20 列的標準差 |
| `s_vol_ratio` | `s_vol5 / s_vol20` |
| `s_amount_z60` | `log(amount)` 減 60 列中位數再除以 1.4826×MAD，at i，裁到 ±5 |
| `s_volume_ratio` | `volume_i / mean(volume, 20 列)` |
| `s_trades_ratio` | `n_trades_i / mean(n_trades, 20 列)` |
| `s_foreign_pct1` | `foreign_net / volume` at i，裁到 ±1 |
| `s_foreign_pct5` `s_foreign_pct20` | `sum(foreign_net, k) / sum(volume, k)` at i |
| `s_trust_pct1` `s_trust_pct5` | 投信同上 |
| `s_dealer_pct1` | `(dealer_self_net + dealer_hedge_net) / volume` at i |
| `s_fhold_chg1` `s_fhold_chg5` | `foreign_hold_pct` 的 1、5 列差 |
| `s_rsi` | `rsi` at i，除以 100 |
| `s_macd_pct` | `macd / adj_close` at i |
| `s_sma_dev` | `adj_close / sma − 1` at i |
| `s_bb_pos` | `(adj_close − bb_lower) / (bb_upper − bb_lower)` at i |
| `s_bb_width` | `(bb_upper − bb_lower) / bb_mid` at i |

### 跨股（前綴 `cs_`，每天對 100 檔算百分位 rank，`(rank − 0.5)/n − 0.5`，再 shift(1)）

`cs_ret1`、`cs_ret5`、`cs_intra1`、`cs_intra_mean20`、`cs_foreign_pct1`、`cs_foreign_pct5`、`cs_amount_z60`、`cs_gap1`。另外 `s_ret1_rel = s_ret1 − m_ret1`（個股減市場）。

### 市場（前綴 `m_`，Top50 等權，同一天各股相同，對到 i）

| 欄 | 定義 |
|---|---|
| `m_ret1` `m_ret5` | Top50 `ret1` 的平均；`m_ret5` 用 5 天 m_ret1 累積 |
| `m_intra1` `m_intra_mean5` | Top50 盤中報酬的平均及其 5 天平均 |
| `m_gap1` | Top50 開盤跳空的平均 |
| `m_breadth1` | Top50 當天 `y` 的比例 |
| `m_foreign_flow` | `sum(foreign_net × amount/volume) / sum(amount)` over Top50（金額加權外資淨買占比），再做 60 天 z-score（只用 ≤ i） |
| `m_vol20` | `m_ret1` 的 20 天標準差 |
| `m_intra_z` | `m_intra1 / std(m_intra1, 60)`，裁到 ±4 |

### 老師 global（前綴 `g_`）

`g_vix`（水準，除以 20 取 log，裁到 [−1, 2]）、`g_vix_chg1`、`g_gspc_ret1`、`g_ixic_ret1`（三者用 date ≤ t 的列，報酬是該列對上一列）、`g_twii_ret1`、`g_ks11_ret1`、`g_txoi_chg_z`（ΔTX_OI 除以 60 列標準差，裁到 ±4；三者用 date < t 的列）。

### yfinance（前綴 `x_`，K棒 date ≤ t − 1）

- 單日報酬 `x_<id>_ret1`：sox、tsm_adr、nvda、dji、n225、hsi、sse、stoxx50e、gdaxi、wti、gold、etf_0050、etf_0052、etf_0055、etf_006201、usd_twd、dxy。股票和 ETF 用 `adj_close`，其他用 `close`。
- 5 日報酬 `x_<id>_ret5`：sox、tsm_adr、nvda、dji、etf_0050、usd_twd。
- `x_us10y_chg1`、`x_us13w_chg1`：殖利率的差（百分點），不用報酬。
- `x_us_shock_z`：照舊研究 Phi-v1 的 C1。對 sox 和 dji 各算：取 US session 日期在 (i, t − 1] 的K棒，`R = log(close_last) − log(close_before_window)`，`z = R / (sigma60 × sqrt(n))`，sigma60 是該序列單日 log 報酬的 60 根標準差（只用窗口前的K棒），裁到 ±4；窗口內沒有K棒（美股休市）記 0。最後 `0.5·z_sox + 0.5·z_dji`。
- `x_tsm_adr_premium_z`：`(tsm_adr adj_close × usd_twd close / 5) / adj_close_2330(at i)`，取 log，減 60 列 rolling 平均再除以 rolling 標準差（只用 ≤ t 的列），裁到 ±4。2330 的 adj_close 有除息調整，比值會在除息日跳一下，60 天 z-score 會吸收大部分；寫在 docstring。這欄只對 2330 以外的股票也一樣值（市場層級）。
- `x_days_stale`：sox 最後一根K棒的日期到 t 的日曆天數（週末、美股假日會變大）。

### 日曆（前綴 `cal_`）

`cal_dow`（0～4）、`cal_gap_days`（t − i 的日曆天數）、`cal_pre_long_gap`（下一個台股日 − t ≥ 4 天為 1；日曆的最後一天 NaN）、`cal_month`（1～12）。

### 數量

大約 85 欄特徵。缺值比例要印出來。

## 評估（twfeat 裡的函式）

- `official_score(pred, r)`：`mean((2·pred − 1)·r)`。
- `evaluate(df)`：`df` 要有 `date, stock_id, pred, r, is_top50`。只取 `is_top50 == 1`。回傳 dict：`n_days, n_cells, score, all0, all1, prevday`（用 `s_intra1 > 0` 當預測，若欄位存在）、`accuracy, frac_up, ci95`（按日期 bootstrap 2000 次，seed 0，對每日平均再取總平均）、`by_month`（{yyyy-mm: score}）、`days_positive`（每日分數 > 0 的天數）。
- `dev_folds()`：9 個 fold，測試期是 2024Q1、2024Q2、…、2026Q1（各一季），訓練期是測試期開始日之前的全部。每個 fold 回傳 `(train_end_exclusive, test_start, test_end_inclusive)`。
- `phase1_fold()`：訓練 date < 2026-06-01，測試 2026-06-01～2026-09-30。訓練和推論只做一次，權重固定（照 Phase 1 的規則）。
- `oct_fold()`：訓練 date < 2026-10-01，測試 2026-10-01～資料最後一天（約 11-03）。yfinance 只到 9/30，所以 10 月的 `x_` 特徵會是 NaN（10/1 那列除外），這是刻意的 robustness 檢查，報告要分開列。
- 模型選擇只看 dev 的 pooled 分數和 9 個 fold 中贏過 all0 的次數。Phase 1 只報告，不拿來調參。

## 每本 notebook 的共同規格

- 位置：`notebooks/kaggle/<slug>/notebook.ipynb` + `kernel-metadata.json` + `output/`。
- 第一個 code cell 是設定：`RUN_MODE = os.environ.get("TW_RUN_MODE", "full")`（`smoke` 只跑 2 個 fold、少量股票或少量 epoch）；找 `twfeat.py`（`/kaggle/input/tw-intraday-data`、`<repo>/notebooks/kaggle/data`）；需要的 pip 套件用 `try: import … except ImportError: %pip install <pkg>==<pinned version>`，版本要發布滿兩週。
- 第二個 cell：`raw = twfeat.load_raw(); feat = twfeat.load_or_build_features(raw, cache_path)`。cache 放工作目錄（Kaggle 是 `/kaggle/working`）。
- 補值、標準化、winsorize 只用訓練期的統計。樹模型可以直接吃 NaN。
- 每個 fold 的預測存起來，最後寫：
  - `output/preds_dev.csv`、`output/preds_phase1.csv`、`output/preds_oct.csv`：欄 `date, stock_id, is_top50, r, pred, raw`（`raw` 是模型的連續輸出：預測報酬或機率）。
  - `output/report.json`：`{"notebook": slug, "ran_on": "local"|"kaggle", "run_mode": ..., "config": {...}, "dev": evaluate(), "dev_folds": [evaluate() per fold], "phase1": evaluate(), "oct": evaluate(), "runtime_seconds": ...}`。
- 最後一個 cell 印一張表：dev pooled、Phase 1、Oct 各自的 score、all0、accuracy、ci95，以及 Phase 1 TCN 參考值 0.000968。
- Markdown cell 用繁體中文，照 CLAUDE.md 的寫作規則：短句、先結論、不用破折號和 emoji。
- 本機先用 `TW_RUN_MODE=smoke` 跑通，再用 `full` 跑（能跑完才算完成）。用 `.venv/bin/python -m jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=-1 notebook.ipynb`，執行過的輸出留在 notebook 裡。
- 本機是 Intel Mac（x86_64，macOS 14）。PyTorch 在 macOS x86_64 最後一版是 2.2.2，而且可能沒有 Python 3.12 的 wheel。需要 torch 的 notebook：先試 `uv pip install --python .venv/bin/python torch==2.2.2`；不行就另外建 `uv venv --python 3.11 .venv-torch` 裝 torch 2.2.2。模型需要更新的 torch 時，本機只跑得動的部分（例如載入資料和特徵）就好，`report.json` 的 `ran_on` 寫 `local-partial`，並在 notebook 開頭的 Markdown 說明要在 Kaggle GPU 跑。
- Kaggle：`kernel-metadata.json` 的 `id` 用 `KAGGLE_USER/tw-intraday-<slug>`、`dataset_sources` 用 `["KAGGLE_USER/tw-intraday-data"]`，`KAGGLE_USER` 是佔位字串，`push_all.sh` 會換掉。`enable_internet: true`。要 GPU 的設 `enable_gpu: true`。

## 7 本 notebook

### 01-lgbm-intraday（CPU）

LightGBM 兩種目標各跑一次：(a) `objective=huber` 回歸 r（alpha 用訓練期 r 的 95 百分位），pred = 1{ŷ > 0}；(b) `objective=binary`，`sample_weight = |r|`，pred = 1{p > 0.5}。參數從 `num_leaves 15, min_child_samples 300, learning_rate 0.02, n_estimators 600, feature_fraction 0.7, bagging 0.8, lambda_l2 5` 起，early stopping 用訓練期最後 60 個交易日當 valid（之後用整段訓練期重訓固定棵數）。3 個 seed 平均 raw 輸出。訓練用 100 檔，評分 Top50。報告兩種目標的 dev、Phase 1 分數，以及 feature importance（gain）前 20。另外跑一個「只用老師資料的特徵（拿掉 `x_`）」的版本，看 yfinance 有沒有幫助。

### 02-linear-core（CPU）

兩個線性模型：(a) Ridge 回歸 r（alpha 用 dev 的第 1～3 個 fold 選，之後固定）；(b) |r| 加權的 L2 logistic，C = 1。特徵先 winsorize（訓練期 1、99 百分位）、標準化（訓練期平均和標準差）、NaN → 0。兩組特徵集：`core`（`x_us_shock_z, m_foreign_flow, m_intra_z, s_intra_tstat20, s_foreign_pct5, g_vix, x_tsm_adr_premium_z, s_gap1, cs_intra_mean20, cal_pre_long_gap`）和 `all`。報告 4 個組合，並列出 core 的係數。這本是穩健基準，舊研究的 E1 就是這類模型。

### 03-chronos-zero-shot（GPU，本機可以用 CPU 跑 smoke）

Amazon Chronos 零樣本。對每檔股票、每個測試日 t：context = 該股 `s_intra1` 的歷史（也就是 r 的 shift，到 i 為止，長度 512），forecast 1 步，取 quantile 0.1～0.9。pred = 1{median > 0}；另一個變體 pred = 1{mean(quantiles) > 0}。模型：`amazon/chronos-bolt-base` 和 `amazon/chronos-2`（支援共變量：把 `m_intra1, x_us_shock_z, x_sox_ret1, s_gap1` 當 past covariates，`cal_dow` 當 future covariate）。版本要在 HF 上查最新並 pin（含 `chronos-forecasting` 套件版本）。不訓練，所以沒有訓練期；dev 和 Phase 1 都直接推論。本機 smoke：bolt-small、5 檔、Phase 1 前 10 天。

### 04-kronos-ohlcv（GPU）

NeoQuasar Kronos（金融K棒基礎模型，`NeoQuasar/Kronos-small` 和 `Kronos-base`，tokenizer `NeoQuasar/Kronos-Tokenizer-base`）。輸入每檔股票到 i 為止的 400 根 `adj_open, adj_high, adj_low, adj_close, volume, amount`（Kronos 要 OHLCV，amount 選填），預測下一根K棒，sample 30 次（T = 1.0，top_p 0.9），`p_up = mean(sample_close > sample_open)`，pred = 1{p_up > 0.5}。先零樣本跑 dev 最後 2 個 fold 和 Phase 1；時間夠再照官方 finetune 流程用 2020～2026-05 的 100 檔微調一次，再跑 Phase 1。安裝方式照 github.com/shiyu-coder/Kronos 的 README（pip 套件若沒上 PyPI 就 `git clone` 指定 commit）。本機 smoke：Kronos-small、3 檔、5 天，跑不動就 `local-partial`。

### 05-timesfm-xreg（GPU）

Google TimesFM 零樣本加共變量。到 HF 查 `google/timesfm-2.5-200m-pytorch` 和是否已有 3.0，用最新能裝的版本並 pin。目標序列同 03（`s_intra1` 歷史，context 512），動態共變量用 `m_intra1, x_us_shock_z, x_sox_ret1, s_gap1, s_foreign_pct1, g_vix`，用官方的 XReg（in-context regression）方式 `forecast_with_covariates`；靜態共變量 `stock_id`。pred = 1{point forecast > 0}。沒有 XReg 的純零樣本也跑一次當對照。本機 smoke 同 03。

### 06-ttm-finetune（GPU，CPU 也勉強可以）

IBM Granite TTM（`ibm-granite/granite-timeseries-ttm-r2`，用 `granite-tsfm` 套件）。多變量輸入：每檔股票的 `s_intra1`（目標）加 `s_ret1, s_gap1, s_foreign_pct1, m_intra1, x_us_shock_z, x_sox_ret1` 當 exogenous channel，context 512，forecast 1。先零樣本，再用訓練期 few-shot 微調（5 epochs，lr 1e-4，early stopping 用訓練期最後 60 天），對 dev 每個 fold 重新微調，Phase 1 微調一次。pred = 1{forecast > 0}。

### 07-seq-tcn（GPU，CPU smoke）

自己寫的 PyTorch 序列模型，改良舊 Phase 1 的 TCN：輸入 lookback 20 天 × 全部特徵（訓練期標準化，NaN → 0 並加缺值旗標），50 檔共用權重，兩個 head 比較：causal TCN（3 個殘差區塊，kernel 3，dilation 1/2/4，channels 64）和 GRU（hidden 64，1 層）。損失 = |r| 加權 BCE。AdamW lr 1e-3，weight decay 1e-4，最多 30 epochs，early stopping 用訓練期最後 60 天，5 個 seed 平均機率。pred = 1{p > 0.5}。

### 08-stack-ensemble（CPU，最後做）

讀前面 7 本的 `output/preds_dev.csv` 和 `preds_phase1.csv`。兩種合成：(a) 多數決（奇數個模型）；(b) logistic stacking：用 dev 的 raw 輸出（標準化）當特徵、|r| 加權，在 dev 前 6 個 fold 訓練、後 3 個 fold 驗證，再用全部 dev 訓練一次套到 Phase 1。只合成有 dev 預測的模型。報告每個子模型和合成的分數，並算模型兩兩的預測一致率。

## Kaggle 佈署檔

- `notebooks/kaggle/data/dataset-metadata.json`：`{"title": "tw-intraday-data", "id": "KAGGLE_USER/tw-intraday-data", "licenses": [{"name": "other"}]}`。dataset 內容：`twfeat.py`、`README.md`、`raw/`（從 `../ml-final-archive/data` 複製 `teacher/`、`teacher_live/`、`extra/yfinance/`）。`raw/` 不進 Git。
- `notebooks/kaggle/build_dataset.sh`：複製 raw、`kaggle datasets create`（第一次）或 `kaggle datasets version -m "..."`（之後）。
- `notebooks/kaggle/push_all.sh`：讀 `KAGGLE_USER`（環境變數，沒有就從 `~/.kaggle/kaggle.json` 的 `username` 讀），用 `sed` 把每個 `kernel-metadata.json` 和 `dataset-metadata.json` 的佔位字串換成真的帳號（寫到暫存複本，不改 repo 裡的檔），然後對每本 `kaggle kernels push -p <dir>`。`--only <slug>` 可以只推一本。
- `notebooks/kaggle/README.md`：給組員。怎麼在本機跑一本、怎麼推到 Kaggle、怎麼看結果、每本 notebook 一句話、結果表。

## 進度

（workflow 跑完後由 synthesis agent 填：每本 notebook 的 dev、Phase 1、Oct 分數和結論。）
