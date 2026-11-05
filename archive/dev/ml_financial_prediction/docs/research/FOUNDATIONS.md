# 林軒田《機器學習基石》研究筆記

本筆記服務課程台股盤中方向預測。正式競賽規則高於公開MOOC的一般方法；教師教材不被解讀為金融市場必可預測或iid假設成立的證明。

## 來源、方法與閱讀範圍

- 官方索引：https://www.csie.ntu.edu.tw/~htlin/mooc/ 。本輪只選索引直接連結的`01_handout.pdf`至`16_handout.pdf`，不猜本學期課程URL。
- 原PDF、MarkItDown Markdown、逐PDF頁文字與來源／轉換雜湊保存在`/workspace/shared/research/lectures/foundations/`，不加入Git。`catalog.json`保存實際取得版本；講義註記以**PDF檔案頁碼**為主，避免動畫答案重複頁造成slide編號與檔案頁不同。
- Microsoft MarkItDown0.1.9（plugins off、本地轉換時socket連線阻擋）提供閱讀Markdown；pdfplumber提供逐頁文字及可核對頁界。讀到的公式破碎與動畫重疊不自行補成「教師已證明」，load-bearing公式另核PDF／推導。
- 本檔採逐講義實際讀取後追加；完整閱讀狀態與hash清單在下方，沒有讀完的部分不標完成。

## 逐講義研究

### 01 — The Learning Problem

已讀PDF頁1–32，包含習題／答案重複頁。重點：學習是以資料改善指定performance measure（頁9），不是把accuracy當成所有問題的目標；資料、未知目標、假設集合與演算法的分工在頁22–25。頁9的金融例子只是使用情境，不保證投資增益。

本題落地：資料X限於截止前可知資訊；方向y、盤中報酬r與官方score分開；所有模型先用同一評分／日期股票全集。報告必須區分資料處理錯誤與模型假設不適合，而不是靠更大模型掩蓋前者。驗收實驗：同一預測表同時計算accuracy與score，找出兩者排名可不同的例子。

### 02 — Learning to Answer Yes/No

已讀PDF頁1–37。線性分類器／偏置向量表示在頁4–6；PLA修錯在頁10–11；收斂前提是線性可分（頁26–31），含噪資料需要不同策略，pocket保留訓練錯誤較少的權重（頁32–34）。動畫頁12–22的幾何文字抽取重疊，未將它當可讀的獨立證明。

本題落地：先採成熟套件的正則化線性基準，不假定股票方向線性可分，也不以訓練零錯誤為驗收。教師pocket是訓練錯誤概念，不能直接當作以同一validation反覆挑選無偏模型的許可。預測需輸出0/1，教材±1符號要有明確轉換；界線值及平價y=0需測試。

### 03 — Types of Learning

已讀PDF頁1–36。分類與回歸是不同輸出問題（頁3–8）；batch、online、active是不同資料交付協定（頁21–25）。online案例是先預測、收到真實label後才更新（頁23）；具物理語意、原始與抽象ID特徵的差異在頁28–33。

本題落地：每天自動重訓仍可採batch，不需要先導入強化學習或逐tick線上學習；當日未收盤label不能因「即時更新」而先進訓練。比較方向分類與盤中報酬回歸是有意改變學習目標；股票ID若加入需categorical編碼而非當可排序數字。海外指數return是具定義的輸入特徵，不代表全部股票需要同樣反應，可測產業交互作用。

### 04 — Feasibility of Learning

已讀PDF頁1–31。No Free Lunch說明僅靠訓練吻合不能保證未知樣本（頁5–6）；Hoeffding／PAC討論建立在獨立抽樣與固定候選的條件（頁10–18），多個候選需考慮選擇的代價（頁23–28）。頁21–22直接以投資規則說明：「未來市場行為類似過去」是必要的附加條件，不是獲利保證。

本題落地：不把50檔同日複製的市場向量當50個獨立市場樣本，金融日期也不直接套iid結論。需按日期的前後順序驗證，另報不同月份／市場狀態的表現；排行榜反覆試模型也是選擇程序。預先登記模型／參數比較，保留最近時段不反覆調參。此處的統計理論不能替缺乏歷史available_at的資料提供時間對齊證據。

