# 金融領域知識如何改變ML問題

狀態：研究綜合與待測假設；沒有新模型績效宣稱。書目由Crossref、OpenAlex及作者／出版者原文核對，來源與閱讀範圍見[SOURCES](SOURCES.md)，完整書目見[references.bib](references.bib)。

## 這個問題需要的金融思維

| 領域問題 | 對本題的實際影響 | 對應設計 |
|---|---|---|
| 資訊可能先反映在開盤價 | 能預測隔夜跳空，不代表能預測開盤後到收盤 | 海外訊號逐組測**盤中return**增益；不把gap與intraday標籤混用 |
| 共同市場成分與個股成分同時存在 | 只有相對排名可能丟掉整個市場同漲／同跌方向 | 保留市場截距，輸出raw intraday return或加權方向；不將target按當日橫斷面去均值後直接取正負 |
| 跨市場收盤／假日／DST不同 | 台灣同日期不等於來源已收盤；相鄰教師global列不等於一個美國session | 原生序列先算return，再按真實available_at對齊；保留age和缺值 |
| 波動與流動性隨市場狀態改變 | 同樣一個return特徵在不同狀態可能影響不同 | 先測lagged volatility、量能、market×stock交互作用；它們是候選而非保證 |
| 少量日期、同日股票高度關聯 | 8萬列不是8萬個獨立市場狀態 | 按日期切分、日期群聚報告；深度模型採小容量，避免無限制搜尋 |
| 訊號可能衰退、來源會修訂 | 歷史效果與今天下載的數值不等於當時可得到的效果 | 固定版本、向前驗證、跟隨新session收集；保存所有負結果 |
| 有些金融量不是價格 | 對淨部位算百分比return會出錯，殖利率變動的單位也不同 | OI水準／口數差、VIX水準／點數差、殖利率基點差；匯率須固定報價方向 |

