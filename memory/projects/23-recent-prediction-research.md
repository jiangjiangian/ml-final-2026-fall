# 近半年股票預測：嚴格測試多半歸零，c2v2d 仍可用

2026-11-27 使用者看到正式期連續虧損，質疑 c2v2d 和研究框架，要 Claude 上網查最近半年真正有實際應用價值的股票預測方法，寫進 memory。做法：四條研究線（2026 學術論文、LLM 和基礎模型、比賽和業界、台股開盤到收盤）各一個 agent，一個 agent 整理成報告，再用一組 agent 回原文核對最關鍵的 14 條引用（結果在「引用核對結果」一節）。原始研究筆記放在 session 的 scratchpad，會被系統清掉，這份檔是唯一的紀錄。使用者 2026-11-27 看完後選了下一步：先做 c2v2d 分數的風格歸因（優先 1，`RP 37`），沒選法人層確認、依名次調整押法、Kronos-small。

2026-05～11 沒有找到任何每天選股的模型，在實盤或真正的樣本外做出可靠的正面成果。設計最嚴的研究（事先登記、單次揭盲、共同基準）都發現：能預測的部分大多在隔夜跳空，開盤之後只剩等級相關（IC，預測名次和實際報酬名次的相關）約 0.02，扣成本或校正多重比較後就不顯著。真正有幫助的是方法紀律：目標配合評分、拿掉風格曝險再看、少而穩定的特徵、事先固定的規則，這些我們大多已經在做。c2v2d 這 8 個交易日合計 −0.0186，其中 11-23 一天 −0.0265，幾乎全是 β 曝險（−0.0259）。那天方向模型的 p 是 0.469，交出去的檔和 `rank_ensemble` 只差 1 組，所以虧損來自基礎排名本來就偏低 β，碰上高 β 股大漲（推斷）。其他 7 天合計 +0.0079，每天約 +0.0011，和回測平均 +0.00123 差不多。8 天分不出運氣和能力：用長期標準差要約 55 個交易日、用 10～11 月的波動要約 180 天，優勢才可能到 t = 2。建議繼續用 c2v2d，把低 β 這個押注當成已知風險量清楚；文獻建議的新方向，有一半其實已經在 `X_price` 裡或做過，還沒試過的只剩少數幾個。

## 證據標籤怎麼讀

每個引用都標兩件事：證據類型，和我們讀到多深。2026-05 以前的來源另外標「背景」。沒有日期的頁面寫「頁面未標日期」。

| 標籤 | 意思 |
|---|---|
| 實盤 | 真錢交易、即時記錄的訊號。比賽用未來資料計分的私榜標「實盤（比賽私榜）」；基金產業的實際報酬標「實盤（產業整體）」 |
| 訓練截止後樣本外 | 測試期在模型訓練或預訓練截止之後，分析計畫事先凍結，或事先登記的前瞻測試 |
| 保留期回測 | 歷史資料按日期切出測試期。測試期可能落在模型預訓練期內時另外註明 |
| 樣本內 | 全期迴歸、全期描述統計，或濾網是看過全期才挑的 |
| 其他 | 理論、論壇說法、新聞、沒有評估 |
| 只讀到摘要或搜尋摘要 | 沒開全文，數字來自摘要頁或搜尋結果。「轉述」是讀到別人報導的數字 |

本專案的數字有兩種來源。標「本專案資料，2026-11-27 重算」的是從每天的回測表和正式分數重算的。標 `memory/` 檔名的是以前 notebook 的結果，日期寫在旁邊。

## 嚴格的 2026 研究多半得到零或接近零

結論：設計越嚴的研究，結果越接近零。正面的大數字都來自中國 A 股的保留期回測，沒算成本，標籤還含隔夜跳空。

