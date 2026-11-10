# 還沒決定的事

需要時問使用者。有答案後，把結果和日期寫進對應的檔，再從這裡刪掉那一節。

## VIXTWN 和 CNN 恐懼貪婪：還沒定的兩件事

使用者 2026-11-09 的決定和查到的事實在 `memory/projects/crawler.md` 的「VIXTWN、CNN 恐懼貪婪」、`memory/projects/features.md`、`memory/context/data-rules.md`。

- CNN 用哪一天：要看量測。oop `~/pubtime/cnn_probe.py` 寫 `~/pubtime/cnn_log.jsonl` 和 `cnn_snap_*.json`，11-09 17:35～11-11 07:12 共 39 次（美股開收盤、台北 07:10、09:15 前後），11-10 16:00、11-11 07:12 抓全部歷史。19:00 那次碰到學校 DNS 斷線沒抓到；19:18 換成第 3 版（PID 136777）：網路錯誤隔 15 秒重試、最多 4 次，每次用沒人要過的開始日（同一個網址 Fastly 會先回上一次的舊版，見 `memory/projects/crawler.md` 的 CDN 快取），log 多記 `cache`（`Age`、`X-Cache`）。分析時看 `cache` 是 `MISS, MISS` 的點；17:33、17:35 那兩次是第一次要那個網址，可以用，19:15 那次是舊版，不能用；21:00 那次 DNS 斷線，重試 4 次都失敗。另外一個乾淨的點（Mac 試跑新程式，`MISS, MISS`，美股 11-09 開盤後）：台北 11-10 00:17，`now.timestamp` 2026-11-09T16:16:50Z，11-06 那點 24.3532（22:20 開盤前是 24.17），11-09 那點 32.2857。到 11-10 08:30 量到的（都是 `MISS, MISS`）：11-06 那點在 14:33Z（美股開盤後 3 分鐘）還等於即時分數 24.153，14:44Z 起停在 24.353 沒再變，等於在美國下一個交易日開盤後 3～14 分鐘內定住。11-09 那點收盤後 21:24Z 起是 31.714，到台北 11-10 08:30 都沒變；`now.timestamp` 從 23:59Z（美東 18:59）起不再更新，台北 08:30 還沒有 11-10 那點。11-09 那點在台北 11-10 09:00 之後會不會變，要看 09:15 前後的點（美股 VIX 夜盤台北 09:15 開始）。最後一天的分數要是在台北 t 日 09:00 前就定住（而且等於 07:10 抓到的值），就和 `vix` 一樣用美國 i 那天；之後還會變，就用 t 之前最後一個美股交易日的前一個美股交易日（美股交易日看道瓊的K棒，現在的設定 `features.fear_greed.day: second_last`，見 `memory/projects/features.md`，使用者 2026-11-09 選的）。舊日子的值如果也會被改，再問使用者。Mac 17:06 的全歷史快照在 session 的 scratchpad（`fgprobe/fg_2020-09-19.json`，session 結束會消失）。
- 什麼時候推：`exchange.enabled` 11-10 上午打開、推上去（使用者選今晚打開，下一次排程一樣是 11-11 07:10）。11-11 07:10 交易所第一次正式跑順、CNN 量完，才推這兩個的程式、config、原始檔和 `--rebuild` 的 `data/processed/`（照 `memory/context/pipeline.md`「特徵欄位變了怎麼推」）。第一次正式跑是 11-12。程式先寫在另開的 worktree，不 commit，免得混進 11-10 那次 push。
- 11-11 交易所「跑順」的標準：這步失敗時爬蟲的回傳值照樣是 0，只能看 manifest。上傳成功後的時段 already_submitted，不會再爬，所以看那天最後一次爬蟲寫的 `data/raw/manifest.json`：`exchange.status` 是 `ok`，`sources` 四個來源的 `has_prev_day` 都是 true、`missing_dates` 是空的，`requests` 是 `{twse: 4, tpex: 4}`（補 11-09、11-10；同一天第二次爬到這步會是 0）；四個 CSV 最後一天是 2026-11-10；`data/processed/manifest.json` 的 `notes` 沒有交易所的檔。
- 程式的進度（2026-11-09 晚上）：寫在 `/Users/ian/Desktop/ml-final-vixcnn`（detached 在 `2e3402e`，沒有 commit）。改了 `src/crawler.py`、`src/features.py`、`configs/config.yaml`、`README.md`，加 `tests/test_vixtwn_cnn.py`，`tests/test_crawler.py`、`test_features.py`、`test_features_new_columns.py`、`test_no_future_data.py` 小改。真網址試跑（Mac，研究模式 t = 11-10，寫到 scratchpad）：9 秒，VIXTWN 4 個請求 66 天，CNN 1 個請求 1,450 天。兩輪獨立審查找到的問題 2026-11-09 晚上都修了（第一輪：CNN 改用道瓊當美股日曆、manifest 寫不出來不讓爬蟲停下等；第二輪：CNN 網址每天不同、那天早上沒抓到 CNN 時 t 那列空白、VIXTWN 每個月份分開等，見 `memory/projects/crawler.md`、`features.md`），全部 431 個測試通過。
- 11-11 推的步驟：
  1. 把 worktree 的改動搬到開發用的 clone（第二輪審查在暫存 repo 試過，直接 `git apply` 會在 README 和 config 失敗）：
     - worktree 裡 `git diff > vixcnn.patch`（`tests/test_vixtwn_cnn.py` 是新檔，另外複製）。它的 `cfg` 夾具 11-10 加了關掉 `exchange.enabled` 那行：clone 的 config 是 true，沒有那行的話 `crawl()` 的測試會跑真的交易所那步、碰 `.cache/` 的鎖。clone 的 `tests/test_crawler.py`、`test_exchange.py` 11-10 也改了 `cfg` 夾具，`--3way` 要合得起來。
     - clone 裡 `git apply --3way --exclude=README.md vixcnn.patch`：src、config、tests 會乾淨套上，config 保留 11-10 打開的 `exchange.enabled: true`。
     - `git apply --reject --include=README.md vixcnn.patch`：2026-11-10 00:30 用當時的 patch 在暫存 clone 試過，README 7 段只有第 6 段 `src/crawler.py` 那行檔案樹沒套上，它（在別的 session 的 Kaggle 那幾行旁邊）進 `README.md.rej`。手動補上，刪掉 `.rej`，README 只 stage VIXTWN、CNN 的段落。
     - CNN 量測如果顯示最後一天在台北 t 開盤前就定住，`features.fear_greed.day` 改 `prev_day`，要一起改：README「只進長表的欄」那段的 CNN 那行、「為什麼 CNN 用倒數第二天」那段和那天早上沒抓到的那段、表格的 fear_greed 兩列、`fear_greed_values` 和 features.py 開頭的說明；`test_fear_greed_never_uses_the_last_cnn_day`、`test_fear_greed_skips_a_us_holiday_cnn_point`、`test_fear_greed_second_last_us_day_before_each_row`、`test_fear_greed_does_not_carry_old_scores_forward` 這 4 個測試會失敗，要照新規則重寫；「檔裡最新的美股日就空白」那條也要重想（prev_day 用的就是最新那天）。README 寫的「推測要到美國下一個交易日開盤才定住」照量測結果改。
  2. `git fetch` 加 `rebase --autostash` 之後，在暫存資料夾當 `raw_dir` 跑一次兩步（研究模式，t = 當天），只把 `taifex/vixtwn.csv`、`cnn/fear_greed.csv` 複製進 `data/raw/`。不要直接對 `data/raw` 跑：`run.save()` 會把 `data/raw/manifest.json` 蓋成只有這兩步的版本。沒有舊檔時 CNN 的開始日照 t 錯開（t = 11-11 是 `2021-01-28`），沒人要過。跑完看暫存資料夾 manifest 的 `cnn.cache`：`X-Cache` 要剛好是 `MISS, MISS`、`Age` 0～5，不是就再跑一次（`MISS, HIT` 是台北那層 CDN 給的存檔，2026-11-09 22:30 試過）。`now.timestamp` 只當第二個參考：美股收盤後它可能比現在晚不只 15 分鐘，11-10 07:10 那次量測會看到晚多少。
  3. `--rebuild`，確認 84 欄、`warnings` 空的、`notes` 沒有 vixtwn、fear_greed、log 沒有「t 那列的 … 空白」，t 那天 50 檔的 0／1 和重建前一樣（模型欄沒變）。
  4. commit 程式、測試、文件（README 照舊不收 Kaggle 那幾行）和資料（`data/processed`、兩個新的原始檔），避開台北 07:00～08:40 推，oop 手動 pull、跑一次測試。
  5. 在 oop 用暫存資料夾當 `raw_dir` 跑一次兩步，確認 oop 的 Python（requests）抓得到 CNN（目前只用 curl 和 urllib 試過）和期交所的月檔。一定在第 2 步之後：同一天、都沒有舊檔時兩邊要同一個網址，oop 和 Mac 都經過台北那層 CDN，oop 會拿到 Mac 留下的那份（`HIT`），這步只看連不連得上，是正常的。這步的結果不要複製到任何地方。