表中「資訊已反映在開盤」是有經濟意義的待測解釋，**不是本輪已證明M0負結果的因果原因**。美國一般核心交易16:00 ET收盤依NYSE官方時刻；季節／提早收盤須用原生日曆，不能固定全年對應台北同一小時。[FIN25](SOURCES.md#fin25)

當前08:10凍結早於本課09:00截止。當日台股開盤價、收盤價、盤後籌碼不能進feature；收盤競價的研究也不能直接搬進盤前。同日稍晚才出現的資訊若要使用，必須另訂cutoff、重建資料與驗證，不默默放寬既有版本。

## 文獻直接支持與移植限制

### 1. 高品質tabular基準與非線性交互作用

Gu、Kelly、Xiu的RFS研究比較資產風險溢酬預測方法，摘要及作者工作論文指出樹／神經網路的優勢與非線性交互作用有關，反覆出現的訊號包括momentum、liquidity、volatility。[FIN07](SOURCES.md#fin07)、[FIN16](SOURCES.md#fin16)

可借用：先做正則化基準，逐步測非線性；把feature、模型、loss與驗證一起視為學習程序。限制：該研究分析美國股票的月度風險溢酬，本題是台股日內二元決策；其投資組合／Sharpe結果不能換算成本題預期分數。已核對RFS2020書目，方法閱讀主要來自2019修訂工作論文，不假稱逐字讀完被擋的出版者全文。

Kelly、Xiu的《Financial Machine Learning》已核對到Foundations and Trends in Finance 13(3–4),205–363,2023。[FIN20](SOURCES.md#fin20) 本輪出版者正文被擋，該條只作經核實的延伸閱讀書目，不以未讀章節支持特定效果。

企業來源另交叉核對AQR的同名研究摘要與Journal發表記錄，確認其比較線性、降維、樹與神經網路的脈絡。[FIN28](SOURCES.md#fin28) Jane Street官方ML頁則自述其研究著重神經網路、低延遲、非平穩市場狀態與研究／工程／交易協作。[FIN27](SOURCES.md#fin27) 前者是公開研究，後者是公司自述；都不等於公開了完整正式策略或證明本題需要同等基礎設施。

### 2. 多試幾次就「進步」的危險

Bailey等人的backtest-overfitting研究指出，策略／配置選擇本身會造成回測過度配適；作者提出評估選擇程序的方法。[FIN17](SOURCES.md#fin17)、[FIN18](SOURCES.md#fin18) Harvey、Liu、Zhu的研究提醒大量因子檢定必須考慮多重比較；本輪核對出版書目及NBER摘要，尚未閱讀出版者完整正文。[FIN09](SOURCES.md#fin09)、[FIN26](SOURCES.md#fin26)

可借用：預先限制研究次數、記錄失敗、保留後續時間外資料。不能照搬：沒有檢查資料相依與假設，就把PBO或Sharpe修正當本課平均score的有效顯著性證明。本專案先報日期層級分數、跨期穩定性與比較範圍；短期樣本也不給獲利保證。

McLean、Pontiff的Journal of Finance摘要比較樣本外與發表後的predictability，發現其研究樣本的效果會減弱。[FIN23](SOURCES.md#fin23) 這支持保留後續資料的重要性；其數值不作為我們訊號將衰退多少的估計，也不能證明所有市場都一樣。

### 3. 時間模型：先決定可用序列，再選神經網路

Lim、Zohren的綜述將CNN、RNN與attention放在encoder／decoder及已知／未知輸入的框架下。[FIN15](SOURCES.md#fin15)、[FIN21](SOURCES.md#fin21) Bai等人的TCN原文定義causal convolution、dilation與residual block，並在一般序列任務比較RNN。[MOD03](SOURCES.md#mod03)、[MOD08](SOURCES.md#mod08)

可借用：小型causal TCN和既有GRU比較；保存完整過去特徵窗口，批次與逐日推論必須一致。限制：通用序列benchmark不證明金融方向可預測；現有GRU正式daily仍因缺中間日期context被阻擋，不用換模型名字掩蓋資料問題。

Deep momentum研究展示把序列模型與金融目標結合的思路。[FIN13](SOURCES.md#fin13)、[FIN22](SOURCES.md#fin22) 本輪核對摘要／出版metadata；它研究的momentum／風險調整目標不同於本課，不直接採用其loss或績效數字。

### 4. 跨股／市場狀態：最需要改的是target

MASTER的AAAI2024原文用市場狀態gating，加上股內與股間attention；其公開實驗使用中國CSI300／CSI800、五日close-price變化及**每日橫斷面標準化target**，另報IC／RankIC和top-30組合指標。[FIN12](SOURCES.md#fin12)、[MOD07](SOURCES.md#mod07)，PDF頁2–5

這是一個重要的移植邊界：本課需要每股的絕對盤中方向，市場共同正負方向也影響score。直接移植每日去均值的target，可能讓「比別股好、但仍下跌」被當成正方向。因此本研究只借用市場gate與跨股資訊整合，改用`mu_market + delta_stock`的raw-return head，或abs(return)加權二元head；不沿用原論文排名標籤與top-k策略。這個改法是本專案提案，尚未驗證。[MODEL_ARCHITECTURES](MODEL_ARCHITECTURES.md)

## 四組優先特徵假設

| 群組 | 具體候選 | 使用限制／驗收 |
|---|---|---|
| F0 個股基準 | 現有7個lag；再測更長歷史return、20日波動、量能相對值 | 所有rolling只用cutoff前值，保留觀測缺口；先證明比F0原版有增益 |
| F1 跨市場 | IXIC／GSPC／SOX／KS11／TWII原生return的1、5、20-session窗口；ADR／NVDA | 同來源算完再對齊；ADR非指數。TSM ADR股數比例與匯率換算若未經官方依據核實，premium特徵先不算 |
| F2 市場狀態 | VIX level／點數差、波動、來源age、休市mask；與個股波動／產業互動 | 不把VIX當可交易資產return；缺值不回填未來；新聞只是後續候選 |
| F3 匯率／利率／產業 | 固定報價FX return、殖利率bp差、產業相對return | 先補發布與vintage；目前FRED只有raw、產業只有單日水準，不宣稱可計完整歷史return |

每一組先單獨對F0比較；首輪R1僅4組資料×2個固定模型共8設定，精確欄位／版本在執行前凍結。少量有機制的交互作用留待另一次有上限的研究階段。現有E01–E03的負結果保持原樣；不宣稱「再多抓指數就會更好」。產業分類、股票全集與公司行動也要有時間範圍；本課固定50股可作競賽全集，不能據此宣稱已解決長期市場存活者偏差。

## 評分導向的loss

令`y=1{r>0}`、`p∈{0,1}`，固定樣本集合下有：

`abs(r)*1{p!=y} = (abs(r) - (2p-1)*r)/2`。

因此比較三個目標：普通分類作對照、abs(r)加權分類、估計`E[r|X]`後取正負的回歸。這是根據本課公式的專案推導，與基石第08／09／10講連接，並非某篇金融論文保證加權logistic勝出。加權log loss是替代loss；Huber、截尾或縮小極端return會改變目標，應另立假設。所有權重只從已完成的歷史label產生，不能變成當日輸入。

## 研究與真實交易分開

競賽平均score未扣除手續費、交易稅、滑價、借券限制或未成交；模型輸出也未指定可執行的倉位、容量與風險管理。研究文章的annualized Sharpe、IC及排名勝出都不能直接當成真實獲利。這裡建立的是可追溯的競賽預測架構，不把排行榜成績冒稱已驗證的實盤alpha。
