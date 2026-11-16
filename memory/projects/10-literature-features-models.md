# 特徵篩選與模型集成的文獻（2026-11-14）

Ian 2026-11-14 晚上要的兩個方向：特徵篩選（冗餘、共線、統計檢定）和更好的模型與集成（ranker、時序、泛化、抓大盤）。workflow `wf_d7da6caa-b41`（22:55～23:40）：11 個 Sonnet 搜尋方向、逐篇查證、三個角度評分（證據、搬得過來、做得到，各 1～5 分取平均）、四個立場的提案者、五個投票者 Borda 排名；收斂和驗證交給兩個 Opus。原始輸出在 scratchpad 的 `research2/result.json`（session 結束會清掉，重點都抄在這裡）。

- 候選 112 篇，查證通過 108 篇（特徵 48、模型 60），查證結果 yes 70、partly 32、unclear 6；平均分 2.51，最高 3.67。
- 「對我們」一欄是 Sonnet 寫的搬移評估，只取第一句；分數是三個角度的平均。

## 特徵軌（48 篇）

### F1 共線性、VIF、有效秩（16 篇）

| 論文 | 年 | 發現 | 對我們 | 分 |
|---|---|---|---|---|
| [Panning for Gold: Model-X Knockoffs for High-dimensional Controlled Variable Selection](https://arxiv.org/abs/1610.02351)，Emmanuel Candès, Yingying Fan, Lucas Janson, Jinchi Lv | 2018 | 在有限樣本控制 FDR，模擬中檢定力高於有對手的方法。 | 對我們有用的是它直接處理「相關欄位互相替代」的問題，單欄打亂和 IC 在共線欄上會互相稀釋，knockoff 會。 | 3.3 |
| [Please Stop Permuting Features: An Explanation and Alternatives (arXiv 標題：Unrestricted Permutation forces Extrapolation: Variable Importance Requires at least One More Model, or There Is No Free Variable Importance)](https://arxiv.org/abs/1905.03151)，Giles Hooker, Lucas Mentch, Siyu Zhou | 2021 | 在實驗中 permute-and-predict 的方法（含 RF 變數重要度、PDP、ICE）會高估相關特徵的重要度，可能嚴重誤導（摘要未給具體數字）。 | 直接解釋 30 的現象：單欄打亂都不顯著、整組打亂才顯著，因為 a_ret1 和 stock_ret_lag1 這類欄互相替代，單欄打亂後另一欄還在，分數幾乎不動。 | 3.3 |
| [Empirical Asset Pricing via Machine Learning](https://www.nber.org/papers/w25398)，Shihao Gu, Bryan Kelly, Dacheng Xiu | 2020 | 樹與神經網路最好，優勢來自非線性交互； | 對我們有利：很多高度相關特徵時，用正則化與非線性模型比事前降維好，並且訊號集中在少數價量欄，與我們 41 欄價量為主的結果一致。 | 3.3 |
| [All Models are Wrong, but Many are Useful: Learning a Variable's Importance by Studying an Entire Class of Prediction Models Simultaneously](https://arxiv.org/abs/1801.01489)，Aaron Fisher, Cynthia Rudin, Francesca Dominici | 2019 | 證明 MCR 的機率界，並和 permutation importance、條件重要度、線性係數連起來。 | 對我們有解釋價值：30 看到 ridge 係數互相抵銷，就是同一類好模型裡替代欄重要度可以大幅不同。 | 3.0 |
| [Cleaning large correlation matrices: tools from random matrix theory](https://arxiv.org/abs/1610.08104)，Joël Bun, Jean-Philippe Bouchaud, Marc Potters | 2017 | 摘要指出在金融市場資料上這類估計量優於先前提出的方法（無具體數字）； | 可以回答「41 欄的有效秩是多少、小特徵值是不是雜訊」。 | 3.0 |
| [Shrinking the Cross Section](https://www.nber.org/papers/w24070)，Serhiy Kozak, Stefan Nagel, Shrihari Santosh | 2020 | 只用少數特徵的稀疏 SDF 無法解釋期望報酬，但少數主成分就能近似 SDF； | 對我們有利也有不利：它說相關特徵不該用「稀疏挑欄」處理，而應該在主成分空間縮收，這和 08 的結果（稀疏挑欄沒有比較好）一致。 | 3.0 |
| [Seemingly Virtuous Complexity in Return Prediction](https://www.nber.org/papers/w34104)，Stefan Nagel | 2025 | RFF 的好表現來自動量歷史上有效，不是從資料學到訊號； | 對我們有幫助的警告：過度參數化的 kernel／隨機特徵模型可能只在複製近期報酬的加權平均，所以我們若擴大 Nyström 維度，要用反轉的人工資料或打亂時序來確認它真的在學。 | 3.0 |
| [Taming the Factor Zoo: A Test of New Factors](https://www.nber.org/papers/w25481)，Guanhao Feng, Stefano Giglio, Dacheng Xiu | 2020 | 對近年提出的因子，多數是冗餘的，只有少數（含獲利能力）仍顯著； | 提供一個正式的「新欄是否有增量」檢定流程，適合我們每次加欄位前使用，替代 25 的單欄 IC。 | 2.7 |
| [Dissecting Characteristics Nonparametrically](https://bfi.uchicago.edu/working-paper/dissecting-characteristics-nonparametrically/)，Joachim Freyberger, Andreas Neuhierl, Michael Weber | 2020 | 許多先前找到的預測變數沒有增量資訊，非線性有影響； | group LASSO 把一個特徵的所有展開綁在一起，可以直接用在我們的『持續性組』『法人組』整組挑，和 30 的整組打亂結果對應。 | 2.7 |
| [Correlation and variable importance in random forests](https://arxiv.org/abs/1310.5726)，Baptiste Gregorutti, Bertrand Michel, Philippe Saint-Pierre | 2017 | 模擬顯示 RFE 能留下少數欄而預測誤差仍低； | 提供了「相關會讓重要度失真」的理論依據，RFE 也是遞迴剔除冗餘欄最常見的做法。 | 2.3 |
| [The best way to select features? Comparing MDA, LIME, and SHAP](https://arxiv.org/abs/2005.12483)，Xin Man, Ernest Chan | 2020 | 三種方法選出的特徵集都顯著改善樣本外預測指標，且彼此預測表現沒有顯著差別； | 對我們有用的重點是：挑欄方法彼此預測表現沒差、各法選出的欄不一致，與 08 的結果一致，也提醒不要依賴某一種單欄重要度排名。 | 2.0 |
| [Benign Overfitting in Linear Regression](https://arxiv.org/abs/1906.11300)，Peter L. Bartlett, Philip M. Long, Gábor Lugosi, Alexander T | 2020 | 需要過度參數化，且對預測不重要的方向數要遠多於樣本數； | 提供「有效秩」的正式定義與為何冗餘方向在 ridge 下無害。 | 1.7 |
| [Surprises in High-Dimensional Ridgeless Least Squares Interpolation](https://arxiv.org/abs/1903.08560)，Trevor Hastie, Andrea Montanari, Saharon Rosset, Ryan J. Tib | 2022 | 重現 double descent； | 提醒「特徵數 ≈ 樣本數」附近才危險； | 1.7 |
| [Overparametrized models with posterior drift](https://arxiv.org/abs/2506.23619)，Guillaume Coqueret, Martial Laguerre | 2025 | 市場擇時結果對子期間與決定複雜度的頻寬參數敏感，只有 15 年持有期這個數字出現在摘要； | 屬不利證據：高複雜度模型在金融資料上不穩定，支持保守的欄位數與正則化，但同樣只在大盤擇時情境，對橫截面名次的外推有限。 | 1.7 |
| [The behaviour of random forest permutation-based variable importance measures under predictor correlation](https://pmc.ncbi.nlm.nih.gov/articles/PMC2848005)，Kristin K. Nicodemus, James D. Malley, Carolin Strobl, Andre | 2010 | 當真有關聯時，未條件化的 RF 重要度會給相關預測變數較大份額，條件化版本會降低它們； | 說明樹模型（我們的 LightGBM 成員）看到一組相關欄時，會把重要度集中到其中幾欄，但預測力本身不受影響，因為樹只需要其中一欄。 | 1.5 |
| [The Virtue of Complexity in Return Prediction](https://www.nber.org/papers/w30217)，Bryan T. Kelly, Semyon Malamud, Kangying Zhou | 2024 | 簡單少參數模型「嚴重低估」報酬可預測性； | 這是不利於『減欄』的證據：它主張欄越多、正則化得當越好。 | 1.3 |

### F2 相關欄的重要度（7 篇）

| 論文 | 年 | 發現 | 對我們 | 分 |
|---|---|---|---|---|
| [Understanding Global Feature Contributions With Additive Importance Measures (SAGE)](https://arxiv.org/abs/2004.00668)，Ian Covert, Scott Lundberg, Su-In Lee | 2020 | 在八個資料集上，SAGE 給的重要度比其他方法更準確（對照已知真實重要度的合成情境）。 | SAGE 衡量的是『整體損失的貢獻』，和我們的目標（每日截面名次相關）接近，可以直接把損失換成每日截面相關。 | 3.0 |
| [Distribution-Free Predictive Inference For Regression (LOCO)](https://arxiv.org/abs/1604.04173)，Jing Lei, Max G'Sell, Alessandro Rinaldo, Ryan J. Tibshirani | 2018 | LOCO 給有限樣本有效的變數重要性區間，不需要模型設定正確。 | LOCO 的設計等於重新訓練版的 LOGO，對共線性比打亂穩； | 3.0 |
| [... and the Cross-Section of Expected Returns](https://www.nber.org/papers/w20592)，Campbell R. Harvey, Yan Liu, Heqing Zhu | 2016 | 新因子的 t 值應高於 3.0，而不是 2.0，因為資料挖掘； | 直接支持背景檔提到的『對 25 的單欄 IC 表做 FDR 或 t > 3』。 | 3.0 |
| [Sparse Signals in the Cross-Section of Returns](https://econpapers.repec.org/RePEc:bla:jfinan:v:74:y:2019:i:1:p:449-492)，Alex Chinco, Adam D. Clark-Joseph, Mao Ye | 2019 | LASSO 提高樣本外擬合與 Sharpe； | 這是『稀疏假設有用』的少數金融證據，但頻率是分鐘且訊號短命； | 3.0 |
| [Conditional Variable Importance for Random Forests](https://bmcbioinformatics.biomedcentral.com/articles/10.1186/1471-2105-9-307)，Carolin Strobl, Anne-Laure Boulesteix, Thomas Kneib, Thomas  | 2008 | 一般（邊際）打亂的重要度偏向高度相關的預測變數，原因有兩個：樹在分裂時偏好相關變數，以及無條件打亂本身多給相關變數的加分。 | 直接對應我們的 30（a_ret1 和 stock_ret_lag1 幾乎一樣、單欄打亂都不顯著）。 | 2.7 |
| [Machine learning from a "Universe" of signals: The role of feature engineering](https://ideas.repec.org/a/eee/jfinec/v172y2025ics0304405x25001461.html)，Bin Li, Alberto G. Rossi, Xuemin (Sterling) Yan, Lingling Zh | 2025 | 在大量原始訊號上，ML 策略樣本外報酬仍顯著，但比用精選訊號的先前研究弱得多； | 對我們不利也有利：不利是『丟一大堆原始欄位進去』會變弱，支持篩選； | 2.7 |
| [Publication Bias in Asset Pricing Research](https://arxiv.org/abs/2209.13623)，Andrew Y. Chen, Tom Zimmermann | 2022 | 平均 Empirical Bayes 修正約為樣本內平均報酬的 10～15%； | 它是『對我們不利』的證據：公開因子大部分樣本外還會存在，所以『特徵多』本身不是風險，風險是樣本內選擇。 | 2.0 |

### F3 多重檢定、knockoffs、穩定性選擇（12 篇）

| 論文 | 年 | 發現 | 對我們 | 分 |
|---|---|---|---|---|
| [Lucky factors](https://econpapers.repec.org/RePEc:eee:jfinec:v:141:y:2021:i:2:p:413-435)，Campbell R. Harvey, Yan Liu | 2021 | 可以辨識因子的增量解釋力，並保住解釋力很強但在橫斷面檢定中常失去顯著性的市場因子； | 它的『imposing the null with bootstrap』可以直接搬到我們的設定：對每天橫斷面做 block bootstrap（保持日內結構，按日整塊重抽），得到『最佳欄的最大 t』的分布，一次處理 41 欄的多重檢定與相依，不用假設獨立。 | 3.7 |
| [Powerful Knockoffs via Minimizing Reconstructability](https://arxiv.org/abs/2011.14625)，Asher Spector, Lucas Janson | 2020 | 在特徵相關的高斯線性模型中，MAC 型 knockoffs 在『極簡單』的設定也可能完全沒有檢定力（摘要寫 ρ≥0.5 的 exchangeable 設計下，幾乎每個特徵統計量的檢定力漸近為零）； | 這是對我們不利的證據：我們的 41 欄裡 `a_ret1` 與 `stock_ret_lag1` 幾乎一樣（30），許多動能、報酬欄的相關很高，標準 knockoffs 在這種設計下會把兩欄都判成不顯著（誰也不能獨立於另一個）。 | 3.0 |
| [Anomalies and False Rejections](https://ideas.repec.org/a/oup/rfinst/v33y2020i5p2134-2179..html)，Tarun Chordia, Amit Goyal, Alessio Saretto | 2020 | 建議 t 門檻：時間序列迴歸 3.8、橫斷面迴歸 3.4； | 這是對我們不利的證據：資料探勘出的策略多數不是真訊號，我們在同一批 100 檔、同一段歷史上做了 36 本實驗，等於同一種風險。 | 3.0 |
| [Replicating Anomalies](https://ideas.repec.org/a/oup/rfinst/v33y2020i5p2019-2133..html)，Kewei Hou, Chen Xue, Lu Zhang | 2020 | 65% 的異常在單次門檻下失敗（交易摩擦類 96% 失敗）； | 對我們不利：特徵數越多，真訊號越稀，且多數『看起來有用』的欄在嚴格檢定下失效，和我們 25、26、31、33 的『新欄都沒過』吻合。 | 3.0 |
| [Most claimed statistical findings in cross-sectional return predictability are likely true](https://arxiv.org/abs/2206.15365)，Andrew Y. Chen | 2022 | 簡單上界在九個先前研究中的八個給 FDR ≤ 25%，改良上界給 FDR ≤ 9%。 | 這是對『嚴格門檻』路線的反證：過嚴的門檻（t>3 以上）會丟掉真訊號，因為真的 FDR 本來就沒那麼高。 | 3.0 |
| [Is There a Replication Crisis in Finance?](https://www.nber.org/papers/w28432)，Theis Ingerslev Jensen, Bryan Kelly, Lasse Heje Pedersen | 2023 | 多數因子可複製，可分群成 13 個主題，樣本外在 93 國新資料中成立； | 這是反方證據：多重檢定的懲罰在『階層式收縮』下比逐一檢定輕很多。 | 3.0 |
| [The control of the false discovery rate in multiple testing under dependency](https://projecteuclid.org/journals/annals-of-statistics/volume-29/issue-4/The-control-of-the-false-discovery-rate-in-multiple-testing-under/10.1214/aos/1013699998.full)，Yoav Benjamini, Daniel Yekutieli | 2001 | BH 在 PRDS 下仍控制 FDR； | 41 欄的單欄 IC 檢定相互高度相關，BH 在 PRDS 下仍有效（正相關的情況大致符合），BY 保守但保證。 | 2.7 |
| [Robust inference with knockoffs](https://arxiv.org/abs/1801.03896)，Rina Foygel Barber, Emmanuel J. Candès, Richard J. Samworth | 2018 | FDR 的膨脹和條件分布估計誤差成正比，所以分布估得準時方法仍可用； | 對我們不利的一面：41 欄名次是重尾、有離散化（名次）和非高斯相依，條件分布很難估準，FDR 保證會打折，且我們沒有辦法事前量化膨脹多少。 | 2.3 |
| [Robust Knockoffs for Controlling False Discoveries With an Application to Bond Recovery Rates](https://arxiv.org/abs/2206.06026)，Konstantin Görgen, Abdolreza Nazemi, Melanie Schienle | 2022 | 在公司債回收率的應用中找出標準因子以外的新相關因子群； | 這是少數有『樣本外：稀疏模型 ≈ 全變數模型』的金融證據，和我們 16（53/46/41 欄分不出）的結果同方向：挑欄不會明顯提升，只是讓模型更精簡。 | 2.3 |
| [High-Dimensional Knockoffs Inference for Time Series Data](https://arxiv.org/abs/2112.09851)，Chien-Ming Chi, Yingying Fan, Ching-Kang Ing, Jinchi Lv | 2021 | 給出時間序列下的漸近 FDR 控制條件，模擬與一個美國通膨預測的研究顯示有限樣本表現； | 它處理的是單一時間序列的特徵選擇，我們是『100 檔 × 1,666 天』的面板，目標是橫斷面名次，每天內的列彼此相依，條件不完全對得上，直接套用不合適。 | 2.0 |
| [Stability Selection](https://arxiv.org/abs/0809.2932)，Nicolai Meinshausen, Peter Bühlmann | 2008 | 可對一些錯誤率提供有限樣本控制，並證明隨機化 Lasso 在標準 Lasso 條件不成立時仍有選擇一致性； | 08 已經試過穩定性選擇，沒有比不挑好，所以這篇不是新方向。 | 2.0 |
| [Variable selection with error control: another look at stability selection](https://arxiv.org/abs/1105.5578)，Rajen D. Shah, Richard J. Samworth | 2011 | 得到比 Meinshausen-Bühlmann 更少假設的有限樣本誤差界； | 它把誤差界放寬到不需要可交換，對我們的相關特徵比較適用，但界是『相對於原選擇器的入選機率』，不是對真正有訊號的欄的保證，在訊噪比極低（偵測下限每天 0.0001～0.0002）的日頻橫斷面上，入選機率本身就很吵，界不會有實質的保證。 | 2.0 |

### F4 降維（PCA、IPCA、RMT、PLS）（7 篇）

| 論文 | 年 | 發現 | 對我們 | 分 |
|---|---|---|---|---|
| [Scaled PCA: A New Approach to Dimension Reduction](https://econpapers.repec.org/RePEc:inm:ormnsc:v:68:y:2022:i:3:p:1678-1695)，Dashan Huang, Fuwei Jiang, Kunpeng Li, Guoshi Tong, Guofu Zh | 2022 | 理論、模擬與總體預測應用都顯示 sPCA 勝過標準 PCA； | sPCA 的用意是『PCA 會被和目標無關但變異大的方向佔據』，在我們 41 欄名次特徵上其實正好成立（持續性組以外大多是雜訊）。 | 3.3 |
| [Characteristics Are Covariances: A Unified Model of Risk and Return (IPCA)](https://www.nber.org/papers/w24540)，Bryan Kelly, Seth Pruitt, Yinan Su | 2019 | 四個 IPCA 因子對股票層級平均報酬的解釋比現有因子模型更準，anomaly intercept 小且不顯著； | 主張「大量特徵其實壓在少數維度」，和我們 41 欄冗餘的直覺一致。 | 3.3 |
| [Estimating Latent Asset-Pricing Factors (Risk-Premium PCA)](https://econpapers.repec.org/RePEc:nbr:nberwo:24618)，Martin Lettau, Markus Pelger | 2020 | 五個樣本外 RP-PCA 因子的最大 Sharpe 比五個 PCA 因子高一倍以上，定價誤差更小（摘要）。 | 這篇說明標準 PCA 的前幾個成分只看變異，會漏掉弱但有用的方向，反而支持『PCA 去噪可能把訊號當噪音刪掉』的風險； | 2.7 |
| [The Three-Pass Regression Filter: A New Approach to Forecasting Using Many Predictors](https://econpapers.repec.org/RePEc:eee:econom:v:186:y:2015:i:2:p:294-316)，Bryan Kelly, Seth Pruitt | 2015 | 在 N、T 都大時對最佳預測一致； | 3PRF 的核心假設是少數共同因子同時驅動預測變數與目標，在總體預測成立； | 2.7 |
| [Prediction by Supervised Principal Components](https://tibshirani.su.domains/ftp/spca.pdf)，Eric Bair, Trevor Hastie, Debashis Paul, Robert Tibshirani | 2006 | 在預測變數遠多於樣本的情形比傳統方法穩，且在稀疏假設下，supervised PC 可得一致的係數估計而一般 PCR 不能（頁面為摘要列表，我沒看到全文數字）。 | 我們是 n >> p（16.6 萬列、41 欄），它要解決的問題（p>>n）不存在。 | 2.3 |
| [High-Dimensional Learning in Finance](https://arxiv.org/abs/2506.03780)，Hasan Fallahgoul | 2025 | 在 12,000 個特徵、12 個月觀測、R² 2–3% 的校準下，要脫離多項式下界需要超過 25–30 年資料，超過一般滾動窗； | 對我們有利：用『樣本量對訊號強度』的下界論證，解釋為何多特徵、多模型的增益在我們偵測下限下幾乎不可能被看到； | 2.0 |
| [Autoencoder Asset Pricing Models](https://ideas.repec.org/a/eee/econom/v222y2021i1p429-450.html)，Shihao Gu, Bryan Kelly, Dacheng Xiu | 2021 | 樣本外定價誤差遠小於其他主流因子模型且多不顯著（摘要，我只看到摘要與書目頁，沒有看到表格數字）。 | 對我們不太合適：它的優勢在於大截面、月頻、定價（解釋風險溢酬），我們是 100 檔日頻 25/25 排名。 | 2.0 |

### F5 mRMR、HSIC、walk-forward 下的篩選（6 篇）

| 論文 | 年 | 發現 | 對我們 | 分 |
|---|---|---|---|---|
| [Design choices, machine learning, and the cross-section of stock returns](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5031755)，Minghui Chen, Matthias X. Hanauer, Tobias Kalsbach | 2024 | 設計選擇造成的非標準誤比標準誤大 59%； | 對我們有利的證據：特徵選擇不是主要槓桿，我們的 08 和 16 分不出和這個一致。 | 2.7 |
| [Selection bias in gene extraction on the basis of microarray gene-expression data](https://pmc.ncbi.nlm.nih.gov/articles/PMC124442)，Christophe Ambroise, Geoffrey J. McLachlan | 2002 | 校正選擇偏誤後，原先宣稱只用少數基因就能零錯誤的結果不成立，錯誤率分別為結腸癌約 15%、白血病約 5%。 | 這是方法學的底線：特徵選擇必須放在每個驗證折內（我們就是按日期切再選）。 | 2.7 |
| [Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest Overfitting on Out-of-Sample Performance](https://scholarworks.wmich.edu/math_pubs/40/)，David H. Bailey, Jonathan M. Borwein, Marcos López de Prado, | 2014 | 測試少量設定就能得到漂亮的回測； | 對我們非常相關：2024～2026 回測、2022～2023、另外 50 檔都被 15～35 用過很多次，這篇說明累積的選擇次數本身就是偏誤來源； | 2.7 |
| [Conditional Likelihood Maximisation: A Unifying Framework for Information Theoretic Feature Selection](https://jmlr.org/papers/v13/brown12a.html)，Gavin Brown, Adam Pocock, Ming-Jie Zhao, Mikel Luján | 2012 | 在小樣本時，JMI 在準確、穩定、彈性上取得最好的權衡； | mRMR（Peng, Long, Ding 2005，IEEE TPAMI，DOI 10.1109/TPAMI.2005.159，我只確認 DOI 存在，沒打開全文）屬於這家族。 | 2.0 |
| [Financial factors selection with knockoffs: fund replication, explanatory and prediction networks](https://arxiv.org/abs/2103.05921)，Damien Challet, Christian Bongiorno, Guillaume Pelletier | 2021 | 實際 FDR 接近設定的 q，但在 q 很大或 q<0.15 時偏離（來自搜尋結果摘要，我只看了 arXiv 摘要，沒看全文數字）。 | 提供金融相關資料用 knockoffs 的範例與注意事項（高共線、非高斯）。 | 1.7 |
| [Supervised Feature Selection via Dependence Estimation（JMLR 2012 版：Feature Selection via Dependence Maximization）](https://arxiv.org/abs/0704.2668)，Le Song, Alex Smola, Arthur Gretton, Karsten Borgwardt, Just | 2007 | 在人工與真實資料集上，HSIC 型選擇可抓到非線性依賴而線性相關抓不到； | 在日頻、訊噪比極低的資料上，核依賴度量需要估計的樣本量大，單欄 HSIC 的雜訊很可能高於線性 IC。 | 1.7 |

## 模型軌（60 篇）

### M1 learning to rank（14 篇）

| 論文 | 年 | 發現 | 對我們 | 分 |
|---|---|---|---|---|
| [Qlib 官方 benchmark（CSI300，Alpha158）：LightGBM、Transformer、ALSTM、TabNet、DoubleEnsemble](https://github.com/microsoft/qlib/tree/main/examples/benchmarks)，Microsoft Qlib 團隊（含 Qlib 論文作者） | 2024 | Alpha158、CSI300：LightGBM IC 0.0448／Rank IC 0.0469／年化 9.0%； | 是對深度模型最不利的證據：同樣是日頻橫截面、技術特徵，GBDT 勝過 Transformer、TabNet、LSTM。 | 3.7 |
| [LambdaRankIC: Directly Optimizing Rank IC for Financial Prediction](https://arxiv.org/abs/2605.00501)，Yan Lin, Yihong Su, Yi Yang | 2026 | 樣本外 Rank IC：OLS 0.0471、XGB(MSE) 0.0418、MLP 0.0428、pairwise 0.0828、NDCG 0.0863、LambdaRankIC 0.1148； | 可能有用的點：日頻、低訊噪比、厚尾正是它的主場，而且與我們 35 的 lambdarank 不同——lambdarank 用 NDCG 的 gain，這篇直接對準 Spearman，和我們的評分（分數對名次線性）更接近。 | 3.0 |
| [The LambdaLoss Framework for Ranking Metric Optimization](https://research.google/pubs/the-lambdaloss-framework-for-ranking-metric-optimization/)，Xuanhui Wang, Cheng Li, Nadav Golbandi, Michael Bendersky, M | 2018 | 在三個公開 LTR 資料集上勝過當時的 LTR 方法（我只讀過摘要，沒有看到數字）。 | 提供理論基礎：lambdarank 並不是對 Spearman 做最佳化，而是對 NDCG 這種偏重頭部的指標。 | 3.0 |
| [Fast Differentiable Sorting and Ranking](https://arxiv.org/abs/2002.08871)，Mathieu Blondel, Olivier Teboul, Quentin Berthet, Josip Djol | 2020 | 比既有可微替代方案快約一個數量級； | 提供「直接最大化每天的 Spearman」的神經網路做法（把每一天當一個 batch），與我們 11 的「直接優化分數」不同：11 優化的是分數，這個優化排名相關。 | 3.0 |
| [Getting the Target Right in Return Prediction](https://quantpedia.com/getting-the-target-right-in-return-prediction/)，Nusret Cakici, Adam Zaremba | 2026 | 依 Quantpedia 摘要：由原始報酬換成標準化或名次目標，預測準確度約三倍、投組報酬約兩倍； | 和我們 15（換成同一天誰比較強的目標是最大的一步）一致，是外部佐證：目標比模型重要。 | 3.0 |
| [MASTER: Market-Guided Stock Transformer for Stock Price Forecasting](https://arxiv.org/abs/2312.15235)，Tong Li, Zhaoyang Liu, Yanyan Shen, Xue Wang, Haokun Chen, S | 2023 | 摘要說優於先前方法； | 正好對應「市場狀態與個股特徵交互」還沒做的方向：用當天市場特徵產生對每個個股特徵的門控權重，不押方向。 | 3.0 |
| [On Evaluating Loss Functions for Stock Ranking: An Empirical Analysis With Transformer Model](https://arxiv.org/abs/2510.14156)，Jan Kwiatkowski, Jarosław A. Chudziak | 2025 | 測試集 top-5 組合 Sharpe：MSE 0.6637、RankNet 0.6771、ListNet 0.7407、Margin 0.7529； | 這是對我們最直接的日頻證據，也是最好的對照：換成排序損失後 IC 幾乎不變（0.0754 對 0.0767），Sharpe 的差距來自 top-5 的少數幾檔，單次測試期、沒有種子重複與檢定，很可能只是雜訊。 | 2.7 |
| [Are Neural Rankers still Outperformed by Gradient Boosted Decision Trees?](https://research.google/pubs/are-neural-rankers-still-outperformed-by-gradient-boosted-decision-trees/)，Zhen Qin, Le Yan, Honglei Zhuang, Yi Tay, Rama Kumar Pasumar | 2021 | 許多近期神經 LTR 模型落後最好的樹模型（LambdaMART 類）一大截； | 對我們不利於神經排序：在表格特徵上，GBDT 的 LambdaMART 是強基準，神經排序要費很大工夫才追平。 | 2.7 |
| [Building Cross-Sectional Systematic Strategies By Learning to Rank](https://arxiv.org/abs/2012.07149)，Daniel Poh, Bryan Lim, Stefan Zohren, Stephen Roberts | 2020 | Sharpe（縮放到 15% 波動）：LambdaMART 2.156、ListNet 1.970、ListMLE 1.611、RankNet 1.502，MLP 迴歸再排序 0.265，JT 0.551，Baz 0.696； | 對我們不利的地方：它的對照組是一個很弱的 MLP（Sharpe 0.265），不是已經換成當天名次目標的 ridge 或 kernel ridge； | 2.3 |
| [Constructing long-short stock portfolio with a new listwise learn-to-rank algorithm](https://arxiv.org/abs/2104.12484)，Xin Zhang, Lan Wu, Zhixue Chen | 2021 | 樣本外年化報酬約 38%、Sharpe 約 2（摘要）。 | 方向吻合我們：多空對稱、頭尾都要。 | 2.3 |
| [Why do tree-based models still outperform deep learning on tabular data?](https://arxiv.org/abs/2207.08815)，Léo Grinsztajn, Edouard Oyallon, Gaël Varoquaux | 2022 | 在約 1 萬筆的中等表格資料上，樹模型仍是最好； | 對深度排序模型最不利：我們是 16.6 萬列、高雜訊、很多弱特徵（41 欄名次化），正是神經網路吃虧的情形，而樹與 ridge／核方法都還在。 | 2.3 |
| [TSPRank: Bridging Pairwise and Listwise Methods with a Bilinear Travelling Salesman Model](https://arxiv.org/abs/2411.12064)，Weixian Waylon Li, Yftah Ziser, Yifei Xie, Shay B. Cohen, Ti | 2025 | 摘要稱在股票排序、資訊檢索、歷史事件排序三個任務上，都勝過純 pairwise 與純 listwise 方法； | 對我們不太適合：它的資料是 1,000 檔以上、有關係圖的設定，我們只有 100 檔，成對關係的組合最佳化在 100 檔上沒有明顯意義； | 2.0 |
| [Enhancing Cross-Sectional Currency Strategies by Context-Aware Learning to Rank with Self-Attention](https://arxiv.org/abs/2105.10019)，Daniel Poh, Bryan Lim, Stefan Zohren, Stephen Roberts | 2021 | 31 種貨幣，Sharpe 約增加 30%（v1 摘要寫約 20%）； | 和「依市場狀態調整個股排名」這個還開著的方向有關：它用 top/bottom 資產當情境，不押大盤方向。 | 2.0 |
| [Graph Neural Networks for Long-Term Stock Ranking Prediction in the Taiwan Stock Market: An Approach Based on Cross-Sectional Data and Optimized Learning to Rank（圖神經網路於台灣股市長期股票排名預測之應用）](https://thesis.lib.nccu.edu.tw/detail/370cb95118a8d4792d0cf9ec823483db/)，鄭玉海（Cheng, Yu-Hai），指導教授 黃泓智，政治大學風險管理與保險學系碩士論文 | 2025 | 滾動視窗回測（台股 2020–2024）勝過大盤與基準； | 同一個市場，有參考價值，但證據弱：沒有數字、沒有顯著性檢定、非日頻、全文未公開，我只讀過摘要。 | 1.7 |

### M2 深度時序與橫截面模型（10 篇）

| 論文 | 年 | 發現 | 對我們 | 分 |
|---|---|---|---|---|
| [Qlib benchmark README (Alpha158 on CSI300), 技術報告／官方基準表](https://github.com/microsoft/qlib/blob/main/examples/benchmarks/README.md)，Microsoft Qlib 團隊（Yang, Liu, Zhou, Bian, Liu 等，見 Qlib 論文 arX | 2025 | Alpha158、CSI300（多種子平均，頁面標 20 個種子）：IC／RankIC／年化超額 — DoubleEnsemble 0.0521／0.0502／0.1158； | 這是對我們最有利的外部佐證：在同一組表格特徵上，樹模型與線性模型打贏 LSTM、TCN、Transformer、TabNet，和我們實驗 02～11 的結論一致。 | 3.7 |
| [Deep neural networks, gradient-boosted trees, random forests: Statistical arbitrage on the S&P 500](https://econpapers.repec.org/RePEc:eee:ejores:v:259:y:2017:i:2:p:689-702)，Christopher Krauss, Xuan Anh Do, Nicolas Huck | 2017 | 1992～2015，k=10，三個模型簡單平均的集成扣費前每天報酬超過 0.45%，扣費後 0.25%； | 設定和我們最像（每天做多前 k、放空後 k； | 3.3 |
| [Learning Multiple Stock Trading Patterns with Temporal Routing Adaptor and Optimal Transport (TRA)](https://arxiv.org/abs/2106.12950)，Hengxu Lin, Dong Zhou, Weiqing Liu, Jiang Bian | 2021 | IC 由 0.053 升到 0.059（Attention LSTM）、0.051 升到 0.056（Transformer）。 | TRA 是『依狀態路由到不同模型』的另一種做法，和 regime gating 同族，但在 Qlib 自己的基準上沒有明顯勝過樹模型，路由本身又需要時間窗內的損失歷史。 | 2.7 |
| [Re(Visiting) Time Series Foundation Models in Finance](https://arxiv.org/abs/2511.18578)，Eghbal Rahimikia, Hao Ni, Weiguan Wang | 2025 | 美股 2001～2023 擴展窗、每年重估：線性基準平均 R² −0.47%，CatBoost −0.10%； | 對我們不利：和我們實驗 05（Chronos 零樣本與微調沒用）相符，而且連『從頭預訓練』也只是追平 CatBoost。 | 2.3 |
| [Tabular Data: Deep Learning is Not All You Need](https://arxiv.org/abs/2106.03253)，Ravid Shwartz-Ziv, Amitai Armon | 2021 | XGBoost 在所有資料集上勝過深度模型（包含它們自己論文的資料集），調參成本低很多； | 對集成設計有用：異質成員（深度加樹）平均的增益，出現在成員差異大時。 | 2.3 |
| [HIST: A Graph-based Framework for Stock Trend Forecasting via Mining Concept-Oriented Shared Information](https://arxiv.org/abs/2110.13716)，Wentao Xu, Weiqing Liu, Lewen Wang, Yingce Xia, Jiang Bian,  | 2021 | CSI300 測試 2017～2020：IC 0.131、RankIC 0.126； | 我們的實驗 31（產業欄）沒過，而 HIST 的核心是產業或概念共享資訊，加上我們只有 100 檔，概念群太少、每群樣本薄。 | 2.0 |
| [Are Transformers Effective for Time Series Forecasting? (DLinear)](https://arxiv.org/abs/2205.13504)，Ailing Zeng, Muxi Chen, Lei Zhang, Qiang Xu | 2022 | 九個真實資料集上，簡單線性模型勝過當時的 Transformer 預測模型，常常差很多； | 給我們的訊息是：序列網路在低訊噪比資料上常輸給線性模型。 | 2.0 |
| [QuantBench: Benchmarking AI Methods for Quantitative Investment](https://arxiv.org/abs/2504.18600)，Saizhuo Wang, Hao Kong, Jiadong Guo, Fengrui Hua, Yiyan Qi,  | 2025 | 摘要只說實證指向三個方向：持續學習（分布位移）、關係型金融資料建模、抵抗低訊噪比下的過擬合。 | 提醒我們評分用的是 (2·pred−1)·r 的盤中報酬，IC 或 RankIC 只是代理。 | 1.7 |
| [A Compact Selective State-Space Model for Cross-Sectional Stock Return Ranking from Raw Intraday Bars (STRATA)](https://arxiv.org/abs/2608.28060)，Mingju Chen, Enze Zhang, Annan Li, Yui Lo, Xiaomin Yuan, Kai | 2026 | 約 1,000 檔中型 A 股，訓練 4 年、保留 1 年評估一次； | 對我們有警訊：論文自己承認可執行價格下訊號消失，我們的目標用開盤到收盤的報酬，和『第一個可執行價』相近，所以這類高報酬數字不能直接搬過來。 | 1.5 |
| [Pretrained Time-Series Foundation Models for Financial Return Forecasting](https://arxiv.org/abs/2606.27100)，Miquel Noguer i Alonso, Rodolfo Pereira Franklin | 2026 | 預訓練模型贏 10 個任務中的 8 個，但相對隨機漫步的增益『小且稀疏』； | 僅五檔、單檔預測，不是截面排名，和我們的設定相距遠，但它再次顯示 PatchTST、iTransformer 在日報酬上沒有穩定贏過基礎模型，基礎模型也沒有顯著 alpha。 | 1.3 |

### M3 集成（stacking、DoubleEnsemble）（12 篇）

| 論文 | 年 | 發現 | 對我們 | 分 |
|---|---|---|---|---|
| [DoubleEnsemble: A New Ensemble Method Based on Sample Reweighting and Feature Selection for Financial Data Analysis](https://arxiv.org/abs/2010.01265)，Chuheng Zhang, Yuanqi Li, Xi Chen, Yifei Jin, Pingzhong Tang | 2020 | A 股日頻（每天持 top 20、對沖）：DoubleEnsemble(MLP) 年化 51.37%、Sharpe 4.94，IC 0.115； | 可能有用但證據偏弱：回測期短（不到 3 年），報酬差距遠大於 IC 差距，表示靠選股組合的放大，不一定是排名品質。 | 3.3 |
| [Out-of-Sample Equity Premium Prediction: Combination Forecasts and Links to the Real Economy](https://ideas.repec.org/a/oup/rfinst/v23y2010i2p821-862.html)，David E. Rapach, Jack K. Strauss, Guofu Zhou | 2010 | 組合預測在樣本外對歷史平均有統計上和經濟上都顯著的持續性改善，原因是納入大量變數資訊的同時大幅降低預測波動。 | 是『簡單平均在金融上有效』的經典證據，支持現行三成員等權做法，但它預測的是大盤，我們的任務已排除大盤方向（13、23、29、Decider）。 | 3.0 |
| [Ensemble Selection from Libraries of Models](https://icml.cc/Conferences/2004/proceedings/abstracts/345.htm)，Rich Caruana, Alexandru Niculescu-Mizil, Geoff Crew, Alex Ks | 2004 | 7 個測試問題、10 種指標上都顯示集成選擇優於單模型和其他集成方式（摘要層級，我沒有核對全文表格）。 | 對我們風險高：貪婪選擇會在驗證集上過擬合，我們的偵測下限約 0.0001～0.0002/天，驗證集選擇出來的『贏』很容易只是雜訊。 | 2.7 |
| [Stacked Regressions](https://statistics.berkeley.edu/sites/default/files/tech-reports/367.pdf)，Leo Breiman | 1996 | 堆疊幾乎總是比交叉驗證選出的單一最佳預測器誤差更低； | 提供我們 stacking 的正確作法：要非負、要用乾淨的樣本外預測。 | 2.7 |
| [On the Forecast Combination Puzzle](https://arxiv.org/abs/1505.00475)，Wei Qian, Craig A. Rolling, Gang Cheng, Yuhong Yang | 2015 | 估計誤差是主因，簡單平均避開了這個成本； | 直接支持我們現況：三個成員已飽和（34），權重估計的雜訊會大於最佳權重帶來的好處，所以等權平均（現行做法）大概已經夠好。 | 2.3 |
| [Online Ensemble Learning for Sector Rotation: A Gradient-Free Framework](https://arxiv.org/abs/2304.09947)，Jiaju Miao, Pawel Polak | 2023 | 1987～2021 美股產業月頻：平均 R²_OOS（等權）最佳單模型 LASSO 0.95%、簡單平均 0.90%、線上集成 1.19%； | 對我們是反面訊號加弱正面：簡單平均在這份資料裡輸給最好的單模型，線上加權只在等權口徑明顯贏。 | 2.3 |
| [A Comprehensive Look at the Empirical Performance of Equity Premium Prediction](https://econpapers.repec.org/RePEc:oup:rfinst:v:21:y:2008:i:4:p:1455-1508)，Ivo Welch, Amit Goyal | 2008 | 近 30 年這些模型在樣本內和樣本外都失敗、也不穩定； | 對我們不利也有用：說明樣本內看起來有用的模型和組合，樣本外常常不穩定，所以我們『每一輪事先登記規則、Holm、2021 年當唯一乾淨樣本外』是對的； | 2.3 |
| [Diversity and degrees of freedom in regression ensembles](https://arxiv.org/abs/1803.00314)，Henry W. J. Reeve, Gavin Brown | 2018 | 資料有雜訊時，適當 λ 的 NCL 集成可勝過 λ=0（沒有多樣性）的集成。 | 提供理論：我們的資料訊雜比極低，所以集成該偏『低自由度、強正則』，而不是追求多樣性。 | 2.0 |
| [How Useful is Bagging in Forecasting Economic Time Series? A Case Study of U.S. CPI Inflation](https://econpapers.repec.org/RePEc:cpr:ceprdp:5304)，Atsushi Inoue, Lutz Kilian | 2005 | 在美國 CPI 通膨預測，bagging 與最佳替代方法差不多或更好； | 提醒 bagging 的好處取決於可預測度：我搜尋到的二手描述說，可預測度很低（像股票報酬）時標準 bagging 幾乎沒用，需要自適應版本。 | 2.0 |
| [Snapshot Ensembles: Train 1, get M for free](https://arxiv.org/abs/1704.00109)，Gao Huang, Yixuan Li, Geoff Pleiss, Zhuang Liu, John E. Hopc | 2017 | 在 CIFAR-10/100 上 DenseNet 快照集成錯誤率 3.4% 和 17.4%，低於單一模型，而且不增加訓練成本。 | 對我們價值有限：Fort et al. 顯示快照的多樣性比獨立初始化低； | 2.0 |
| [Error Reduction from Stacked Regressions](https://arxiv.org/abs/2309.09880)，Xin Chen, Jason M. Klusowski, Yan Shuo Tan | 2023 | 在子空間維度差至少 3 的條件下，堆疊估計量的母體風險嚴格小於 AIC/BIC 選出的最佳單模型，且訊雜比越低增益越大。 | 對我們有利的理論：低訊雜比時堆疊（有收縮效果）比『選最佳』好，說明用集成而不是挑一個模型是對的。 | 1.7 |
| [Deep Ensembles: A Loss Landscape Perspective](https://arxiv.org/abs/1912.02757)，Stanislav Fort, Huiyi Hu, Balaji Lakshminarayanan | 2019 | 隨機初始化的集成比子空間取樣（含 snapshot 類方法）更能去相關預測，因此集成效果更好。 | 意涵：若要用神經網路成員，真正的多樣性來自『獨立初始化』，不是 snapshot 或同一軌跡取點。 | 1.7 |

### M4 概念漂移與適應（10 篇）

| 論文 | 年 | 發現 | 對我們 | 分 |
|---|---|---|---|---|
| [Model Instability and Choice of Observation Window（Pesaran & Timmermann；另有 2007 JoE 'Selection of estimation window in the presence of breaks'）](https://ideas.repec.org/p/cdl/ucsdec/qt8zx626k6.html)，M. Hashem Pesaran, Allan Timmermann | 1999 | 長窗降低變異數但斷點後有偏誤，短窗相反； | 可上線、很便宜，但增益不能期望大。 | 2.7 |
| [The Nonstationarity-Complexity Tradeoff in Return Prediction](https://arxiv.org/abs/2512.23596)，Agostino Capponi, Chengpiao Huang, J. Antonio Sidaoui, Kaizh | 2025 | 17 個產業組合（美股，三十年以上）：樣本外 R² 比固定窗與 regime-switching 基準高約 14%（搜尋摘要寫 14～23%），衰退期增益最大。 | 對我們的啟示是『簡單模型在非平穩時比複雜模型更耐用，窗長要和模型複雜度一起選』，與 Chen 等人的『擴張窗較好』相反，形成真正的未解爭論。 | 2.7 |
| [Factor Timing](https://www.nber.org/papers/w26708)，Valentin Haddad, Serhiy Kozak, Shrihari Santosh | 2020 | 論文稱市場中性股票因子是強而穩健可預測的，擇時顯著改善組合； | 這是『依市場狀態調整個股排名』最接近的金融文獻：因子報酬可預測，等於『特徵的權重該隨時間變』。 | 2.7 |
| [Out-of-Sample Performance of Factor Return Predictors](https://du-dnguyen.github.io/papers/OOSPerformanceOfFactorReturnPredictors2024_Nguyen.pdf)，Du Nguyen | 2024 | 九個預測變數下，只有 5%～28% 的因子在標準顯著水準下可預測； | 對我們不利的證據：因子擇時在樣本外很弱，意味著『依狀態調整排名』的增益本來就小，和 Haddad 等人形成對立。 | 2.7 |
| [The forecast combination puzzle: A simple theoretical explanation](https://econpapers.repec.org/RePEc:eee:intfor:v:32:y:2016:i:3:p:754-762)，Gerda Claeskens, Jan R. Magnus, Andrey L. Vasnev, Wendun Wan | 2016 | 在權重必須估計的現實中，『最優』組合不保證比等權好，甚至不保證比原本的預測好（結果來自摘要； | 對『自適應集成權重』直接不利：我們每天的排名有雜訊大的 IC，估計成員權重的誤差大於等權的偏誤，且 34 號顯示三成員飽和、任一成員拿掉只少 0.00003，權重空間裡沒有可抓的差異。 | 2.7 |
| [Era Splitting: Invariant Learning for Decision Trees](https://arxiv.org/abs/2309.14496)，Timothy DeLise | 2023 | 摘要稱在 Numerai 資料上勝過最新 GBDT（沒有數字，我只看了摘要頁）； | 這是少數直接針對『截面股票預測+時間分布變動』的樹模型設計，與我們的情境（每天是一個 era、相對報酬標籤）最像。 | 2.7 |
| [DoubleAdapt: A Meta-learning Approach to Incremental Learning for Stock Trend Forecasting](https://arxiv.org/abs/2306.09862)，Lifan Zhao, Shuming Kong, Yanyan Shen | 2023 | CSI300、GRU、Alpha360：IC 0.0687，滾動重訓（RR）0.0629，一般增量學習（IL）0.0633。 | 只能研究，不能上 oop（需要 PyTorch 雙層優化）。 | 2.7 |
| [Predictive regressions with time-varying coefficients](https://econpapers.repec.org/RePEc:eee:jfinec:v:106:y:2012:i:1:p:157-181)，Thomas Dangl, Michael Halling | 2012 | 樣本外對 S&P 500 月報酬顯示統計與經濟上的可預測性； | 支持『係數應該隨時間變』的主張，但是大盤時序預測而非截面，且我們的『抓大盤』已結案（猜對率最好 52～54%）。 | 2.3 |
| [DDG-DA: Data Distribution Generation for Predictable Concept Drift Adaptation](https://arxiv.org/abs/2201.04038)，Wendi Li, Xiao Yang, Weiqing Liu, Yingce Xia, Jiang Bian | 2022 | 摘要稱在股票趨勢、電力負載、太陽輻射三個任務上對多種模型有顯著改善（我只看到摘要，沒有數字）。 | 只能研究（要元學習網路，不在 oop 的輪子）。 | 2.3 |
| [Time-varying neural network for stock return prediction (Online Early Stopping, OES)](https://arxiv.org/abs/2003.02515)，Steven Y. K. Wong, Jennifer Chan, Lamiae Azizi, Richard Y. D | 2020 | 美股月頻：平均 rank correlation 4.69%，約為 Gu-Kelly-Xiu 式擴張窗 DNN 的近兩倍； | 部分可借鑑、只能研究。 | 2.0 |

### M5 市場條件化的橫截面模型（8 篇）

| 論文 | 年 | 發現 | 對我們 | 分 |
|---|---|---|---|---|
| [Machine Learning vs. Economic Restrictions: Evidence from Stock Return Predictability](https://papers.ssrn.com/abstract=3450322)，Doron Avramov, Si Cheng, Lior Metzker | 2023 | 機器學習的獲利集中在難交易的股票； | 對我們不利：預測力集中在『高波動、難交易』的時段與股票，而我們的 100 檔是大型流動股、且比分是盤中報酬不扣成本，所以預期學習到的 alpha 本來就比較小，市場狀態條件化的增益多半來自高波動日，且可能不穩定。 | 3.7 |
| [Market States and Momentum](https://doi.org/10.1111/j.1540-6261.2004.00665.x)，Michael J. Cooper, Roberto C. Gutierrez Jr., Allaudeen Hamee | 2004 | 1929～1995：UP 狀態後動能策略月均報酬 0.93%，DOWN 狀態後為 -0.37%； | 支持『動能的符號隨市場狀態改變』，也是我們『持續性組』（30）很重要的原因，而 24 發現 X_price 暗中押大盤跌，有可能和這個機制有關。 | 3.3 |
| [Deep Learning in Asset Pricing](https://arxiv.org/abs/1904.00745)，Luyang Chen, Markus Pelger, Jason Zhu | 2019 | 樣本外在 Sharpe、解釋變異和定價誤差都勝過所有基準； | 『把市場狀態壓成幾個低維狀態再條件化個股權重』的概念和我們剩下的方向一致，但它是月頻、大樣本、長歷史，且總體狀態變動慢； | 2.7 |
| [Temporal Relational Ranking for Stock Prediction (Relational Stock Ranking, RSR)](https://arxiv.org/abs/1809.09441)，Fuli Feng, Xiangnan He, Xiang Wang, Cheng Luo, Yiqun Liu, Ta | 2019 | 在 NYSE、NASDAQ 的回測，平均 return ratio 分別約 98%、71%（來自作者回報、未經獨立重現）。 | 排名損失我們已用 LGBMRanker 測過（35：和迴歸 Spearman 0.919、只多 0.00003）； | 2.7 |
| [Qlib 官方基準表（Alpha158 / Alpha360：LightGBM、GATs、Transformer、TRA、HIST 等）](https://github.com/microsoft/qlib/tree/main/examples/benchmarks)，Microsoft Qlib 團隊 | 2024 | Alpha158 上 LightGBM 與多數神經網路相當或更好（一份快照：LightGBM IC 0.0475、Transformer 0.0274、TRA 0.0474）； | 對我們不利、也最符合我們的經驗：在特徵已經設計好的情況下，圖與注意力模型沒有穩定勝過 GBDT。 | 2.7 |
| [Forest Through the Trees: Building Cross-Sections of Stock Returns](https://papers.ssrn.com/abstract=3493458)，Svetlana Bryzgalova, Markus Pelger, Jason Zhu | 2025 | 樣本外 Sharpe 和定價誤差比領先的簡化式模型最高好到約 3 倍（作者在 SSRN 摘要的說法； | 方法重點是『依特徵條件分群排序』，和『特徵與市場狀態交互』的概念接近，但是以月頻投組為單位； | 2.3 |
| [Volatility Forecasting and Return Prediction under Market Regimes: Evidence from High-Frequency Chinese Equity Data](https://arxiv.org/abs/2606.09478)，Xinyue Fang, Robert Ślepaczuk | 2026 | CSI300 指數：樣本外全期相關 0.0449、命中率 53.49%； | 負面或混合：它預測的是指數方向（我們已結案、猜對率只有 52～54%），並顯示狀態條件化的預測力不均且不穩； | 2.0 |
| [Are Characteristics Covariances? A Comment on Instrumented Principal Component Analysis](https://ideas.repec.org/p/ces/ceswps/_8377.html)，Christian Fieberg, Lars Hornuf, Gerrit Liedtke, Thorsten Pod | 2020 | 結論是 IPCA 無法回答這個問題：因子估計太多時會把 alpha 吃掉（alpha-eating），太少時變成特徵解釋； | 對我們不利的證據之一：『用市場因子條件化個股暴露』的模型因子數是不可辨識的自由度，結果容易被因子數 K 的選擇左右。 | 1.7 |

### M6 低訊噪比下的泛化（6 篇）

| 論文 | 年 | 發現 | 對我們 | 分 |
|---|---|---|---|---|
| [TabArena: A Living Benchmark for Machine Learning on Tabular Data](https://arxiv.org/abs/2506.16791)，Nick Erickson, Lennart Purucker, Andrej Tschalzev, David Hol | 2025 | GBDT 在實務資料上仍強； | 『跨模型集成最好』和我們集成方向一致，但我們 34 號已顯示三成員飽和； | 2.7 |
| [Accurate predictions on small data with a tabular foundation model (TabPFN)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11711098/)，Noah Hollmann, Samuel Müller, Lennart Purucker, Arjun Krishn | 2025 | 在 10,000 筆以內的資料上大幅勝過先前方法； | 我們每天訓練列數約 500 天 x 100 檔 = 5 萬，超過 1 萬樣本上限，需要子取樣； | 2.7 |
| [Evaluating data augmentation for financial time series classification](https://arxiv.org/abs/2010.15111)，Elizabeth Fons, Paula Dawson, Xiao-jun Zeng, John Keane, Ale | 2020 | 小資料集（約 3 萬樣本）風險調整報酬最多提升 400%，大資料集（約 30 萬樣本）最多 40%； | 我們約 16.6 萬列，介於兩者之間，預期增益偏小； | 2.7 |
| [Trade When Opportunity Comes: Price Movement Forecasting via Locality-Aware Attention and Iterative Refinement Labeling (LARA)](https://arxiv.org/abs/2107.11972)，Liang Zeng, Lei Wang, Hui Niu, Ruchen Zhang, Ling Wang, Jian | 2021 | 在股票、加密貨幣、ETF 三個市場（Qlib 平台）上顯著勝過多個 ML 基準（摘要頁沒給數字）。 | 『用訓練損失大小識別並降權噪音標籤』是標籤雜訊穩健性的具體做法。 | 2.3 |
| [The Label Horizon Paradox: Rethinking Supervision Targets in Financial Forecasting](https://arxiv.org/abs/2602.03395)，Chen-Hui Song, Shuoling Liu, Liyuan Chen | 2026 | 報告在大規模金融資料集上穩定勝過常規基準（摘要頁沒有市場、期間、數字）。 | 和我們 35 號『5 天平均標籤沒過』直接相關，是對我們不利或至少已試過的方向：我們是盤中報酬，次日雜訊占比很高，其他中間期間（如 close-to-close、隔日）標籤沒試過全部。 | 2.3 |
| [Virtue or Mirage? Complexity in Exchange Rate Prediction](https://www.federalreserve.gov/econres/feds/virtue-or-mirage-complexity-in-exchange-rate-prediction.htm)，Rehim Kilic | 2025 | Ridge-RFF 在短窗勝過 OLS（MSPE 最多少 97%），但對隨機漫步只在少數幣別贏； | 對不利：『複雜度的美德』在低 SNR 的別的資產上沒有複製。 | 2.0 |

## 沒通過查證的 4 篇

- Understanding variable importances in forests of randomized trees：標題不符 宣稱不成立 網址錯。
- Asset Pricing with Omitted Factors：標題不符 NBER w23527 的標題是 'Inference on Risk Premia in the Presence of Omitted Factors'（2017 年 6 月工作論文），不是 'Asset Pricing with Omitted Factors'；
- FactorVAE: A Probabilistic Dynamic Factor Model Based on Variational Autoencoder for Predicting Cross-Sectional Stock Returns：不存在 標題不符 未能查證。
- StockMixer: A Simple Yet Strong MLP-Based Architecture for Stock Price Forecasting：不存在 標題不符 未能查證。

FactorVAE（AAAI 2022）和 StockMixer（AAAI 2024）是查證時被網站擋住、搜尋額度用完，沒查到，不代表論文不存在。
## 收斂（兩個 Opus，2026-11-15 凌晨，Claude 和兩個收斂者各討論兩輪；之後三個獨立審查者挑錯，已全部改進來）

兩軌的結論一樣：同一組 41 欄上，挑欄、去冗餘、降維、加模型、換排序損失、改集成權重，增益都在偵測下限以下。這一輪只留一個會改分數的比較（市場狀態條件化，而且要先過閘門），其他都是回答 Ian 問題或替死路結案的診斷。

審查（workflow `wf_2e07784c-323`，統計、資料、事實三個角度）找到 1 個 blocker（38 的 2021 規則前後矛盾）和 7 個 major（41 的等價檢定沒定義統計量、「每組都有替身」把分不出寫成結論、38 B 段的偏差項在評分日不是零平均、38 閘門的「超額上限」沒定義、mde_B 用 Top50 的標準差會低估、2021 截短窗會拿掉持續性欄、ridge 最小方向的數字錯一個數量級），下面都已改正。

### 對 Ian 第一個問題（特徵太多、有沒有統計檢定能快速篩）的回答

- 有。對我們最合適的是：每天算一次 rank-IC 當一個觀測（處理同一天股票之間的相關），t 用 Newey–West 或 20 天區塊 bootstrap，再用 Romano–Wolf max-t step-down（同一批重抽的日子，處理時序相依和欄之間的相關）。第二合適的是整組拿掉重訓（LOCO），唯一直接量分數的方法，但每組的偵測下限約 0.00014，只有持續性組量得出來。
- 其他方法：BH 在相關常態統計量的雙邊檢定沒有保證；BY 一定成立但門檻嚴約 4.2 倍；Harvey–Liu–Zhu 的 t > 3 在 41 欄約等於 Bonferroni；stability selection 08 做過。knockoffs 不適合：去重後最小特徵值約 1e-4～0.007，近似重複的幾對檢定力接近 0；名次是離散均勻分布、列之間不獨立，FDR 保證不成立；oop 沒有套件。
- 單欄檢定只量「單獨」的關係，看不出一欄「多出什麼」。同一群（Top50）的反例：25 的單欄 t，報價組到 −6.1、法人組最大 3.6；26 加進模型，報價組 2022～2023 −0.00009，法人組 +0.00018。法人組後來在另外 50 檔再驗證也過了（33）。所以單欄表只能報告，不能當加欄或刪欄的規則。
- 冗餘幾乎不傷分數，理由是重複的方向變異很小。37 的條件數 326.85 是奇異值比，特徵值比約 10⁵；500 天 × 100 檔的 X'X 約是 16,667 × 相關矩陣，去完全重複後最小的方向約 1.7，去到 35 欄約 64，和 ridge 的 α 40 同量級或更小，所以 ridge 本來就把這些方向縮掉大半。完全重複的欄 ridge 給一樣的係數；係數互相抵銷只發生在近似重複的對（`a_ret1`／`stock_ret_lag1`、`o_parkinson20`／`o_garman_klass20`、兩組 mean20）。kernel ridge 的等向 RBF 讓重複方向在距離裡算 2～3 次；LightGBM 只是那個方向每棵樹被抽到的機率從 0.68 變成 0.9～0.97。34 拿掉整個成員也只差 0.00003。
- 預期：去重 |Δ| ≤ 0.00004；每群留一個代表欄小幅變差（ridge 一直用到 parkinson 和 GK 的差，但訓練窗重疊，等於只看了 2～3 次，證據不強）。

### 對 Ian 第二個問題（更好的 ensemble、ranker、時序模型、泛化和抓大盤）的回答

- 文獻在「日頻、橫截面、做好的表格特徵」上最穩的做法，就是 GBDT 和線性模型各自排名再平均。Qlib Alpha158（CSI300，20 個種子）IC：DoubleEnsemble 0.0521、XGBoost 0.0498、CatBoost 0.0481、LightGBM 0.0448、Linear 0.0397；LSTM、GRU、Transformer、TabNet、TCN 都比較低。Rank IC（比較接近 25/25 的排名）：TRA（全欄）0.0540 最高，XGBoost 0.0505、DoubleEnsemble 0.0502、Linear 0.0472、LightGBM 0.0469。深度模型在吃原始序列（Alpha360）時贏（HIST 0.0522 對 LightGBM 0.0400）；表格特徵上的例外是 TRA 的 Rank IC 比 LightGBM 高 0.007，TRA 正好是「依市場狀態路由」的模型，沒有檢定，CSI300 有 300 檔。
- MASTER、HIST、TRA 是 300～800 檔、每天學股票之間關係的序列模型；MASTER 自己的消融，拿掉市場門控 RankIC 只從 0.076 變 0.074。我們每天只有 100 檔、41 欄名次，03 的 LSTM、TCN 和 04 的 Chronos 已經輸了。
- 排序損失沒有理由贏：25/25 的分數對 r 是線性的，最好的排序是照 E[e|x]，正是 MSE 估的東西。主要證據是 35：LGBMRanker 和迴歸 LightGBM 每天相關 0.919，進集成只多 0.00003。文獻裡和我們最像的 arXiv 2510.14156（110 檔 S&P 500、日資料）8 種損失 IC 差在 0.0034 內，MSE 排第 7，沒有檢定，分不出。LambdaRankIC 的 0.04 → 0.11 比的是「用原始報酬當目標的 MSE」，這一步 15 換成標準化目標時已經拿到。
- 加模型的門檻（Krogh–Vedelsby 的 ambiguity 分解寫成相關的形式）：三個成員每天名次相關 0.86～0.96（平均 0.91），等權平均理論上只比單一成員好約 3%，和 34 對得上。第四個等權成員要多約 0.0001，單獨要和最強的成員一樣強，而且和三個成員的相關平均要 ≤ 約 0.45～0.5；弱 20% 時要 ≤ 約 0.26～0.30（看用哪一群算）。這個公式本身在另外 50 檔高估現有集成約 0.00005，是門檻的一半，只能當粗篩。量過相關的候選（三個成員、35 的 ranker）都 ≥ 0.86；用同一組欄做 NCL 只能拿準度換相關。
- 抓大盤：當天方向已經結案。文獻裡市場條件化的增益多半來自「隨狀態放大、縮小整個部位」（Cooper 等 2004、Daniel–Moskowitz 2016、Nagel 2012），我們固定 25/25，只能改各組訊號的相對權重，增益是二階的：兩個狀態的增量 IC 要差約 0.07 才值每天 0.0001。15、27、32 已經讓樹可以照市場狀態分裂，都沒有東西。TRA 的 Rank IC 是唯一有利的線索，所以 38 還是值得跑一次閘門。
- 能突破天花板的只剩新資訊或新樣本，見最後的「未來方向」。

### 這一輪的規則（事先登記）

- Holm 家族：兩軌合起來 m = 1 固定，就是 38 的 B 段；閘門沒過記 p = 1。單邊 α 0.05。
- 偵測下限換成 α 0.05（原本 α 0.0125 的值乘 0.807）：1,155 天的換成員類約 0.000088、加欄類 0.00011～0.00018；909 天（38 B 段）的換成員類約 0.00010、加欄類 0.00013～0.00020。
- 評分期的結束日一律 2026-10-08，不混進 Phase 2：A 段 2022-01-03～2026-10-08（1,155 天），B 段 2023-01-03～2026-10-08（909 天）。
- 診斷不進家族，但每個都寫好結果會怎麼改下一步。41 的任何正向結果只能登記成下一輪的 Holm 候選，證據只用上線後的日子，這一輪不上影子跑。
- 2021（244 天，從來沒評分過）：最多兩個事先登記的確認，38 B 段（過了 Holm 才做）和法人組 H-F1（Ian 同意才做）。規則和程式在打開 2021 標籤前都凍結，同一本一起解鎖。兩者都是單邊配對 t、主要統計量是兩群（Top50、另外 50 檔）每天差的平均，m = 實際要跑的個數（打開前就知道），Holm 單邊 0.05。38 B 段只看 Holm 調整後的 p；H-F1 另外要「兩群的點估計都 > 0」（額外的必要條件，只會讓通過更難）。其他點估計只報告，不當判斷。
- 2021 的訓練窗從 2020-01-02 起，照現有缺值規則（價量欄在訓練窗空白超過 10% 就拿掉）會拿掉 `c_amount_z60`、`o_gap_intraday_corr60`、`p_e_mean120`，1～3 月再加 `p_e_up60`。所以 2021 的兩個確認把價量欄的缺值上限改成 0.30（和 33 的法人欄一樣，空白照舊排名後給 0），並在 2022～2026 核對：除了 2022 前兩段，結果要和 33、35 一樣。開跑檢查是「每段實際用到的價量欄 = 41（H-F1 加法人欄 = 23），不符就停」。
- 照日期切、不用 t 當天的資料；兩群每天各自排 25/25。

### 實驗清單

| 編號 | 名稱 | 種類 | 用到的標籤 | Kaggle 時間 | 上線 |
|---|---|---|---|---|---|
| 38 | 市場狀態條件化的排名（A 段閘門，過了才做 B 段） | A 診斷、B 是唯一的 Holm 比較 | A：Top50 2022-01-03～2026-10-08；B：另外 50 檔 2023-01-03～2026-10-08 | 各約 5 分鐘，B 加平移 null 約 20 分鐘 | B 可以（凍結的 7 欄線性後處理） |
| 39 | 集成算術和候選庫上限 | 診斷 | 14、16、17、18、20、21、26、32、35 存的預測 | 5 分鐘內 | 不改 |
| 40 | 單欄檢定表和篩選閘門的必要條件檢查 | 診斷（只報告） | 2022～2026，兩群分開 | 約 10 分鐘 | 不改 |
| 41 | 去重等價、代表欄、拿掉單一組重訓 | 診斷（等價檢定） | 100 檔 2022-01-03～2026-10-08 | 60～70 分鐘，拆兩本 | Ian 可為維護改用 35 欄 |
| 42 | 2021 確認（38 B 段、H-F1） | 確認 | 2021 | 約 15 分鐘 | 看結果 |

### Ian 的決定（2026-11-15 02:15）

- 38、39、40、41 四本都跑。
- 法人組要不要用 2021 確認：等 38 跑完再決定。

### 實作進度

- 2026-11-15：workflow `wf_b0731847-c7b` 寫好 38、39、40、41a、41b 的原始檔（scratchpad 的 `kaggle/src/`），每本一個作者、一個獨立審查者、一輪修正；審查沒有 blocker。38 只做 A 段閘門和 mde_B 的 Top50 樣本外版本，B 段過了閘門才另寫一本。41b 自己重訓一次去重 35 欄當基準，不用等 41a。
- 40 的兩個交叉格（兩個閘門結論不一樣）計畫沒寫，推 smoke 前（看任何結果前）確認：用不會擋掉法人組的那個閘門；兩個都不擋時保留現有閘門。
- slug：`2026-1111-raw-feature-model-38-market-state-gate`、`-39-ensemble-math`、`-40-screening-tests`、`-41a-dedup`、`-41b-drop-group`。11-15 12:36 推 smoke（version 1），五本都跑完沒有錯誤（0.4～2.6 分鐘）；12:41 推 full（version 2），五本同時跑。38 B 段的登記在看任何結果前已寫死，所以 41 不用等 38。

### 結果（2026-11-15 13:58 五本 full 跑完）

- 38 閘門沒過，B 段和 2021 確認不跑；39 stacking、成員權重結案；40 只報告（單欄 t 和模型效果無關，殘差 IC 較接近；D 項改用乾淨版閘門）；41 去重 +0.00003 分不出、代表欄變差、拿掉任一組都在 ±0.0001 附近。數字在 `memory/projects/04-raw-feature-experiments.md` 的「38～41」。
- 38 的構造有缺陷：z_X 的迴歸係數只有 0.014，各組的狀態偏差 ±0.01～0.02 主導了排名，連隨機狀態都每天少約 0.00047～0.00049，U 不是上限。可信的只有「真的狀態沒有比隨機狀態好」（p 0.14～0.40）。

### Ian 的決定（2026-11-15 下午，看完 38～41 之後）

- 2021：等 43（時間衰減權重）跑完，再把所有過了檢定的候選一起確認，只打開一次；法人組在那之前維持先不動。
- 38 用乾淨構造再算一次（38c）：狀態係數疊在全期加權版本上（X_pool = rank(b̄·x)，X_state = rank(b̄_S·x)），和同樣的隨機狀態 placebo 比。看完結果才加的，只報告、不進檢定、不改這一輪的結論，只決定下一輪要不要再開這條線。只用 Top50 的標籤。
- 38c 的判讀（寫 notebook 前定好）：某個 S 同時滿足「循環平移和 block 兩種 placebo 的 p 都 < 0.05」和「Top50 擴張窗樣本外 X_state − X_pool > 0 且 t > 2」，才寫「下一輪值得再開」；否則寫「乾淨構造也看不到，市場狀態條件化結案」。slug `2026-1111-raw-feature-model-38c-state-clean`。結果（11-15 傍晚）：判讀是「乾淨構造也看不到，市場狀態條件化結案」，數字在 04-raw-feature-experiments.md 的 38～41。38～41b 補好結論格後 11-15 下午重推（version 3）。

### Ian 的新方向：時間衰減權重（2026-11-15 下午）

- Ian 上課的講義（sampling bias）：驗證集要模仿測試情境（例如拿最後幾筆，不要隨機抽），也可以在訓練時給時間較晚的資料較高的權重；課堂討論題是「股票比賽用隨機 K-fold 會不會犯一樣的錯」。我們的驗證本來就照日期往前走（CLAUDE.md 禁止隨機拆列），所以沒有這個錯；後半句「較晚的資料權重較高」就是 Ian 要的實驗。
- Ian 要的：訓練窗（500 天）裡越接近預測日的日子權重越高，衰減速度當超參數，做研究和實驗。
- 以前的相關結果：07（舊的總分評分）試過半衰期 180 天，沒有共同的最佳長度；另一個 session 的 `binary_decay`（半衰期 120 天）；10 的 500 天比 125 天好；35 的全部歷史比 500 天好 +0.00012（另外 50 檔 p 0.037，沒過 0.0125）；24 沒有衰減趨勢；28 不更新的舊模型沒有比每天重訓差。

### Ian 的追問：驗證期要多長（2026-11-15 下午）

- 投影片（Learning From Data「Three Learning Principles／Sampling Bias」）：「If the data is sampled in a biased way, learning will produce a similarly biased outcome.」實務規則是 match test scenario as much as possible；例如測試是使用者「最後」的紀錄時，訓練 emphasize later examples（KDDCup 2011），驗證用 late user records。Ian 手寫：「error 在某情境大 ⇒ adjust related data or weight、parameter」。最後的 puzzle：用銀行既有紀錄學信用卡核准的危險。
- Ian 問：訓練階段讓接近明天的日子權重高（43 的衰減權重）；驗證階段要拉多長，是不是也可以調？目標是讓訓練和驗證的日子和未來的測試日子分布相似。
- 現況：模型比較用 walk-forward（每月重訓、評下一個月），2022～2023 485 天加 2024～2026 670 天共 1,155 天，另外 50 檔當獨立的第二群；超參數固定，沒有內層驗證（10、17 顯示短的內層驗證只選到雜訊）；正式流程每天用 500 天重訓，沒有驗證步驟。
- 要點：特徵是每天的名次（每天都是 −1～1 的均勻分布），所以輸入的分布每天都一樣，沒有 covariate shift 可以修；會變的只有「特徵和報酬的關係」（concept drift），能做的只有近期加權（43）或依相似的市場狀態加權（38、38c）。驗證期越短越像明天，但越吵：兩個相近設定每天差的標準差約 0.0012～0.0024（34），驗證 L 天的標準誤約 0.0013 ÷ √L，L = 60 約 0.00017、250 約 0.00008、500 約 0.00006、1,155 約 0.00004。H 之間的差估計在 0.0001 以內，要 L 約 700 天以上才分得出來。
- 43 加一個維度：auto-H 用過去 L 天的樣本外分數挑 H，L 本身就是 Ian 問的驗證期長度。

### Ian 的新目標和組員的大盤模型（2026-11-15 傍晚）

- 新目標：Phase 2 正式名次（2026-11-16 起從零累計）拿第一，累計分數超過第一名。Ian 覺得主對話被既有框架局限，要「敢押大盤」的膽量，並要用 Fable 從全新的角度重看進度和方向（子代理 `fable-fresh-eyes`，11-15 傍晚開始）。
- 組員今天在 Google Drive 新建 2 本大盤方向的 notebook（C2、C2V2D，「離大盤的日子權重加重」），模擬 Phase 2 累計 return ratio 0.14。這個 session 沒有 Google Drive 的權限（沒有 Drive connector，Mac 也沒掛 Drive），檔案還沒拿到。
- Ian 要兩個 session 互相交流：已寄訊息給「大盤方向預測模型與演算法」session（問 notebook 的位置、方法、評估方式和它的進度）。
- 11-15 晚上 MT session 用 Drive connector 存好兩本：`notebooks/teammate/c2_tilt_backtest.ipynb`（21 格）、`notebooks/teammate/rank_ensemble_backtest.ipynb`（29 格，不進 git）。純文字版在 scratchpad `teammate/c2.txt`、`re.txt`。
- C2 的做法（靜態讀過）：仍是 25/25。分數 = combined + γ·(2p − 1)·β̃，γ = 2；combined 是三個成員當天 50 檔名次（−0.5～0.5）的平均，和正式流程同一個模型（`rank_ensemble_backtest` 是組員重寫的 `X_price`，Phase 1、2 的預測和它逐格一致）；β̃ 是過去 120 天對 100 檔平均盤中報酬的斜率（兩邊退一天）在 50 檔的名次 − 0.5；p 是 |m| 加權的 L2 logistic（C = 1），目標是 Top50 當天平均盤中報酬 m > 0，2020-03 起擴張窗、每月第一個交易日重訓。C2 用 14 個開盤前狀態（老師 global 第 t 列的 `^GSPC`、`^IXIC`、`^VIX`，`^TWII`、`^KS11`、`TX_OI` 只用 t 以前，前 1／3／5 天 m、前一天跳空和離散度），C2v2d 加 9 個 `*_ret_lag1`（`tx_night`、`sox`、`tsm_adr`、`dji`、`usd_twd_am`、`us10y`、`wti`、`gold`，拿掉 `us_gspc`、`us_ixic`、`nvda`）共 20 個，欄在 `data/processed` 特徵表、Kaggle `modelnovice/decider-02-dataset` 也有。時間對齊兩個 session 都查過，沒看到偷看。
- C2 的數字（組員那本）：Phase 1（84 天每日平均）原版 0.001457、C2 0.001763、C2v2d 0.002080，和原版差的 95% 區間都含 0；Phase 2 模擬 22 天加總 0.0872、0.0932、0.0864；方向命中 0.48～0.55；每天換 1.5～2 組。p 平均 0.444，所以 tilt 平均 −0.22：大部分是在 `X_price` 原本的低 β 偏好（24：暗中押大盤跌約 0.31；組員量到猜漲 25 檔的 β 比猜跌低 0.64）上再固定多押一點跌，只有一小部分隨 p 擺動。γ 在 2023～2024 從 {0.25, 0.5, 1, 2} 挑到最大值，也像固定那一半在賺。長期 1,134 天 C2v2d +0.00020、C2 +0.00015 出自組員的 `experiments/RESULTS_CONDITIONAL.md`（我們沒有），2023～2024 是挑 γ 的段，乾淨樣本外只有 2025-01 起。MT session 估每換一組市場曝險約變 0.04，每天約 0.08，比規則 B 的上限 0.2 小。最新一次重訓的係數最大的是美股、ADR 前一夜報酬的負號（漲多了當天盤中往回走）。
- 0.14 是模擬榜第 1 名 22 天的累計 0.143（scratchpad `site/state_full_2026-11-12_1700.json`），不是組員的數字。第 1 名 22 天都交、20 天正、每天 +0.0065；每天都在當天 09:00 截止前交（10-14 08:47、11-02～11-06 08:59，其他多在前一晚 07:4x），沒有補交過去日子的跡象；11-02、11-06 的分數剛好等於全猜漲。同 22 天我們的模型每天 +0.0040（0.087），差距每天 0.0025，比 Fable 寫的「回測的 6 倍」小很多（回測期離散度比 Phase 2 小）。
- Fable（`fable-fresh-eyes`，11-15 晚上回）的主張：25/25 拿第一的機率不到 1%；拿第一要變異，猜漲檔數改由落後差距、剩餘天數、預期波動決定；方向用 C2 或任何 ≥ 50% 的訊號；從每天公開的榜反推各隊曝險；預測波動決定哪天押。它的 P(第一) 表是從 23 的前 5 機率除以 3 外推的，沒有重算。主對話的更正：「不用 t 當天價格」是 Ian 定的規則；當天開盤前的資訊 22 已經用真正的 09:00 開盤當替身測過上限（單獨 IC 0.07、加進 `X_price` +0.0001 不顯著，台指期 08:45 沒用），不算新方向；「凍結 `X_price`、停掉選股研究」和 Ian 要的 43 衝突，要問 Ian；`n_up` 可調的程式要先講定義、Ian 確認，也會改到 Ian 11-15 和 MT session 定的「正式期 25/25」。
- Ian 11-15 晚上在 MT session 選「在 Kaggle 做 C2 的樣本外檢查」。分工：主對話做 44（重現 C2、C2v2d 的 2022～2026，拆固定和擇時、placebo、上限）；MT session 做 p 對 P4 的相關、曝險換算（e = β 差 ÷ 2，Ĉ(Δe) 照 MT 04 的 iid 和循環平移）、帳本歸類。44 要存每天一列的 CSV 給 MT：date、m、p_C2、p_C2v2d、三版每天分數、換幾組、三版的 β 差（猜漲 25 檔平均 β120 − 猜跌 25 檔）。MT 提醒：γ 掃描只報告；固定那一半和 MT 的 C1 是同一個對照，只有擇時那一半算證據。
- 44 的事先登記在 scratchpad `teammate/spec44.md`（Holm m = 2，單邊 0.05，只用 2025-01-02～2026-10-08 的 Top50：H1 C2v2d total − original > 0；H2 total − fixed > 0 且月內重排 p 的 placebo p < 0.05）。11-15 晚上用 workflow `wec9jzuja` 寫、審、修。
- Ian 11-15 晚上的四個決定：(1) 正式 Phase 2 先 25/25，11-19 前再定；這幾天在 Kaggle 模擬「押多少、哪幾天押」各自拿第一的機率，加上 44 的結果再選。(2) 不問助教，照目前知道的規則規劃。(3) 43 繼續，和 Phase 2 策略並行。(4) 「不用 t 當天價格」放寬到研究：只在 Kaggle 研究 09:00 前公開的當天資訊（日韓 08:00 開盤、台指期 08:45、試撮價）能不能決定押大盤的方向和大小，要進正式流程時再問 Ian。Decider 已經量過 08:25、08:50 兩級對方向沒有多帶資訊，新的角度是用它們預測當天波動（|m|），決定哪幾天押。
- MT session 11-15 晚上：MT 24 已寫好，讀 44 的 `c2_daily_44.csv`，44 跑完通知它就推。MT 25（Kaggle `modelnovice/mt-25-exposure-cost-count-tilt-vs-beta-swap`，只當決策依據）：同樣改市場曝險，換高低 β 比改猜漲檔數貴。回測 670 天每天的選股成本：改檔數 2 檔（|Δe| 0.073）−0.000003、5 檔（0.183）+0.000006；換 β g 0.25（0.063）+0.000021、0.5（0.139）+0.000070、1（0.334）+0.000272、2（0.475）+0.000577。網站 21 天：改 5 檔 0.000416，換 β g 0.5 0.000727、g 2 0.002529。C2 的 γ(2p − 1) 平均 −0.22、標準差約 0.4，大約是 g 0.25～0.5。它建議 H2 過了再看「同樣的 p 改用改檔數押」，主對話不加進 44，由 MT 用 44 的 CSV 算。
- MT session 11-15 晚上接了 MT 26（P(第一) 的真模擬，對手用 23 的模型逐日跑，T = 20、30、40，固定押、只押三分之一的日子、看天數的追趕，用去名的 `modelnovice/ml-final-phase2-board-anon`）和 MT 27（用開盤前資訊預測 |m|，要 MT 26 顯示「知道哪天 |m| 大」有用才做）。規格寫在 `memory/projects/09-market-timing.md`。
- 44 的 workflow（`wec9jzuja`）完成：81 格（39 code）。修的人沒照審查者改 Holm 的往下走條件：照規格字面，Holm 只看 t 的 p，placebo 只當 H2 自己的通過條件；這樣 placebo 只會讓 H2 少過，整體錯誤率還是 ≤ 0.05。主對話同意（11-15 晚上，看結果之前）。`decision_44.json` 的 `tests.H2` 分 `holm_step_pass`（t 的 p 過了 Holm 這一步）和 `passes`（最後結果）。另外加了三個只印的重現核對（β120 在組員 106 天的分布、C2 的 2026-11 重訓的訓練天數和係數、P1 逐月）。方向模型照規格從 2020-03-01 訓練，用到 2021 的 Top50 m；2021 不評分。如果之後 C2 要用 2021 確認，方向模型要改成只用 2021 以前的資料。11-15 晚上推 smoke（version 1）。
- 44 smoke（version 1，全部資料，只是 placebo 20 次、bootstrap 2,000 次）：重現核對全對上組員（β120 在 106 天 5,300 格的分布、2026-11 重訓的 1,623 天和 14 個係數都一樣；P1 原版 0.001269 對組員 0.001457，35 的 `X_price` 和組員的重寫不完全一樣，C2 0.001782 對 0.001763）。A 段 p 平均 0.477（不是 0.444，那是組員 106 天的值），p̄_train 0.464～0.488，所以固定部分幾乎是 0：Top50 C 段 `fixed − original` 只有 +0.00003～+0.00004。偵測下限（D 段算）H1 0.000343、H2 0.000341。C 段 428 天 Top50：H1 C2v2d `total − original` +0.000324（t 2.54，p 0.006）；H2 `total − fixed` +0.000290（t 2.30，p 0.011），placebo 20 次都沒贏（p 0）；Holm 兩個都過，smoke 的判讀是「擇時有樣本外證據」。我原本猜「大部分是固定多押跌」是錯的。其他段（只報告）：C2v2d `total − original` 2022 +0.00016、D +0.00014、P1 +0.00057；Other50 C 段 +0.00028。oracle（β 傾斜的天花板）A 段每天 +0.0016。另外要記：組員可能試過多個版本才選 C2v2d（名字有 v2d），狀態清單和 |m| 加權是不是看過 2025～2026 才定的，我們不知道，C 段只對 γ 算乾淨。full（version 2）11-15 晚上推。
- 44 full（version 2，placebo 500 次、bootstrap 10,000 次，1 分鐘）：數字和 smoke 一樣。H1 +0.000324（SE 0.000128，t 2.54，p 0.0056），H2 +0.000290（SE 0.000126，t 2.30，p 0.011），placebo 500 次 p = 0（placebo C 段平均 −0.00005）。Holm 兩個都過，判讀「C2v2d 的擇時在 2025 起的樣本外有證據，可以當 2021 確認（42）的候選，Ian 決定」。corr(p, m) A 段 C2 0.078、C2v2d 0.067（每年 0.04～0.15），命中 0.47～0.56。C2v2d 係數 58 次重訓正負號都沒換的：`tsm_adr_ret_lag1` −0.60、`twii_prev` +0.40、`dji_ret_lag1` −0.33、`oi_chg1` +0.18、`us10y` −0.17、`vix_chg` −0.13、`mkt_5` −0.13、`tx_night` +0.13；`mkt_1` −0.24（5% 正）。oracle（β 傾斜天花板）C 段 +0.0020，是完美全押 0.0063 的 31.5%。擇時和原版分數的相關 A 段 −0.23、C 段 −0.15；每天換 2.1～2.6 組；β 差原版 A 段 −0.60、C2v2d −0.56。γ 掃描（只報告）C 段 0.25 +0.00008、4 +0.00040。事後描述（本機讀 `c2_daily_44.csv`，不算檢定）：C2v2d `total − original` 每年都正（2022 +0.00016、2023 +0.00007、2024 +0.00022、2025 +0.00017、2026-06～10-08 +0.00057）；2025-01～2026-05（組員評分前）338 天 +0.00026（t 2.01）；C 段 |m| 前 10% 的日子佔增益 42%，拿掉最好 5 天剩 +0.00015。version 3 補結果文字重推。已通知 MT session 推 MT 24。
- MT 24（MT session 11-15 深夜，version 5 full，讀 44 version 2 的 `c2_daily_44.csv`；細節在 `memory/projects/09-market-timing.md` 的「MT 24」）把 C2v2d 的 +0.000324 拆成兩塊。押大盤那塊（Δe·m）Ĉ +0.000144，iid p 0.062、循環平移 p 0.008（規格取 0.062）；corr(p, P4) 0.60～0.65，算 P4 那一類；對 P4 規則 B 的 n_b 取殘差剩 +0.000068（p 0.21），2022～2024 是負的。另一塊 D − Δe·m 每天 +0.000182（t 約 1.95），D 對 Δe·m 的斜率 0.94（se 0.16），不是 β120 少算曝險；打亂 p 就沒了，和 2p − 1 的相關主要段 0.17、2024 0.12、2022～2023 0.07；拿掉 |m| 最大的 10 天還有 +0.000223，拿掉它自己最好的 5 天剩 +0.000095。MT 的判讀：C2v2d 比 P4 多的只有第二塊，像是 p 高（多半台積電 ADR 前一晚跌）的日子高 β 股盤中比 β120·m 好（電子股開低回補）；這塊是看完結果才拆的，2022～2023 很弱。MT 建議用「β120 × 前一晚 ADR 報酬」的交互特徵在新資料上事先登記測。主對話的對照：31 的 `X_us`（每檔對 SOX、台積電 ADR 的 120 天敏感度排名 × 前一晚報酬 ÷ 250 天標準差，4 欄）已經測過很接近的東西，Top50 回測 +0.00004，沒過；42 的 H-C2 會給 C2v2d 總效果一個 2021 的獨立檢查。
- Ian 11-15 晚上在 MT session 再改決定（取代「只影子跑」）：每天交件換成 C2v2d，備援依序 C2、rank_ensemble（MT 另外留 persist、online_lr 在最後）。MT session 寫了 `src/c2_tilt.py`（照組員那本和 44），推上分支（748db97），config 還是 rank_ensemble；Kaggle `modelnovice/c2-tilt-production-code-check` 核對 p 和 44 的 1,155 天最大差 1.5e-12，組員 Phase 2 的 22 天 C2 全一樣、C2v2d 只有 11-11（WTI、黃金收盤在 07:10 後被 yfinance 修正，差 0.006）和 11-12（組員的檔沒更新）不同。整條流程重播 10-12～11-13 過了才改 config，台北 06:30 前過就 11-16 換，否則 11-17。之後 `scores_<t>.csv` 多 `base_prob`、`base_pred`（rank_ensemble 的選法）、`p_up`、`tilt`、`beta_rank`。MT 給的 `scores_<t>.csv` 欄名（C2 系列才有後面這些）：`date`、`stock_id`、`model`、`ridge`、`kridge`、`lgbm`、`base_prob`、`base_pred`（rank_ensemble 的 0/1）、`combined`（三個模型名次 − 0.5 的平均）、`beta120`、`beta_rank`（β120 在 50 檔裡的名次 − 0.5）、`p_up`（P(m > 0)）、`fit_day`、`n_train`、`missing_states`、`tilt`（= 2·(2·p_up − 1)）、`score`（combined + tilt·beta_rank）、`prob`、`pred`（交的 0/1）、`variant`、`rank`。MT 11-16 08:40 以後要把 `src/` 照 ML 專案結構重排（`src/pipeline/`、`src/models/`）；主對話的 Kaggle notebook 都沒有從 GitHub 抓 `src/*.py`，只讀 `data/processed/`、`data/raw/teacher/`、`data/submission/`，已請 MT 不要動 `data/` 的路徑，MT 確認照舊（scores 欄名也不變）；C2v2d 生效那天 scores 的 `variant` 是 `c2v2d`。MT 27 full：08:25、08:50 的開盤跳空對挑 |m| 大的日子沒有用。主對話這邊：45 不再需要影子跑 C2v2d，改成每週核對（重算當天早上 C2v2d 和 rank_ensemble 的選法，對 submission 和 `base_pred`，再算兩者分數差）；46 照做（MT 說對 12-06 的判斷有用）；42 照做。
- Ian 11-15 深夜在 MT session 的三個決定（MT 轉述，Ian 直接回 MT）：C2v2d「影子跑，再用正式的排名重測」；Phase 2 維持 25/25；MT 27（用開盤前資訊預測哪幾天大盤波動大）要做，在 MT session 做，只當參考。主對話查證：35 的 `X_price` 和 16 同邊 100%，都是每月重訓；正式流程 `src/rank_ensemble.py` 每天早上重訓（說明寫「沒有單獨回測過」）。所以「正式的排名」做成 46：46a（2022-01-03～2024-06-28）、46b（2024-07-01～2026-11-13）每天重訓、只預測 Top50，46c 照 44 量（H1、H2、Holm m = 2 重量，不是新證據；判讀三句：都過「在正式排名上重現」、一個沒過「只部分重現」、都沒過「依賴每月重訓的 35」）。`c2_daily_46.csv` 欄位和 44 一樣給 MT 24 重跑。核對：兩個段首日和 35 比；46b 的 2026-11-13 選法和 commit `c0c51437` 的 `submission_2026-11-13.csv` 比（那天正式流程是 rank_ensemble）；P1 和組員每天重訓的 0.001457、0.001763、0.002080 比。規格 scratchpad `teammate/spec46.md`，workflow `wkfa3ux7w` 寫、審、修。42 照凍結的規格用每月重訓（沒改）。
- Ian 11-15 深夜的兩個決定：(1) C2v2d 先影子跑，只記錄不交。做法不改 `src/`、不動 oop：Kaggle 45（`2026-1111-raw-feature-model-45-c2-shadow`，規格 scratchpad `teammate/spec45.md`）用每天早上 09:00 前最後一個動到 `data/submission/scores_<t>.csv` 的 commit 重算 C2v2d 的猜法，和實際交的比，只描述。(2) 2021 現在打開，法人組和 C2v2d 一起確認（42）。
- 42 打開 2021 前凍結的東西（11-15 深夜）：規格 scratchpad `teammate/spec42.md`；Holm m = 2（H-F1 `X_inst − X_price`、H-C2 C2v2d `total − original`），單邊 0.05，主要統計量是兩群每天差的平均，SE 取 iid／NW lag 10／stationary block 最大，通過還要兩群點估計都 > 0；法人組定義用 Kaggle kernel 33 version 2、`decision_33.json` 的 23 個 `inst_columns`、kernel 25 version 1 的 `new_columns_25.csv.gz`；C2v2d 用 44（version 2）的程式；資料固定在 commit `2f86dca36e97a52dde37358c4537ad79be69d035`；價量欄缺值上限 0.30；評分期 2021 第一個能訓練的日子（預期 01-11）到 12-30，約 239 天。smoke 完全不算 2021 的分數。重跑規則：檢定印出前當掉可以直接重跑；印出後才發現 bug，先寫進 memory 再重跑，兩次都報告。
- 43a、43b smoke version 1 停在 H = ∞ 的 ridge 核對：和 35 差 1.4e-8，超過 1e-9。原因是 35 存的 ridge 分數是 float32（約 8 位有效數字）；真的訓練列不同會差 1e-3 以上。門檻改成 1e-6 加同邊 100%，version 2 重推 smoke。smoke version 2 兩本都過（ridge 1.4e-8、同邊 100%；1 個種子的 kernel ridge 同邊 0.998～0.999、LightGBM 0.964～0.968，smoke 只印）。43a 3 段 × 4 個設定 0.5 分鐘、43b 1.4 分鐘，推算 full 約 30、80 分鐘。有效天數：500 天窗 H 1000／500／250／125 是 495／481／433／318；全部歷史 H 1000／500／250 約 1,450～1,480／1,160～1,170／705。接著推 43c smoke（讀兩本的 smoke 輸出），它跑完才推 43a、43b full。43c smoke（version 1，1 分鐘）從頭跑到尾沒錯；只有 47 天，檢定數字不看。漂移診斷不靠 43a、43b，smoke 也是 2022～2026 全段：41 欄每天 IC 的 local level 隱含半衰期中位數 336 天（< 500 天 23 欄、> 1,155 天 17 欄），照事先的句子印「漂移比預期快，衰減值得在影子跑裡留著」（只報告）。11-15 深夜把 43a、43b 改成 full 推（version 3）；兩本都跑完才推 43c full。43a full（version 3）28.8 分鐘，核對通過：3 個種子時 ridge 差 1.4e-8、kernel ridge 1.4e-8、LightGBM 1e-16，三個都同邊 100%；58 段 × 4 個設定、115,453 格、1,155 天，每段每個設定約 28 秒。
- 43b full（version 3）63.0 分鐘，核對和 43a 一樣通過。43c full（version 2）1.1 分鐘：D1、D2 都沒過，分不出，時間衰減結案（數字在 04-raw-feature-experiments.md 的 43～46）。補完三本的結果格，11-15 晚上重推 43c version 3、43a、43b version 4。
- 46a、46b smoke（version 1，11-15 21:22 推，各 1.2 分鐘，1 個種子、核對日加最後 5 天）都過：兩個段首日（2022-03-01、2026-10-01）每天重訓和 35 的每月版 ridge 差 3.7e-8、同邊 100%，1 個種子的 kernel ridge 同邊 100%、LightGBM 0.96（smoke 只印）；46b 重算 2026-11-13 的選法，和 commit `c0c51437` 的 `submission_2026-11-13.csv` 50 檔一樣、猜漲 25 對 25、不同 0 檔；長表自我核對（11-12 當 t）最大差 0。每天每個 worker 約 7～8 秒，推算 full（3 個種子）46a 約 40 分鐘、46b 約 55 分鐘。11-15 晚上推 full（version 2），同時推 46c smoke（version 1，讀兩本的 smoke 輸出，沒有的日子用 35 補）。正式流程 11-15 21:23 已經換成 C2v2d（commit 888cadd），11-16 起生效。46c smoke（version 1，0.8 分鐘）從頭跑到尾沒錯：讀到 46a、46b 的 smoke 版（各 5 天），A 段只有 5 天來自 46，其他 1,150 天用 35 補，所以 H1、H2 和 44 一樣（數字不看）；35 有 25 天 Top50 只有 49 檔有答案，46c 拿掉 `r` 空的格子後對得上。smoke 的判讀句沒有標 smoke，不影響 full。42 full（version 2）11-15 晚上推。42 full 跑完（數字在 04-raw-feature-experiments.md 的 43～46）：H-F1 法人組未確認（+0.000155，p 0.078），H-C2「2021 不支持 C2v2d」（−0.000228，t −1.11）。11-15 晚上（約 21:55）用 AskUserQuestion 問 Ian 11-16 要不要換回 rank_ensemble（推薦換回，理由是唯一沒人看過的保留段沒過，38、43 也是這樣結案）；Ian 隨即選「維持 C2v2d」。已轉告 MT，config 不動。同時用 workflow `w9eegvdhm` 檢查 42 只有 2021 走到的程式路徑（β120 暖機、2020 狀態的標準化、擴張窗訓練、評分），找到真的 bug 照重跑規則處理。45 改版（agent 照 scratchpad `teammate/spec45.md` 最後的「改版」改，原本的影子跑版備份在 `kaggle/src/nb45_shadow.txt.bak`）：每天依 `scores_<t>.csv` 的 `model` 欄（寫法是 `rank_ensemble（c2v2d 的備援）` 這種，取「（」前面）分 official（c2v2d，逐格核對 combined、base_pred、β120、beta_rank、p_up、fit_day、n_train、tilt、score、pred，不一致只記下，`pred` 和 submission 不同才停）、shadow（退到 rank_ensemble，重算 C2v2d）、skipped（c2、persist、online_lr；c2 照樣評分但不進累計）。p 的容許差在看資料前從 1e-8 放寬到 1e-6（正式的 p 在 oop 算，sklearn 是離線 wheel），tilt 4e-6、score 2e-6。smoke（version 1，11-15 晚上）0 天的路徑正常結束（API 用 2 次）。第一次 full 等 11-16 09:00 以後；46c 跑完要把 nb45 第 1 節的 `C_SEGMENT_46C` 填成 46c 的 C 段每天差。42 的程式檢查（workflow `w9eegvdhm`，4 個審查者 + 3 個反駁者，11-16 凌晨結束）沒有找到會改 2021 數字的 bug：β120 獨立重算 23,898 格最大差 1.8e-15；狀態、標準化、方向模型照 44；擴張窗訓練列只用重訓日以前的日子；分數、SE、Holm 從輸出重算差 1e-16。唯一的發現：2021-01 方向模型的重訓日是第一個評分日 01-11（216 天），組員和 `src/c2_tilt.py` 的 `fit_day_of` 會用 01-04（211 天）；照規格和 44 的寫法，3 個反駁者都推翻，要翻判讀 1 月每天得多 +0.0036，做不到。42 version 3（只補結果文字）11-16 凌晨推，跑完。46a full（version 2）76.6 分鐘、46b full（version 2）60.5 分鐘：3 個種子時兩個段首日三成員和 35 同邊 100%（ridge 3.7e-8、kernel ridge 1.9e-5、LightGBM 1e-16）；46b 的 2026-11-13 和正式交件檔 0 檔不同；46a 602 天 30,086 格、46b 576 天 28,789 格（49 檔的日子 11 天）。46c full（version 2）11-16 凌晨推。46c full（version 2）跑完：H1 +0.000279（t 2.29）、H2 +0.000242（t 2.01）、placebo p 0，判讀「44 的結果在正式交件的排名上重現」（數字在 04-raw-feature-experiments.md）；version 3 補結果文字 11-16 凌晨推（MT 讀 version 2 的輸出）；nb45 的 `C_SEGMENT_46C` 填 0.000279。11-16 MT 轉告：網站上 11-16 00:50（台北）已經有一份手動交的 `submission_2026-11-16_C2.csv`（不是這個 session 或它的 agent 交的，查過 transcript），排程 07:10～08:25 六次都照「已經有提交就不蓋掉」結束，所以 11-16 沒有交 C2v2d、沒有 `scores_2026-11-16.csv`，爬蟲和特徵也沒跑。45 第一個能核對的日子最早是 11-17（那天沒人先手動交才有）。MT 11-16 09:44 推 `src/` 重排（733cce8）：`src/rank_ensemble.py` 變成 `src/models/m3_rank_ensemble.py`、`src/c2_tilt.py` 變成 `src/models/m4_c2_tilt.py`，流程在 `src/pipeline/step1_crawler.py`～`step5_merge_raw.py`；`data/` 路徑和 `scores_<t>.csv` 的欄名不變。這邊的 notebook 只讀 `data/`，不用改；42～46 文字裡的 `src/rank_ensemble.py` 指的是當時的檔，照舊。11-17 07:10 是正式流程第一次用新程式。11-16 凌晨發現 scratchpad 的 `kaggle/src/shared/teacher_day.py`、`teacher_extra.py` 和 11-11 的下載（`out/nb01` 等）被 macOS 的暫存清理刪了（`/private/tmp` 裡 3 天沒讀的檔）；從 `nb46b/notebook.ipynb` 還原，重新 build 46b 和原本逐位元一樣；整個 scratchpad 用 `touch -a` 更新讀取時間。
- 11-15 19:4x 三個寫 notebook 的 agent 撞到 5 小時用量上限（20:10 重置），留下半成品：`nb42.txt`（可 build）、`nb46c.txt`（可 build）、`shared/daily_refit.py`；`nb45.txt` 寫完沒審；`nb46a.txt`、`nb46b.txt` 沒寫。20:15 用 workflow `w0243lx9v` 接著補完、審、修三本。42、45 用 workflow `w1580rzge` 寫、審、修；make_push 已加 nb42、nb45。
- MT 26 結果（MT session 11-15 晚上，細節在 `memory/projects/09-market-timing.md` 的「MT 26 拿第一的機率」）：T = 20、按天重抽，P(第一) 左邊回測成本、右邊網站成本。25/25：收縮的對手 0.09%／0.09%，不收縮 0%／0%（P(前 5) 4.7%）。沒有訊號每天全押：4.35%／0.31%、1.54%／0.08%，20 天總分平均從 0.0201 掉到 0.0001／−0.047，後半的機率 61%／92%。不看天數的追趕（落後 0.01 以上才全押）：4.66%／1.04%、1.26%／0.29%；看天數的版本猜錯天數更差。corr 0.11 的方向訊號押 0.4（樂觀）：2.57%／0.32%、0.49%／0.04%。MT 27 那段 MT session 後來更正：原本「同成本」用 a·√3 配（假設成本和 a² 成正比）不對，改成同樣的 20 天總分平均比較（在每天押的幾個點上內插）。回測成本下挑日子沒有好處（oracle 日 0.99% 對每天押 0.90%，前 20 天波動 v20 0.68% 對 0.63%；不收縮的對手 oracle 還輸，0.12% 對 0.15%）；網站成本下有小好處（oracle 0.39%、v20 0.30%、每天押 0.06%），因為網站每個押的日子都付一塊固定成本。MT 27 最多多出 oracle 減 v20，網站成本下 0.09 個百分點（不收縮的對手 0），所以先不做；這是判斷，交給 Ian 和押多少一起決定，不是事先寫好的條件沒過。v20 只用前一天為止的波動。結論：拿第一靠變異，不靠訊號；押越大第一的機率越高、平均總分越差。要不要為了 1～4% 的第一機率放掉約 0.02 的 20 天總分（等於整個選股的收益），是 Ian 11-19 前的決定，配上 44 的結果。
- 43 的文獻（workflow `wmgqfwoyi`，9 個 agent，36 篇查證過，全文在 scratchpad `research2/recency_result.json`）：在我們的設定，時間衰減預期分不出。指數衰減只在係數持續小幅漂移時最適（Pesaran, Pick & Pranovich 2013），漂移趨近 0 時等權最好；斷點小時舊資料省下的變異大於偏誤（Pesaran & Timmermann 2007）。有效樣本約 2.9H 天，H 約 175 天和 500 天窗打平，所以 500 天窗內加衰減等於縮窗（10：125 天比 500 天差）。最像我們的實證多半沒差：DoubleEnsemble（A 股、500 天窗）時間加權四個設定都輸等權；DDG-DA 只幫到 LightGBM（IC +4.8%，ICIR 沒變好）；Dangl & Halling（S&P 500 月報酬）半衰期約 360 天被淘汰、約 720 天和不衰減差不多。挑 H 要很長的驗證期：兩個相近設定每天差的標準差 0.0012～0.0024，要分出 0.0001 得 700～2,000 天（Cawley & Talbot 2010；10 的 63 天只挑到雜訊）。在多個 H 上挑最好的是 data snooping（Rossi & Inoue 2012）。2021 的訓練歷史只有 245～490 天，各個 H 幾乎一樣，2021 確認不了 43，所以「2021 等 43 跑完再一起打開」的理由不在了，要問 Ian。
- 43 的事先登記在 scratchpad `teammate/spec43.md`：拆 43a（500 天窗 × H {1000, 500, 250, 125}）、43b（全部歷史 × H {1000, 500, 250} 和按天打亂權重的 `shuf500`）平行跑，43c 讀 35、43a、43b 做檢定。Holm m = 2，單邊 0.05，Other50 1,155 天：D1 `X_dec500`（全部歷史、H 500）− `X_price`；D2 `X_autoH`（每月用 2022 起、重訓日以前的樣本外分數，在 `X_price`、`X_all`、H 1000／500／250 裡挑）− `X_price`。D1 過了還要 Other50 的 `X_dec500 − X_all` > 0 才算衰減的功勞。驗證期 L = 60、250、500 和 sup-t、PBO、漂移的 local level 診斷（只用 2022 起）只報告。預期 `X_dec500` +0.00005～+0.00010，`X_autoH` +0.00002～+0.00008，偵測下限 0.00019～0.00021。11-15 晚上用 workflow `w7qwx812g` 寫、審、修；make_push 已加 nb43a、nb43b、nb43c。

### 先後順序

1. 38 A 段（閘門，約 5 分鐘）：先跑，結果決定這一輪的 Holm 家族有沒有比較。
2. 39、40（各 5～10 分鐘，只用已存的預測或特徵）：和 38 A 段平行也可以，它們不看另外 50 檔的新結果。
3. 41a、41b（各約 35 分鐘，要訓練）：38 A 段之後跑。
4. 38 B 段（約 20 分鐘，含平移 null）：只有閘門過了才跑。
5. 42（約 15 分鐘）：只有 38 B 段過了 Holm，或 Ian 同意法人組用 2021，才跑。兩個都要跑時同一本一起解鎖。

每本先 smoke 再 full。全部都跑約 2 小時 Kaggle CPU；閘門沒過（預期）時約 1.5 小時，38 B 段和 42 都不跑。

### 38 市場狀態條件化的排名

- 問題與假設：依昨天的市場狀態調整各組訊號的權重，排名會不會更好。預期 H0 成立（閘門 85% 以上過不了）。
- 狀態變數（07:10 前都知道）：S1 昨天 100 檔等權盤中報酬 m 的正負；S2 m 的 20 日已實現波動三分位（VIX 的替身，VIXTWN 2026-08-03 才有）；S3 昨天 100 檔 r 的橫斷面標準差三分位。三分位切點一律用 t 以前 250 天的滾動值（至少 120 天），A、B 段和 2021 用同一個定義。
- 成分：z_X（`X_price` 的當天名次，來自 35 存的 100 檔三成員分數）加 30 的 6 組合成分數 G1～G6。欄到組的對應在 `features_30.csv` 的 `group` 欄。每組照 2022 年（B 段的暖身年）的 `model_corr` 正負號相加再取名次；`model_corr` 是欄的名次和集成分數每天的相關，用 35 的成員分數算，不用答案。跨組的兩對完全重複欄留在持續性組（`p_e_mean20`、`p_gap_rel20`），習慣組拿掉 `c_intraday_mean20`、`o_gap_mean20`。
- A 段（只用 Top50 的標籤，不看另外 50 檔，2021 只當歷史）：每天把 e 對 [z_X, G1～G6] 做橫斷面迴歸得 b_d。δ_{j,s} = b̄_{j,s} − b̄_j。U_S = 用 rank(b̄_X·z_X + Σ_j δ_{j,S}·x_j) 排的 25/25 分數減 `X_price`，in-sample。placebo：狀態序列整條循環平移，排除 |k| < max(60, 3 × 平均連續長度)，其餘 k 全用；另做 block 長度等於平均連續長度的 stationary block 打亂。P95_S 取兩種 placebo 95 百分位較大的。excess_S = U_S − P95_S。
- mde_B：在 Top50 上用擴張窗跑一次樣本外的 A 段版本（2023-01-03～2026-10-08），取它每天差的標準差 SD_oos，mde_B = 2.487 × 1.4 × SD_oos ÷ √909（1.4 是 34 量到的另外 50 檔對 Top50 標準差比的保守值）。
- 過關要同時滿足：某個 S 的 excess_S ≥ max(0.0001, mde_B)；2022～2023、2024～2026 兩段用同一個全期 δ，各自 U_seg − P50_seg ≥ 0.00005（P50_seg 是同一組平移在該段的中位數）。過關的 S 不只一個時取 excess_S 最大的。全期重新加權版減 `X_price` 只報告。
- B 段：X_state(t) = rank(b̂_X·z_X + Σ_j δ̂_{j,S(t)}·x_j)，b̂、δ̂ 用 t 以前的 100 檔日資料，2022-01-03 起擴張窗，2022 全年暖身。評分：另外 50 檔 2023-01-03～2026-10-08，909 天。主要統計量 `X_state − X_price`，單邊；p 值用一般配對 SE 和 Newey–West（lag 10）SE 較大的那個。
- B 段的副作用控制：擴張窗下 δ̂ 在評分日上不是零平均（各狀態在評分期的比例和估計窗不同），會混進 34 那類整體加權。所以每個評分日記下實際套用的 δ̂_{j,S(t)}，報告評分期每組的平均 tilt 和各狀態的比例；另外把 A 段用過的循環平移狀態挑 40 個 k，照同一個 B 流程跑一次，當成「含同樣副作用的 null」。
- worth_shadow：過 Holm；`X_state − X_price` 超過平移 null 的 95 百分位；另外 50 檔 beta 調整後的差 > 0；猜漲 25 檔的平均 beta 和 `X_price` 差 ≤ 0.1。Top50 2023～2026 只報告（被閘門用過）。另外報告「平移狀態裡過閘門的那些，B 段 p < 0.05 的比例」，量閘門和 B 段的選擇相依。
- 上線版：δ̂ 在 2026-10-08 凍結，正式流程只多一個 7 欄的線性後處理（z_X 和 6 組分數都能從當天的特徵和集成分數算）。正式流程只預測網站給的 50 檔、每天重訓，Kaggle 是 100 檔、每月重訓，上線前要確認兩者的 z_X 一致；不打算每天重估 δ̂。
- 2021 確認：δ̂ 用 2022～2026 估好後凍結，套到 2021；2021 的 `X_price` 用 2020-01-02 起的截短窗重建（照上面的缺值規則）。限制：2022～2026 的 z_X 來自含 2021 標籤的訓練窗，δ̂ 間接碰到 2021 標籤；2021 的 z_X 品質和估 b̂_X 時不同。
- 沒過：記死路「市場狀態條件化的排名（MASTER 式門控、regime 交互、TRA 路由）在 100 檔上沒有偵測得出來的空間」。
- 限制：S 在 Top50 挑、在另外 50 檔測，日子相同。B 的 δ̂ 也用到 Top50 的標籤。過閘門時 B 的名目 0.05 實際約 0.06～0.13（吃市場狀態的候選可能更高），無條件的 FWER 仍 ≤ 0.05。

### 39 集成算術和候選庫上限

- 問題與假設：「再加模型」有沒有用，能不能只靠新成員單獨的分數和它與成員的相關預測。假設等權名次平均的公式 S = Σg ÷ √(ΣR) 對得上過去的實驗。
- 資料：16（Top50，1,175 天，三成員和四種集成）、17（有 `flaml_forward`，沒有 kridge）、18（只有 2024-01-02 起）、20（`rank:persist120`）、14（`rank:E3_persist120`）、21（placebo、5 類、3 類，沒有 `X_price` 的成員）、26（六組欄 × 四種模型，含 XGBoost）、32、35（100 檔，有 `is_top50`）。17、21 照 (date, stock_id) 和 16 接上成員分數；全部只用共同的日子；18 只放進 2024～2026 的比較。另外 50 檔只驗 32、35 的候選（ranker、placebo、`T_avg`、h5）和 33 的 `X_inst`。22 用到 t 當天開盤，排除。
- 方法：每天 25/25 分數和兩兩每天 Spearman 平均。先報公式對 `X_price` 本身的誤差（另外 50 檔約高估 0.00005），再用比例校正（實際 S3 × 公式的 S4/S3）預測「當第四成員」「取代 LightGBM」的差，和實際並排。報 `persist120` 和 `X_price` 每天的相關，用公式預測 18 的 `X_price_persist`，對不上就先修公式。三成員的最佳非負權重；候選庫的最佳非負權重（in-sample 一次，再做 2022～2023 學、2024～2026 用和反過來）。
- 判斷：候選庫上限的時間切開版本 < 0.0001，stacking 和 ensemble selection 結案；三成員最佳權重的上限約 +0.00002，成員權重（NNLS、IC softmax）記死路。之後任何新模型（TabPFN、MASTER 簡化版、NCL、DoubleEnsemble、LambdaRankIC）先在 Top50 2024 試跑，比例校正後的公式預測 ≥ 0.0001 才給 Holm 名額。

### 40 單欄檢定表和篩選閘門的必要條件檢查

- 問題：Ian 問「有沒有統計檢定能快速篩特徵」，在我們自己的資料上做一張表給他看，並量「單欄 IC」和「殘差 IC」（候選欄扣掉基本欄、目標扣掉 `X_price` 分數之後的相關）哪個比較接近模型測試的結果。
- 方法：35 個不重複的基本欄，每天 Spearman IC，NW lag 10、Romano–Wolf、Holm、BH、BY、|t| > 3 並列，再加 Fama–MacBeth 多變量斜率的整群 Wald。Top50 用 26 的四組加 31 的四組，另外 50 檔用 33 的法人組加 31 的四組，各算單欄 IC 和殘差 IC。
- 判斷：只報告，不當停止規則（正例只有法人一組，答案在雜訊內，閘門和模型結果用的是同一批日子）。唯一的判斷是必要條件檢查：把借券融資（未編號的 D 項）現有的閘門（至少 1 欄兩段 |t| ≥ 2；法人欄的方向沒有事先指定，回頭檢查時只要求兩段同號）和乾淨版（Top50 組 Wald、日內打亂 null、p < 0.10）套在 Top50 2022～2026 的法人組上。會擋掉法人組：D 項拿掉閘門直接進模型測試；不會擋：D 項保留閘門但只在 Top50 算、模型測試放另外 50 檔。

### 41 去重等價、代表欄、拿掉單一組重訓

- 問題與假設：去重在 ±0.00005 內等價；每群留一個代表欄小幅變差；拿掉單一組時只有持續性組明顯變差（約 −0.0003）。
- 去重的 35 欄：拿掉 `gap_rel`、`o_gap_rank`、`o_intraday_rank`、`a_ret1`、`c_intraday_mean20`、`o_gap_mean20`（跨組的兩對留持續性組那一欄，和 38 一致）。
- 方法：100 檔 2022-01-03～2026-10-08，兩群各自 25/25，每月重訓，種子 0～2，程式和 31～35 相同，只有 γ 固定 0.2/41（31～35 是 0.2 ÷ 實際欄數，2022 前兩段是 0.2/38，要改一行）。九個臂：去重 35 欄對 `X_price`；去重 35 欄、γ = 0.2/35（次要）；每群留一個（37 的 0.7 分群剩 19 欄，代表欄取群內平均 |ρ| 最高的，不用答案）；從 35 欄各拿掉 30 的一組，共六臂。代表欄和拿掉組的臂對去重 35 欄比。另外單獨報 ridge 一個成員的差。
- 統計量：兩群每天差的平均，1,155 天；SE 用一般配對和 20 天區塊 bootstrap 較大的那個。開跑前用 35 的 `X_placebo` 的 SE（兩群平均約 0.0000163）算出等價的通過機率寫進 notebook：真值 0 時約 84%，0.00002 時約 57%，0.00004 時約 15%。
- 三個結局：90% 區間在 ±0.00005 內記「等價」；95% 區間不含 0 記「有差」；其他記「分不出」。同邊比例只報告，附 18 的 0.969～0.990 當參考。
- 判斷：去重「等價」，寫「冗餘不影響分數」，PCA、sPCA、IPCA、knockoffs 挑欄、代表欄結案，Ian 可以為了維護改用 35 欄（`kernel_gamma_scale` 改成 0.171 = 0.2 × 35/41）；「有差」，記差的方向和大小，維持 41 欄；「分不出」，維持 41 欄，不寫機制。代表欄兩群平均 95% 區間 < 0，記「群內的差有訊號」。拿掉一組：90% 區間在 ±0.0001 內，才在 `02-feature-table.md` 寫「這組有替身」，其他只寫「分不出」。任何正向結果只登記成下一輪的 Holm 候選。

### 42 2021 確認（條件式）

- 共同規則見上面「這一輪的規則」：凍結、同一本解鎖、單邊配對 t、兩群平均、Holm m = 實際個數、價量欄缺值上限 0.30、逐段欄數檢查。
- H-F1 法人組（Ian 同意才跑）：定義是 Kaggle kernel 33 version 2 的程式、`decision_33.json` 的 `inst_columns`、25 version 1 的 `new_columns_25.csv.gz`、法人欄缺值上限 0.30。三個成員、種子 0～2、每月重訓，訓練窗最多 500 天、不足用擴張窗、滿 250 天就先訓練一次（第一次是 2021-01-11，可評分 239 天）。法人 18 個新欄 2020 年覆蓋率 0.878～0.996，2021 全部 1.0。SE 用 34 的 `X_inst` 標準差算約 0.000106，MDE 約 0.00026。通過的規則：Holm 調整後單邊 p < 0.05，而且兩群的點估計都 > 0。分支的機率（真值 +0.00012 ± 0.00006）：單獨跑（m = 1）通過約 30%、未確認（沒過但兩群平均的點估計 > 0）約 54%、點估計 ≤ 0 約 16%；和 38 B 一起（m = 2，第一個門檻 0.025）通過約 22%、未確認約 62%、≤ 0 約 16%。通過：上線候選，Ian 決定，2021 確認不等於一定要影子跑；未確認：只留給上線後的日子；≤ 0：法人組結案。打開 2021 前把 33 的 kernel 版本號記在這裡（notebook 不進 repo）。
- 38 B 段（過了 Holm 才做）：見 38。
- 規格放哪裡（11-16 補）：scratchpad 的 `teammate/spec42.md`～`spec46.md` 會被 macOS 的暫存清理刪掉，以 Kaggle notebook 開頭的「問題與假設」「實驗設計」「實驗方法」幾格為準（帳號 modelnovice，slug 前綴 `2026-1111-raw-feature-model-`）：42 `42-holdout-2021` version 2、43a／43b／43c `43a-decay-window500`／`43b-decay-full-history`／`43c-decay-tests` version 3／3／2、44 `44-c2-tilt-check` version 2、45 `45-c2-shadow`（改版後 version 1 是 smoke）、46a／46b／46c `46a-daily-refit-early`／`46b-daily-refit-late`／`46c-c2-daily-check` version 2。
- 打開 2021 前補記的讀法（11-15 21:30，審查 42 的 agent 提出）：規格裡「方向模型只用 2021 以前的答案」和凍結的公式有衝突，因為 C2v2d 的方向模型照組員的規則每月重訓、擴張窗，2021-02 起的重訓會用到 2021-01 的 m。42 照凍結的公式做，讀法是「每次重訓的係數只用重訓日以前的答案」，沒有用到評分當天或之後的答案；2021-01 那段的 p 只用 2020-03～12 的答案。42 實驗方法裡的小標「核對（不碰 2021 的答案）」指 smoke 不算 2021 的分數，不是不讀 2021 的列。
- 掛載的版本（11-15 21:30 查 Kaggle，CLI 和 API 都不給版本號，用輸出檔的建立時間和 sha256 確認）：25 輸出建立於 11-12 14:48 UTC（version 1）；33 是 11-13 14:01 UTC（version 2，`decision_33.json` 的 `run_mode` 是 full）；35 是 11-13 15:35 UTC（version 2）；44 是 11-15 10:43 UTC（version 3，只補結果文字，程式和 version 2 一樣）。42 加了一格印掛進來的檔的 sha256，smoke 跑完要和本機下載的對：`columns_25.json` d7988341、`new_columns_25.csv.gz` 543cbfb6、`decision_33.json` 176e656a、`predictions_33.csv.gz` 587036d0、`predictions_35.csv.gz` 818fbf6f、`c2_daily_44.csv`（version 2）368ab245。44 version 3 的 `c2_daily_44.csv` 如果指紋不同，逐格比數值，一樣才跑 full。42 smoke（version 1，11-15 晚上）印的六個指紋和本機的全部一樣（44 version 3 的 `c2_daily_44.csv` 和 version 2 逐位元相同），掛的就是凍結的版本。smoke 沒有評分 2021（輸出只有核對段 2022-03-01～2026-10-08 的 29 天）；核對：ridge 和 35、33 差 1.4e-8、同邊 100%，2025-01 的 p 和 44 差 6e-17；2021 有 12 段、239 天，價量欄在 0.30 上限下每段 41 欄（照 10% 會是 37～38 欄），法人組 64 欄（照 33 的規則 60～61 欄），照凍結的 0.30 上限；2021-01 的 p（重訓日 2021-01-11，訓練 216 天）平均 0.474、標準差 0.32、沒有一天落在 0.5 ± 0.01。凍結的判讀句「C2v2d 寫進影子跑的判斷」是正式流程換成 C2v2d 以前寫的，不改程式，結果出來在 memory 寫成對正式流程的意義。

### 刪掉的提案

- 有效秩普查：37 做完了。
- null 校準四個（`F-deployable-4` 等）：打亂的一欄幾乎不動 ridge，null 比真實候選的成對差窄很多，校準不了偵測下限；模型雜訊 18 量過（±0.00004）。
- knockoffs 三個、IPCA、sPCA、PCR、Romano–Wolf 挑欄對不挑：理由見第一個問題；IPCA 是秩受限的線性模型，和 ridge 幾乎同一個函數。
- 市場狀態診斷三個：併進 38 A 段；衰退那一半 24 做過。
- DoubleEnsemble 四個：重加權後的 LightGBM 和原本的相關 > 0.95，公式預測 < +0.00002；只用 5 棵樹的軌跡退化成 11 的截尾權重。
- 直接優化 Rank IC 三個：丟掉 r 的大小；35 已經是同樣的結果。
- 成員權重兩個：最佳權重上限 +0.00002，39 記錄結案。
- 窗長集成、指數衰減：07、35 結案；訓練 ×3 超過 oop 的時間。
- 隨機子空間：有效秩約 11，子模型彼此相關高、單獨又弱；欄位子集撞 08。
- TabPFN：oop 沒有 PyPI、GPU；同一組 41 欄，公式預測 < +0.00004。Ian 想試時先照 39 的試跑閘門。
- 法人視角集成：要 Ian 決定；2021 檢定力約 0。

### 抽查更正（收斂者和審查者查原文）

- Qlib：第 27 篇寫的 LightGBM 0.0475、TRA 0.0474 和現在的 README 不符，現在是 LightGBM 0.0448、TRA（全欄）IC 0.0440、Rank IC 0.0540。
- LambdaRankIC（arXiv 2605.00501）：實證是月頻美股 1964～2024、274.6 萬個股票月、94 個特徵，MSE 基準用原始報酬，單次樣本外、沒有檢定。
- arXiv 2510.14156：8 種損失 IC 0.0733～0.0767，MSE 0.0754 排第 7，Sharpe 最低，沒寫種子數、沒有檢定。
- TabPFN：「1 萬列上限」只是 v2，TabPFN-2.5（arXiv 2511.08667）目標 5 萬列。
- Cooper、Gutierrez、Hameed 2004：下跌狀態原文寫「不顯著」，−0.37% 只在二手摘要；`M-bold-gain-5` 誤寫成 Daniel–Moskowitz。
- Chen、Hanauer、Kalsbach（SSRN 5031755）：59%、1,056 個模型、不挑欄最好都只來自二手摘要。
- Hooker、Mentch、Zhou：arXiv 現在的標題是 Unrestricted Permutation forces Extrapolation…。
- 04-raw-feature-experiments.md 的 33「64 欄每段都用到」是錯的（2022 前兩段 61 欄），已更正。

### 未來方向（不在這一輪）

- 法人組上線：唯一有證據的一項（33：另外 50 檔每天 +0.00019，過了 Holm）。正式流程要補 18 個新欄和缺資料時退回 `X_price`；卡在 Ian「先不動」。
- 擴大訓練股票到全市場（MV4）：證交所、櫃買每天全部個股的開高低收量，用全市場訓練、只預測 100 檔。預期 +0.0001～+0.0003，不確定性大（35 的 `X_all` 多三倍天數就 +0.00012，p 0.037）；要改爬蟲；約 85 萬列時 kernel ridge 要改每週重訓或抽樣。
- 借券賣出和融資：從 FinMind 抓，預期 0～+0.0001；40 決定它的閘門怎麼用。
- 2020 年以前的歷史：回補 100 檔 2010～2019，預期 0～+0.00012；35 照 MV3 規則把窗長結案，要 Ian 決定重開。