### 05 — Training versus Testing

已讀PDF頁1–30。頁4將學習拆成「訓練誤差小」與「樣本外接近訓練」兩問；頁5說明候選集合大小的取捨；頁19–28以dichotomy、growth function與break point說明有效複雜度，不是只數無限多個實數權重。

本題落地：增加指數、交互作用、lag與模型容量都會增加選擇空間；不能把一次較高分視為穩定增益。固定小型候選特徵群，逐組消融並保存所有嘗試。模型參數數量不是金融有效樣本需求的精確公式，本研究不以VC界推稱特定資料量足夠。

### 06 — Theory of Generalization

已讀PDF頁1–37。break point限制growth function的組合證明在頁15–30；樣本外誤差以ghost sample替換、按dichotomy分組及Hoeffding步驟在頁31–35。頁36展示一般界可能很鬆，不能把它當緊的實務誤差估計。

本題落地：理論支持要限制資料驅動的選擇，但並未替非iid、跨日期漂移、跨股票關聯提供現成保證。主要驗證採時間外資料及逐月穩定性，若報不確定性應以日期群聚而非股票列獨立bootstrap。這裡只引用教材的思路與前提，不聲稱重新完成VC證明或得到投資保證。

### 07 — The VC Dimension

已讀PDF頁1–28。VC dimension定義為可shatter的最大樣本數（頁5）；d維線性分類器的d+1結果及線性依賴證明在頁10–17；複雜度與樣本量的解釋在頁18–26。頁25明列理論需求與實務經驗法則差距，頁26說明worst-case界很鬆。

本題落地：先用低容量線性／樹基準，再比較MLP／GRU；資料量應以日期與來源可用樣本衡量，而非拿複製市場特徵後的股票列數當成獨立N。不要把「N約10倍參數」寫成保證本題樣本足夠的門檻，也不要把深度模型名目參數量直接代入此線性VC例子。

### 08 — Noise and Error（直接影響官方score的重點）

已讀PDF頁1–26。含噪目標以P(y|x)表示（頁4–7）；不同pointwise loss導出不同ideal target，0/1對應最可能類別、平方誤差對應條件均值（頁9–14）。應用目標loss與便於最佳化的algorithmic loss明確分開（頁15–20）。加權分類與virtual copying／weighted pocket在頁21–24。

已視覺核對PDF頁21（原slide20/25）的成本矩陣、in/out-of-sample加權錯分公式；另保存頁12、24的渲染供核對。教師例子是CIA類別成本，**不是**教師已給出的金融return策略；以下是依本課公式所作的本專案推導。

令`r=(adj_close-adj_open)/adj_open`、`p∈{0,1}`、`y=1{r>0}`，則逐樣本恆等式為：

\[
|r|\mathbf1\{p\ne y\}=\frac{|r|-(2p-1)r}{2}.
\]

固定評估集合時，最小化以`|r|`加權的0/1錯分率等價最大化官方score；r=0時兩邊均0，不受平價方向慣例影響。又因`E[(2p−1)r|x]=(2p−1)E[r|x]`，理想二元決策為條件期望報酬正時預測1，負時預測0，零時兩者同分（本專案固定0）。

本題落地：比較普通方向分類、`sample_weight=abs(r)`分類及報酬平方誤差回歸後取符號；不能用class_weight=balanced冒充逐樣本收益權重。實作可在每個train fold把權重除以train平均，以固定正則化尺度；C等參數仍只在訓練內時間驗證選擇。加權logistic是替代loss、有限模型可能近似不足，不保證官方分數提高；剪掉大報酬／改Huber等另立消融，不能說仍與原score精確等價。當日r只可用於已完成歷史訓練或事後評分，不能進當日盤前feature。

### 09 — Linear Regression

已讀PDF頁1–24。平方誤差、矩陣梯度及解在頁6–11；頁11特別建議使用成熟的pseudo-inverse routine，而非在接近奇異時手算矩陣反矩陣。頁15–18的預期in/out誤差分析有ideal target落在假設空間等條件，不能無條件套進金融資料；回歸轉分類與替代loss在頁20–23。

