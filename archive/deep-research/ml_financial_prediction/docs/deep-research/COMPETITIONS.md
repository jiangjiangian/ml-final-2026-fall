# 金融預測競賽：能移植的是方法，評分與時點必須重建

研究日期：2026-10-30。來源索引見[SOURCES](SOURCES.md)。本輪實際取得七場Kaggle競賽的匿名公開metadata，未登入Kaggle、未加入比賽或上傳課程資料。案例涵蓋金融預測的代表性問題，並非對所有業界交易系統的普查。

## 先分清這個專案在比什麼

本課每個指定股票都要輸出0/1，目標為**當日還原開盤至收盤**，官方分數為`mean((2p-1)*r)`，`r=(adj_close-adj_open)/adj_open`。09:00台北截止，現行08:10特徵凍結是專案提案。因此預測昨收至今收、選top-k、直接最佳化Sharpe或輸出連續價格，都不是直接等價的解法。

競賽通常把研究問題固定成資料、標籤、評分、可用時間和執行限制。上市公司／交易公司提供的競賽只公開其問題的一部分，不能從競賽模型推定該公司的正式交易模型。Jane Street主辦方明說其2020活動也有招募與觀察社群解法的目的。[CMP01](SOURCES.md#cmp01)

## 七個經過官方metadata核對的案例

| 案例 | 已核實的評分名稱 | 問題／執行形式 | 本題可借用及不能照搬的部分 |
|---|---|---|---|
| Jane Street Market Prediction | `Jane Street Trading`，越大越好 | Code competition；未來行情評估；目前metadata不使用public leaderboard | 借用按時序重播、關注收益而非accuracy的思維。metadata沒有完整utility公式，本輪不冒稱已核對其全部公式或動作限制 |
| Jane Street Real-Time Market Data Forecasting | `Jane Street Zero-Mean R2`，越大越好 | 預測market responders；Code competition、同步重跑 | 借用連續目標、狀態／lag與逐批推論設計；R²高不保證本課二元return分數高。精確權重／公式仍應讀正式evaluation全文 |
| Optiver Trading at the Close | `Mean Columnwise Mean Absolute Error` | Nasdaq收盤前十分鐘，整合order book與auction資訊；私有評估使用截止後新資料 | 借用市場微結構與跨股訊號整合；不能把美股收盤競價特徵直接放到台股08:10。MAE也不是本課分數 |
| Optiver Realized Volatility Prediction | `Root Mean Square Percentage Error` | 預測10分鐘波動；Code competition，模型在後續真實市場資料評估 | 借用波動、多窗口統計、缺值與模型融合；預測波動幅度不等於方向 |
| JPX Tokyo Stock Exchange Prediction | `JPXSharpe`，越大越好 | 日本股票預測，Code competition、同步重跑 | 可研究跨股建模與投資組合評估；不可用排名／挑股規則代替本課50檔全部二元輸出 |
| G-Research Crypto Forecasting | `Weighted Correlation Coefficient`，越大越好 | 加密市場預測；metadata表示訓練階段已結束且持續更新資料 | 可研究不同資產共通因子、時序更新；相關係數不檢查與本課相同的報酬量級、二元方向決策 |
| Two Sigma Financial Modeling | `R Value`，越大越好 | 不確定金融資料中的連續預測，Code competition | 借用弱訊號、穩定性及正則化；本輪僅核對到此metric名稱，沒有把它擴寫成未核實的精確公式 |

依據：`CMPAPI1`至`CMPAPI7`的官方`GetCompetition`公開回應；問題描述另以CMP01、CMP10–12核對。`usesSynchronousReruns`未提供值的案例不推定為false。現在看到的leaderboard說明是**比賽結束後的metadata**，例如Jane Street real-time目前public/private顯示相同，不代表競賽期間從未有不同分割。

## KDD Cup的位置

ACM SIGKDD官方archive將KDD Cup定義為年度資料探勘競賽，所列任務包括廣告點擊、音樂評分、醫學、直接行銷等，**KDD Cup不是金融競賽的同義詞**。[CMP09](SOURCES.md#cmp09) 本次可讀archive只列至2016，不能據此宣稱已完整調查2026所有賽道。

KDD系統論文如XGBoost提供成熟、可擴充的樹模型方法；「論文發表於KDD」也不等於「該方法贏過KDD Cup金融賽道」。我們採用其建模工具與驗證思想，不編造冠軍故事。[MOD01](SOURCES.md#mod01)

## 參賽者方案提供什麼證據

已讀一份Optiver volatility參賽者本人公開方案：使用LightGBM、TabNet、MLP、時間窗口特徵及融合，也提醒time_id特徵可能造成驗證問題。[CMP15](SOURCES.md#cmp15) 這支持「有人實際使用這組方法」，不證明它是所有金融賽事的主流最優解。其名次為作者自述，本輪未以主辦方名單逐一交叉核實，不拿名次當證據。

另外兩份候選repository README只有名次／標題，沒有足夠技術內容；它們只記入[存取限制](access_limitations.json)，不據此推導模型結構。網路搜尋與README的聲量不是方法有效性的證明。

## 實務上可移植的研究流程

1. **先讀metric與規則。** 固定標籤、股票全集、截止時點、可否更新模型／外部資料與推論限制；再選loss和模型。
2. **建立同一份可重跑評分器與簡單基準。** 全0、全1、訓練集多數類別及正則化線性，必須與複雜模型使用完全相同的日期／股票鍵。
3. **按真實預測方式驗證。** 訓練早於驗證，同日股票同側，按來源發布／修訂版本取值。若標籤窗口重疊才按重疊規則purge，不把隨機GroupKFold一律當金融時間驗證。
4. **先做領域特徵，再測模型容量。** 波動、流動性、不同原生交易日／時區、缺值／陳舊與市場×個股交互作用，逐組做消融。
5. **融合只使用樣本外預測。** 先小型固定平均／非負權重；stacking使用時間有效OOF。不可把base model自己的訓練預測當meta特徵。
6. **保留真正沒碰過的後續資料。** 排行榜與反覆看validation也會成為選擇程序。高名次或更高歷史score不自動表示可交易或穩定。
7. **分開驗收研究、工程與上線。** Notebook能跑、CI綠燈、資料當時可用、預測準時提交、真實交易扣費後可執行，是不同證據。

這七點是本輪來源與現有ML課程知識的**專案綜合建議**，不是宣稱每家公司均採用完全相同流程。

## 對現有結果的解讀

原E00–E03已顯示：固定linear加權模型加入M0／SOX／ADR後未勝個股基準；2025勝出的MLP在2026年1–5月保留期未勝全0。這不是增加模型名稱就能解決的問題。接下來優先查驗證代表性、訊號與標籤的經濟含義、缺值／age，以及交互作用，並使用尚未看過的後續session驗收。不能把已看過的保留期重新命名為全新test。

## 存取與查核限制

Kaggle HTML直讀只得到JavaScript外殼；第三方文字reader取得了部分主辦方描述，卻沒有可靠呈現evaluation全文。後來以匿名、只讀的官方`competitions.CompetitionService/GetCompetition` RPC取得七個案例的metric名稱與執行旗標；HTTP方法是POST，但body只有公開competitionName，**沒有送出預測**。本輪未將metadata沒有提供的精確metric公式、live API每一步細節或冠軍技巧寫成已核實。

參考：[Jane Street主辦方](https://blog.janestreet.com/announcing-our-market-prediction-kaggle-competition-index/)、[KDD Cup archive](https://www.kdd.org/kdd-cup)、[本專案實驗](../EXPERIMENTS.md)。完整可追溯來源與閱讀範圍在[SOURCES](SOURCES.md)。
