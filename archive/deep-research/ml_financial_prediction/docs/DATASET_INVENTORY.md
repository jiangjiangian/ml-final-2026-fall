# Training data 與 Live Training Data

更新：2026-10-30，Asia/Taipei；最新取得於台北16:58。Training與Live皆由可重跑下載器取得，正常TLS、授權登入、ZIP／schema／標籤稽核後保留不可變版本；這不證明歷史欄位在各cutoff已可用。下表為最新runtime快照，10/27研究版本及更早歷史另列並保留。

| 項目 | Training data | Live Training Data |
|---|---|---|
| 網站說明 | 完整訓練資料，含市場、全域資料與股票清單 | 「即時更新」，取得最新 training data，使用網站提供的公開金鑰 |
| 來源 | 課程站 `/downloads/fin_pred_data.zip` | `https://fin-pred-daily.jiangxuehaokeai.chatgpt.site/`；公開頁面核實 `/login` 與 `/data.zip` |
| 狀態 | 已重新下載並稽核，18,278,354 bytes，內容hash未變 | 已正常TLS下載並稽核，541,298 bytes |
| 結構／日期 | 100個股CSV、global、info；個股2020-01-02～2026-08-31 | 100個股CSV＋global，無info.json；各40日期列，2026-09-01～2026-10-30；global40列 |
| 標籤 | 含真實y，全部161,746列已核對 | 4000個股列；3900個完成標籤，10/23的100個y=-1仍待完成 |
| 更新 | 本次 hash 與前次包相同；未證實更新頻率 | 台北時間每網站所稱交易日 00:00 新增列，未知暫填 -1，再逐欄更新；快照保留 9/1 起區段 |
| 用途 | 歷史開發／時間回測的原始快照，須符合可用性契約 | 補充 9/1 起的新區段與更新狀態，並非無標籤測試輸入；不能替換舊歷史包 |

兩包股票集合與欄位相同，日期無重疊；無法藉兩包共同日期檢查歷史改寫，也不能把Live未含舊日期解讀為刪除舊歷史。40個日期列是下載內容觀察，尚未獨立證明完整官方交易日曆。名稱含training不代表所有欄位都能用於每個歷史cutoff。

## 最新取得與每日表證據

最新資料位於Git外`/workspace/shared/finpred-runtime/raw/`，各來源保留objects及每次manifests：

| 來源 | fetched_at（UTC） | SHA256 |
|---|---|---|
| course-training | 2026-10-30T08:58:44.157286+00:00 | `7433b27103107c630e293708a7ca4b7bfcec524e91ea6dc5be3e9b7d885b90e2` |
| course-live | 2026-10-30T08:58:49.072701+00:00 | `038d1a0fe29f4377fe9e2161962fde9bb3eda5afbb05d4ac7d9fc205af9517a3` |

兩個manifest為`course-training/manifests/20261030T085844.157286Z_42aada4ac12c4ca0b37b096af5ddc819.json`與`course-live/manifests/20261030T085849.072701Z_c0f0cafc317d4cff952afc4cee12f88e.json`，記錄真實來源、取得時間、大小、hash、TLS及稽核metadata。原10/27研究快照不覆寫，E00～E03資料版本／分數不因重抓被改寫。

daily table橋接只使用cutoff前已取得的私有bytes，建立七個個股滯後欄位；observed_fetch要求available_at等於fetched_at。這能證明當日可用，不能推論歷史發布／調整vintage。最新資料在台北16:58取得，晚於10/30的08:10，因此真實prediction table CLI正確回報blocked；沒有把時間倒填，這也不等於五日盤前演練已完成。strict training仍因歷史證據不足blocked，研究opt-in才產研究表。

## 已下載真實資料

`/workspace/shared/downloads/course/fin_pred_data.zip` SHA256：

```text
7433b27103107c630e293708a7ca4b7bfcec524e91ea6dc5be3e9b7d885b90e2
```

- ZIP 102 項：100 個股 CSV、1 global CSV、info.json。Top50／Top100 各 50／100 檔，全數有資料檔。
- 個股合計 161,746 列，每檔 1603～1618 列；Top50 合計 80,874 列。全部股票日期範圍均為 2020-01-02～2026-08-31，各表 date 無重複。
- 個股 21 欄：date、還原 OHLC、成交筆數／金額／股數、外資持股比、四種法人買賣超、RSI、SMA、MACD、ATR、BBANDS 上／中／下、y。
- y 為 0/1，全部 161,746 列符合 `etl:adj_close > etl:adj_open`；收開相等的 11,610 列為 0。
- 四種法人買賣超欄各有 2 格缺值，不能當作所有個股數值完整。
- global 1506 列，2020-01-03～2026-08-31；date、^VIX、^IXIC、^GSPC、^TWII、^KS11、TX_OI。比 2330 少 112 日期。

Phase1 模板為 50 檔×84 日期（2026-06-01～09-30）。固定包已有前 64 日期、3200 個標籤；Live 實際補齊後 20 個 9 月日期、1000 個 0/1 標籤。這只是資料交集觀察，不推測官方目的。歷史回測仍按預測日切分，不能用未來標籤訓練／選參。

當日 y、OHLC、成交量與盤後法人資料須隔離至 label／evaluation，或依實際可用時間接入，不直接作當日盤前 feature。info.json 沒有 date／shift／發布時間／版本 metadata，時間證據限制見 SOURCE_ALIGNMENT.md。