本題落地：以成熟套件Ridge預測盤中return後取符號作基準，避免自行實作normal equation。平方誤差的理想解是條件均值，和第08講推導的理想決策方向一致；有限樣本、模型限制與正則化下仍須以官方score驗證。高度相關指數不靠矩陣反解硬撐；訓練內縮放及正則化優先。

### 10 — Logistic Regression

已讀PDF頁1–35。硬分類與機率預測的差異在頁3–6；sigmoid與likelihood／cross-entropy在頁7–18；凸梯度、迭代最佳化與步長影響在頁20–33（頁31示範不合適步長）。

本題落地：普通方向機率以0.5切分對應方向分類，並不直接估計期望報酬；以abs(r)加權的logistic另立候選。使用套件穩定solver、縮放與明確max_iter，記錄收斂警告及每日時間預算。機率供診斷，提交仍為0/1；若研究門檻偏移只能在訓練內時間驗證選擇，不能看測試結果後改門檻。

### 11 — Linear Models for Classification

已讀PDF頁1–40。頁3–11比較0/1、平方與cross-entropy替代loss；未縮放的自然對數cross-entropy並非逐點0/1上界（頁11答案），不要混寫。SGD的隨機梯度／計算與穩定性取捨在頁12–16；OVA／OVO在頁17–39，是多類別的拆解方法。

本題落地：二元任務先用普通成熟solver，不因「自動每天訓練」就需要SGD或多類別拆解。若未來資料量需partial_fit，先預測再等待真實label更新，保存scaler／模型版本與更新順序；隨機梯度在已合法取得的train fold內抽樣，不等於可把未來日期混入validation。權重替代loss的優化值也不能當官方score。

### 12 — Nonlinear Transformation

已讀PDF頁1–27。轉換後交給線性模型的步驟在頁10–13；feature transform可以是領域知識而非只有多項式（頁13）。計算、儲存與模型容量代價在頁16–18；頁19警告先看資料再選轉換也包含人為選擇複雜度；頁22–24建議先線性再增加容量。

本題落地：先預先定義return、lag、rolling volatility與少數產業×指數交互作用，分群消融，不一次展開全部高次多項式。transform的資料依賴部分（縮放、缺值統計、選特徵）只fit train；rolling視窗只含截止前已發布值。市場收盤時間、交易日與available_at是轉換前資料契約，不能由非線性模型補救。

### 13 — Hazard of Overfitting

已讀PDF頁1–27。頁3–4區別bad generalization與增加容量後樣本外惡化的overfitting；有限資料、隨機／deterministic noise與過高容量在頁8–19討論。資料清理／刪除、data hinting在頁22–24；教材明確提醒虛擬樣本未必遵守原資料分布。

本題落地：先修來源、重複列、價格調整與時間，再加模型容量。不能因某日大跌難預測就刪掉該日：大幅報酬恰可能主導官方score；真實行情極值與格式錯誤分開。金融資料不直接採圖片式旋轉／翻轉增強；合成樣本若無可辯護不變性，先不做。頁20–21的特定正弦練習未作獨立公式驗證，本研究不依賴該答案。

### 14 — Regularization

已讀PDF頁1–28。硬約束、軟約束與ridge在頁4–14；正交基底例子顯示特徵尺度與權重懲罰的關係（頁15）。教材的有效複雜度解釋在頁18–22，L1／L2與選λ在頁23–25。

本題落地：以Pipeline封裝train-only imputer／scaler／Ridge或LogisticRegression；L2作第一基準，L1選擇另作小規模比較。套件的alpha／C、loss是sum或mean、sample_weight規模會改變有效懲罰，保存完整設定，不能把課程λ直接當任意套件同名值。正則化也不能挽救未來資訊洩漏；參數仍只在過去的日期fold挑選。

### 15 — Validation