## 2026-11-09 features 實作時 Claude 定的細節，等使用者確認

細節和數字在 `memory/projects/features.md` 的「實作時 Claude 定的細節」。要使用者看的是這三個：

- fresh 欄怎麼往回數：照規格數台股交易日。老師 Training 有 112 個台股日沒有 global 列，那幾格空白，所以 `teacher_gspc_fresh_ret_lag1` 有值的天數是 1,445，`teacher_gspc` 是 1,548。另一種做法是像 `teacher_gspc` 那樣數 global 自己的列。2026-11-09 問過使用者，使用者問老師為什麼缺、Claude 建議哪個：缺的原因見 `memory/context/data-rules.md`；Claude 建議維持現在的做法（跳過的做法在美國休市那 48 天剛好是一天的漲跌，但在韓國休市那 62 天會把兩天的美股漲跌算成一天，表上分不出來），使用者還沒選，沒改程式。
- 停牌：交易所停牌那天照樣有列（開高低收 `--`、成交股數 0，估值沿用前一天）。Claude 照核准定義的「停牌空白」把這種列當成沒有列，9 欄空白，共 21 個股票日。
- 韓國晚開盤的「每年第一個交易日」：取每年第一根和第一根有成交量的K棒，兩根都空白。2026-11-09 看過真資料：每年第一根都對，只有 2022 年 Yahoo 少了 01-03，結果擋到正常開盤的 01-04（多擋一天）。

