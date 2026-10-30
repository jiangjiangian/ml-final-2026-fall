# 教師資料時間對齊查核

## 本輪實測更新

已完成Fixed／Live與八個外部原生歷史序列的水準比對、正常日／跨市場休市及長假反例；完整結果與方法見[DATA_ALIGNMENT.md](research/DATA_ALIGNMENT.md)。這使既有位移由「完全未知」進展為有量化實測支持，但歷史發布／vintage仍未核實，strict生產接入限制維持。

Fixed的IXIC／GSPC／VIX，各1505/1505可比列匹配**前一個教師global列日期**的原市場close；各僅1418/1506匹配前一美國native session，最長落後9個來源session。Fixed TWII／KS11各1506/1506匹配同日close，不能直接作當日盤前輸入。Live兩美股欄37/37匹配前一美session；VIX僅28/37，不能一概套用。這些是raw水準對照，不是發布時間證明，也不能把同價巧合當獨立source lineage。

已實作`data/normalization.py`、`availability.py`及`build_course_market_features.py`：strict缺證據交blocked；research須明示旗標，使用獨立exchange_calendars日曆及close＋2h假設。真實研究市場表1655日期、M0＋SOX／TSM ADR／NVDA報酬已產生，readiness為research_assumption；OI仍缺。原有下表是首輪起點的證據狀態，閱讀時應與本節更新並用。

## 首輪查核記錄（歷史狀態）

固定包查核：2026-10-25 已從課程網站授權下載並執行 audit_dataset.py。ZIP hash 與既有 DATA_AUDIT.json 相同；這表示該次內容未變，不保證網站未來不會更新。助教新入口補充查核已正常 TLS 取得 Live，以下分開記錄兩種來源的證據範圍。

global 1506 列，2020-01-03 至 2026-08-31；2330 1618 列，多出 112 個日期。ZIP 的 info.json 只有股票清單，沒有各欄位的原市場日期、時區、首次發布時間、既有 shift 或歷史修訂 metadata。

| 固定包教師欄位 | M0 轉換 | 日期／既有位移 | 原生日曆／發布時間 | 接入狀態 |
|---|---|---|---|---|
| ^IXIC | ixic_ret_1s | 未核實 | 未提供 | blocked |
| ^GSPC | gspc_ret_1s | 未核實 | 未提供 | blocked |
| ^TWII | twii_ret_1s | 未核實 | 未提供 | blocked |
| ^KS11 | ks11_ret_1s | 未核實 | 未提供 | blocked |
| ^VIX | 水準與點數差 | 未核實 | 未提供 | blocked |
| TX_OI | 淨部位水準與口數差 | 未核實 | 未提供 | blocked |

不能把交集 global 表當各市場完整原生日曆，不能因多 lag 一期就宣稱無洩漏。blocked 指教師來源接入；標準化且有證據的輸入可執行已實作的引擎。

## Live 已取得的文件證據

新入口 `https://fin-pred-daily.jiangxuehaokeai.chatgpt.site/` 已正常驗證 TLS 並下載，資料日期列為2026-09-01～10-27；下載不再是本次阻礙。固定包與 Live 日期無重疊、同樣七欄 global，不能僅以欄名相同就套用相同 shift 語意。

| Live 系列／事項 | 已核實的網站說明 | 仍缺證據／接入限制 |
|---|---|---|
| ^IXIC、^GSPC | 使用前一美國交易日收盤，屬已對齊台灣日期的政策 | 未列原美國 session 日期與完整原生日曆；缺逐欄歷史 available_at，`ret_1s` 正式接入仍 blocked |
| ^VIX、^TWII、^KS11、TX_OI | 實際在 ZIP 中，歸「其他特徵與 y」群組更新 | 未逐系列說明來源日期／既有位移；不能直接套用兩美股指數規則 |
| 時區／新增列 | 全部台北時間；每來源稱交易日00:00新增當日列 | 日期列存在不表示價格／標籤已完成，也不證明完整官方交易日曆 |
| 逐欄取得 | 未知暫填-1，取得後替換；真值也可能=-1 | UI只有日期×群組取得數／狀態，無逐欄有效 mask；有號欄位保留 sentinel 歧義 |
| 最後更新／補抓 | 表示值或來源日期變更後寫入本站時間 | 不是原來源歷史發布時間；不得當歷史 published_at 或 available_at |

已文件化的 Live 美股對齊政策不等於完整歷史可用性證明，不能對 Live 再盲目 shift，也不能回推固定包已按同一規則處理。仍應在完整原生序列計算報酬，再依實際可用時間對齊。若原生 session 缺口無法補齊，只能另定義相鄰觀測報酬並記錄間隔，不能命名 ret_1s。

原始值與兩頁群組更新證據均已保存。建立 normalized adapter 時需逐欄／逐版本記錄可用性依據；當前快照下載時間可證明本次實際取得時點，不能證明更早歷史 cutoff 已取得資料。`-1` 不能全域轉 NaN；應保留 raw、欄位型別與未完成／歧義狀態。

解除條件：逐系列確認 date、既有 shift 與來源時區；取得原生 session 日曆及版本發布證據；建立帶 basis／evidence 的 available_at；以正常日、週末／長假及台美不同休市日各至少一例核對教師表與原始來源。缺 session 時補來源或另定義相鄰觀測報酬，不得命名 ret_1s。

首輪原始 ZIP、模板、download_manifest.json、重跑 audit 位於 `/workspace/shared/downloads/course/`，不入 Git。實際網站路徑見 SOURCES.md。首輪當時未訓練或回測；本輪已完成研究模型與市場消融，結果見EXPERIMENTS.md，尚無正式提交；合成範例不代表真實市場增益。

Training／Live存量、正常TLS成功證據及原IP／curl -k診斷見DATASET_INVENTORY.md。完整原生日曆已有第三方排程，逐欄歷史發布／vintage仍待核實。後續執行與驗收以RESEARCH_PLAN.md、STATUS.md為準，IMPLEMENTATION_PLAN.md保留首輪歷史；正式normalized adapter的時間證據要求維持不變。
