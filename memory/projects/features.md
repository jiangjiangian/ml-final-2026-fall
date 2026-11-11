# src/features.py

## 狀態

- 2026-11-06：寫好了。對照測試 (a)、(a2) 都通過（`tests/test_features.py`）：50 個 lag 欄、label、is_top50 和舊長表逐格相同；(a2) 的 56 筆紀錄日期和規則都相同，adj_close 最大相對差 6.7e-7。(b) 等第一次連網。
- `usd_twd_am` 要等爬蟲存 `data/raw/yfinance/usd_twd_1h.csv`（第 4 步）。檔案欄位是 `features.HOURLY_COLUMNS`：`start,open,high,low,close,volume`，`start` 是K棒開始時間、ISO 格式帶時區。沒有這個檔時，2024-01-22 起整欄空白，cleaning.json 和 log 記一筆警告。
- 每天的用法：`python -m src.features --date t`，只留早於 t 的交易日，再加 t 那列（label 一定空白）。不給 `--date` 時用爬蟲 `data/raw/manifest.json` 的 `target_date`。跑一次約 20 秒。
- 2026-11-06 使用者決定輸出一個月一檔，進 Git，組員用網址讀（README 有範例）：`data/processed/features/YYYY-MM.csv.gz` 加 `data/processed/manifest.json`（months、model_columns、last_date、清理紀錄）。每天只重寫最後兩個月（`features.rewrite_months`），內容沒變不寫，repo 每年約多 10 MB。整張壓成一個 .gz 的話每天都是新的 7 MB，Git 存不了差異。
- 有 yfinance 檔不見時（`warnings` 不是空的）只寫最後兩個月，沒有檔的舊月份先不建立，不能 `--rebuild`：過去的月份寫了就不再動，不能讓空白欄凍在裡面。
- t 比 manifest 的 `last_date` 早時丟 `FeatureError`，不蓋掉較新的月份；特徵定義改了用 `--rebuild` 全部重寫。`load_features()` 讀回全部月份。
- 2026-11-09：使用者 2026-11-08 決定的 17 欄做完（見「使用者的決定」2026-11-08 那條），含三個審查後的修正，全部離線測試 333 個通過。長表從 63 欄變 80 欄。用本機 11-06 的 `data/raw` 跑 `load_raw` 加 `build_features(t=2026-11-06)`，和 HEAD 的 `data/processed` 比：166,200 列，原本 63 欄逐月寫成 CSV 後和 HEAD 逐字相同，32 個模型欄 5,318,400 格完全相同，所以程式沒有改到模型欄。在更新的 `data/raw` 上 `--rebuild` 時，舊月份的還原價序列會有 1e-6 級的變動，那是 Yahoo 重抓造成的，和程式無關（見 `memory/context/pipeline.md`「特徵欄位變了怎麼推」第 4 步）。本機建全表從 4.7 秒變約 9 秒，多的主要是交易所欄。
- 推送（2026-11-09 下午做完）：程式、`configs/config.yaml`、pull 之後 `--rebuild` 的 `data/processed/`、`data/raw/twse/`、`data/raw/tpex/`、`data/raw/exchange_backfill.json`、`data/raw/yfinance/kospi.csv` 同一次推。重建用 oop 11-09 的 `data/raw`（t = 11-09）：166,300 列、80 欄，`warnings`、`notes` 都是空的。和 origin 原本的表比：只有還原價序列（`tsm_adr`、`nvda`、`etf_*`）有差，最多 1.6e-6，沒有格子從有值變空白；股票、老師、`usd_twd_am`、台指期的欄沒變。t = 11-09 的 50 檔 0／1 和重建前相同，機率最多差 0.0011。之後欄位再變，照 `memory/context/pipeline.md` 的「特徵欄位變了怎麼推」。
- 2026-11-11：VIXTWN、CNN 的 4 欄（`vixtwn_lag1`、`vixtwn_ret_lag1`、`fear_greed_lag1`、`fear_greed_chg_lag1`）推上去，長表 84 欄，都不進 `model_columns`。經過和檢查見 `memory/projects/crawler.md` 的「推上去（2026-11-11）」。
- 待辦（2026-11-09 審查）：
  - 交易所的檔斷了超過 `exchange.gapfill_days`（10 個交易日）時，每天的爬蟲補不到中間那段。先用 `--exchange-backfill` 補上再 `--rebuild`，不然那段的 `val_*`、`quote_*` 會凍成空白。2026-11-10 打開時只差 11-09、11-10 兩天：11-11 的爬蟲補進原始檔，每天重寫最後兩個月時 t = 11-10 那列跟著補上，不用 `--rebuild`。
  - 只進長表的輸入缺檔時，log 的那行會寫「檔案補齊後要 --rebuild」。每天看一次 manifest 的 `notes`。
- manifest 多 `notes`（2026-11-09）：只進長表的輸入（`features.optional_inputs` 的 yfinance 序列，現在只有 `kospi`，和證交所、櫃買的四個檔）不見或讀不了時記在這裡，log 用 warning 等級，不算缺檔，不擋 `--rebuild`。
- 這份的內容來自 data-collection 的交接文件（`origin/claude/data-collection` `cb03a34` 的 `memory/projects/handoff-stock-market-challenger.md`）。data-collection 之後不再更新，所以要用的部分都抄到這裡。數字除了標「推論」的，都是那邊實際量過的。

