# 資料來源與真實時間對齊研究

## 已執行與證據範圍

本輪完成八個Yahoo公開chart歷史快照、三個TWSE官方產業指數當日水準、教師／外部歷史水準比對，以及可執行的strict／research對齊入口。下列「匹配」是數值與日期的實測，不冒充資料提供者發布承諾或歷史vintage證明。

Yahoo八個原始JSON、SHA256與取得時間均在`/workspace/shared/downloads/market-history/yahoo-*/{objects,manifests}/`，正常TLS、不需要金鑰、不進Git。其公開chart介面並非本專案已取得SLA／商用授權的正式API；完整來源限制保存在每個manifest。TWSE原始JSON另存`twse-sectors/`。課程原始檔仍保留原位。

| 序列 | 本輪實取列數 | 觀測日期 | 用途／限制 |
|---|---:|---|---|
| IXIC、GSPC、SOX、TSM ADR、NVDA | 各1736 | 2019-12-02～2026-10-28 | 額外補齊原生歷史；Yahoo最新歷史版本，不是當時發布版本 |
| TWII | 1677，1缺值 | 2019-12-02～2026-10-28 | 缺值保留；不把相鄰非缺值當完整native session |
| KS11 | 1692，1缺值 | 2019-12-02～2026-10-29 | 時戳按provider時區解讀；日期不等於發布時間 |
| VIX | 1803，65缺值 | 2019-12-02～2026-10-28 | 包含無值日期；用水準及點數差，不稱持有VIX報酬 |
| 台灣電子工業、半導體、金融保險 | 各1水準 | 2026-10-29 | 官方MI_INDEX當日快照；尚無前一原生session，不能計算1s報酬 |

TSM／NVDA歷史close不是本研究已核實的總報酬，可能有事後分割／調整與修訂；此限制傳入research報告，不允許直接升級正式模型。

## 教師表既有位移：實測結果

比較對象為固定包hash `7433b271…b90e2`與Live hash `2ea21246…39b5d`，分別1506與37個global日期；Yahoo快照hash逐系列保存。匹配容忍度為`max(0.02指數點, 2e-6×abs(教師水準))`，每個分母只統計實際可比日期。完整候選比較與假日例子在`/workspace/shared/research/alignment/teacher_level_comparison.json`。

| 教師來源／欄位 | 實測匹配 | 結論與界線 |
|---|---|---|
| Fixed IXIC／GSPC／VIX | 各1505/1505可比列匹配「前一個教師global列的日期」之原市場close | 強烈支持先取多市場交集、再以global列位移的既有行為；不是保證前一美國native session |
| Fixed上述三系列 | 各僅1418/1506符合前一美國來源session | 有55次落後2個session、其餘可更長，最長9個；不可把教師相鄰列直接叫1session報酬 |
| Fixed TWII／KS11 | 各1506/1506匹配相同日期原市場close | 當日台／韓收盤在台股盤前不可知；不得當當日盤前輸入 |
| Live IXIC／GSPC | 各37/37匹配前一美國來源session | 與服務頁「前一美交易日」政策一致；不應再全表無條件shift |
| Live TWII／KS11 | 分別36/36、35/35可比同日值匹配 | 未完成或來源休市列另列，不由存在日期推論完成狀態 |
| Live VIX | 28/37匹配前一來源session | 尚有9列不符此簡單規則；不把兩美股指數的政策直接套給VIX |

具體長假反例：Fixed的2020-01-30美股欄匹配2020-01-17，落後8個美股session；2021-02-17匹配2021-02-05，落後7個。這解釋了為何盲目`shift(2)`或對教師交集表直接算`ret_1s`不正確。來源日期的實測對應，仍沒有證明該值在歷史何時公開或是否經過事後修訂。

## 已實作對齊介面

