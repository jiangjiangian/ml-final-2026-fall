# 來源與查核紀錄

查核日期：2026-10-25。原始課程檔不隨此套件重新散布。此檔提供團隊定位依據，不代表候選資料API已全部可用。

## 課程與團隊來源

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

- GitHub排程：https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule 。高負載可能延遲或丟棄、default branch、UTC與時區設定。
- OpenAI官方Codex指引：https://learn.chatgpt.com/docs/agent-configuration/agents-md 。AGENTS.md讀取與分層規則。
- OpenAI官方執行環境：https://learn.chatgpt.com/docs/environments/modes 。local/worktree/cloud差異與本機登入不自動移轉。

新增外部資料特徵前，補上真正使用的資料介面、欄位與歷史範圍，不只留下來源首頁。