已讀PDF頁1–27。訓練分數選模型偏向高容量（頁5）；test與validation角色在頁6–13；LOOCV成本與V-fold在頁16–24。已視覺核對PDF頁10的train／validation分離圖、iid抽樣前提，以及頁24「validation仍較testing樂觀；報test結果」。

本題落地：不照搬教材iid情境的random K-fold。以完整日期分組、train早於validation，驗證日所有股票同側；inner時間fold選C／alpha等，outer時間段或封存最近時段報成績。若標籤橫跨多日，需按label完成時間移除跨界樣本；本題一日盤中label仍必須當日收盤後才可進train。挑定設定後可用截至執行時已完成label的全部歷史重fit，但不能以那個refit的in-sample成績冒充先前out-of-time成績。

### 16 — Three Learning Principles

已讀PDF頁1–30。Occam在頁3–8；sampling bias在頁9–15；頁12–13的推薦系統案例直接顯示random validation與預測後來紀錄的test不一致。data snooping在頁16–19，頁17貨幣交易例子顯示僅把train+test一起shift／scale就可製造誤導收益。已視覺核對頁17圖、時間切分及train-only scaling對照，不將圖中的收益數字轉作本題預期效果。

本題落地：資料處理、模型與人為選擇都算學習程序。截止前availability證據不足的外部歷史特徵不能靠「數值看來合理」進正式回測；來源後來修訂的數值需要vintage或適當保守規則。排行榜觀察／人工挑指數也是選擇，保存嘗試紀錄；資料、fold、特徵清單、訓練設定、預測與score皆版本化。比較固定歷史視窗與expanding window處理漂移，但先登記候選，勿以測試結果無限縮放視窗。

## 建議實驗與落地順序

下表是本研究建議，**不是已完成的模型成績**。各候選共享同一日期股票全集、同一合法feature快照、同一時間fold與官方score，另報accuracy及逐日score分布。

| 順序 | 資料／演算法 | 要回答的問題 | 限制 |
|---|---|---|---|
| 0 | 固定0、固定1、既有基準 | 模型是否勝過簡單方向基準？ | 必須同樣本評分 |
| 1 | 既有合法股票特徵＋L2 logistic | 標準方向分類基準 | 對accuracy合理，未直接優化return |
| 2 | 相同特徵＋abs(r)加權logistic | 對齊大幅報酬錯分成本是否改善score？ | 只用歷史label；只在train算權重尺度 |
| 3 | 相同特徵＋Ridge return回歸取符號 | 估計條件均值是否較合適？ | 小預測值附近符號不穩；不保證增益 |
| 4 | 分群新增指數return、lag、波動與產業交互作用 | 哪群資料提供時間外增益？ | 先完成point-in-time契約及可用率報告 |
| 5 | 固定小組樹模型／ensemble | 線性假設是否限制表現？ | 與前面共享時間驗證，控制搜尋預算 |

資料return需分清：label是官方定義的當日調整開收盤return；海外／市場指數feature是截止前最後兩個合法可得觀測的變動。不同交易日、假日、DST、期貨結算與現貨收盤不可只用同名日期join。宏觀發布資料若頻率低，附age／缺值／發布時間，不能把尚未發布數值回填到過去。

每日流程只把已通過時間驗證的設定重訓，不每天用當日未知label「驗證後挑最好」。預先設定缺來源、資料過舊、模型失敗與收據未確認的失敗條件，保留明確fallback版本與證據；排程存在不代表資料對齊或提交成功。

## 閱讀證據與可重現性

16份官方PDF共**495個實體PDF頁**的逐頁抽取文字皆已讀至EOF，包含習題及答案／動畫重複頁。這是文字完整閱讀，**不是**495頁全部圖形的逐頁視覺審閱，也未獨立重證全部理論。重疊動畫、純圖形與字型解碼仍有限制；本研究使用的核心成本公式／validation與snooping圖另視覺核對（08頁21；15頁10、24；16頁17）。

`catalog.json`及`reading_coverage.json`在上述Git外artifact根目錄，原PDF hash如下；每列連結為本輪已驗證出現在官方索引的來源。轉換Markdown與逐頁文字hash保存在每份manifest，方便確認之後讀到的是哪個版本。