- `normalize_course_market`要求逐系列date政策、獨立native日曆、close時刻、快照SHA256／來源／取得時間，以及availability依據。支援原生日期、Live前一session及有證據的逐列source-session映射；未核實系列交blocked理由，不猜統一位移。
- `observed`模式只把值設為本次實際取得之後可用；不把今天取得的歷史值放回更早cutoff。`documented`歷史模式另外要求vintage已核實聲明。`strict`拒絕未核實vintage／保守假設。
- OI原始-1可能是未知或真值：沒有逐格有效性證據時，標準化值留空並記錄歧義；只有明確提供有效性依據才保留-1。原始檔不修改，不能全域替換所有有號欄位。
- 研究入口使用exchange_calendars **4.13.2**的XNAS／XNYS／XTAI／XKRX完整排程，先算native報酬再按cutoff對齊。這是獨立於教師交集的第三方日曆證據，尚未逐日核實全部特殊停市；VIX暫用NYSE日曆＋15分鐘close代理，明列假設。
- `research`以「排程close＋2小時」作明示provider延遲假設，`published_at=null`，保留真正fetched_at及最新歷史版本限制。這不是量測到的歷史發布時間；要加`--allow-research`，輸出不能宣稱production verified。

## 真實研究表與檢查

`scripts/build_course_market_features.py`已由真實歷史快照產出1655個目標日（2020-01-02～2026-10-27，08:10台北cutoff）的市場表，位於`/workspace/shared/research/alignment/market_features.csv`，旁附完整`market_report.json`、`market_summary.json`及targets。目標日取已下載2330日期作研究索引，不冒充官方每日session清單。

M0維持八欄schema，其中四個股價指數報酬、VIX水準／點數差可取得；OI兩欄暫全缺，不以猜測填值。新增`sox_ret_1s`、`tsm_adr_ret_1s`、`nvda_ret_1s`，使用各自完整日曆之前一session；缺前序不跳過。1655列中TWII報酬6缺值、KS11報酬4缺值；IXIC／GSPC／VIX及三新增報酬此研究表無缺值。缺值日期保留。

例如2020-01-30的研究表使用IXIC原生2020-01-29及TWII原生2020-01-20；2026-09-08使用美股2026-09-04與台股2026-09-07，正確保留不同休市日。它比教師交集位移更接近所需資訊集合，但仍是`readiness=research_assumption`，不是無洩漏正式回測認證。

```bash
uv run --locked --no-sync python scripts/build_course_market_features.py --history-root /workspace/shared/downloads/market-history --targets /workspace/shared/research/alignment/targets.csv --mode research --allow-research --out /workspace/shared/research/alignment/market_features.csv --report /workspace/shared/research/alignment/market_report.json
```

不指定research時，對相同最新歷史快照的strict執行退出2、產出blocked診斷，不產生冒充正式的市場CSV；`strict_report.json`已實跑驗證。其餘synthetic測試覆蓋：取得時間不回填、未來bar、native假日缺口、已位移資料不雙移、映射歧義、原始檔hash改動、signed -1有效性、Yahoo錯symbol／非有限／重複日期、TWSE確切三類指數schema及TLS／不可變保存。

## 後續與來源

生產接入仍需：歷史vintage／provider發布證據，或從現在開始保留實際cutoff前取得的版本；核實所有來源特殊停市；TAIFEX淨部位日期／逐欄有效性；三個台灣產業指數歷史回補。FinMind匿名TAIEX曾實讀成功，但本輪部分查詢HTTP403，不能宣稱全資料集免token可用；未讀取或記錄任何私人token。

- [Yahoo公開IXIC chart介面](https://query1.finance.yahoo.com/v8/finance/chart/%5EIXIC)：實際JSON；其他symbol及參數在manifest，非本研究已驗證的正式授權/SLA。
- [TWSE官方MI_INDEX](https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX)：三個明確命名價格指數水準，與同頁報酬／槓桿指數區分。
- [NYSE交易時間與日曆](https://www.nyse.com/markets/hours-calendars)：美國一般核心交易09:30～16:00ET；實際提早收盤仍按日曆。
- [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars)：第三方維護日曆，版本固定且可重跑，不等於所有來源發布時間已核實。
- [FinMind資料文件](https://finmind.github.io/)及既有API_INVENTORY：權限與歷史覆蓋逐dataset確認，來源授權不因可HTTP200就自動成立。
