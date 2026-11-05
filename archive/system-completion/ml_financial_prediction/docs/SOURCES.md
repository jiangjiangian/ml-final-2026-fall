# 來源與查核紀錄

查核日期：2026-10-25。原始課程檔不隨此套件重新散布。此檔提供團隊定位依據，不代表候選資料API已全部可用。

## 課程與團隊來源

- 課程競賽網站：https://final.html2026.csie.org 。2026-10-25 實測 Email／密碼登入；公開前端確認 `POST /api/auth/login`，需同源 Origin／Referer。授權登入後核實 `GET /downloads/fin_pred_data.zip`、`GET /api/sample-submission?phase=1`，資料及模板下載成功。只下載資料，未實作或測試提交。憑證由個人 Secrets 注入，cookie 僅存記憶體，不寫入 Git 或 log。
- 這次網站 ZIP 的 SHA256 與 `DATA_AUDIT.json` 相同：`7433b27103107c630e293708a7ca4b7bfcec524e91ea6dc5be3e9b7d885b90e2`。模板 SHA256：`2081e92b216ff1cd231f0e1ec32d709b6e6b734d9ace41fc7d0b3fe02cc93f28`。ZIP 僅有股票清單 metadata，仍無發布時間、原生日期或已位移證據。
- 2026-10-25 核實課程站 Live Training Data 卡片：「即時更新」「前往資料服務取得最新 training data，並使用下方公開金鑰存取」，連至 `https://140.112.31.182:8444/`。雲端代理憑證缺 IPAddress SAN，標準 TLS 驗證失敗，尚未讀取 payload；不推測 Live 日期、label 或增量語意。細節及無密鑰證據見 DATASET_INVENTORY.md。
- 助教新入口：https://fin-pred-daily.jiangxuehaokeai.chatgpt.site/ 。正常TLS已實測HTTP200，頁面公布POST /login（表單欄位key）、GET /data.zip，公鑰登入後ZIP下載成功。Python預設User-Agent曾403/1010，使用正常瀏覽器User-Agent／Accept後成功，未降低TLS驗證。cookie僅存記憶體，key值不存Git／log。
- Live ZIP SHA256：292643cac8f995bdf2ae4db1a82d27e98e8b466aa6167b13d9a09d29d5c2d10c，494,300bytes，101members，CRC通過。資料日期2026-09-01～10-27；去key的兩頁HTML及hash／來源URL／74筆更新群組紀錄在live/verified/website_evidence.json及對應檔案，不入Git。頁面明示台北時間、00:00新增列、IXIC/GSPC前一美交易日、未知與真值都可能-1、最後更新是本站寫入。這是Live政策證據，不是固定ZIP已位移或歷史來源發布時間的證明。
- 依使用者指示比較curl -k：原IP略過本地驗證後，在本雲端仍HTTP503，body明示proxy上游TLS驗證失敗，未取得Live資料。採用新網域正常TLS下載；診斷在live/connection_tests/connection_results.json，沒有新增全域insecure或verify=false設定。

- final.pdf，release 2026-10-24：p.1資料使用與任務；p.2兩階段及score；p.3至少四approaches、最多七頁報告；p.4截止、配分與原始碼保存。
- Financial_Prediction_with_SDAI_Motivation.pdf：pp.4-6目標與資料；p.11六個全球欄位與TX_OI定義；p.14可重現與資料分享；pp.20-21洩漏與walk-forward。p.12較早競賽日期不作現行依據。
- Note Oct 14, 2026_compressed.pdf：十頁掃描與手寫筆記，以圖像檢視；市場資料、評分、時間驗證及drift發想與上述簡報互相參照。手寫簡略註記不凌駕正式規範。
- Google Docs，2026-fall-ML，讀取時修改時間2026-10-24T16:03:10.186Z：https://docs.google.com/document/d/119Mqc6NO4STwww-2uQlHBQK9Robn8w9wZIm1UCzyO8I 。使用可讀文字中的分工、X_market_return公式及候選發想，未從空白圖形區推測meta結構。
- sample_submission.csv：實讀50列股票、84日期欄，2026-06-01至2026-09-30；占位值全0，不能當真實label。
- fin_pred_data.zip：本次取得的既有上傳版本，雜湊與日期範圍見DATA_AUDIT.json；不代表最新dashboard版本。
- Google AI Mode分享：https://share.google/aimode/tgcGVeKaSbKAlPzth 。本次讀取失敗，內容未納入事實依據。

## 官方外部資料