| 講義來源 | PDF頁數／已讀 | SHA-256 |
|---|---:|---|
| [01](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/01_handout.pdf) | 32/32 | `92a475552bb030995dd6dd3540861b571e9f4694271b09250884b95d54790d5e` |
| [02](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/02_handout.pdf) | 37/37 | `45572ddbb2d9d3f9c45e45517cc4146fb9b15212d1e64230728dde8f461b5f30` |
| [03](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/03_handout.pdf) | 36/36 | `11bb0ffb5468b5dc1a63a9938075ae82caa3e5aeeeafb3f866107f6d0262c18e` |
| [04](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/04_handout.pdf) | 31/31 | `9ee8ac0539dd30e9f6deb11e1b4b3cb0152bb8d1e1f40887a66dacda3bbd04d6` |
| [05](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/05_handout.pdf) | 30/30 | `75908a419d9c30a6b918293a45bba21357d55a4d59d7c13d2555651a880793a9` |
| [06](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/06_handout.pdf) | 37/37 | `973b08ff5025995fa93f22afdfe764eddfba76490965295214926ef10e355530` |
| [07](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/07_handout.pdf) | 28/28 | `b6fac487addbd87fbdc7846887898d1b39ebb8f6dbda270aa0159ba10dd93ad9` |
| [08](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/08_handout.pdf) | 26/26 | `5eb185e2b7710fb0838a810237743f380358fc71bc024346147c87f6695c1be1` |
| [09](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/09_handout.pdf) | 24/24 | `0f49eb103b285bb570f058bc5366f2b74431b9bd46234682d197225a6ba4a17c` |
| [10](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/10_handout.pdf) | 35/35 | `724b488643002f3361eddf30f4835daefa62f8a6536ceb883a3b6911c64d6387` |
| [11](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/11_handout.pdf) | 40/40 | `f1c7af86f382129e907e8dd8cbc94b680f2020aeb9ee1f48e7a9b2d338e34401` |
| [12](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/12_handout.pdf) | 27/27 | `f0dc7b77b206406a537939e4f835aa6f82031dbda2ed43b5d937d7fee2c7f7f4` |
| [13](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/13_handout.pdf) | 27/27 | `3d2264cc45afce63abb8fc1855bcf5e05ac108d1d0b375faa60a057875c47c05` |
| [14](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/14_handout.pdf) | 28/28 | `6c72302d1fe030c34770b9b6ce6a0013c3464106cdd777259ee97b8e702d838d` |
| [15](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/15_handout.pdf) | 27/27 | `b3a468384f6b30a80c6a138fc0763de90b9086b008974c409d6a5961d84057f2` |
| [16](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/16_handout.pdf) | 30/30 | `141607c7e6964f7408f58eb8217c7142910fb22175202cd5976532dbad5d3329` |

重跑收集：`/workspace/.tools/markitdown/bin/python scripts/collect_lecture_corpus.py --course foundations --out-dir /workspace/shared/research/lectures/foundations`。此命令會重新取得官方版本並產生新manifest；既有閱讀紀錄只對應上述hash，內容更新後不能沿用「已讀」宣告。

工具方法來源：Microsoft MarkItDown，https://github.com/microsoft/markitdown （本機0.1.9、PDF extra、plugins停用）。本輪採用已安裝的MarkItDown skill協助本地轉換方法；依其引用要求記錄：Timothy Kassis, Vinayak Agarwal, Yuhuan He, Darshil Patel, Aubrey M. Brueckner, *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*, 2026，https://doi.org/10.48550/arXiv.2609.00065 。標題、作者及識別碼已核對arXiv原始頁面；此方法來源不作為本專案模型有效性的證據。

雜湊語意補充：收集器v1的`page_text_sha256`對應`pages.md`最後額外追加換行之前的UTF-8文字，不是`pages.json`或`pages.md`實體位元組雜湊。核對時用`pages.md`移除**最後一個**換行後計算；來源PDF的`source_sha256`則直接對應PDF實體位元組。既有manifest原值保留，避免改寫來源證據。