| 研究 | 日期 | 市場和目標 | 證據 | 結果 |
|---|---|---|---|---|
| OLIVIA，〈Thinking Fast, Trading Late〉（[arXiv 2611.03985](https://arxiv.org/abs/2611.03985)） | 2026-11-02 | S&P 500 新聞，測試期 2026-01～07 | 訓練截止後樣本外（雜湊凍結的分析計畫、遮蔽公司名、單次揭盲）；讀過全文（核對） | 微調的 ModernBERT 編碼器 Laya-Fin（論文叫非生成式「決策模型」，不是生成式 LLM）兩季驗證 IC 0.055、0.065，測試期掉到 0.020（t 1.7），這是對收盤到收盤；對開盤到收盤只有 0.010（t 0.8）。三個商用決策模型的判讀和隔夜跳空相關（IC 0.074～0.077），和開盤後的走勢無關，但三個都沒過事先登記的身分洩漏檢查。唯一的生成式 LLM 是基準，IC 從 0.052 掉到 0.001。扣成本和 deflated Sharpe 後沒有一個事先登記的策略留下。遮蔽後商用模型仍認出 62～74% 的公司（基準 28%） |
| STRATA（[arXiv 2608.28060](https://arxiv.org/html/2608.28060)） | v1 2026-08-28，v4 2026-09-14 | CSI 1000，5 分鐘 K 棒，測試 2024 年 241 天 | 保留期回測；讀過全文 | 收盤到收盤 IC 0.0728、多空每天 +73.9 bp。拆開後隔夜 IC 0.1275、多空 +75.6 bp；可交易時段（開盤到收盤）IC 0.0215、多空 −1.6 bp（t −0.37）。GRU、LSTM、TCN、Transformer、MLP、Mamba 六個基準在可交易時段的多空全是負的，IC 卻是正的 |
| 〈Benchmarking Deep Time Series Models for Equity Portfolios〉（[arXiv 2606.09420](https://arxiv.org/abs/2606.09420)） | 2026-06-08 | CRSP 每天，2018～2024，15 種架構 | 保留期回測；讀過全文（核對） | 15 種是深度加統計架構（含 TS-RIDGE、TS-OLS、AR1-GARCH11）。沒有一個架構勝出，最好的排第一機率 0.352。20 bp 成本下，十分位多空有 4 個模型（TS-RIDGE、LSTM、TransEnc-8、TransEnc-10）淨 Sharpe 為正；換成有限制的二次規劃組合，5 個入選模型全是負的（TransEnc-8 −0.76 到 TS-RIDGE −2.37） |
| QLoRA LLM 情緒基準（[arXiv 2608.04200](https://arxiv.org/abs/2608.04200)） | 2026-08-04 | S&P 100，2019 年 13,115 則標題 | 保留期回測（2019 在模型預訓練期內）；讀過全文（核對） | 分類正確率最高 0.884，隔天 IC 最高只有 0.0143。28 個檢定在 Newey-West 和 FDR 校正後全部不顯著 |
| 〈(Mis)Understanding Benign Overfitting〉（[arXiv 2608.23761](https://arxiv.org/abs/2608.23761)） | 2026-08-24 | 股票報酬預測 | 保留期回測；只讀到摘要 | 最佳 ridge 和無正則化模型都贏不了歷史平均；沒有真訊號時複雜模型會收斂到歷史平均 |
| 異質集成（[arXiv 2611.12389](https://arxiv.org/abs/2611.12389)，ICAIF 2026） | 2026-11-09 | CSI 300，Qlib Alpha158 | 保留期回測；只讀到摘要 | 挑誤差相關低的線性加非線性模型一起平均，Rank IC 比單一神經網路高 13% 以上，也贏 XGBoost 和 DoubleEnsemble。切分日期和成本沒寫 |
| LSTM 加產業嵌入（[arXiv 2608.05755](https://arxiv.org/abs/2608.05755)） | 2026-08-06 | S&P 500 每天 | 保留期回測；只讀到摘要 | 說贏過基本 LSTM 和隨機森林，訊號來自短期反轉和產業動能。摘要沒有數字 |
| 時間序列基礎模型事先登記測試（[arXiv 2611.12141](https://arxiv.org/abs/2611.12141)） | 2026-11-09 | E-mini 期貨，5～120 分鐘 | 保留期回測（自己雜湊鎖定的分析計畫、單次揭盲，盲測期 2025-01～2026-05）；讀過全文（核對） | 5 個凍結模型（Chronos-Bolt、Chronos-2、TimesFM 2.5、Moirai 2.0、TiRex）× 4 種輸入 × 4 個 5～120 分鐘期間 × 2 個市場共 160 格，用 MAE 比，0 格贏「不變」預測，Hansen SPA p = 1.000。Kronos 不在這 160 格裡；同一篇的 Kronos-small 每日下一節排名訊號在盲測期重現（NQ IC +0.116，p 0.015），只是沒過交易條件 |
| 兩個 LLM 交易 agent 機隊的生產紀錄（[arXiv 2609.05663](https://arxiv.org/abs/2609.05663)） | 2026-09-04 | 加密貨幣，2026-02～03 3,505 個帳戶、06～08 約 500 個 agent | 實盤（加密貨幣）；只讀到摘要 | 兩個機隊都沒有方向優勢。一個不賺錢，來回交易勝率 41%，對照散戶 50%。416 個重播情境裡各前沿模型的決策品質分不出差別 |
| KTD-Fin（[arXiv 2605.28359](https://arxiv.org/abs/2605.28359)） | 2026-05-27 | CSI 300，十個 LLM agent，2024～2026 | 保留期回測（遮蔽公司名和日期來控制記憶）；讀過全文（核對） | 累積報酬大多由大盤和風格曝險解釋，沒有持續的選股 alpha |
| MinervaScore（[arXiv 2608.23808](https://arxiv.org/abs/2608.23808)） | 2026-08-24 | 359,062 筆回測紀錄的強健度評分 | 訓練截止後樣本外（事先登記的前瞻測試）；只讀到摘要 | 在合成資料上分得出訊號和運氣（AUROC 0.989），在沒看過的真實資料上和之後績效無關（ρ 0.013，p 0.40）。作者註明這群策略本來就少有真優勢；我們的判讀是檢定力不夠，不能證明篩選無效 |

我們的題目就是 STRATA 說的「可交易時段」。2026 年的證據一致指出，前一晚的資訊大多在 09:00 開盤就反映完了。這給我們一個天花板的參考：風格中和後的 IC 約 0.02。

我們自己的數字比這高很多。`X_price` 每天的 IC 在 2024-01～2026-10 是 0.093、2022～2023 是 0.086（`memory/projects/05-experiment-critique.md`，2026-11-12 用 notebook 16 的預測算）。差距可以這樣解釋：市場不同（台股大型股對 CSI 1000 小型股）；我們直接用開盤到收盤訓練；我們的 IC 沒先拿掉風格，分數裡約 14% 來自 β（notebook 24，`memory/projects/04-raw-feature-experiments.md`，2026-11-12）。這三點讓 0.09 有可能是真的，但也表示往後要打折。notebook 24 建議往後用每天 +0.0009～+0.001 估。

## 撐過樣本外的是紀律和風險控制

結論：比賽和業界留下來的經驗，幾乎都是方法紀律和曝險控制。新模型架構的貢獻最小。

| 來源 | 日期 | 證據 | 學到的事 |
|---|---|---|---|
| DRW 加密貨幣第 1 名（[Kaggle writeup](https://www.kaggle.com/competitions/drw-crypto-market-prediction/writeups/drw-solution-1st)） | 2025-08-14，背景 | 實盤（比賽私榜）；各元件的增益是保留期回測 | 特徵篩選最重要：相關 > 0.6 的欄分群、每群留中心欄（約 60 欄），再丟掉幾乎沒相關的，只留每個 fold 的 SHAP 前 20 都出現的（約 30 欄）。損失 0.6×MSE + 0.4×Pearson。驗證用分組、清掉相鄰期的時間序列切分。作者說「線性模型很強」 |
| Jane Street 第 8 名（[Kaggle writeup](https://www.kaggle.com/competitions/jane-street-real-time-market-data-forecasting/writeups/evgeniia-grigoreva-private-lb-8th-solution)） | writeup 2025-01-14，最終榜 2025-07-14（[公告](https://www.kaggle.com/competitions/jane-street-real-time-market-data-forecasting/discussion/589672)），背景 | 實盤（比賽私榜）；增益是保留期回測 | 每天用新答案更新一次（學習率 0.0003，基礎訓練是 0.0005），CV +0.008，是 writeup 列出的增益裡最大的（其他最多 +0.002）；writeup 沒有測更新學習率本身。輔助目標 +0.001。3 個種子 × 2 種 GRU 平均 |
| Hull Tactical 第 4 名（[Kaggle writeup](https://www.kaggle.com/competitions/hull-tactical-market-prediction/writeups/4th-place-technical-model-no-learning-short-te)） | 2026-07-03 | 實盤（比賽私榜） | 沒有機器學習。核心是比賽前就研究好、刻意不調參的短期均值回歸，只跑了幾次完整實驗。分數主要來自波動目標的部位調整，這點我們用不到（每檔固定 ±1，沒有部位大小可調） |
| Hull Tactical 榜單變動（[Leaderboard EDA](https://www.kaggle.com/competitions/hull-tactical-market-prediction/discussion/663201)） | 2026-01-21 對 02-19，背景 | 實盤（比賽期間的榜），參賽者整理 | 約 3,340 隊，名次相關 +0.68。前 10 名一個月後只剩 2 隊，1 月第 1 名掉到第 50，第 2 名掉到第 310 |
| Hull Tactical 隨機提交討論（[Kaggle 討論](https://www.kaggle.com/competitions/hull-tactical-market-prediction/discussion/608135)） | 2025-09-18、11-24，背景 | 論壇說法（模擬） | 180 天的隨機部位，100 次內就有 Sharpe > 2。一萬次模擬裡 Sharpe ≥ 2 的機率 9.35% |
| Mitsui 商品第 10 名（[Kaggle 討論](https://www.kaggle.com/competitions/mitsui-commodity-prediction-challenge/discussion/668589)） | 2026-01-17，背景 | 實盤（比賽私榜） | 作者認為沒有機器學習能用的訊號，交的是正則化的樸素組合。他說約 3 個月的測試期太短，小優勢贏不過隨機 |
| M6 投資比賽（[Staněk, IJF 41(4) 2025](https://ideas.repec.org/a/eee/intfor/v41y2025i4p1413-1427.html)、[arXiv 2412.04490](https://arxiv.org/abs/2412.04490v1)） | 2024-11-21／2025，背景 | 實盤（比賽資料）加模型 | 50 個資產、12 個月。極端的 Sharpe 沒有超出運氣能解釋的範圍。依目前名次對抗式調權重可以提高贏的機會；空單多、和別隊不同的隊進前段的機率高 8 倍以上 |
| Numerai 2026 規則（[2026 獎金更新](https://blog.numer.ai/numerai-monthly-numercon-speakers-new-dataset-target-2026-payout-updates/)、[Unity 合併](https://blog.numer.ai/unifying-numerai-and-signals/)、[NCORR 定義](https://docs.numer.ai/numerai-signals/scoring/definitions)） | 2026-01-06（背景）、2026-10-16；文件 2026-11-27 讀取 | 規則公告；Unity 的「NCORR 加倍」是保留期回測 | CORR 倍數 0.5 → 0.75，MMC（和群眾不同的貢獻）2.0 → 2.25。計分前先對一大組已知風格中和。沒有公布哪種建模方法在實盤有效 |
| FactorBench（[arXiv 2610.06947](https://arxiv.org/html/2610.06947v1)） | 2026-10-03 | 保留期回測，測試 2024-01～2025-10；讀過 HTML | 約 5,000 個自動挖出的因子。中和掉 β、波動、動能、短期反轉、流動性後：R&D-Agent 的 IC 0.0253 → 0.0011，Alpha101 0.0238 → 0.0237。看起來的預測力大多是已知曝險。目標是 20 天後報酬，五個市場等權（S&P 100、恆生、CSI 300、FTSE 100、日經 225），沒有測每天開盤到收盤 |
| A 股量化私募 2026（[東方財富／中國證券報](https://finance.eastmoney.com/a/202611153931408392.html)） | 2026-11-15 | 實盤（產業整體） | 上半年規模和超額都擴張，下半年超額「幾乎被抹平」。新財富 1000 指增私募指數 10 月跌超過 17%，今年新成立的量化多頭超過七成是負報酬。文章列三個原因：風格反轉、相似模型造成的隱性擁擠、成交量縮小。「動能和 β 同步反轉」是其中一位管理人（正仁量化）的看法；7 月和 10 月兩波修正是另一位（大岩資本）的描述，7 月擁擠的科技股被賣、資金轉向防禦和微型股，10 月是指數漲、個股跌。業者的修法是事前限制風格、產業、市值偏離，和多頻率訊號 |
| A 股 10 月因子報酬（[新浪財經](https://k.sina.cn/article_5952915720_162d249080670554d2.html)、[21 經濟網](https://www.21jingji.com/article/20261117/herald/4a59afd2994071c882b8340bda7a6202.html)、[證券時報](https://www.stcn.com/article/detail/4068483.html)） | 2026-11-17；新浪和證券時報頁面未標日期 | 實盤（產業整體）；只讀到搜尋摘要 | 10 月 Barra 因子 β −5.87%、動能 −2.89%、殘差波動 −2.15%，只有市值是正的。上半年指增平均超額 3.11%，前一年同期 14.17% |

能搬到我們題目的有四件事。目標要配合評分。特徵要減，不要加。規則可以事先固定、少做實驗。風格曝險要有上限。第一件已經做了：`X_price` 的三個成員都是對報酬做迴歸。第二件只做到「不加」：法人、基本面、微結構、技術指標、產業、美股敏感度這些欄組加進去都沒過門檻（notebook 26、31），所以一直是 41 欄，但還沒試過往下減。後兩件只做了一部分。這三件都在後面的表裡。

## 台股的開盤到收盤：高 β 偏弱，隔夜和盤中各自延續

結論：台股有文獻支持的規律，大多在 `X_price` 的欄裡了。和 c2v2d 最有關的是「高 β 股盤中比較弱」，它解釋了基礎排名為什麼一直偏低 β。

| 規律 | 來源 | 證據 | 09:00 前能用嗎 |
|---|---|---|---|
| 台股 β 和報酬的關係在隔夜和盤中正負相反（隔夜正、白天反轉），作者解釋為白天過度修正。「高 β 股盤中報酬較低」是從這個框架推的，看不到台股的係數、大小和樣本期。「保證金提高讓關係變平」來自它引用的美股研究（Jylha 2018），不是這篇的台股結果 | Chang、Tseng、Yang，PBFJ vol. 95（2026）art. 103003，2025-11-17 上線（[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0927538X25003403)） | 樣本內；只讀到摘要（全文 403） | 能（β 用過去資料估） |
| 美股 β 在隔夜有正的定價，盤中沒有 | Hendershott、Livdan、Rösch，JFE 2020（[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0304405X20301732)） | 背景，樣本內 | 能 |
| 動能和反轉的利潤要嘛全在隔夜、要嘛全在盤中，兩段正負相反 | Lou、Polk、Skouras，JFE 2019（[PDF](https://personal.lse.ac.uk/polk/research/TugOfWar.pdf)） | 背景，樣本內 | 能（用過去的兩段） |
| 台股用過去盤中報酬排的動能為正，用過去隔夜報酬排的為負 | PBFJ 2023（[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0927538X23002226)） | 背景，樣本內；只讀到搜尋摘要 | 能 |
| 台股隔夜報酬短期延續、長期反轉，散戶比重高時更強 | PBFJ vol. 80，2023（[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0927538X23001646)） | 背景，樣本內；只讀到搜尋摘要 | 能 |
| 可交易濾網後的上市櫃股票（前一天成交值至少 5,000 萬、沒被處置、可當沖，檔數沒寫）開盤到收盤平均 −25 bp、收盤到隔天開盤 +29 bp（2020-01～2026-11） | [TANGCHIH0221/forced-flow-reversal](https://github.com/TANGCHIH0221/forced-flow-reversal) | 資料到 2026-11，樣本內（描述統計） | 基準率 |
| 約 390 檔流動股開盤到收盤平均 −0.26%（README 的數字；它自己的表扣 0.23% 成本後換算毛報酬約 −0.31%，沒有隔夜數字）；3 天 MA5 斜率最高一成的股票 −0.52% | [raywu918daytrade/quant_trading_v2](https://github.com/raywu918daytrade/quant_trading_v2) | 資料到 2026-10，樣本內（作者說濾網是看過全期才挑的） | 能 |
| 我們的 50 檔：全猜漲每天 −0.00046（WF_Test 2024-01～2026-10） | 本專案資料，2026-11-27 重算 | 保留期回測 | 基準率 |
| 弱勢股暴漲後隔天放空：每筆淨 +19.2 bp、勝率 57.7%，2023、2025 接近 0 | [forced-flow-reversal](https://github.com/TANGCHIH0221/forced-flow-reversal) | 資料到 2026-11，樣本內，全體上市櫃 | 能 |
| 月營收創新高的隔天開盤放空，勝率 57%；公布前漲多、股價高、營收成長快的更明顯 | Lai、Tsai、Lin、Lin（[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S154461232600440X)、[SSRN 5345252](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5345252)） | Finance Research Letters 100（2026）109911，期刊已確認；樣本內。57% 和「12 年一秒資料」只出現在搜尋摘要，摘要本身沒寫，全文 403 | 能，只要營收在 t 前一晚以前公布 |
| 台積電營收創新高 NT$5,870 億，三天跌近 10% | [24/7 Wall St](https://247wallst.com/investing/2026/11/16/taiwan-semiconductor-booked-a-record-nt587-billion-month-the-stock-has-lost-nearly-10-in-three-days-anyway/) | 2026-11-16，新聞 | 單一事件 |
| 亞洲指數期貨對美股大波動反應過度，盤中反轉 | J. Empirical Finance（[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0927539809001078)） | 約 2009，背景，樣本內；只讀到搜尋摘要 | 能（美股收盤已知） |
| 台指期夜盤和隔天日盤同方向只有 44.2% 的日子 | [vocus 數字沙龍](https://vocus.cc/article/6b06c5defd89780001a0499f) | 資料 2026-01～10-29（197 天），樣本內（描述統計） | 部分（夜盤 05:00 收） |
| 11 月下旬夜盤一度跌 1,881 點、開低，盤中來回超過 1,600 點後收高 | [BigGo](https://finance.biggo.com/news/87863ec0-43ce-44de-b3bf-9be9f24282c8)、[BigGo 夜盤](https://finance.biggo.com/news/9bcd7356-d4fb-4cc4-8199-dd8dea8b8ae3) | 新聞，各報導點數不一致，日期沒核對 | 單一事件 |
| 台股隔夜和白天的漲跌方向負相關 | Tsai、Lih、Ko，Physica A 2012（[RePEc](https://ideas.repec.org/a/eee/phsmap/v391y2012i24p6497-6505.html)） | 背景，樣本內；只讀到搜尋摘要 | 要當天開盤，不能用 |
| 正隔夜後白天反轉較多的組合沒有顯著較好 | 成大碩論 2024（[NCKU](https://thesis.lib.ncku.edu.tw/thesis/detail/4af6b2f36d5183af397e9ae338140bb1)） | 背景，樣本內，結果是零 | 能 |
| 韓國散戶開盤買、收盤賣，散戶比重解釋隔夜和盤中的差距 | Ahn、Fan、Noh、Park（[ResearchGate](https://www.researchgate.net/publication/379633524_Retail_Trading_Intensity_and_the_Overnight-Intraday_Return_Gap)） | 2025-12-19 版，背景，樣本內；只讀到搜尋摘要 | 能（用前一天的散戶比重） |

高 β 這條和我們的資料對得上。c2v2d 的基礎排名和 β120 的相關一直在 −0.5～−0.8（本專案資料，2026-11-27 重算）。notebook 24 把 β 中和掉，回測每天少 0.00035（區間 −0.00061～−0.00006），表示低 β 股盤中較強這件事本身是訊號的一部分（`memory/projects/04-raw-feature-experiments.md`，2026-11-12）。同一本也量到代價：大盤盤中大漲（m > 1%）的日子 `X_price` 平均 −0.0026，大跌（m < −1%）的日子 +0.0048。

方向模型的傾斜層在 2021 的確認期沒過，也和這條一致。那年方向模型反而比較準（corr(p, m) 0.158），c2v2d 還是每天比原版少 0.000228（t −1.11），虧在猜漲的日子高 β 股沒有比低 β 股多漲（`memory/projects/14-c2-tuning.md`）。

在 25 漲 25 跌、每檔權重一樣的格式下，賺低 β 的盤中溢酬和承擔負的 β 曝險是同一個押注。猜漲那 25 檔的平均 β 比猜跌的低，整本就會在高 β 股大漲的日子賠錢。這個押注沒辦法只留好處。

## 用正確的標準差重算檢定力

結論：這次研究一開始的檢定力估計用每天標準差 0.01，比實際大一倍多。c2v2d 實際的長期標準差是 0.00456。重算後，驗證 c2v2d 自己的優勢約要 55 個交易日；分辨兩個模型差 0.0002 要好幾百天。

| 情境 | 每天標準差 | 每天優勢 | t = 2 要幾天 | 單邊 5%、檢定力 80% | MinTRL（95%，常態） | 8 天平均的標準誤 | 數字來源 |
|---|---|---|---|---|---|---|---|
| 一開始的假設（標準差設錯） | 0.01 | 0.0005 | 1,600 | 2,473 | 1,085 | 0.0035 | 原本的算術，作廢 |
| 長期標準差，原本假想的優勢 | 0.00456 | 0.0005 | 333 | 514 | 227 | 0.0016 | 重算 |
| 長期標準差，c2v2d 的回測優勢 | 0.00456 | 0.00123 | 55 | 85 | 40 | 0.0016 | 重算 |
| 保留期的波動，c2v2d 的回測優勢 | 0.0083 | 0.00123 | 182 | 282 | 126 | 0.0029 | 重算 |

標準差和優勢來自本專案資料（2026-11-27 重算），天數是常態近似的算術。MinTRL（最短紀錄長度）的公式和 deflated Sharpe 的來源是 Bailey 和 López de Prado（[SSRN 2460551](https://papers.ssrn.com/abstract=2460551)，2014，背景；[PerformanceAnalytics MinTrackRecord](https://rdrr.io/cran/PerformanceAnalytics/man/MinTrackRecord.html)）。厚尾或負偏態會讓天數更長。

其他重算：

- 最近 5 天至少 4 天是負的：原本算 16.4%（標準差 0.01、優勢 0.0005）。用 c2v2d 的回測數字是 8.2%，歷史實際 8.3%。完全沒優勢時是 18.75%。
- 成對比較（兩個模型同一天的分數差）：原本用標準差 0.01 算，差 0.0005 在相關 0.5、0.8、0.9 時要 1,600、640、320 天到 t = 2。改用 0.00456 是 333、133、67 天。
- 影子模型：notebook 34 量到的成對差標準差，多一個成員約 0.0012，加欄約 0.0016～0.0024（`memory/projects/04-raw-feature-experiments.md`，2026-11-13）。新成員實際能多的約每天 +0.0001～+0.0002（`memory/projects/11-breakthrough-research.md`）。差 0.0002 要 144～576 天才到 t = 2。
- 影子模型的勝負天數：「5 天贏 4 天」在完全沒差時機率 18.75%，「3 天贏 3 天」12.5%。

Phase 2 正式期到哪天還沒查到（`memory/context/01-competition.md`）。照這張表，比賽結束前 c2v2d 的正式紀錄大概到不了 t = 2，影子模型的比較更不可能。選模型只能靠長期、按日期切、事先登記的回測。

## c2v2d 還值得用嗎

結論：值得繼續用。這 8 天的虧損落在已知風險之內，重現也確認程式沒錯。要處理的是基礎排名偏低 β 這個押注，它在 10～11 月的高波動裡被放大了。

### 這 8 天的數字

| 項目 | 數字 | 來源 |
|---|---|---|
| 正式期 11-17～11-26（8 個交易日）合計 | −0.0186 | 本專案資料，2026-11-27 重算 |
| 11-23 一天 | −0.0265，其中 β 曝險 −0.0259（重算表裡叫「β 傾斜」，為什麼讀成整本的 β 曝險見下一小節） | 同上 |
| 其他 7 天合計 | +0.0079（每天約 +0.0011） | 同上 |
| 8 天拆解 | β 曝險 −0.0092、選股 −0.0094、大盤方向 0（每天都 25 漲 25 跌） | 同上 |
| 拆解推算 | 11-23 以外的 7 天：β 曝險 +0.0167、選股 −0.0088；11-23 選股 −0.0006 | 用上面兩列相減 |
| 11-23 交出去的版本 | p = 0.469、傾斜 −0.125，和 `rank_ensemble` 只換 1 組 | oop 推上來的 `data/submission/run_2026-11-23.log`，07:27 |
| 傾斜層每天改了幾檔（和 `rank_ensemble` 比） | 11-17 12、11-18 6、11-19 4、11-20 0、11-23 2、11-24 6、11-25 14、11-26 2 | `shadow_<t>.csv`，2026-11-27 重算 |
| 正式和回測重現（11-17～11-20） | 0.0188 對 0.0195 | 本專案資料，2026-11-27 重算 |
| 網站分數 | 11-18 −0.0011、11-19 +0.0221、11-20 −0.0034、11-25 −0.0071、11-26 −0.0086 | 同上 |
| 11-24 網站上的版本 | Mac 08:18 手動交的全猜漲，蓋掉 oop 的 c2v2d | commit `b0061a8` |
| 11-26 累計名次 | 126 隊第 109（含 11-16 組員手動交的 C2 和 11-24 的全猜漲，不全是 c2v2d） | 本專案資料，2026-11-27 重算；`memory/context/01-competition.md` |
| 回測 2022-01～2026-11-20（1,183 天） | 每天 +0.00123，標準差 0.00456，約 60% 的日子是正的 | 同上 |
| 分段 | Val 2022～2023 +0.00092；WF_Test 2024-01～2026-10 +0.00130；Holdout 2026-10-12～11-20 +0.00500（標準差 0.0083，和正式期的 11-17～11-20 重疊） | 同上 |
| 不加傾斜（只有 `X_price` 排名） | WF_Test +0.00101 | 同上 |
| 8 天合計 ≤ −0.0186 的歷史比例 | 1.0% 的 8 天視窗 | 同上 |
| 8 天合計 < 0 的歷史比例 | 21% | 同上 |
| 10～11 月的波動下（標準差約長期的 1.8 倍） | 這麼大的 8 天虧損約 10 次有 1 次 | 常態近似 |

影子模型（天數太少，下不了結論）：`overnight_up`（前一晚美股大跌就全猜漲）比 c2v2d 多 +0.0578，全部來自 11-23；`rank_inst`（加法人欄）多 +0.0200，5 天贏 4 天；`n1` 多 +0.0153、`js_n1` 多 +0.0193，3 天都贏（本專案資料，2026-11-27 重算）。

### 8 天說明了什麼

程式沒壞。11-17～11-20 的正式分數和回測重現只差 0.0007。

虧損集中在一天，來源是 β 曝險。11-23 傾斜層幾乎沒動（p 0.469，只換 1 組），所以拿掉傾斜層救不了那天。換 1 組最多讓分數變 (r_a − r_b) ÷ 25；要換出 −0.0259，兩檔當天的報酬要差約 65 個百分點，漲跌幅限制 ±10% 下不可能。重算表裡的「β 傾斜」那一塊，公式是當天 50 檔報酬對 β 的橫斷面斜率乘上整份預測的 β 曝險，所以是整本的 β 曝險，大部分來自基礎排名（2026-11-27 核對 `decompose_live.py` 的定義；11-23 c2v2d 和 `rank_ensemble` 只差 2 檔，也就是 1 組）。高 β 股當天大漲是推斷，根據是那天 β 那塊大虧、`overnight_up`（全猜漲）又贏 c2v2d 0.0578。能明顯減少那天虧損的，是把基礎排名的低 β 傾向中和掉，而 notebook 24 量過這樣長期每天少 0.00035。

這和 notebook 24 量到的輪廓一樣：大盤大漲日賠、大跌日賺。11-23 以外的 7 天，β 曝險反而賺了約 +0.0167。

在長期波動下，這種 8 天虧損約百分之一的機會。用 10～11 月的波動算，約十分之一。這兩個月很多天大盤上下 3～4%，β 曝險的波動跟著放大。

### 8 天沒說明什麼

分不出優勢還在不在。8 天平均的標準誤是 0.0016（長期）到 0.0029（現在的波動），比回測優勢 0.00123 還大。

分不出影子模型比較好。5 天贏 4 天、3 天贏 3 天在完全沒差時都有 12～19% 的機會出現。`overnight_up` 的 +0.0578 是單一事件；方向和文獻一致（亞洲期貨對美股大跌反應過度、夜盤和日盤只有 44.2% 同方向），但一次不能確認一條規則。

分不出低 β 溢酬是不是已經翻轉。A 股 2026 的教訓是，風格因子反轉可以持續好幾個月，超額報酬會被抹平。如果 AI 循環的高 β 股持續領漲，c2v2d 的 β 那塊會連續拖好幾週，到時候也要很多天才看得出來。

### 文獻怎麼看

短期紀錄分不出運氣和能力。Hull 的前 10 名一個月換掉 8 隊，Mitsui 第 10 名說 3 個月太短，M6 的極端 Sharpe 都在運氣範圍內。這些都指向同一件事：8 天不能拿來換模型。

台股 2026 的研究（Chang、Tseng、Yang，PBFJ vol. 95）支持低 β 傾向有結構上的原因，所以基礎排名的方向是對的。同一條研究不支持「猜漲日改押高 β」，2021 的確認失敗也一致。傾斜層在 2025-01～2026-10 每天多 +0.000324（t 2.54），2021 每天少 0.000228（t −1.11）（`memory/reference/05-daily-model.md`）。

A 股 2026 是反例的警告：超額報酬和風格曝險重疊時，風格一反轉就一起虧。業者的修法是事前限制風格偏離。

### 結論和要做的事

- 繼續用 c2v2d：回測每一段都是正的，正式期重現正確，8 天的虧損在已知風險內。不要因為影子模型贏了幾天就換。
- 12-06 的檢討：原本就要看要不要改成 `c2`。在那之前先做下一節表裡的第 1 項（c2v2d 分數的風格歸因和依波動縮小），用數字決定。
- 低 β 押注的大小：要不要縮小是風險取捨，期望分數只會小降。值不值得要看名次目標，也就是下一節的第 2 項，要 Ian 決定。

## 還沒試過、文獻有支持的方向

### 研究框架有沒有把我們綁住

部分有。幾乎每個新點子都寫成「`X_price` 加一點東西」，比較的是期望分數；風險和名次很少當成目標（notebook 23 是例外）。基礎排名的低 β 傾向一直被當成訊號，沒有風險預算。台股特有的事件資料（月營收創新高）只做成連續欄，沒做事件。

另一方面，模型種類的搜尋已經比文獻廣：TRA、HIST、PatchTST、TabPFN、Chronos、DoubleAdapt、線上學習都測過。2026 年的證據說模型種類最不重要。文獻建議的「新方向」有一半其實已經在 `X_price` 裡，見第二張表。真正的天花板在題目本身：開盤後剩下能預測的部分很小。

### 還沒試過的方向（依優先順序）

| 優先 | 方向 | 文獻證據強度 | 09:00 前能用嗎 | 怎麼公平測試 | 本專案做過的部分 |
|---|---|---|---|---|---|
| 1 | c2v2d 分數的風格歸因（殘差 IC），和依波動縮小低 β 傾向 | 中。A 股 2026 實盤產業經驗（事前限制風格偏離）；台股高 β 盤中偏弱（PBFJ 2026，樣本內，只讀到搜尋摘要）；FactorBench 的殘差 IC（保留期回測） | 能。β120、前一晚美股、VIX、過去 20 天的波動在 07:10 前都有 | 先只診斷：用 1,183 天的每日表，每天在 50 檔裡把 c2v2d 的名次對 β、20 天動能、前一天反轉、波動、流動性、產業做迴歸，算殘差 IC，把分數拆成各風格和殘差，看每年和 11-17～11-26 各佔多少。再依事先選好的波動代理（前一晚美股 \|報酬\|、VIX 或 50 檔平均報酬過去 20 天的波動）分五組，看 β 那塊在各組的平均和標準差。如果高波動組的平均接近 0、標準差最大，再事先登記「高波動日把基礎排名的 β 部分縮小 λ」，λ 固定不調，在沒拿來挑規則的期間（例如 2006～2019 長歷史，先確認哪些用過）測成對日差，Newey-West 區間。夜盤 2017 年才開始，`data/raw/taifex/tx.csv` 也只從 2020 起，所以長歷史不能用夜盤當代理 | notebook 24 量過整體 β 份額（回測 14%、2022～2023 −11%、Phase 2 27%）和全部中和（每天 −0.00035）；notebook 20、34 測過群中和；notebook 40 做過單欄的殘差 IC；notebook 44、42 量過傾斜層。沒有對 c2v2d 的分數做多風格歸因，沒有依波動分組，也沒有部分中和。這個想法是看了 11-23 才有的，不能用 2022～2026 驗證。notebook 23 量到 \|夜盤報酬\| 和當天 \|m\| 的名次相關只有 0.14，波動代理可能不夠準 |
| 2 | 依目前名次和剩餘天數調整風險 | 中，理論加比賽資料。落後時誇大、偏離別人比較好（[Lichtendahl、Winkler，Management Science 2007](https://econpapers.repec.org/RePEc:inm:ormnsc:v:53:y:2007:i:11:p:1745-1755)，背景，理論）；領先時應該向共識靠（[arXiv 2409.19477](https://arxiv.org/html/2409.19477v2)，2024，背景，理論）；M6 依名次調權重（實盤，比賽資料） | 能，名次前一晚就知道 | 把 notebook 23 的名次模擬改成從目前名次出發，依剩餘天數算每種押法（25/25、押漲 n、丟銅板）進前 5、前 10、中位數以上的機率。目標和規則先寫好、Ian 同意才執行，之後照規則每天自動決定 | notebook 23 做過從零開始和接著模擬榜的靜態表：20 天從零開始時 25/25 進前 5 是 4.2%，丟銅板全押 14.3%、期望分數 0。沒有依目前名次的規則。11-24 的手動全猜漲是臨時決定。需要先查到 Phase 2 的結束日 |
| 3 | 月營收創新高的隔天猜跌 | 弱到中。Lai 等 2026（樣本內、一秒資料，只讀到搜尋摘要）；台積電 11 月的單一事件 | 能，營收要在 t 前一晚以前公布 | 事件研究：Top50 2019 起，每檔公布營收後的第一個交易日，事先固定「創新高」的定義（例如歷史新高），比較有旗標和沒旗標的股票日的相對盤中報酬。過了再測「排名猜漲但有旗標就改猜跌」的成對日差。事件數有限，先算檢定力 | notebook 25 的月營收年增、月增等 `h_*` 欄單欄 \|t\| < 2.4，notebook 26 基本面組沒過 Holm；`05-experiment-critique.md` 把「營收公布日」列為死路（文獻判斷，沒實測）。「創新高」這個事件旗標沒測過，先驗要放低 |
| 4 | Kronos-small 當第四個成員 | 弱，正負都有。事先登記的指數期貨測試裡，它的每日排名訊號在盲測期重現（NQ IC +0.116，p 0.015），沒過交易條件（[arXiv 2611.12141](https://arxiv.org/abs/2611.12141)，2026-11-09，讀過全文）；訓練截止後的美股測試 IC +0.022（t 1.39，12 天收盤到收盤、每 6 天換倉，單一使用者沒經審查的報告）（[Kronos issue #375](https://github.com/shiyu-coder/Kronos/issues/375)，2026-07-29，訓練截止後樣本外）；A 股複製等同均值回歸（[nlim820/kronos-forecast](https://github.com/nlim820/kronos-forecast)，2026，保留期回測，可能在預訓練期內） | 能，用 t − 1 以前的日 K 棒在前一晚跑 | 只用 2025-08（Kronos 發表）以後的資料，約 300 天（[Release-Date Rule](https://jiripik.com/2026/08/31/kronos-foundation-model-validation/)，2026-08-31，其他：實務部落格的做法建議，沒有評估）。`X_price` 加 Kronos 名次，和 `X4_placebo`（多一個換種子的成員）比成對日差；同時報它和 Chronos、前一天反轉的相關。300 天的最小可偵測差約 +0.0002（用 notebook 34 的數字按天數粗估），一般成員到不了，事先寫好「沒過就收掉」 | BT 11 測過 Chronos 零樣本當第四個成員，停在試跑關，它大致是過去 512 天平均盤中報酬的平滑版（名次相關 0.84）；BT 14 的聯合候選 J 在 Other50 沒過（`memory/projects/11-breakthrough-research.md`）。Kronos 沒測過，但很可能重複 Chronos 的結果 |
| 5 | 特徵依群集精簡 | 弱。DRW 第 1 名（實盤，比賽私榜；增益是保留期回測），Hull 第 4 名說大部分工程特徵都丟了 | 能 | 每次重訓只看訓練窗：相關 > 0.6 的欄分群、留中心欄，再留每個 fold 重要度都排前段的欄。`X_pruned − X_price` 成對日差，2022～2023 和沒用過的期間，Holm | notebook 30 量過每欄、每組打亂的影響；notebook 34 說成員數已經飽和。沒有依群集精簡後重訓。41 欄本來就少，DRW 是從幾百欄減，先驗低 |
| 6 | 事先固定、不調參的經濟規則 | 弱。Hull 第 4、Mitsui 第 10（實盤，比賽私榜），兩人都說短窗分不出運氣 | 能 | 從外部文獻挑一條（例如過去 3 天 MA5 斜率最高一成猜跌），今天就寫下規則，不看我們的資料，直接影子跑；回測只報告，不拿來改規則 | `persist`、`overnight_up`、RB 的反彈訊號都是從我們的資料挑出來的，不算「不調參」 |

### 看起來是新方向、其實做過

| 方向 | 文獻來源 | 本專案做過的 | 結果 |
|---|---|---|---|
| \|r\| 加權的訓練目標 | DRW 第 1 名的 MSE 加 Pearson 損失；Jane Street 的加權 R² | `X_price` 的三個成員（ridge、kernel ridge、LightGBM）都是對報酬做迴歸；Kaggle raw 系列的樣本權重是 \|r\| ÷ 平均（`04-raw-feature-experiments.md`「切分和評分」）；notebook 21 `X4_binary_w`、35 `X_w1`；\|z\| 加權收掉 | 都在 ±0.00005 內或沒過門檻 |
| 過去報酬拆成隔夜和盤中 | Lou、Polk、Skouras 2019；台股 PBFJ 2023 | `X_price` 已經有 `a_gap`、`a_intraday`、`c_intraday_mean5/20`、`o_gap_mean5/20`、`o_intraday_minus_gap5`、`o_gap_intraday_corr60`、`p_gap_rel20`、`p_e_mean120`（`src/models/m3_rank_ensemble.py`）；長窗的拆法查證過已涵蓋（`05-experiment-critique.md`） | 已在模型裡 |
| 基礎排名的 β 中和 | STRATA、Numerai 的風格中和 | notebook 24 `X_beta_neutral` | 每天 −0.00035（−0.00061～−0.00006） |
| 產業或群中和 | Numerai、FactorBench | notebook 20 `P1_neutral`；notebook 34 的 λ 曲線 | −0.00024；λ > 0 一路變差 |
| 單欄的殘差 IC | FactorBench | notebook 40 | 只報告；殘差 IC 比單欄 t 接近模型效果 |
| 時間序列基礎模型零樣本 | 2611.12141、2606.27100 | BT 11 Chronos、BT 14 J | 停在試跑關；Other50 沒過 |
| 多期間輔助目標 | Jane Street 第 8 名 | notebook 35 `X_h5`（5 天平均標籤） | +0.00006（p 0.21） |
| 每天線上更新 | Jane Street 第 8 名 | raw 28a～28e；Numerai 式和 Jane Street 式線上學習；JS_ONLINE（`n1`、`js_n1`） | 校正後沒有顯著贏 c2v2d；`n1`、`js_n1` 影子跑中 |
| 異質集成（線性加非線性） | 2611.12389 | `X_price` 本身就是 ridge、kernel ridge、LightGBM | 成員已飽和（notebook 34） |
| 美股個股同業（台積電 ADR、SOX × β） | 美股對中國個股的領先落後圖（[arXiv 2603.10559](https://arxiv.org/abs/2603.10559)，2026-03-11／04-13，背景，保留期回測，只讀到摘要） | notebook 31 `X_us`；`05-experiment-critique.md` 把 ADR 溢價、供應鏈列為死路 | 沒過 |
| 結算日、MSCI 生效日、營收公布日的虛擬變數 | 台股結算規則（[期交所](https://www.taifex.com.tw/cht/5/formulaStock)）、MSCI 生效日新聞（[Newtalk](https://newtalk.tw/news/view/2026-08-31/1056763)，2026-08-31，新聞） | `05-experiment-critique.md` 列為死路（文獻判斷，沒實測） | 效果多在收盤前的結算時段，判斷理由仍成立 |
| 融資、當沖比率（散戶參與） | 韓國散戶研究 | `16-concept-drift.md`：融資集中在中小型股；`04-raw-feature-experiments.md` 收掉當沖比率 | 沒做或沒過 |
| 押大盤、改猜漲檔數 | M6、比賽理論 | MT 01～21、notebook 23、UB 研究進行中 | MT 沒過；UB 照登記走 |

## 確定沒用或證據是負面的方向

結論：下面這些方向，2026 年有直接的負面證據，或在我們的格式下根本用不上。組員不用再試。

| 方向 | 主要證據 | 對我們沒用的原因 |
|---|---|---|
| LLM 新聞情緒當每天開盤到收盤的訊號 | OLIVIA：新聞在開盤就反映完，對開盤到收盤的 IC 只有 0.010（[arXiv 2611.03985](https://arxiv.org/abs/2611.03985)，2026-11-02，訓練截止後樣本外，讀過全文）；28 個檢定全不顯著（[arXiv 2608.04200](https://arxiv.org/abs/2608.04200)，2026-08-04）；新聞類別的歷史平均勝過嵌入，Llama-2 的優勢到預訓練截止就消失（[arXiv 2611.33458](https://arxiv.org/abs/2611.33458)，2026-11-24，訓練截止後樣本外，只讀到摘要）；記憶過的公司日期才準（LAP，[arXiv 2512.23847](https://arxiv.org/abs/2512.23847)，v2 2026-06-12，訓練截止後樣本外，只讀到摘要）。反方：時間點模型 DatedGPT 在美股新聞仍有 Sharpe 3.20，偷看溢酬每一標準差 26.4 bp（[arXiv 2603.11838](https://arxiv.org/abs/2603.11838)，v2 2026-07-23，訓練截止後樣本外，只讀到摘要） | 新聞有資訊，但在 09:00 開盤就反映了。要有 09:00 前的中文新聞來源，免費模型的截止在 2025～2026，幾乎沒有乾淨的歷史可回測。還要贏過「新聞類別歷史平均」這個便宜基準。`05-experiment-critique.md` 也把新聞、PTT 情緒列為死路 |
| 零樣本時間序列基礎模型 | 160 格 0 格贏「不變」（[arXiv 2611.12141](https://arxiv.org/abs/2611.12141)，2026-11-09）；五檔美股的增益「小而零星」（[arXiv 2606.27100](https://arxiv.org/abs/2606.27100)，2026-06-25，保留期回測，可能在預訓練期內）；全球日報酬上表現普遍差（[arXiv 2511.18578](https://arxiv.org/abs/2511.18578)，v2 2026-11-15）；Kronos 訓練截止後 IC +0.022 不顯著，85 天裡最好的 5 天佔 91% 的毛利（[issue #375](https://github.com/shiyu-coder/Kronos/issues/375)，2026-07-29）；A 股複製和均值回歸 48 次有 45 次同號（[nlim820](https://github.com/nlim820/kronos-forecast)）；CSI 1000 擇時 2025 樣本內 +32.01%、2026-01～08 樣本外 −5.16%（[FFasir/Kronos](https://github.com/FFasir/Kronos)，訓練截止後樣本外，只讀到搜尋摘要）；5,000 檔 A 股波動預測 Kronos 每年墊底（[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1544612326011347)，2026，只讀到搜尋摘要） | 我們的 BT 11 也看到 Chronos 只是長期平均的平滑版。台股沒有任何評估（[twse-research issue #52](https://github.com/j1998719/twse-research/issues/52)，2026-10-07，提案被關掉） |
| LLM 交易 agent 直接下單 | 兩個機隊沒有方向優勢（[arXiv 2609.05663](https://arxiv.org/abs/2609.05663)，2026-09-04，實盤，加密貨幣）；Alpha Arena Season 1.5（交易的是 Hyperliquid 上的美股永續合約）合計虧約 27%～33%，32 個帳戶 5～6 個是正的（來源不一致，官方榜 404），11 個公開競技場只有 2 個的中位數模型賺錢（[briefs.co](https://www.briefs.co/news/public-ai-trading-contests-largely-lose-money-and-raise-new/)，2026-11-07，實盤，轉述）；CSI 300 的報酬大多是風格曝險（[KTD-Fin](https://arxiv.org/abs/2605.28359)，2026-05-27）；上證 50（日頻）6 個模型 0 個贏指數（[AI-Trader，arXiv 2512.10971](https://arxiv.org/abs/2512.10971)，2025-12，背景，實盤約 5 週，經 [Quantex](https://quantex.com.sg/research/2026-10-17-llm-agents-vs-buy-and-hold/) 2026-10-17 轉述）；長期回測優勢明顯退化（[FINSABER，arXiv 2505.07078](https://arxiv.org/html/2505.07078v2)，2025-05，背景）；LMArena 分數高不代表交易好（[LiveTradeBench，arXiv 2511.03628](https://arxiv.org/abs/2511.03628)，2025-11，背景，實盤 50 天，只讀到搜尋摘要）；熱門選股提示詞五條都輸 0050（[FinLab](https://finlab.finance/blog/ai-stock-picking-prompts-backtest)，頁面未標日期，保留期回測，可能在模型訓練期內，只讀到搜尋摘要） | 唯一一致的好處是回撤小，來自常常空手。我們 25 漲 25 跌不能空手。`19-ai-agent-feasibility.md` 已暫停 |
| 開盤前半小時動能（第一個半小時預測最後半小時） | 2018 年後在美國 ETF 扣成本每天 −2.30 bp（t −5.17），每個子期間都虧（[Dead Signals Lab](https://deadsignalslab.substack.com/p/replication-intraday-momentum-eight)，2026-09-30，訓練截止後樣本外：用的是原論文發表後的資料）；台股 ETF 版本控制外資和法人單後消失（[JBEF 2021](https://www.sciencedirect.com/science/article/abs/pii/S2214635021001015)，背景，只讀到搜尋摘要） | 要當天盤中資料，09:00 前用不到 |
| 當天跳空反轉（用今天的跳空排序） | 〈Overnight-Intraday Reversal Everywhere〉（[作者頁](https://yangliu-finance.github.io/research/)、[Paperswithbacktest 摘要](https://paperswithbacktest.com/strategies/overnight-intraday-reversal-everywhere)，2015 初稿、2025 版，背景，樣本內，只讀到摘要） | 要 t 的開盤價，碰到「不用 t 當天價格」的規則。SD 01 也看不出開盤前資料有用 |
| 深度序列模型在可交易時段 | STRATA 六個基準在開盤到收盤的多空全負；CRSP 基準沒有架構勝出 | 我們的 TRA、HIST、PatchTST、KD 系列也沒贏 |
| LLM 或 agent 自動挖因子 | FactorBench：R&D-Agent 中和後 IC 0.0011，LLM 因子池最像 Alpha101（[arXiv 2610.06947](https://arxiv.org/html/2610.06947v1)，2026-10-03） | 挖到的大多是已知風格，`X_price` 已經有 |
| 波動目標、反波動加權（Hull 第 4 名的主要分數來源） | [Hull 第 4 名](https://www.kaggle.com/competitions/hull-tactical-market-prediction/writeups/4th-place-technical-model-no-learning-short-te)，2026-07-03 | 每檔固定 ±1，沒有部位大小可調 |
| 漲停隔日沖 | 台大碩論，限股本 50 億以下的中小型股（[NTU](https://tdr.lib.ntu.edu.tw/retrieve/641179a0-5bd4-498d-b692-b713a33ab599/ntu-114-1.pdf)，2026-01，背景，樣本內） | 我們是大型股，只在極端日才相關 |
| 「跳空一定回補」 | 台股所有跳空當天回補率 49%，超過 1.5% 的只有 21%（[BOS 巴菲特線上學院](https://buffettonlineschool.com.tw/gap-fill-myth/)，約 26 年資料，樣本內） | 迷思，而且要當天開盤 |

本專案已經測過、校正多重比較後沒有顯著贏 c2v2d 的（本專案資料，2026-11-27 重算）：線上 logistic 迴歸、持續性規則、法人資料疊加（最好的候選，累積 SPA 校正後 p 約 0.09）、HMM 和馬可夫切換、大盤擇時和改猜漲檔數、DoubleAdapt、TRA、HIST、PatchTST、TimeDistill、Qlib Alpha158 式因子、Numerai 式和 Jane Street 式線上學習、路徑簽名、小型 CNN、決策導向損失、線上專家加權、反彈訊號、概念漂移方法、當天開盤前資料（日韓開盤跳空、台指期 08:45 開盤）。

## 引用核對結果（2026-11-27）

結論：14 條都真實存在，數字大多對得上。6 條的措辭要修，已改進前面各表；1 條改變方向（Kronos 在事先登記的測試裡有重現的排名訊號）。

| 代號 | 引用 | 存在 | 內容相符 | 讀到 | 更正 |
|---|---|---|---|---|---|
| A1 | STRATA，arXiv 2608.28060 | 是 | 是 | 全文 | 數字全對；v1 2026-08-28，現行 v4 2026-09-14。多空是風格殘差化後的十分位差，三個種子平均 |
| A2 | OLIVIA，arXiv 2611.03985 | 是 | 部分 | 全文 | 「微調 LLM」其實是 ModernBERT 編碼器；0.020 是收盤到收盤，開盤到收盤 0.010（t 0.8）；商用的是三個非生成式決策模型，都沒過身分洩漏檢查 |
| A3 | 深度模型基準，arXiv 2606.09420 | 是 | 部分 | 全文 | 15 種含 3 種線性或統計模型；淨 Sharpe 全負只在有限制的二次規劃組合，十分位多空有 4 個是正的 |
| A4 | QLoRA 情緒基準，arXiv 2608.04200 | 是 | 是 | 全文 | 28 = 7 個模型 × 4 個期間，BH 校正後最小 q 0.9622；7 個裡 3 個不是 LLM；2019 樣本在預訓練期內 |
| L1 | 基礎模型事先登記測試，arXiv 2611.12141 | 是 | 是 | 全文 | 「事先登記」是自己雜湊鎖定；指標是 MAE 比；Kronos 不在 160 格裡，它的每日排名訊號在盲測期重現（NQ IC +0.116，p 0.015），筆記原本寫成沒有 |
| L2 | Kronos issue #375 | 是 | 是 | 全文 | 12 天收盤到收盤的排名 IC，每 6 天換倉，只有 Kronos-small；存活偏差減少但沒消除；單一使用者的報告 |
| L3 | KTD-Fin，arXiv 2605.28359 | 是 | 是 | 全文 | 10 個 agent 9 個是負的、1 個約 +0.2%；歸因沒做顯著性檢定；期間和模型訓練截止重疊 |
| L4 | Alpha Arena Season 1.5 | 是 | 部分 | 全文（新聞） | 文章沒寫 Season 1.5，是從配置推的；官方榜 404；鏈上重算約 −27%、5 個是正的 |
| T1 | Chang、Tseng、Yang，PBFJ 95 | 是 | 是 | 摘要 | 正負相反有直接寫；「高 β 盤中較弱」是推論；保證金那句來自美股文獻 |
| T2 | Lai 等，FRL 100（2026）109911 | 是 | 是 | 摘要 | 期刊確認；57% 和一秒資料只在搜尋摘要；平均放空報酬 0.34%（收盤回補），成本沒確認 |
| T3 | 台股 GitHub 兩個 repo | 是 | 部分 | 全文 | −25 bp 和 +29 bp 只來自 forced-flow-reversal 的濾網後樣本；390 檔是另一個 repo，−0.26% 和它自己的表（毛約 −0.31%）不一致 |
| C1 | FactorBench，arXiv 2610.06947 | 是 | 是 | 全文 | 20 天後報酬、五個市場等權，沒有測每天開盤到收盤 |
| C2 | A 股量化私募 2026 下半年 | 是 | 部分 | 全文 | 原因有三個（風格反轉、隱性擁擠、量縮），「動能和 β 同步反轉」是一位管理人的看法 |
| C3 | Jane Street 第 8 名 | 是 | 是 | 全文 | 「最大增益」是從數字推的；學習率 0.0003 對基礎 0.0005，不算很小 |

## 還沒查證

下面的引用只讀到摘要、搜尋摘要或別人的轉述。最關鍵的 14 條已經回原文核對，結果在上一節；下表是還沒核對的。

| 引用 | 日期、證據類型 | 讀到的程度 | 影響的結論 | 要核對什麼 |
|---|---|---|---|---|
| Chang、Tseng、Yang，PBFJ vol. 95（[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0927538X25003403)、[IDEAS](https://ideas.repec.org/s/eee/pacfin2.html)） | 2026，樣本內 | 搜尋摘要（403） | 高 β 盤中偏弱；c2v2d 低 β 傾向的理由 | 樣本期、效果大小、大型股有沒有成立 |
| Lai、Tsai、Lin、Lin，月營收創新高（[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S154461232600440X)、[SSRN 5345252](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5345252)） | 2026，樣本內 | 搜尋摘要 | 方向 3 | 期刊、樣本期、報酬是開盤到收盤還是更長、大型股的結果 |
| A 股 10 月因子報酬和指增超額（[新浪財經](https://k.sina.cn/article_5952915720_162d249080670554d2.html)、[21 經濟網](https://www.21jingji.com/article/20261117/herald/4a59afd2994071c882b8340bda7a6202.html)、[證券時報](https://www.stcn.com/article/detail/4068483.html)、[東方財富](https://wap.eastmoney.com/a/202607013790075168.html)） | 21 經濟網 2026-11-17、東方財富 2026-07-01，新浪和證券時報頁面未標日期；實盤（產業整體） | 搜尋摘要 | c2v2d 和 A 股風格反轉的類比 | β −5.87%、動能 −2.89%、上半年 3.11% 對 14.17% 的原始出處 |
| 2608.23761（2026-08-24）、2611.12389（2026-11-09）、2608.05755（2026-08-06）、2608.23808（2026-08-24）、2611.33458（2026-11-24）、2512.23847（v2 2026-06-12）、2603.11838（v2 2026-07-23），連結見前面各表 | 各篇的證據類型見前面各表 | 摘要 | 第二節的整體判斷 | 切分日期、成本假設、程式有沒有公開。2512.23847 v2 有一段搜尋摘要說殘差預測「撐過樣本外」，沒核對 |
| 美股對中國的領先落後圖（[arXiv 2603.10559](https://arxiv.org/abs/2603.10559)） | v1 2026-03-11、v2 2026-04-13，背景；保留期回測 | 摘要 | 個股同業方向 | 樣本外 R²、Sharpe |
| 〈Do Published Equity Anomalies Survive Clean Data?〉（[SSRN 7075658](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7075658)） | 2026-07（依搜尋結果）；保留期回測（無存活偏差資料上的複製） | 搜尋摘要（403） | 用事後還原價排序會造出約 3.5 的假 Sharpe | 只影響用價格水準的欄；`X_price` 的報酬類欄不受影響 |
| Muravyev 複製研究「42% 在新資料成立」（[wealthhubtrading.com](https://www.wealthhubtrading.com/articles/does-empirical-finance-replicate-ai-answers-the-question)） | 2026 的部落格，頁面未標確切日期；其他（轉述） | 轉述，原文沒找到 | 背景 | 原文 |
| M6 只有 33% 的隊贏等權基準（[IJF 41(4) 2025](https://ideas.repec.org/a/eee/intfor/v41y2025i4p1383-1394.html)、[arXiv 2406.19105](https://arxiv.org/abs/2406.19105v2)） | 2024～2025，背景；實盤（比賽資料） | 搜尋摘要 | 短期名次多半是運氣 | M6 期間的大盤方向（判斷「空單多的隊名次好」是不是只反映大盤跌） |
| Numerai `ender_60`、3×CORR + 15×MMC（[TradingView](https://www.tradingview.com/news/coinmarketcal:7bcc7881b094b:0-numeraire-atomic-staking-changes-numerai-payout-mechanics-28-aug-2026/)）、Signals 新獎金從 round 1363 起（[Numerai Signals scoring](https://docs.numer.ai/numerai-signals/scoring)） | TradingView 2026-08-28，Numerai 文件頁面未標日期；其他（規則） | 搜尋摘要 | Numerai 越來越重視和群眾不同 | 現在的獎金目標到底是 Ender20、ender_60 還是 Jupiter 60D2L |
| Numerai 基金 2024 淨 25.45%、Sharpe 2.75，2025-10 前淨 8%（[Hedgeweek](https://www.hedgeweek.com/quant-hedge-fund-numerai-secures-500m-jpmorgan-allocation/)、[Bitget](https://www.bitget.com/news/detail/12560605074172)） | 頁面未標日期（內容是 2025-08、2025-10），背景；實盤 | 搜尋摘要 | 背景 | 2026 年的數字 |
| Jane Street 第 162 名、Hull 第 100 和 163 名、Hull 前三名（[JS 162](https://www.kaggle.com/competitions/jane-street-real-time-market-data-forecasting/writeups/max-abhi-private-lb-162nd-solution)、[Hull 100](https://www.kaggle.com/competitions/hull-tactical-market-prediction/writeups/100th-place-ensemble-prediction-naive-allocation)、[Hull 163](https://www.kaggle.com/competitions/hull-tactical-market-prediction/writeups/163th-place-solution-sharpe-ratio-2-16)、[Hull 私榜](https://www.kaggle.com/competitions/hull-tactical-market-prediction/leaderboard?tab=private)） | 頁面未標日期（Jane Street 2025，背景；Hull 2026-06 結束）；實盤（比賽私榜） | 搜尋摘要 | 比賽經驗 | 前三名的方法 |
| RD-Agent 原論文（[arXiv 2505.15155](https://arxiv.org/pdf/2505.15155)）、AlphaSeek（[arXiv 2608.13913](https://arxiv.org/pdf/2608.13913)）、AlphaDiverse（[arXiv 2609.29014](https://arxiv.org/pdf/2609.29014)） | 2025-05（背景）、2026-08、2026-09；保留期回測（AlphaDiverse 用 2026-01～08 當一次性的外層評估） | 搜尋摘要 | 自動挖因子 | AlphaDiverse 外層評估的數字 |
| FinRL Contest 2025（[概覽](https://finrl-contest.readthedocs.io/en/latest/finrl2025/overview.html)、[arXiv 2505.06408](https://arxiv.org/html/2505.06408v2)、[arXiv 2504.02281](https://arxiv.org/pdf/2504.02281)） | 2025，背景，概覽頁面未標日期；比賽，方法主張是保留期回測 | 搜尋摘要 | 背景 | 最終榜和樣本外數字 |
| FinLab 的策略數字（[策略頁](https://finlab.finance/strategies)、[四因子](https://finlab.finance/strategies/four-factor-composite)、[多因子 2026](https://finlab.finance/blog/multi-factor-stock-selection-beat-0050)、[RSI 動能](https://finlab.finance/blog/rsi-indicator-taiwan-momentum)、[投信買超](https://finlab.finance/blog/institutional-strategy)、[AI 挖因子](https://finlab.finance/blog/ai-factor-mining-agent)、[機器學習 8 年樣本外](https://finlab.finance/blog/machine-learning-predict-stock-price)、[程式交易](https://finlab.finance/tools/program-trading)） | 頁面未標日期（回測到 2026，有一篇到 2026-09-30）；保留期回測（業者內容），投信買超 2026 年起那段是業者自報的前瞻紀錄 | 搜尋摘要 | 台股業者經驗（月、季頻率） | 投信買超 2026 年起 +39.8% 對 0050 +45.0% 是不是真的事先固定 |
| 台股 PBFJ 2023 兩篇、Physica A 2012、成大碩論 2024（連結見台股表） | 2012～2024，背景；樣本內 | 搜尋摘要 | 隔夜和盤中的規律 | 樣本期和效果大小；這些規律大多已在 `X_price` |
| Kronos #354、#355 的 AAPL 方向正確率 48.5～54.3%（經 [jiripik.com](https://jiripik.com/2026/08/31/kronos-foundation-model-validation/) 轉述） | issue 2026，部落格 2026-08-31；訓練截止後樣本外 | 轉述 | 基礎模型負面 | 原 issue |
| A 股 5,000 檔波動預測（[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1544612326011347)）、FFasir/Kronos（[GitHub](https://github.com/FFasir/Kronos)） | 2026；前者保留期回測（2023～2025，可能在預訓練期內），後者 2026 那段是訓練截止後樣本外，頁面未標日期 | 搜尋摘要 | 基礎模型負面 | 原文數字 |
| Alpha Arena Season 1.5 各模型報酬（[forklog](https://forklog.com/en/ai-model-grok-4-2-triumphs-in-trading-tournament/)、[gncrypto](https://www.gncrypto.news/news/mystery-model-alpha-arena-season-1-5-winner/)、[aihola](https://aihola.com/article/grok-wins-alpha-arena-trading)） | 約 2025-12 結束，背景，頁面未標日期；實盤 | 搜尋摘要，數字互相矛盾（+12.11% 對 +34.59%～−96.15%） | LLM agent 負面 | 官方榜（nof1.ai 回 404） |
| Season 1 加密貨幣（[protos.com](https://protos.com/llm-crypto-trading-contest-finds-llms-cant-trade-crypto/)、[Yahoo Finance](https://finance.yahoo.com/news/ai-trading-bots-really-deliver-100216403.html)）、Season 2（[reviewnexa](https://reviewnexa.com/nof1-ai-review/)、[buildix](https://www.buildix.trade/blog/nof1-alpha-arena-lessons-ai-trading-byok-strategy-advisor-2026)） | Season 1 2025-10～11，背景，實盤；Season 2 查到 2026-08-06 仍沒有結果 | 搜尋摘要 | LLM agent 負面 | Season 2 有沒有公布 |
| Agent Market Arena（[arXiv 2510.11695](https://arxiv.org/html/2510.11695v1)）、StockBench（[arXiv 2510.02209](https://arxiv.org/abs/2510.02209)）、AlphaForgeBench（[arXiv 2602.18481](https://arxiv.org/abs/2602.18481)），經 [Quantex](https://quantex.com.sg/research/2026-10-17-llm-agents-vs-buy-and-hold/) 轉述 | 2025-10、2025-10、2026-02，背景；實盤 2 個月、保留期回測（可能在預訓練期內）、保留期回測 | 轉述 | LLM agent 負面 | 「最好的 agent」是不是事後從 20 組裡挑的 |
| Fin-Analyst（[arXiv 2607.12233](https://arxiv.org/pdf/2607.12233)）、LiveOption（[arXiv 2609.33470](https://arxiv.org/pdf/2609.33470)）、FinPanel（[arXiv 2611.18150](https://arxiv.org/abs/2611.18150)）、拓撲異常分數（[arXiv 2606.08586](https://arxiv.org/abs/2606.08586)） | 2026-07、2026-09、2026-11、2026-06；前兩篇實盤（單一股票短窗、選擇權），後兩篇證據類型不明 | 搜尋摘要 | LLM agent 和小樣本研究 | 原文數字 |
| 韓國盤後新聞情緒（[SSRN 6516494](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6516494)）、日本標題詞典（[CIRJE 2026cf1267](https://www.cirje.e.u-tokyo.ac.jp/research/dp/2026/2026cf1267.pdf)）、中國論壇情緒（[SSRN 6570552](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6570552)）、台股六檔新聞融合（[arXiv 2603.19286](https://arxiv.org/html/2603.19286v1)） | 2026-03～04，背景；證據類型不明，台股那篇是保留期回測（可能在預訓練期內） | 搜尋摘要 | 亞洲新聞情緒 | 效果大小、樣本期和模型截止的關係 |
| 中國中期隔夜報酬（[SSRN 6840249](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6840249)）、美股傳到 A 股（[SSRN 7407698](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7407698)）、資訊不對稱和隔夜（[SSRN 7443340](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7443340)） | 2025～2026（SSRN 7443340 依搜尋結果是 2026-09）；樣本內，SSRN 7407698 證據類型不明 | 搜尋摘要（403） | 隔夜和盤中 | 效果大小 |
| 亞洲指數期貨對美股反應過度（[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0927539809001078)） | 約 2009，背景；樣本內 | 搜尋摘要 | `overnight_up` 的文獻支持 | 樣本期、台指期的結果 |
| 商品 ETF 隔夜和白天（[MDPI Commodities 5(3):16](https://doi.org/10.3390/commodities5030016)）、分段 GARCH（[arXiv 2607.03669](https://arxiv.org/html/2607.03669)） | 2026-08、2026-07；證據類型不明 | 搜尋摘要（MDPI 回 403） | 背景 | 效果大小 |
| TimesFM-3 在 2026-08-31 發布（[pasqualepillitteri.it](https://pasqualepillitteri.it/en/news/26634/time-series-ai-compared-timesfm-chronos-timestral)） | 頁面未標日期；其他（新聞） | 搜尋摘要 | 基礎模型 | Google 的原始公告和授權 |
| 11 月下旬夜盤大跌後收高（[BigGo](https://finance.biggo.com/news/87863ec0-43ce-44de-b3bf-9be9f24282c8)、[BigGo 夜盤](https://finance.biggo.com/news/9bcd7356-d4fb-4cc4-8199-dd8dea8b8ae3)） | 2026-11 下旬，頁面未標日期；新聞 | 新聞，點數不一致 | 11-23 的市場背景 | 日期是不是 11-23，點數 |
| MSCI 11 月生效日（[TVBS](https://news.tvbs.com.tw/money/2885820) 寫 11-24，[Top1 Markets](https://www.top1markets.com/tw/insights/stocks/msci-semi-annual-adjustment-november-taiwan-stocks) 寫 11-30 收盤） | 2026，頁面未標日期；新聞 | 新聞，互相矛盾 | 背景 | 正確日期 |

## 後續：`RP 37` 的多因子歸因（2026-11-27）

優先 1 做完了（結果在 `memory/projects/22-ml-research-pipeline.md` 的 `RP 37` 結果）。和這份報告有關的三點：

- 11-23 的讀法要更正。這份報告的 β 曝險 −0.0259 是單變量拆法。換成多因子（β、動能、反轉、波動、流動性、產業）後，11-23 的 β 是 −0.0118，反轉 −0.0063、動能 −0.0039、流動性 −0.0038；8 天合計的 β 是 +0.0077，虧損主要是反轉 −0.0117 和產業 −0.0096。
- 低 β 傾向是 c2v2d 的主要收入：`WF_Test` 每天 +0.00130 裡 β 佔 55%、選股 18%，β 主要是結構性的溢酬，每年都是正的。
- 依波動縮小低 β 押注這條結案：09:00 前的波動代理（rv20）預測不了大盤波動，高波動日 β 那塊平均也是賺的。
