# 團隊每日資料：live-data

使用者於2026-11-03暫定程式與資料全部公開；實際可見性以GitHub設定為準。程式與排程在 `dev`／`system-completion`；研究在 `deep-research`。本分支存實際取得的教師、Live及額外市場資料，保留修訂與來源時間，不放帳密或cookie。教師ZIP與Yahoo原始資料的公開再散布授權尚未核實，此處不代表已取得來源授權。

資料是否真的更新，以 `catalog/latest.json` 指向的內容、來源的 `fetched_at` 及 Git commit 為準；不是看到本 README 就代表排程成功。研究特徵標記 `research_assumption`，不等於已取得歷史發布／修訂版本的證明。真正的正式模型、提交回執與每日運作驗收另看程式分支的 STATUS。

## File tree

```text
live-data/
├── README.md                      # 你正在讀：資料位置、特徵與lag的意義
├── catalog/
│   ├── latest.json                # 目前成功版本的pointer與hash
│   └── versions/<sha256>.json     # 不可變catalog；各來源及歷次取得紀錄
├── manifests/<source>/<hash>.json # 可攜來源manifest：實際取得時間、hash、覆蓋／缺值
├── objects/<sha256>.<ext>         # 原始ZIP／CSV／JSON；相同內容只存一次
├── features/
│   ├── stock_lags.csv.gz          # 50股×目標日期的個股輸入；沒有當日label
│   ├── market.csv                # 市場return、VIX／OI及missing／age追溯欄
│   ├── market_report.json        # 原生交易日、時間假設與排除原因
│   ├── schema.json               # 精確欄位／公式／單位／lag定義
│   ├── lineage.json              # 產物hash、原始版本與實際取得時間
│   ├── build_status.json         # 這個catalog的匯出成功／失敗狀態
│   └── research-frozen-v1/       # 固定10/27研究版本；不是每日latest
├── labels/
│   └── stock_outcomes.csv.gz      # 獨立當日y／盤中return；pending不當真值
└── runtime/                      # 部署啟用後的私有持久狀態；不含登入資訊
```

樹中產物以實際檔案及lineage為準；`runtime/`僅在部署寫入狀態後出現。資料儲存採內容hash，不將來源主機的絕對路徑當成隊友的路徑。

## 怎麼取得與其他branch完全相同的版本

先在程式分支取得完整程式，再由 `ml_financial_prediction/` 執行：

```bash
# 公開repo可匿名下載；請明確加上--allow-public-data。實驗應固定回傳的40碼commit。
uv run --locked --no-sync python scripts/fetch_live_data.py \
  --repo jiangjiangian/ml-final-2026-fall \
  --revision live-data --runtime-dir /private/finpred-runtime --with-features --allow-public-data

# 可重現實驗：把live-data替換成已記錄的40碼commit，避免默默換成明天的資料。
```

消費端先核對catalog、每份manifest及原始物件hash，再重建本機runtime。`source_fetched_at`與隊友的`received_at`分開，不將下載到隊友電腦的時間回填成來源當時發布。也可以另開worktree瀏覽本分支；切換程式branch不會自動替你鎖定資料版本。

## 資料來源與用途

| 來源ID | 內容 | 能做什麼／限制 |
|---|---|---|
| course-training | 教師固定歷史ZIP，100股及global表 | 歷史基底；Top50名單從ZIP的info核對，不能只用global日期inner join |
| course-live | 後續日期及修訂ZIP | 更新歷史／新日期；未完成值保留，不能以Live取代固定包 |
| course-template | 官方預測模板 | 核對日期、50股、順序與輸出格式；不是價格feature |
| yahoo-ixic／gspc／twii／ks11 | Nasdaq／S&P500／台股／韓股指數原生歷史 | 原生session先算return，再按台灣cutoff對齊；最新bar可能尚未收盤 |
| yahoo-sox | 半導體指數SOX | 指數本身；不混成SOXX／SMH ETF |
| yahoo-tsm_adr／nvda | TSM ADR／NVDA個股 | 海外股票return，不稱經濟指數；尚非認證total return |
| yahoo-vix／cboe_vix | 波動率指數歷史 | 水準、點數變化；不是可交易VIX資產return |
| twse_twii | 官方台股指數當月窗口 | 官方原始資料交叉核對；不能冒稱2020起完整歷史 |
| fred_usd_twd | DEXTAUS，TWD per USD | 上升表示台幣貶值；紐約觀測與實際發布日期不同，須處理修訂 |
| fred_us10y | DGS10，美國10年殖利率，百分比年率 | 使用水準／基點差，不套價格百分比return |
| twse-sectors | 電子／半導體／金融保險三類指數水準 | 持續收集；只有單一歷史水準時不能計算完整產業return |

以上是取得的來源種類；每一輪是否成功、最後來源日期與缺值請看catalog。Yahoo公開介面沒有本專案的服務保證；採集失敗保留前個成功版本並記錄partial，不假裝全部來源已齊。