## 2026-10-27研究Live版本與修訂查核（保留歷史）

可重跑下載器於2026-10-27T13:34:27Z（台北21:34）取得506,233bytes，SHA256 `2ea21246910eb3fd84561f9c5a5cd9c52c4c71c8a677268ae13bf4c27db39b5d`。不可變物件、manifest及稽核位於`/workspace/shared/downloads/course/snapshots/course-live/`，該舊下載根目錄的`live/latest_verified.json`仍記錄此研究版本；不是上方10/30 runtime快照的最新索引。

新舊均3700個股鍵及37個global日期，沒有新增／移除鍵；100個10/27個股列的19個輸入候選欄與y補齊，原本待完成的100個標籤變成二元值；global一列的KS11與TWII改值。新快照3600個完整標籤、100個10/23待完成；最新完整日期為10/27。比較器按原始字串比對，結果在`snapshots/live_revision_comparison.json`；不把重抓當成只append，也不把目前完成狀態套回早前下載時點。

原494,300bytes快照與當時網站群組狀態完整保留。`live/latest_verified.json`及`data_inventory.json`保留前版本索引；舊UI截圖／HTML只證明當時規則及狀態，不冒充新快照的即時群組完成資訊。

## 早前Live快照與時間證據（保留歷史）

已依新入口的實際表單 `POST /login`（欄位 key）登入，再下載頁面公布的 `GET /data.zip`；cookie 僅在記憶體，金鑰值不寫入程式、文件或 log。某些預設 Python User-Agent 曾被回覆 403／1010，使用正常瀏覽器 User-Agent／Accept 後成功，全程保持 TLS 驗證。

快照為 `live/verified/data_292643cac8f995bd.zip`，SHA256：

```text
292643cac8f995bdf2ae4db1a82d27e98e8b466aa6167b13d9a09d29d5c2d10c
```

- 101 個成員：global＋100 個股 CSV，無 info.json；股票集合與固定包相同，個股 21 欄、global 7 欄皆相同。以固定包 info 清單與快照 hash 作對照，不能假稱 Live 自帶清單，也不把原始 info 加入 Git。
- 各表 37 個日期列、個股合計 3700 列。3500 個二元 y 均符合 `adj_close > adj_open`，最後100股皆有二元標籤的日期為2026-10-22；200 個 y=-1 分別位於10/23、10/27，各100檔；此快照沒有10/26列。
- 網站將10/23的「其他特徵與 y」標為「資料未齊全，等待下一交易日」、10/27標為「更新中」，兩日皆只取得2/2004；兩日美股指數組均2/2。不能把日期存在或 ZIP CRC 通過當作欄位齊全。
- 頁面明示全部使用台北時間，`^IXIC`／`^GSPC` 使用前一美國交易日收盤；不能對已對齊的 Live 美股欄再盲目 shift，也不能將此規則直接套用到未核實的固定包。
- 未知值暫填 -1，實際值也可能等於 -1。y 的 -1 不是有效二元標籤；有號法人、MACD、TX_OI 的 -1 需保留歧義，不能全域替換 NaN。本次 raw 快照未被清洗。
- UI 提供每日期×兩群組的取得數、狀態及最後本站寫入時間，共74筆紀錄；沒有逐欄有效 mask 或來源 published_at。補抓／最後更新不是原來源歷史發布時間，下載成功仍不代表歷史 normalized observations 已 ready。

## 連線方式對照與歷史診斷

原 IP `https://140.112.31.182:8444/` 的正常請求有憑證身分驗證錯誤。依使用者要求作不帶帳密／金鑰的 `curl -k` 連線診斷後，仍收到 HTTP503，body 指出代理連上游的 TLS 驗證失敗。`-k` 只略過 curl 本端的憑證驗證，無法關掉代理端的驗證；不採作常態下載或安裝設定。新網域則正常 TLS HTTP200 並完成實際資料下載。

下列早前證據在`/workspace/shared/downloads/course/`；最新10/30 runtime證據見本文件前段。所有來源均不入Git、目錄700／檔案600：

- data_inventory.json：Training／Live schema、日期、標籤與缺值 metadata，保留前次失敗及最新成功狀態。
- download_manifest.json、dataset_audit.json：固定包下載與稽核。
- live/website_evidence.json、live/download_manifest.json：前次 IP 失敗的歷史診斷，`data_downloaded=false` 不代表新入口狀態。
- live/verified/download_manifest.json：早前`downloaded_verified_tls`成功狀態、ZIP hash／大小／CRC與來源；新下載在snapshots/，不覆寫此檔。
- live/verified/website_evidence.json、website_page1.html、website_page2.html：已去金鑰的頁面規則、原文 hash 與群組更新狀態。
- live/verified/comparison.json：兩包結構、日期、標籤與 -1 歧義的實際比較；connection_tests/ 保存三種連線測試結果。
- live/verified/comparison_summary.json、live/latest_verified.json：精簡差異報告與最新成功快照索引；成功索引不覆寫原始失敗診斷。

目前實作／部署計畫見[RESEARCH_PLAN](RESEARCH_PLAN.md)及[STATUS](STATUS.md)；IMPLEMENTATION_PLAN保留為較早歷史計畫。
