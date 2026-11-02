# live-data 每日衍生資料與 lag 定義

原始資料獲授權放在私人 `live-data` 分支；本文件及產生器本身留在程式分支。發布端先檢查 repository 為 private，產生器不執行 Git push、不搬移登入狀態。這些重建歷史表仍為 `research_assumption`，不宣稱已取得歷史發布／修訂證據。

```text
live-data/
├── catalog/                 # 不可變 raw 版本與 latest 指標
├── manifests/               # 可攜來源 manifest；真實取得時間
├── objects/                 # 內容 hash 去重的原始 ZIP／JSON／CSV
├── features/
│   ├── stock_lags.csv.gz    # 每目標日完整50股；七個個股滯後值，沒有當日label
│   ├── market.csv           # 一日一列；M0及SOX／TSM ADR／NVDA，另附來源時間／missing
│   ├── market_report.json  # 可用性假設、缺值與原生日曆的摘要
│   ├── schema.json         # 每欄公式、單位、lag與缺值政策
│   ├── lineage.json        # 原始來源／catalog／程式與每份輸出的hash
│   └── build_status.json   # 本次匯出成功／blocked／失敗，避免誤讀舊CSV
└── labels/
    └── stock_outcomes.csv.gz # 當日y與盤中return；pending留空且保留status
```

`t` 是欲預測的台股日期，`obs-1` 是該股在 `t` **之前最後一筆來源觀測列**；`s` 是某個來源市場在cutoff前最新可用的原生交易session。這兩種索引不能混用：缺列時前一觀測可能隔多個交易日。全表不套固定 `shift(2)`。

| 個股欄位 | 公式 | lag／單位 |
|---|---|---|
| stock_prev_intraday_return | C[obs-1]／O[obs-1]−1 | 前一觀測日的盤中報酬，小數 |
| stock_return_between_observed_rows | C[obs-1]／C[obs-2]−1 | 相鄰觀測列的收盤報酬；不能稱原生一日return |
| stock_prev_log_volume | log(1＋成交股數[obs-1]) | 前一觀測列，log股數 |
| stock_prev_rsi | RSI[obs-1] | 前一觀測列，沿用來源RSI尺度 |
| stock_prev_atr_fraction | ATR[obs-1]／C[obs-1] | 前一觀測列，價格比例 |
| stock_prev_sma_deviation | C[obs-1]／SMA[obs-1]−1 | 前一觀測列，相對均線偏離 |
| stock_previous_observation_gap_days | t−date[obs-1] | 日曆日間隔，並非交易session數 |

個股日期全集是課程實際觀測日期的聯集，不假裝它是獨立認證的TWSE日曆。每一日保留50股，上市前／缺列／pending造成的空值不補未來資料。前一觀測若仍pending，不跳過它改用更早完成值；數值lag保留缺值。當日結果改變，不影響當日feature。

| 市場欄位 | 公式／含義 | 時間限制 |
|---|---|---|
| ixic／gspc／twii／ks11／sox／tsm_adr／nvda_ret_1s | P[s]／P[previous_native_session(s)]−1 | 各自完整原生日曆先計算，再as-of對齊；TSM與NVDA是股票，非指數 |
| vix_level | VIX[s] | 波動指數點數 |
| vix_change_points | VIX[s]−VIX[previous_native_session(s)] | 點數差，不是可交易VIX資產return |
| tx_foreign_net_oi／tx_foreign_net_oi_change | 有號淨部位水準／口數差 | 日期與sentinel證據未齊，保持缺值；禁止一般百分比return |
| *_source_session_date／*_source_available_at | 真正採用的來源session及可用時刻 | 歷史時刻為明示研究假設，不冒充實際發布 |
| *_age_hours | cutoff−選中來源available_at | 描述資訊陳舊，休市不自動等於資料錯誤 |
| *_is_missing | 必要輸入或其原生前一session缺值 | 保留目標日，禁止bfill或跳過缺期 |
| *_is_new_session_since_previous_tw_target | 是否有新來源session | 首個目標為未知；來源修訂不是新session |

市場歷史沿用 `exchange_calendars` 與收盤＋2小時供應商延遲的**研究假設**；VIX日曆仍是NYSE＋15分鐘proxy。查詢只取 `available_at <= cutoff` 的來源，08:10台北為專案提案，正式截止09:00。實際取得時間逐筆保留在lineage；今天下載不證明歷史當時可得。

兩個價格計算出一次return，不是「lag2」；例如110／100−1＝0.10＝10%。lag2表示更早的一次return；兩期累積return則是P[s]／P[s−2]−1。除權息／分割與修訂政策仍須個別核實。

FRED匯率／殖利率與單日產業快照在這個日常匯出中只標raw，沒有混稱已完成可回測的特徵。獨立的有限預算研究擴充由 `research_expansion.py` 管理；匯率固定TWD per USD報價，殖利率用bp差，單日產業水準無法計歷史return。

```bash
# 私有raw先由fetch_live_data.py按指定Git SHA還原，再執行；不能供public目的地。
python scripts/build_shared_features.py --runtime-dir /private/finpred-runtime \
  --bundle-dir /private/live-data-checkout --allow-research
```

gzip的mtime固定為0，相同輸入會輸出相同bytes；lineage列出每份檔案SHA256與程式hash。若缺Training或未opt-in研究模式，舊的managed衍生表會失效並回報blocked，raw採集仍可獨立成功。來源hash／schema錯誤會停止匯出，`build_status.json`記錄失敗；舊CSV可供已固定的舊實驗追溯，但不能當本次更新成功。

消費端先用`finpred.data.shared_features.validate_shared_feature_exports(bundle_root)`，它要求成功status、lineage內容hash、目前raw catalog版本及全部CSV／schema hash一致。不能只見CSV存在就讀入最新模型。這個檢查只證明交付一致，不認證歷史發布／vintage，也不訓練、升級模型或提交預測。