## 使用者的決定

- 2026-11-06：lag 只用 lag1、lag2，不用 lag5。使用者和組員都同意。`configs/config.yaml` 的 `features.lags` 是 `[1, 2]`。
- 2026-11-06：`features.csv.gz` 放全部序列（個股自己、19 個 yfinance、老師 global 5 個、`usd_twd_am`）的 lag1、lag2。`configs/config.yaml` 的 `features.model_series` 列出模型要用的序列，`train.py`、`predict.py` 只讀這些欄。之後換序列只改 config。
- 2026-11-06：組員給的 12 個指標：SOX、台積電 ADR、NVDA、Nasdaq、S&P 500、VIX、0050、美元兌台幣、黃金、道瓊、原油、美國短期和長期債利率。對到序列是 sox、tsm_adr、nvda、teacher_ixic、teacher_gspc、teacher_vix、etf_0050、usd_twd_am、gold、dji、wti、us13w、us10y，共 13 個（債利率是兩個序列；這個對應是 Claude 整理的）。
- 2026-11-06：模型用這 13 個序列加個股自己，各 lag1、lag2，共 28 欄（使用者選的）。同一天後來加台指期的 `tx_day`、`tx_night`，變 16 個序列、32 欄（見下一條）。
- 2026-11-06：老師 Live 的 `^VIX` 不是收盤（和 Yahoo 比：`^GSPC` 100% 一樣，`^VIX` 只有 64%，10/13 以後幾乎都不對；11/06 那列 16.83，Yahoo 收盤 28.18）。沒有洩漏，只是不準。使用者決定換成 yfinance 的 `^VIX`（序列 `vix`），模型欄的 `teacher_vix` 改成 `vix`，`teacher_vix` 還留在表裡。
- 2026-11-06：加台指期（使用者要求）。yfinance 和老師的資料都沒有台指期的價格，所以加開關 `tx_futures.source`：`taifex`（預設，期交所網站下載）或 `yfinance`（用 `tx_futures.yfinance` 填的代號，現在留空，切過去會報錯）。來源的查證見 `memory/context/data-rules.md` 的「資料來源」。
  - 用近月合約（到期月最早、有收盤價的那個）。分子分母用同一個合約，每月第三個週三換月時不會多出一段假的漲跌。i−k 數的是台指期自己的日盤日子（2020-01～2026-11 和老師交易日完全一樣）。
  - `tx_day`：日盤（08:45～13:45）收盤，lag 和其他序列一樣，要有 i 那天的日盤。
  - `tx_night`：標 t 日的夜盤（前一個營業日 15:00 到 t 日 05:00）收盤，t 開盤前就知道。使用者選「比日盤收盤」：lag1 = 夜盤收盤 ÷ t 之前最後一個日盤收盤 − 1（隔夜這段），lag2 比再前一個日盤收盤（兩天累積）。另一個選項「比前一天的夜盤」沒選，因為和日盤的 lag 有一段重疊。
  - 期交所的列只擋 close ≤ 0、超出最高最低、重複，沒成交（'-'）直接不用。
  - 2026-11-06 獨立重算四個台指期欄，1,662 天和表逐位元相同。82 次換月都用同一個合約（直接接成連續序列，換月日中位數多 37 bp、最多 348 bp 的假漲跌）。結算日那晚的夜盤，到期的合約有在交易，表也用它。`tx_day` lag1 和 `teacher_twii` lag1 相關 0.952，`tx_night` lag1 和 sox lag1 相關 0.768。2020-01-07 起全部有值。
  - 加欄之後 `data/processed/manifest.json` 多記 `columns`，欄位和上次不一樣時 `features.py` 要 `--rebuild` 才會寫。沒有個股自己的特徵時，同一天 50 檔的值都一樣，模型每天只會給一個答案。
