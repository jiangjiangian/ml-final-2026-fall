# API 與額外市場資料清單

查核：2026-10-27，Asia/Taipei。本檔區分「文件中提過」「原始資料已可下載」「可作歷史盤前特徵」；三者不是同一狀態。現有紀錄找到了同學提及的 TWSE、TAIFEX、FinMind、TWSE MIS、GDELT，無須使用者重貼既有清單；沒有聲稱所有介面或私人token都已具備。

## 已實作的第一批公開來源

`configs/sources.json` 是來源／候選清單；CLI 按 `adapter_id` 選用 `src/finpred/ingestion/external.py` 的固定、已核實介面。它不是啟用中的排程，也未把JSON設定自動當作可用時間政策。

| adapter_id | 資料與已核實介面 | 本次實讀覆蓋／單位 | 特徵政策與限制 |
|---|---|---|---|
| cboe_vix | [Cboe官方VIX CSV](https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv) | DATE與OHLC欄，1990起，指數點；舊cdn.cboe.com網址會導向此cdn-api網址 | 水準＋點數差；不是持有VIX的投資報酬。日日期不等於發布時間，修訂與原生日曆證據待補 |
| twse_twii | [TWSE MI_5MINS_HIST](https://openapi.twse.com.tw/v1/indicesReport/MI_5MINS_HIST) | 民國年日期，開高低收；本次為2026年10月的多日窗口 | 先驗證完整來源session再算單期報酬；此網址尚未證明能任意回補2020起歷史，不以窗口缺舊列當刪除 |
| fred_us10y | [FRED DGS10 CSV](https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10)／[定義](https://fred.stlouisfed.org/series/DGS10) | 1962-01-02～2026-10-23，Percent，年率百分比 | **新增**US10年期公債constant-maturity yield；用水準＋bp差。4.0→4.1為10bp，不用價格百分比報酬 |
| fred_usd_twd | [FRED DEXTAUS CSV](https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXTAUS)／[定義](https://fred.stlouisfed.org/series/DEXTAUS) | 1983-10-03～2026-10-23，Taiwan Dollars to One U.S. Dollar | **新增**TWD/USD報價（TWD per USD）；數值上升表示台幣貶值。官方說明為紐約中午買入匯率，不能冒充台北外匯收盤；FRED可能延後發布／修訂，需補證據 |

四個下載介面皆以一般TLS驗證實讀HTTP200，CSV／JSON內容可解析；不需為這四個公開下載另給API key。FRED的 `.`／空欄保留為缺值，並保留其日期；不能把它們刪掉後假稱剩下相鄰列是一個交易session。FRED整份最新歷史值不自動具有歷史vintage或發布時間。

同一實作CLI已實際執行成功，快照在 `/workspace/shared/downloads/external/`，各來源manifest在 `<adapter_id>/manifests/`：

| adapter_id | 列數／缺值 | 實際日期範圍 | payload SHA256 |
|---|---:|---|---|
| cboe_vix | 9302／0 | 1990-01-02～2026-10-26 | `8e67801e46bab11ab543ac8d575544db4e8cd6fd7e4c7e9dc419b498de8a77ff` |
| twse_twii | 15／0 | 2026-10-01～2026-10-22 | `6800c13392d34ae27a0dc9327b88d28f92f2112e369bf266a819116122f27ee1` |
| fred_us10y | 16909／721 | 1962-01-02～2026-10-23 | `27cfa7aee0c2427ad1ccd53f19d99f2b9feaaab21a1847623fed62c9d7960efc` |
| fred_usd_twd | 11235／727 | 1983-10-03～2026-10-23 | `a1d3ce1702bf41b88e027e706a9a995126a223750f93821f54a085e6b3f86f33` |

這些最大日期只是此次raw覆蓋，未經發布排程與日曆核對，不能單以落後一天或數天就判定來源停更。

從專案目錄執行：

```bash
uv run python scripts/download_external_data.py \
  --source cboe_vix --source twse_twii \
  --source fred_us10y --source fred_usd_twd \
  --out-dir /workspace/shared/downloads/external
```

此命令使用 `requests`、有界timeout與GET失敗重試、TLS驗證、內容大小上限、嚴格日期／數值／schema驗證，再共用 `snapshot_bytes` 保存checkout外的content-addressed原始快照與每次取得manifest。相同內容共用同一原始物件，各次仍各有取得紀錄；改值保留新hash，不覆蓋舊版。下載失敗回非零退出碼；沒有把HTTP200或正常解析當成歷史特徵ready。manifest中的 `provider_series_id` 保留FRED查詢的序列識別；不記錄帳密、cookie或token。

## 同學提過、仍待逐項接入的來源

| 來源 | 已有連結／用途 | 目前狀態 |
|---|---|---|
| [TWSE OpenAPI](https://openapi.twse.com.tw/) | 台股行情／指數／類股等；有歷史命名端點 | 已有一個raw adapter；不把曾提143端點當固定數量，新增類股需核對當前schema、原生日期與可回補範圍 |
| [TAIFEX一般盤](https://www.taifex.com.tw/cht/3/futContractsDateView)／[夜盤](https://www.taifex.com.tw/cht/3/futContractsDateAhView) | 外資期貨部位及夜盤 | 文件已有，下載adapter與完整歷史待做；一般盤OI與夜盤交易多空差不能混用，夜盤歸屬日另核對 |
| [FinMind](https://finmind.github.io/)／[方案](https://finmind.github.io/Pricing/) | 台股、類股、匯率、利率等候選 | 文件已有，尚未宣稱token存在／資料集權限齊全；若選用，採 `FINMIND_TOKEN` 環境變數。免費額度、資料清單與禁止原始再散布按當前方案核對 |
| [TWSE MIS](https://mis.twse.com.tw/stock/index?lang=zhHant) | 未來盤前快照候選 | 歷史快照API未核實，動態頁可開不等於取得了完整歷史 |
| [GDELT](https://gdeltproject.org/) | 新聞量、tone、公司提及候選 | 尚未做adapter；DOC查詢窗口與GKG歷史檔分開，須處理當時收錄時間、重複文章與公司辨識 |
| [Nasdaq SOX](https://indexes.nasdaq.com/Index/Overview/SOX) | 優先補半導體指數 | 定義已有；穩定且允許自動化的完整歷史下載／授權未核實；SOXX／SMH是ETF proxy，不冒充SOX |
| TSM ADR、NVDA | 後續海外個股候選 | 是股票而非經濟指數；來源、分割／配息調整、歷史與發布時間待選，不假定教師資料包含它們 |

## 與04:00～09:00自動化的交接

先以同一CLI建立可重跑raw snapshot，再接標準化、可用時間與特徵層。04點是使用者希望的操作窗口起點，並非所有來源保證發布時間；美國正常收盤在台灣夏令04點／冬令05點，供應商另有延遲。FRED紐約觀測日與實際發布日不可混成一個日期。

來源層交付原始快照、hash、fetched_at、欄位／缺值／覆蓋audit；不把fetched_at、HTTP Last-Modified或當前網站更新時間填成更早歷史available_at。正式歷史市場表需再補每來源完整日曆、發布／vintage證據及時間對齊抽查；當前輸出明示 `raw_downloaded_needs_publication_evidence`，`historical_features_ready=false`。模型訓練及每日排程由上層工作流負責，這些下載器不啟動背景任務。
