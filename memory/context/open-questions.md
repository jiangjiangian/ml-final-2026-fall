# 還沒決定的事

需要時問使用者。有答案後，把結果和日期寫進對應的檔，再從這裡刪掉那一節。

## 證交所、櫃買每天的步驟什麼時候打開（2026-11-09）

- `exchange.enabled` 是 false。打開前要量證交所、櫃買每天幾點公布 i 那天的資料，07:10 抓不抓得到；也要先推回補的檔（見 `memory/projects/crawler.md` 的「每天的步驟」）。
- Claude 實作時自己加的三個設定，等使用者決定要不要留：`daily_retries: 0`、`daily_max_failed_dates: 1`、`daily_budget_seconds: 180`。

## 2026-11-09 features 實作時 Claude 定的細節，等使用者確認

細節和數字在 `memory/projects/features.md` 的「實作時 Claude 定的細節」。要使用者看的是這三個：

- fresh 欄怎麼往回數：照規格數台股交易日。老師 Training 有 112 個台股日沒有 global 列，那幾格空白，所以 `teacher_gspc_fresh_ret_lag1` 有值的天數是 1,445，`teacher_gspc` 是 1,548。另一種做法是像 `teacher_gspc` 那樣數 global 自己的列。
- 停牌：交易所停牌那天照樣有列（開高低收 `--`、成交股數 0，估值沿用前一天）。Claude 照核准定義的「停牌空白」把這種列當成沒有列，9 欄空白，共 21 個股票日。
- 韓國晚開盤的「每年第一個交易日」：取每年第一根和第一根有成交量的K棒，兩根都空白。2026-11-09 看過真資料：每年第一根都對，只有 2022 年 Yahoo 少了 01-03，結果擋到正常開盤的 01-04（多擋一天）。

其他的在 features.md 那節，沒有特別要問的：t 那列的開盤跳空一律空白、價格不在升降單位格子上時檔數空白、三個旗標欄存成整數、notes 用 warning 等級寫 log。

## 前一次交了不完整的版本，後面的時段要不要重交（使用者 2026-11-08：先觀察）

- 爬蟲有序列沿用舊檔時回傳 3，`run_daily_test.py` 只寫警告，照樣上傳。後面的時段看到網站上已經有 t 的提交就結束，不會重爬。所以多排的時段救得了「整次停下」（例如 git 那步失敗），救不了「Yahoo 限流、部分序列沒抓到」。
- 先每天看 `data/raw/manifest.json` 各序列的 status、`kept_previous_file`、`run.no_bar_i`。常發生再設計：只在前一次是自己交的、而且 stale 時重交，不蓋掉組員的手動版本。

## 五個時段的實測（2026-11-08 檢查留下的）

- 期貨和 ^VIX：拿 11/10 早上那次 data commit 和 11/11 那次比 `data/raw/yfinance/{wti,gold,vix,dxy,usd_twd}.csv` 的 2026-11-09 列。close 不一樣，就代表早上抓到的是盤中列，Yahoo 在 end 之後回了兩列，yfinance 的同日規則蓋掉了結算K棒。11/09 的 i 是 11/06，測不出來。
- 期交所夜盤：看 11/10（二）以後 07:10 那次 manifest 的 `taifex.has_night_t`、`rechecked`。11/09 的夜盤已經放上去兩天，測不出來。
- 執行時間：看 manifest 的 `run.started_at`、`finished_at`，確認 oop 平常跑幾分鐘。
- 夏令時間（2027-03-14 起）時，VIX 的延長時段 20:15 EDT 是台北 08:15，比賽那時還在的話要重看。

## 雲端主機的細節

- 2026-11-07 定了：學校的 oop 主跑、使用者的 Mac 備援、GCP 備用（見 `memory/context/pipeline.md`）。推資料用 oop 上的 deploy key。下面是當初的考量。

- 使用者 2026-11-06 決定用雲端小主機跑 cron（見 `memory/context/pipeline.md`），不用 GitHub Actions。理由：GitHub 的 `schedule` 11/04 晚了 3 小時 42 分到 6 小時 17 分，11/05 16 個時點只觸發 5 個。
- 還沒定：用哪一家（提議 GCP 免費的 e2-micro，要綁卡）、誰的帳號、主機怎麼推資料到 GitHub（只能推這個分支的金鑰）、Healthchecks.io 的通知接在哪。
- 要先查：Yahoo 會不會擋雲端主機的 IP。

## 舊系統的排程停了沒

- 2026-11-05：GitHub 預設分支已經是空的 `main`，使用者因為 GitHub Actions 一直延遲而換掉。`system-completion` 最後一次排程是 11/05 台北 11:39，之後沒有再跑。使用者 2026-11-06 決定改用雲端小主機跑 cron。
- 換之前的狀況：`system-completion` 的 `course-benchmark.yml` 每天照排程跑，上傳開關寫死成開，舊模型也通過了上傳前的檢查。台北 08:20、08:27 這兩個排程準時觸發時，它會真的上傳。
- 這個分支把 `submit.enabled` 改成 `true` 之前，要先跟使用者確認舊排程已經停了。不然兩套程式會搶著交答案、用掉上傳次數。
- `system-completion`、`dev`、`deep-research` 使用者 2026-11-05 已在 GitHub 刪掉；`live-data` 還在。

## 每天的資料誰 commit、push

- 2026-11-06 第一次連網試跑之後，`data/raw/`、`data/processed/` 是手動 commit、push 的（研究模式，t = 11/06）。之後每天還沒有步驟會做這件事。
- 雲端主機上的 `run_daily.py` 要在 features 之後 commit、push 這兩個資料夾（只加這兩個路徑），寫到排程那一步再問。

## 組員的腳本要改讀新資料

- 組員的 `build_dataset.py`（其實是 `notebooks/build_model.ipynb` 前 5 格）和 Kaggle 的 `notebooks/kaggle/data/twfeat.py`、`build_dataset.sh` 還在讀 data-collection 的 `panel_lag.csv.gz`（欄名 `ticker`、lag2 和 lag5、日K的 `usd_twd`、清理過的 `extra/yfinance/`）。
- 要改成 README 的網址，欄名是 `stock_id`、lag1 和 lag2、`usd_twd_am`、`tx_day`、`tx_night`，模型欄看 manifest 的 `model_columns`（32 欄）。`date` 要日期型態就加 `parse_dates`（README 的範例已經加）。`data/raw/yfinance/` 是 Yahoo 原樣、沒清理（0052 分割前的價格沒除），不能拿舊程式直接讀。`feature_switch.ipynb` 的 `STOCK_LAG_GROUP` 要改成 lag1、lag2。push 特徵表之後通知組員（2026-11-06 第一輪檢查整理）。

## 正式流程用哪位組員的帳號

還沒決定。帳號密碼只放 `.env` 或執行環境的 secret。

## Phase 2 用哪個模型

- `configs/config.yaml` 先寫 LightGBM，之後依驗證結果換。
- Phase 1 的模型見 `memory/context/competition.md`。
- `claude/hopeful-brahmagupta-wikys1` 有 11/04 的 R4 模型研究，commit 訊息寫選了 E1 線性模型、LightGBM 沒贏 E1。選模型時可以參考。