- 2026-11-08 決定，2026-11-09 實作（`src/features.py`，測試 `tests/test_features_new_columns.py` 43 個，`tests/test_no_future_data.py` 加 5 個）。17 欄只進長表、不進 `model_columns`，和回補好的原始資料、`--rebuild` 的長表一起推（見「狀態」）：
  - 證交所、櫃買中心 9 欄（t 那列用 i 的值，i 那天兩個交易所都沒有這檔的列就空白，不往前找；哪邊有就用哪邊，6446 2024-01-25 從櫃買轉上市）：`val_ep_lag1`（1 ÷ 本益比，> 0 時）、`val_pe_loss_lag1`（虧損記號證交所 `-`、櫃買 `N/A` 是 1，數字是 0）、`val_log_pb_lag1`（ln 股價淨值比，> 0 時）、`val_dy_lag1`（殖利率(%) ÷ 100，0 也算）、`quote_spread_ticks_lag1`（買價到賣價差幾檔，升降單位在 config 的 `features.tick_table`，跨區間一檔一檔數）、`quote_rel_spread_lag1`（(賣 − 買) ÷ 兩者平均）、`quote_imbalance_lag1`（(委買張數 − 委賣張數) ÷ 兩者相加，量是空的或兩邊都是 0 時空白）、`quote_limit_up_lag1`（沒有賣價、有買價）、`quote_limit_down_lag1`（沒有買價、有賣價）。沒有揭示的價格：證交所 `--`、櫃買 `0.00`。價差兩欄在沒有買價或賣價、買價 ≥ 賣價時空白。原始資料見 `memory/projects/crawler.md` 的交易所回補。
  - 日韓開盤（使用者：「組員要啥就給啥」）：`kospi_open_gap`、`n225_open_gap` = d 那根日K的 Open ÷ 前一個當地交易日收盤 − 1，放在 d 那列。這是 t 當天的值，台北約 08:30 才看得到（Yahoo 延遲 20～30 分），所以每天早上 t 那列是空白，隔天補上。CLAUDE.md 和 `memory/context/data-rules.md` 加了只限這兩欄的例外，`model_columns()` 遇到名字有 `open_gap` 的序列丟 `FeatureError`。韓國休市、Yahoo 補的假K棒（開高低收相同、量 0 或空）、韓國 10:00 才開盤的日子（每年第一個交易日從序列找；大學入學考試日列在 config 的 `features.open_gap.late_open`，2020～2026）留空白。另加 yfinance `^KS11` 序列 `kospi` 的 `kospi_ret_lag1`、`lag2`。2026-11-08 的研究：扣掉現有特徵後，開盤跳空和 50 檔平均「收盤比開盤」的相關在 ±0.02 以內，對 y 幾乎沒有新資訊。
  - 老師 S&P 500、Nasdaq 的「不退格」版本：老師 global 的 ^GSPC、^IXIC 第 d 列放的是 d 開盤前最後一次美股收盤（2026-11-08 和 Yahoo 逐列比對，Training 1,506 列、Live 45 列沒有一列放 d 當天或更晚的收盤）。現在的 `teacher_gspc`、`teacher_ixic` 跟著 ^TWII 的規則只用 t 之前那列，所以是「前前晚」的美股，比 `dji` 晚一天，照舊保留。另加 `teacher_gspc_fresh_ret_lag1/2`、`teacher_ixic_fresh_ret_lag1/2`（config 的 `features.teacher_fresh`），用 t 自己那列，公式和 `usd_twd_am` 一樣；沒有那列、-1、≤ 0 空白。`teacher_fresh` 只能放 ^GSPC、^IXIC，放別的丟錯。^TWII、^KS11、TX_OI 第 d 列是 d 當天收盤，照舊只能用 t 之前那列。
  - 實作時 Claude 定的細節：
    - fresh 往回數的是台股交易日，老師 Training 有 112 個台股日沒有 global 列，那幾格空白。所以 `teacher_gspc_fresh_ret_lag1` 有值的天數是 1,445，`teacher_gspc` 是 1,548。另一種做法是像 `teacher_gspc` 那樣數 global 自己的列，沒採用。
    - 開盤跳空的「前一根」跳過佔位K棒；t 那列一律設成空白，就算資料裡已經有 t 那根；算式寫成 (open − close) ÷ close，和其他報酬欄一致。
    - 價格不在升降單位的格子上時，檔數空白，相對價差照算。同一天同一檔出現在兩個交易所時空白，記在 notes。實際資料這兩種都沒有。
    - `val_pe_loss_lag1`、`quote_limit_up_lag1`、`quote_limit_down_lag1` 存成整數（`Int64`），CSV 寫 1、0 或空白。
    - 停牌（2026-11-09 審查後補）：交易所停牌那天照樣有列，收盤行情的開高低收是 `--`（櫃買 `----`）、成交股數 0，估值沿用前一天。照核准的「停牌空白，不往前找」，這種（日期, 代號）兩張表都當成沒有列，9 欄空白。2020-01～2026-11 有 21 個（證交所 20、櫃買 1 個：5347 2024-06-05），老師資料那幾天也都沒有這檔的列。改了之後，這 21 天的下一個交易日那列有 6 欄（估值 4 欄和漲跌停旗標 2 欄，共 126 格）從沿用的舊值或 0 變成空白，其他格不變。例：1101 2025-08-13 停止交易，2025-08-14 那列的 `val_ep_lag1` 原本是 08-13 沿用的 0.051308，現在空白。
    - 韓國晚開盤的「每年第一個交易日」取每年第一根和第一根成交量 > 0 的K棒，兩根都空白（2026-11-09 審查用合成資料發現：Yahoo 在 1/1 補一根量 0、開高低收不同的K棒時，原本會漏掉真正的第一天）。只影響 `kospi`。
    - 交易所的格子算不出來（算術溢位、看不懂的字串）時那張表的欄空白，不丟例外；大得離譜的價格（例如 `1e307`）檔數空白。交易所的檔每天由爬蟲照回應寫入，內容不能擋住每天的流程。
    - 欄的順序：鍵、stock、yfinance（照 `yfinance.tickers`）、老師 global、`usd_twd_am`、台指期、fresh 4 欄、開盤跳空 2 欄、交易所 9 欄、答案。`kospi_ret` 排在 `vix` 後面，所以 `teacher_vix` 到 `tx_night` 往後移 2 格，用位置取欄的腳本會錯。
  - 實際資料的檢查（2026-11-09）：買價 ≥ 賣價的列是 0。t = 11/06 那列有 15 檔價差空白，因為 11/05 這 15 檔跌停鎖住，沒有買價。
  - `kospi.csv` 的真資料（2026-11-09 研究模式抓的，2020-01-02～2026-11-06，1,678 根）：每年第一根都是 KRX 的第一個交易日，只有 2022 年 Yahoo 少了 01-03 那根，第一根變成 01-04，那天的跳空也設成空白（多擋一天，01-04 是正常 09:00 開盤）。量 0 的K棒只有 2 根（2024-09-12、2026-06-29），開高低收都相同，當成佔位K棒。大學入學考試日 2020～2025 的 6 天 Yahoo 都有K棒，照 config 設成空白。
  - 順帶確認：老師 Live 的 ^GSPC 45 列都對，對不上的只有 ^VIX（10/13 起大多不對），模型已經用 yfinance 的 `vix`。Yahoo 的 ^VIX 在美國假日（2026-05-25、09-07）也有K棒，`vix_ret_lag1` 那幾天會用到它。