## Lag與return：先看這個例子

假設週一台北08:10預測，`k`是該cutoff前合法可用的最後來源session。`ret_1s = close[k]/close[k-1]-1`，不是「直接把表格shift一列」。如果前一個台股日是週五，來源市場又遇休市，來源session可能更早。`age_hours`會告訴你資訊多舊。

`ret_5s = close[k]/close[k-5]-1`，代表五個**來源交易session**，不是五個日曆日。價格100→102的return是0.02，即2%；下跌到98為-0.02。先在完整原生序列計算，再依可用時間對齊；不能將多國inner join後的相鄰列當作同一交易日跨度。

固定教師global的美股欄位已存在位移；台股／韓股欄位可能含同日收盤。這些欄位不能盲目再shift(2)或直接當盤前輸入。市場特徵由原始來源重建並保存日期、available_at與假設。

## 七個個股feature

令 `u` 為該股在目標日之前最後一筆觀測、`v`為更早一筆。前筆為pending時保留缺值，不跳過它偷偷改成更早的「上一筆」。

| 欄位 | 精確意義 | lag／單位 |
|---|---|---|
| stock_prev_intraday_return | `adj_close[u]/adj_open[u]-1` | 上一**觀測列**的盤中return；不是預測日return |
| stock_return_between_observed_rows | `adj_close[u]/adj_close[v]-1` | 前兩筆觀測之間的return；缺日期時不能冒稱native1s |
| stock_prev_log_volume | `log(1+volume[u])` | 前筆成交股數的對數，減少量級差異；不是return |
| stock_prev_rsi | 前筆RSI | 前筆技術指標；最新歷史計算版本仍有可用性限制 |
| stock_prev_atr_fraction | `ATR[u]/adj_close[u]` | 前筆波動幅度相對價格；非報酬方向 |
| stock_prev_sma_deviation | `adj_close[u]/SMA[u]-1` | 前筆價格偏離均線的比例 |
| stock_previous_observation_gap_days | `target_date-u`的日曆天數 | 明示觀測間隔；週末／休市也計天，不假裝每日皆有資料 |

所有分母須為合法正值。缺資料保留空值，不用未來補值；同一目標日的股票全集保持50股。缺label不代表可以刪除該股可見的feature。

## 市場feature與擴充研究

| 欄位／家族 | 定義 | 使用界線 |
|---|---|---|
| ixic_ret_1s／gspc_ret_1s／twii_ret_1s／ks11_ret_1s | 截止前最新來源session的單期價格return | 各自原生交易日；台股／韓股不使用預測日收盤 |
| sox_ret_1s／tsm_adr_ret_1s／nvda_ret_1s | 同上，依序為SOX、TSM ADR、NVDA | TSM／NVDA是個股；不直接解釋成台股盤中必漲 |
| vix_level／vix_change_points | 最新VIX水準／與前一來源session相減 | 指數點差；不是價格資產return |
| tx_foreign_net_oi／tx_foreign_net_oi_change | 外資淨未平倉口數／有號差分 | 未有足夠來源／逐欄有效性證據時保留缺值，尤其不能把-1一律當真值或缺值 |
| `<source>_source_session_date`／available_at | 被選用版本的來源日期／可用時刻 | date不是發布時間；歷史close＋2小時是明示研究假設，不是量測證明 |
| `<source>_age_hours`／is_missing／is_new_session_since_previous_tw_target | 資訊年齡、缺值、相較前一台股目標日是否有新來源session | 休市、來源中斷與正常延續分開；不能因休市而把同一衝擊當成每天新訊息 |
| 擴充F1：1／5／20-session return | 在原生序列取各自跨度 | 精確欄名／版本見研究輸出的frozen_schema；不默默更換群組選最好分數 |
| 擴充F2：20-session volatility、age／mask | 過去return的波動與來源新鮮度 | 僅過去窗口；不能centered rolling或全資料fit |
| 擴充E04：FX return／殖利率bp差 | FX固定TWD/USD報價；殖利率4.0→4.1為10bp | FRED發布與vintage未認證；研究延遲假設與正式可用性分開 |

擴充研究產物不自動加入正式模型；本分支的 `schema.json`／`lineage.json`列出本次**實際匯出**欄位。市場負結果仍保留，不能因多抓指數就宣稱模型變好。

## Labels與正式使用

目標為`y=1{adj_close>adj_open}`；盤中return=`(adj_close-adj_open)/adj_open`。它們只在獨立labels檔，不能接回當日features。pending不訓練。官方50檔二元分數為`mean((2*prediction-1)*return)`；accuracy與排名僅輔助。

正式使用還需逐來源時間證據、相容已驗證模型、截止前推論、提交與有效回執。研究表、Notebook成功或CI綠燈都不能取代這些證據。來源採集可以先每天運作，模型尚未合格不應停止保存新快照。