其他的在 features.md 那節，沒有特別要問的：t 那列的開盤跳空一律空白、價格不在升降單位格子上時檔數空白、三個旗標欄存成整數、notes 用 warning 等級寫 log。

## 前一次交了不完整的版本，後面的時段要不要重交（使用者 2026-11-08：先觀察）

- 爬蟲有序列沿用舊檔時回傳 3，`run_daily_test.py` 只寫警告，照樣上傳。後面的時段看到網站上已經有 t 的提交就結束，不會重爬。所以多排的時段救得了「整次停下」（例如 git 那步失敗），救不了「Yahoo 限流、部分序列沒抓到」。
- 先每天看 `data/raw/manifest.json` 各序列的 status、`kept_previous_file`、`run.no_bar_i`。常發生再設計：只在前一次是自己交的、而且 stale 時重交，不蓋掉組員的手動版本。
- 觀察紀錄：
  - 2026-11-09：乾淨，沒有警告。
  - 2026-11-10：07:10 那次在 git pull 就停了（學校 DNS 查不到 github.com）。07:25 那次 07:28 交出去、網站核對一樣，但 stale：期交所連不上（重試 5、10 秒都失敗），tx_day、tx_night 空白；Yahoo 沒有 stoxx50e、kospi 的 11-09 那根。後面的時段都 already_submitted。
  - 兩天都 50 檔全部猜跌（猜漲 0.000；Phase 1 的 84 天是 0.303）。11-09 沒有任何警告，所以不是缺資料造成的，是模型自己的輸出。

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