- 2026-11-09 決定（使用者選了 Claude 建議的定義；程式寫在 worktree `/Users/ian/Desktop/ml-final-vixcnn`，11-11 推）：VIXTWN 和 CNN 恐懼貪婪各 2 欄，只進長表、不進 `model_columns`，排在交易所 9 欄後面，長表從 80 欄變 84 欄。來源見 `memory/projects/crawler.md` 的「VIXTWN、CNN 恐懼貪婪」。
  - `vixtwn_lag1`：i 那天 13:45 的 VIXTWN。`vixtwn_ret_lag1`：(v_i − v_前一天) ÷ v_前一天，前一天數 VIXTWN 自己的日子，和 `vix_ret_lag1` 同算法。i 沒有值就空白，不往前找。VIXTWN 是台股當天收盤的東西，只能用 i，不能用 t。官方檔從 2026-08-03 起，所以 t ≤ 2026-08-03 的列空白。
  - `fear_greed_lag1`：CNN 分數（0～100）。`fear_greed_chg_lag1`：和前一個美股交易日的分數差幾分。不用漲跌幅：2021-02-01 起最低到過 2.9（2025-04-08），1 分就是 30% 以上（2020-10-28 的 0.3 在 cnn.start 以前，不算）。用哪一天看量測：最後一天的分數在台北 t 日開盤前就定住，就和 `vix` 一樣用美國 i 那天（美股 i 休市就空白，`features.fear_greed.day: prev_day`）；不然用 t 之前最後一個美股交易日 e 的前一個美股交易日（`second_last`，使用者選的，現在的設定）。2026-11-10 量到：最後一天的點收盤後還會跟著下一個美股交易日的盤前變，開盤後 3～14 分鐘才定住（11-09 那點台北 11-10 13:00 是 31.714，19:03 是 33.229），11-05 以前的點 26 小時內沒有一點被改。所以定案用 `second_last`；s 那點的值是 e 開盤後約 10 分鐘的分數（大約台北 i 那天 22:40），不是 s 收盤的分數。量測細節在 `memory/context/open-questions.md`。通常比 `vix` 舊一天；台股休市期間美股開了 n 天時比 `vix` 新 n − 1 天（休一天時同一天，2023-01-30 那列新 7 天）。2021-02-01 以前不用。
  - 2026-11-09 晚上使用者選「空白」：s 是 CNN 檔裡最新的美股交易日時，那列空白。代表那天早上沒抓到 CNN，檔裡 s 的值是前一次抓的，那時還沒定住（審查找到：舊版只有連續兩天沒抓到才空白，只失敗一天時 t 那列會拿到還沒定住的值）。之後抓到新的、重寫最後兩個月時補上。真資料（11-09 的 data/raw 加 11-10 00:17 抓的 CNN 檔）上這條規則沒有改到任何一列。程式在 `fear_greed_values`，features.main 在 t 那列只進長表的欄空白時寫警告。
  - 美股交易日看 `features.fear_greed.us_calendar: dji`（道瓊有K棒、不是佔位K棒的日子）。審查 2026-11-09 找到的：CNN 每天 00:00 UTC 先建當天的點（值是前一天的），美國假日可能也會建（歷史裡沒有假日的點，可能事後拿掉）；用 CNN 自己的日期當日曆時，假日隔天那列會用到還在變的 e。`vix` 有假日K棒（2026-05-25、09-07），不能當日曆。選到的那天 CNN 沒有分數就空白，不往前找（不然 CNN 的檔停住時會一直沿用舊分數）。道瓊的檔不見時整欄空白。道瓊的檔沒更新（^DJI 抓失敗、留著舊檔）時不會空白，e、s 照檔裡最後一天往前選，用比較舊的分數，道瓊補上後重寫時改回來（第二輪審查 2026-11-09 判定只改文件：同一次 `dji_ret_lag1` 也會空白、爬蟲回傳 3，看得出來）。道瓊出現量 0、開高低收不同的假日K棒才會選錯日子，1,722 根裡沒有（審查判定不是 bug，沒加量 > 0 的條件：us_calendar 換成 sox、vix 這種沒有量的序列時日曆會整個變空）。