- TWSE OpenAPI：https://openapi.twse.com.tw/ 。可見歷史指數端點，不採「全站無歷史」概括。
- TWSE加權指數JSON：https://openapi.twse.com.tw/v1/indicesReport/MI_5MINS_HIST 。本次實讀當月多個交易日；完整2020回補能力未證實。
- TAIFEX一般盤三大法人：https://www.taifex.com.tw/cht/3/futContractsDateView 。淨部位與交易資訊分開，該頁歷史範圍有其限制。
- TAIFEX夜盤：https://www.taifex.com.tw/cht/3/futContractsDateAhView 。官方說明交易歸屬日期，例如前日下午開始、次日凌晨結束歸次日。
- FinMind文件：https://finmind.github.io/ 。用於資料類型概觀。
- FinMind方案與價格：https://finmind.github.io/Pricing/ 。Free當時列300次/小時，註冊600；含逐方案資料清單與禁止原始資料再散布的說明。
- TWSE MIS：https://mis.twse.com.tw/stock/index?lang=zhHant 。本次動態頁沒有可讀資料；未確認歷史快照API。
- GDELT：https://gdeltproject.org/ 。新聞、實體與事件資料概觀。
- GDELT DOC示例：https://blog.gdeltproject.org/doc-2-0-api-llms-summarizing-headlines-turkish-investment-inflation-the-niger-coup/ 。2023官方示例說明查詢與窗口限制；不作2020全史可查的證據。
- Nasdaq SOX：https://indexes.nasdaq.com/Index/Overview/SOX 。指數為半導體相關公司組成，官方定義與歷史資料授權分開。
- Cboe VIX：https://www.cboe.com/tradable-products/vix 。VIX為SPX選擇權所反映的近期待波動指標，與可交易VIX衍生商品不同。
- NYSE交易時間：https://www.nyse.com/markets/hours-calendars 。一般Core Trading Session 09:30-16:00 ET；台灣04/05點轉換是依時區換算，不是競賽更新時間的證據。

## 工程與產品文件

- ML系統設計參考：[Chip Huyen《Designing Machine Learning Systems》](https://www.oreilly.com/library/view/designing-machine-learning/9781098107956/)、[作者書目](https://huyenchip.com/books/)、[Cookiecutter Data Science v2](https://cookiecutter-data-science.drivendata.org/)。官方頁已核實；採生命週期與資料分層原則，不宣稱書中規定此專案的確切tree，也未確認這就是使用者記得的書。
- 2026-10-27首批外部下載介面及實讀覆蓋：[API_INVENTORY.md](API_INVENTORY.md)。Cboe、TWSE、FRED DGS10及DEXTAUS正常TLS下載成功；FRED最新歷史匯出不是歷史vintage證據。
- 課程可重跑下載器同日取得新Live：506,233bytes，hash `2ea21246910eb3fd84561f9c5a5cd9c52c4c71c8a677268ae13bf4c27db39b5d`；3600完整／100待完成標籤，較早快照補齊10/27。不可變manifest在`snapshots/course-live/`，版本差異見DATASET_INVENTORY，不覆寫早前網站證據。
- GitHub排程：https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule 。高負載可能延遲或丟棄、default branch、UTC與時區設定。
- OpenAI官方Codex指引：https://learn.chatgpt.com/docs/agent-configuration/agents-md 。AGENTS.md讀取與分層規則。
- OpenAI官方執行環境：https://learn.chatgpt.com/docs/environments/modes 。local/worktree/cloud差異與本機登入不自動移轉。

新增外部資料特徵前，補上真正使用的資料介面、欄位與歷史範圍，不只留下來源首頁。

## 軟體與 ML 開發技能參考

2026-10-25 已查核 OpenAI 官方 skills catalog；以下候選尚未加入本專案：

- [jupyter-notebook](https://github.com/openai/skills/tree/main/skills/.curated/jupyter-notebook)：EDA、可重現 notebook 原型。
- [gh-fix-ci](https://github.com/openai/skills/tree/main/skills/.curated/gh-fix-ci)：GitHub Actions PR check 除錯。
- [playwright](https://github.com/openai/skills/tree/main/skills/.curated/playwright)：真實瀏覽器登入／下載與 UI 流程驗證。
- [security-best-practices](https://github.com/openai/skills/tree/main/skills/.curated/security-best-practices)：明確要求時做 Python／JS／Go 安全審查。
- [skill-creator](https://github.com/openai/skills/tree/main/skills/.system/skill-creator)：日後建立專案資料／實驗技能。

Graphify 已安裝，cloud setup 已可用。Codex Security／Linear 為可選插件，尚未連接。MLflow／DVC 是工程工具，不是目前已連接的插件；採用與資料儲存目的地須依團隊需求決定，不自動上傳課程資料。