- 凍結的 6 個股票和 ETF 檔沒有空的 adj_close（2026-11-06 數過），所以決定 3 不會讓對照測試 (a) 和舊長表不同。
- 2026-11-06：lag2 定案用累積版。組員 notebook 寫 `the stock's own 2- and 5-day returns`，他用的 `panel_lag.csv.gz` 也是累積版。
- 2026-11-06：交易日照下面「交易日和 i」那條規則，取代「以 `phase2Days` 為準」。
- 2026-11-06：台幣匯率另外加一個和美股收盤同步的序列 `usd_twd_am`：台北日期 d 的值是 TWD=X 小時資料在台北 d 日 06:00 的報價（05:00 開始那根 1h 的 close）。組員要求「跟美股收盤同步、變成預測那天早上的指標」，使用者交給 Claude 決定。
  - 06:00 在美股收盤之後（冬令 05:00、夏令 04:00），07:10 的爬蟲一定抓得到，不用 08:00 後再抓。
  - 這個序列的 lag 用 t 自己的值當 cur：lag_k(t) = (x_t − x_{t 往回第 k 個台股交易日}) / 那個值。值在 t 開盤前就知道，不算用到 t 當天的資料。
  - 取法（Claude 2026-11-06 改定，使用者看過後同意開始寫）：取「結束時間 ≤ 台北 d 日 06:00」的最後一根 1h 的 close，最多往回 4 天。平常就是 05:00 開始那根。週一 05:00 那根不存在，會取到週五收盤，剛好和美股的 i（週五）對齊。2026-11-06 第一次連網後實測：存下來的 1h 裡 145 個週一（冬令 43、夏令 102）全部沒有 05:00 那根，TWD=X 一週在台北週一 07:00～09:00 才開始；原本寫的「只有冬令、紐約週日 17:00 開」不對，結論不變（例：11/02 取到 10/31 06:00 那根）。
  - 舊K棒的修正（2026-11-08 發現、使用者同意定義，2026-11-09 修）：1h 沒抓到、沿用 i 那天存的舊檔時，以前會取到 i 那根，`usd_twd_am_ret_lag1` 變 0.0、lag2 錯一天，有值所以中位數補值也不處理。現在選到的K棒除了 4 天內，還要晚於前一個交易日的 06:00 結束，不然 x_d 空白。爬蟲的 `has_value_t` 用同一條規則（見 `memory/projects/crawler.md`）。歷史 1h 期間的 673 天，x 一格都沒變；用本機現在的舊 1h 檔算 t = 11/09，x_t 從 33.066 變成空白，就是這個 bug。`tests/test_features.py` 的 `test_usd_twd_am_lookback_cap` 原本期望 1/22 有值，那正好是舊K棒的情況，改成空白，另加一個只測 lookback 的例子。
  - Yahoo 小時資料從 2024-01-22 開始。使用者 2026-11-06 決定更早的日子用 d 那根日K的 close 補。那根 close 是倫敦 d 日 00:00～01:00 那一小時的報價，換成台北是夏令 07:00～08:00、冬令 08:00～09:00，都在台股開盤前，但確切是哪一刻還沒驗證（第一次連網時對 2024 年以後的冬、夏各一天）。留空白的話，組員的 LogisticRegression 和 MLP 在訓練期間整段早於 2024-01-22 的 fold 會報錯。
  - 分界日取「config 的 2024-01-22」和「存下來的 1h 檔第一天」較晚的那個，Yahoo 的小時資料往前滾時也不會中間空一段。分界日起只用小時資料，取不到就空白，不退回日K。還沒有 1h 檔時（爬蟲第 4 步之前），分界日起整段空白，log 記一筆警告。
  - 舊的 `usd_twd`（日期 i 那根日K，台北 i 日 08:00）照樣保留。
  - 爬蟲要多抓並保存 1h 序列，Yahoo 只給大約兩年多，所以要合併舊檔、不能整個蓋掉（第 4 步的爬蟲計畫裡處理）。

## 資料來源

2026-11-06 從 data-collection `a806959` 搬來（這個分支的 commit `Move data-collection's data/ into this branch`），commit 後 8 個 tree hash 都核對過。2026-11-06 使用者決定刪掉沒有人讀的 `features/` 和 `transform/lag2`、`transform/lag5`（約 15 MB，和長表重複），原檔在 data-collection `a806959`：

| 來源 | 這個分支 | tree hash |
|---|---|---|
| `a806959:data/teacher/` | `data/raw/teacher/training/` | `61da1df7…` |
| `a806959:data/teacher_live/` | `data/raw/teacher/live/` | `50225f19…` |
| `a806959:data/teacher_live/` | `tests/fixtures/data-collection/teacher_live/` | `50225f19…` |
| `a806959:data/extra/` | `tests/fixtures/data-collection/extra/` | `281446bd…` |
| `a806959:data/transform/panel_lag.csv.gz` | `tests/fixtures/data-collection/transform/panel_lag.csv.gz` | blob `b8b905c5…` |
| `a806959:schema.json` | `tests/fixtures/data-collection/schema.json` | blob `19b27071…` |
| `0820473:data/extra/yfinance/` | `tests/fixtures/data-collection/yfinance_raw_0820473/` | `d2257778…` |

使用者 2026-11-06 決定整理資料夾：`data/raw/teacher/`、`teacher_live/` 改成 `data/raw/teacher/training/`、`live/`，`data/reference/data-collection/` 搬到 `tests/fixtures/data-collection/`。搬完 tree hash 都沒變。

- `data/raw/teacher/training/` 和 Training ZIP `7433b271…` 逐位元組相同（LF），`data/raw/teacher/live/` 和 Live ZIP `eea89fce…` 相同（CRLF）。
- `data/raw/teacher/live/` 帶金鑰連網跑時會被新的 Live 蓋掉，對照測試要用 `tests/fixtures/` 那份。
- `yfinance_raw_0820473/` 是還沒清理的 Yahoo 原樣，2026-11-04 07:35 UTC 抓的，資料到 8/31。
- `schema.json`、`extra/manifest.json` 裡的路徑是舊 repo 的（`data/extra/…`）。比對前要換：`data/teacher` → `data/raw/teacher/training`，`data/{extra,transform,teacher_live}` → `tests/fixtures/data-collection/…`。

## 交易日和 i（使用者 2026-11-06 決定照交接文件改）

現在有三套說法：
- data-collection 用寫死的 `LIVE_CLOSED_DAYS` 把 10/23 從日曆拿掉，所以 t = 10/27 的 i 是 10/22。
- 爬蟲的 `live_check` 取 `phase2Days` 裡早於 t 的最後一天；那天在 Live 裡沒填好，就退回最後一個填好的日子，並標 `prev_day_never_filled`、回傳 3。
- `src/features.py` 的說明和 `memory/context/data-rules.md` 寫「交易日曆以 `phase2Days` 為準」，Live 待定列只要 `phase2Days` 有就算交易日。如果 `phase2Days` 有 10/23，訓練特徵的 i 會是 10/23，每天預測時的 i 卻是 10/22。

決定的規則（爬蟲和 `features.py` 呼叫同一個函式）：
- 某天算台股交易日：那天老師個股資料填好了，也就是 100 檔裡至少 `crawler.min_stocks_filled`（90）檔的 `y` 是 0 或 1，而且 `etl:adj_open`、`etl:adj_close` > 0。
- i 是 t 之前最後一個這樣的日子。還是 `-1` 的列（10/23、當天早上 t 那列）不當 i，往回數 i−k 時也不算，那天 global 表的列也不用。
- 單一檔股票那天是 `-1` 或沒有列（停牌），就當這檔沒有那一列。
- `phase2Days` 只用來決定 t，不會讓日曆多出日子。
- config 加 `closed_days: [2026-10-23]`。那天之後出現數值就停下來（每日流程報錯，不是叫人看）。
- 這條規則下長表的日曆剛好 1,660 天（2020-01-02～2026-11-04，沒有 10/23），和 data-collection 相同。

Live global 表的 `-1`：`eea89fce` 只有兩列有。10/23 是 `^TWII`、`TX_OI`；11/05（t 那列，08:55 下載）是 `^TWII`、`^KS11`、`TX_OI`。07:10 時 `^VIX` 是不是 `-1` 沒量過，所以 6 欄（`^VIX ^IXIC ^GSPC ^TWII ^KS11 TX_OI`）的 `-1` 都當缺值，一格一格判斷。

## lag 的公式

- i：t 之前最後一個台股交易日。close：股票和 ETF（TSM、NVDA、0050、0052、0055、006201、老師個股）用 `adj_close`，其他用 `close`。i−1、i−2 往回數這個序列自己的列。
- lag_k(t) = (close_i − close_{i−k}) / close_{i−k}。函式寫成可以帶任意 k，正式只產 k = 1、2，對照測試用 k = 2、5。
- 序列在 i 那天沒有K棒就留空白，不往前找；不能用「最後一根 ≤ i」，因為 08:30 後才跑時爬蟲會留著舊檔。兩個端點任一是空的或 ≤ 0 也留空白（WTI 2020-04-20 是 −37.63，^IRX 2020-03 有負值）。
- 台指期的公式見「使用者的決定」的台指期那條。
- 寫成 `(cur − base) / base`。用 `cur / base − 1`（pandas `pct_change`）時 76,675 個市場格裡有 74,262 個最後一位不同，最大差 4.4e-16；那樣的話對照容差設成絕對值 1e-15。

測試值（data-collection 的凍結資料，算過兩次）：

| 序列 | t | i | lag1 | lag2 |
|---|---|---|---|---|
| 2330 | 2026-11-04 | 11/03 | −0.015021459227467818 | −0.03164556962025325 |
| 2330 | 2026-10-27 | 10/22 | −0.014462809917355376 | −0.00831600831600827 |
| sox | 2026-11-04 | 11/03 | 0.02634213957551902 | −0.008270284379704918 |
| sox | 2026-10-27 | 10/22 | −0.06723524369545192 | −0.04890450322862169 |
| sox | 2026-09-08 | 9/07（美國勞動節） | 空白 | 空白 |
| teacher_vix | 2026-10-27 | 10/22 | −0.10418906802463328 | −0.10418906802463328 |
| 2327 | 2022-11-01 | 10/31，i−1 是 10/19（停牌） | 0.09880239520958087 | 沒算 |

teacher_vix 的 lag1 和 lag2 一樣，因為 Live 的 10/20、10/21 都沿用 18.62。2327 在 2022-10-20～10-28 停牌，t = 10/21～10/31 的 lag 都是空白。

副作用：
- 老師 global 的 `^GSPC`、`^IXIC`、`^VIX` 每一列已經是前一個美股交易日的值，所以 `teacher_gspc` 的 lag1 比 yfinance 美股的 lag1 晚一天（和前一列 `dji` lag1 相關 0.867，同一列只有 −0.176）。
- 只用 lag1、lag2 時，台股連休中間那幾天的美股報酬不會出現在任何一列。以 SOX 來說，這種日子從 20 天變成 57 天。
- 停牌或休市之後，lag1 會跨過整段空檔，分布有長尾。
- TWD=X 日期 d 那根的 close 是台北 d 日 08:00 左右的報價（2026-11-06 用 1h 資料對過：11/04 日K 32.733，小時資料 08:00 是 32.73）。用 i 那根時，匯率比美股舊將近一天。Yahoo 的 1h 資料從 2024-01-22 開始。

## yfinance 清理規則 R0～R5

照順序做，和舊爬蟲（data-collection `crawler.py:493-625`）一樣。紀錄裡的價格是 Yahoo 原始單位，還沒做分割修正。刪掉的列要整列拿掉，不能留成空白的一列：實測留空白時，7 個序列有 295 個 lag2、lag5 格和長表不同。

### R0 篩掉不能用的列（全部序列）

- None、bool、NaN、inf 當空值。close 是空的列整列拿掉（爬蟲把 NaN 存成空字串，所以 `features.py` 要自己做）。
- 期貨和殖利率以外的序列出現 close ≤ 0：舊程式讓整個序列失敗、沿用舊檔。日期重複也一樣。
- 依日期排序。

### R1 壞報價（全部 19 個序列）

low、high 都有值而且 low ≤ high 時才檢查。close < low − 0.005 × |low|，或 close > high + 0.005 × |high|（嚴格不等式），刪掉這一列。只看 close。

### R2 債市假日的平盤K棒（只有 ^TNX、^IRX）

開高低收相同（不看 adj_close 和成交量），而且日期是哥倫布日（10 月、週一、8～14 號）或退伍軍人節（11/11；週六提前到 11/10，週日延到 11/12），刪掉。下一個是 2026-11-11（週三），在 Phase 2 期間。

### R3 佔位K棒（只有股票和 ETF：TSM、NVDA、0050、0052、0055、006201）

依日期掃 R1、R2 留下的列，第一列一定保留，只看開高低收相同的K棒：
- 成交量是 0 或空的，而且 close 和前一個「保留下來的」列的 close 完全相等，刪掉。連續停牌時，每一根都和停牌前最後一根比。
- 其他情況：取前 21 個保留下來的列裡不是 0 的成交量，排序後取 `recent[len // 2]`（偶數個時是上中位數，和 `statistics.median` 不同）。成交量不是 0 而且小於這個數的 1%，刪掉（不完整的K棒）。
- 成交量 0 但 close 和前一列不同的平盤K棒，兩條都不成立，保留。

### R4 台股分割（股票和 ETF）

看相鄰兩個保留下來的列 (prev, cur)：
- ratio = prev.close / cur.close，n = round(ratio)。2 ≤ n ≤ 50 而且 |ratio − n| / n < 0.03，factor 是 n。不成立時用 1/ratio 再檢查一次，成立的話 factor 是 1/n（反向合併）。任一價格是空的或 ≤ 0 不算。
- adj_close 的比值也要算出一模一樣的 factor。
- 代號不是 `.TW`、`.TWO` 結尾（TSM、NVDA）只記錄，不改資料。
- 台股：分界那列之前的每一列，開高低收和 adj_close 都除以 factor，成交量乘以 factor。分界那列和之後不動。往下掃時用修正過的值。

### R5 分割前的股利調整乘回去

R4 修正台股之後立刻做（Yahoo 對分割前的除息只調了約 1/n）：
- r_t = adj_close / close（用除過 factor 的值），範圍是分界之前的列。分界前不到 2 列，或有空值、≤ 0，直接結束。
- level 從分界前一列的 r 開始，那一列的 adj_close 不改。
- 從分界前第二列往回到第一列：step = 1 − r_t / r_{t+1}。step > 1e-5 時 fixed = min(step × factor, 0.95)，level 乘上 (1 − fixed)，記一筆 {ex_date = 下一列的日期, yahoo_fraction = step, rescaled_fraction = fixed}；否則 level 乘上 r_t / r_{t+1}。
- 每一列的 adj_close 設成 close × level。

### 測試資料

凍結的 `tests/fixtures/data-collection/extra/manifest.json` 有 62 筆紀錄，每筆都有原始值：
- 壞報價 2：usd_twd 2020-12-08、2024-08-28。
- 債市假日 24：^TNX、^IRX 各 12 天（2020-10-12、2020-11-11、2021-10-11、2021-11-11、2022-10-10、2022-11-11、2023-10-09、2024-10-14、2024-11-11、2025-10-13、2025-11-11、2026-10-12）。
- 佔位 29：成交量 0 的 26 筆（006201 10、0050 7、0052 7、0055 2，含 2026-10-23 颱風假的 4 筆），不完整的 3 筆（0050、0052、0055 都在 2024-11-20）。
- 分割 1：0052，分界 2025-11-17，factor 7。2025-11-14 原始 (O 248.3000030517578, H 249.64999389648438, L 248.0500030517578, C 248.5, adj 242.5469207763672, V 5021929)，修正後 (35.47142900739397, 35.66428484235491, 35.43571472167969, 35.5, 34.6495601109096, 35153503)。
- 股利乘回 6：都是 0052（yahoo_fraction → rescaled_fraction）：2020-04-22 0.0042352 → 0.0296467、2021-04-20 0.0011495 → 0.0080467、2022-04-20 0.0120857 → 0.0845996、2023-04-21 0.0053832 → 0.0376827、2024-04-18 0.0057143 → 0.0400004、2025-04-23 0.0030159 → 0.0211113。分割後的 2026-04-20 是 Yahoo 自己調的，不動。

要保留的反例（寫成單元測試）：
- usd_twd 2020-03-31、006201 2021-09-13：close 在高低區間外，但只超出 0.358%、0.368%。
- ^TNX 2023-11-10：日期符合退伍軍人節，但不是平盤。
- 0050、0052 的 2025-04-07、04-10：跌停平盤，成交量正常。
- 006201 2023-11-01：平盤，成交量 1000，是中位數的 5%。
- 0055 2020-09-18：close 等於前一列，但成交量 10188，是中位數的 25%。

## 清理細節的決定（使用者 2026-11-06）

1. close ≤ 0（期貨、殖利率以外）和日期重複：只丟那一列（重複的日期留最後一列），每筆記在清理紀錄。和舊程式不同，舊程式讓整個序列失敗。
2. 中位數各用各的：R3 照舊用上中位數 `recent[len // 2]`，結果才和凍結資料一樣；爬蟲的期貨防線維持 `statistics.median`。兩個函式分開寫，不共用。
3. adj_close 空的那一列當缺值：那天的價格空白，用到它的 lag 留空白，不退回用 close。
4. 反向合併（使用者交給 Claude 決定）：照樣修正價格和成交量，但不做 R5 的股利乘回，只在清理紀錄記一筆。目前沒有實例。
5. Yahoo 修好 0052 的歷史時，R4 不觸發，資料本來就對。使用者要全自動、不要叫人看：每天的流程沒有要人確認的步驟。對照測試 (b) 只在第一次連網時跑一次，分割那筆不見了、但價格和修正後一致時自動算通過。

## 對照測試

### (a) 離線

- 輸入：`tests/fixtures/data-collection/extra/yfinance/` 的 19 個凍結檔、`data/raw/teacher/training/`、`tests/fixtures/data-collection/teacher_live/`（只取 ≤ 2026-11-04，10/23 依交易日規則拿掉）。
- 清理開著跑，要 0 筆紀錄（凍結檔再清一次是 0 筆，位元組不變）。
- 日曆剛好 1,660 天，沒有 10/23。
- `stock_ret` 和 24 個市場序列的 lag2、lag5，和 `transform/panel_lag.csv.gz` 逐格相同，空白位置也一樣。用 repr 字串比，或 `pandas.read_csv(..., float_precision="round_trip")`。
- 快速檢查 lag2 有值的列數：sox 1603、usd_twd 1654、us13w 1585、etf_0050 1649、n225 1552、teacher_* 1545。
- lag1 沒有對照答案，用上面的測試值。

### (a2) 離線，測清理

- 輸入：`yfinance_raw_0820473/`（到 2026-08-31）。凍結資料沒有之後才加的 `vix.csv`、`kospi.csv`，`raw_0820473` fixture 只跳過這兩個（`LATER_SERIES`），其他檔不見就失敗，不會默默少比（2026-11-09）。
- 清理後和凍結檔 ≤ 2026-08-31 的部分比：日期、開高低收、成交量完全相同，adj_close 相對差 ≤ 2e-6（實測 8.2e-7）。
- 紀錄 56 筆，日期和規則都相同：壞報價 2、債市假日 22、佔位 25、分割 1、股利 6。和 62 筆差的 6 筆是 2026-10-12 的兩筆債市假日和 2026-10-23 的四筆佔位K棒。

### (b) 第一次連網之後

- `data/raw/yfinance/` 清理後，取 ≤ 2026-11-04 和凍結檔比。日期集合、開高低收和成交量要相同，≤ 11/04 的 (序列, 日期, 規則) 剛好是那 62 筆。
- adj_close 不比水準，比 lag2：絕對差 ≤ 5e-6（實測最大 9.85e-7），跨過 11/04 之後新除息日的格子除外。
- close 有任何不同就當成 Yahoo 改了歷史，給人看，不放寬容差。
- 11/04 之後的新紀錄（例如 2026-11-11 退伍軍人節）可以接受，記下來。
- 接下來可能的除息（推論，照 2025 年）：0055、006201 約 11 月下旬，NVDA 約 12 月初，TSM 約 12 月中，0050 約 1 月下旬。

## 組員的特徵

- 組員的 notebook：`notebooks/feature_switch.ipynb`（使用者放進來的，沒進 Git）。讀他自己用 `build_dataset.py` 產生的 `train_data_v2.csv`，lag 欄來自 data-collection 的長表。資料搬過來後，他的腳本要改讀新位置。
- 他的 36 個特徵裡，技術指標 9、老師原始欄位 14、前一天報酬 3 是他自己從老師資料算的；從 GitHub 拿的只有 lag 欄。
- notebook 裡的集合：`us_tech`（sox、tsm_adr、nvda、teacher_ixic 的 lag2）、`key_lag2`（us_tech 的 4 個再加 teacher_gspc、teacher_vix、etf_0050、usd_twd，共 8 個，目前選這個）、`all`（24 個市場序列的 lag2、lag5）、另外 `USE_STOCK_LAG` 開關的 `stock_ret_lag2`、`stock_ret_lag5`。
- 2026-11-06 組員給的 12 個指標見「使用者的決定」。
