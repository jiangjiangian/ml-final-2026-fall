# 林軒田《Machine Learning Techniques》研究紀錄

本檔對應公開MOOC的201–216講義，屬舊公開教材，不取代本學期final規則。原PDF與轉換物保存在checkout外；本檔只保留筆記、來源與查核證據。已完成16講共503頁的逐頁抽取文字閱讀；另抽查4頁原PDF公式圖像，覆蓋界線詳見下文。

## 研究問題與判準

本題每檔股票都要輸出0/1，主分數為 `mean((2*p-1)*r)`，其中 `r=(adj_close-adj_open)/adj_open`。研究要區分教材直接支持、套用到此題的推論、實驗後才知道的增益。

- 模型：線性／SVM／kernel、樹與boosting、神經網路、聚合；以一致日期切分比較。
- 目標：普通方向分類、絕對報酬加權分類、報酬回歸後取正負。
- 驗證：同日股票保持同fold；參數、scaler、imputer和特徵選擇只使用訓練資料。
- 資料與模型增益必須透過同股票／日期／版本的消融驗證；教材不證明任何市場特徵或投資策略一定有效。

## 官方來源

- 課程索引：https://www.csie.ntu.edu.tw/~htlin/mooc/
- 講義：https://www.csie.ntu.edu.tw/~htlin/mooc/doc/201_handout.pdf 至216_handout.pdf，以索引實際連結為準。
- 轉換工具：Microsoft MarkItDown 0.1.9；K-Dense markitdown skill固定版本及來源見repository內INSTALLATION.json。Markdown輔助搜尋，公式與圖像仍以PDF為準。

## 閱讀與驗證進度

16/16講取得、正常TLS下載、索引連結核對與雜湊留存完成；PDF共503頁（包含動畫重複頁），逐頁抽取文字`pages.md`共10,784行、257,232字元，已逐講讀至EOF。`catalog.json`保留取得當下的`converted_not_yet_read`；閱讀證據另見`reading_progress.json`與`coverage_summary.json`。

- 原PDF、MarkItDown完整`lecture.md`、pdfplumber逐頁文字`pages.md`／`pages.json`都在`/workspace/shared/research/lectures/techniques/`，不加入Git。實際全文閱讀的是有頁碼的`pages.md`，沒有聲稱讀完兩份轉換物每個字。
- 轉換為本地Microsoft MarkItDown0.1.9，plugins停用、socket連線封鎖；無LLM／OCR外送。503頁皆有頁碼區塊，PDF、Markdown和已讀文字雜湊核對通過。collector的`page_text_sha256`指`pages.md`追加最後一個換行前的payload，非`pages_path`所指的JSON實體檔案；閱讀紀錄另存實體Markdown雜湊，coverage另存JSON雜湊。
- 視覺抽查：205 PDF p.11 hinge／cross-entropy上界；206 p.10 epsilon-insensitive tube；211 p.22殘差擬合；212 p.18反傳鏈式法則。圖片留在上述目錄。**不是503頁逐像素審查**；其他圖和公式仍可能抽取缺損，未依賴未核對的複雜公式作實作保證。

下列頁碼指原PDF第幾頁；slide數指頁面右下角，兩者因動畫重複而不同。

### 201 — Linear Support Vector Machine

- 來源：PDF pp.15–19（slides11–15）、pp.29–32（slides23–26）；逐頁Markdown全文讀至EOF。
- 教材：幾何margin與縮放後的hard-margin QP；大margin是約束下的weight-decay觀點。
- 本題應用：可把正則化線性模型作低成本基準，feature scaling僅train fit；金融方向含噪，不要求hard-margin完全可分。
- 限制：教材margin的泛化直觀／界不能保證時間漂移金融資料上的報酬。

### 202 — Dual Support Vector Machine

- 來源：PDF pp.10–13（slides8–11）、p.18（slide15）、p.24（slide20）；逐頁Markdown全文讀至EOF。
- 教材：KKT連結primal與dual；dual由N個變數表達，教材提醒N=30000的dense kernel matrix已超過3GB。
- 本題應用：大樣本先採成熟線性／樹實作；kernel候選須記錄記憶體與訓練時間，避免每日重訓超時。
- 限制：不自行寫QP；強對偶說明有凸性、可行性及線性約束等條件，不套到一般神經網路。

### 203 — Kernel Support Vector Machine

- 來源：PDF p.6（slide5）、p.12（slide10）、pp.18–24（slides15–20）；逐頁Markdown全文讀至EOF。
- 教材：Kernel是transform內積捷徑；線性較快，Gaussian較強但仍可overfit，需選γ。
- 本題應用：先跑線性與樹基準；若加入kernel，使用train-only scaling與內層時間驗證選C／γ，記錄kernel成本。
- 限制：教材一般CV不可直接照搬為同日股票隨機CV；金融驗證需依日期隔離。

### 204 — Soft-Margin Support Vector Machine

- 來源：PDF pp.5–6（slides4–5）、p.17（slide14）、pp.21–24（slides17–20）；逐頁Markdown全文讀至EOF。
- 教材：Slack表示margin違反；C平衡margin與違反；SVM可overfit，參數透過validation選擇，SV數只是LOOCV上界的粗檢查。
- 本題應用：金融標籤有噪，採soft-margin／正則化，不追求training0錯誤；超參數只能在較早日期fold選。
- 限制：LOOCV與#SV的教材關係不是本題跨時間無洩漏證明，不能用nSV代替官方score回測。

### 205 — Kernel Logistic Regression

- 來源：PDF pp.4–6（slides3–5）、p.11（slide8，已視覺核對）、pp.16–17（slides12–13）、p.21（slide16）；逐頁Markdown全文讀至EOF。
- 教材：Hinge與scaled cross-entropy是0/1錯誤的凸上界；正則化LogReg與SVM相連。Platt兩層學習是校準score，不是直接把SVM輸出當真機率。
- 本題應用：普通logistic是基準；以abs(return)作sample_weight另成候選，仍需按官方score選模；校準與stacking用時間有效OOF。
- 限制：替代損失最小不保證有限樣本官方score最大；L2 representer條件不能套到任意非凸模型。

### 206 — Support Vector Regression

- 來源：PDF pp.5–6（slides4–5）、pp.10–14（slides8–12）、p.19（slide16）；p.10 tube公式已視覺核對；逐頁Markdown全文讀至EOF。
- 教材：Kernel ridge為regularized squared loss但dense解成本高；SVR使用epsilon-insensitive tube loss，較不受outlier影響並可產生稀疏解。
- 本題應用：用成熟Ridge／樹回歸直接預測盤中return，再取正負作另一個score導向候選；SVR僅在時間驗證與成本允許時補測。
- 限制：平方誤差和tube誤差都不是官方score；穩健損失或截尾會改變報酬幅度的影響，需預先註冊並驗證。

### 207 — Blending and Bagging

- 來源：PDF pp.11–12（slides9–10）、pp.17–18（slides14–15）、p.24（slide20）；逐頁Markdown全文讀至EOF。
- 教材：Uniform平均在平方誤差下有分解；blending／stacking用heldoutvalidation上的base預測，bootstrapping提供多樣性。
- 本題應用：若融合，用時間有效OOF預測學權重，與各base模型同fold比較；估計不確定性以日期為單位重抽樣。
- 限制：教材i.i.d. bootstrap與平方損失結果不保證金融score；p.19歷史競賽test-setblending案例不能當成反覆調Phase1榜單的許可。

### 208 — Adaptive Boosting

- 來源：PDF p.13（slide10）、pp.20–22（slides16–18）、p.25（slide20）；逐頁Markdown全文讀至EOF。
- 教材：例子加權學習可用SVM變動上界或weighted LogReg；AdaBoost依錯分動態改權重，弱學習假設要求每輪加權錯誤率優於1/2。
- 本題應用：abs(return)是由評分導出的固定樣本重要度，與AdaBoost依難例動態調權重分開比較；可測加權線性／樹作早期基準。
- 限制：AdaBoost訓練錯誤的理論不能保證時間外報酬；不能因大報酬樣本難就無限放大噪音，調參僅內層時間驗證。

### 209 — Decision Tree

- 來源：PDF pp.9–12（slides7–10）、p.17（slide14）、p.19（slide16）；逐頁文字Markdown全文讀至EOF。
- 教材：C&RT以impurity分支、常數葉作分類或回歸；fully-grown可能overfit，需剪枝／validation；缺值surrogate branch在訓練期建立。
- 本題應用：樹可學指數、個股與市場狀態交互作用；限制depth、leaves、min_samples_leaf；缺值處理依所選套件實際能力，保留missing／age。
- 限制：不假設每個樹套件都實作教材surrogate；feature importance不代表因果，分類impurity也不等於官方score。

### 210 — Random Forest

- 來源：PDF pp.4–6（slides3–5）、pp.10–12（slides8–10）、pp.17–18（slides14–15）、p.42（slide20）；逐頁文字Markdown全文讀至EOF。
- 教材：RF把bootstrap與隨機子特徵的樹聚合；OOB為未抽中的樣本評估，permutation比較打亂特徵前後表現；樹數需要考慮seed穩定性。
- 本題應用：RF可作非線性基準；特徵群組消融在較晚日期驗證集做；記錄多個seed與訓練成本，不任選幸運樹數。
- 限制：普通OOB會使用未來日期訓練樹，不能代替本題時間驗證；相關指數的permutation重要度不應解讀為獨立或因果貢獻。

### 211 — Gradient Boosted Decision Tree

- 來源：PDF pp.20–24（slides14–18）、pp.27–30（slides20–23）；p.22殘差公式已視覺核對；逐頁文字Markdown全文讀至EOF。
- 教材：Gradient boosting可換損失；平方損失下逐輪擬合殘差，之後決定聚合步長；RF、AdaBoost-DTree、GBDT使用不同多樣性來源。
- 本題應用：優先用成熟GBDT套件，分別測普通分類、abs(return)加權分類、return回歸；限制樹複雜度、learning rate與輪數，early stopping只用內層較晚日期。
- 限制：教材演算法是原理，不證明現代套件特定設定最佳；替代損失下降不保證官方score提高；不自行重寫boosting。

### 212 — Neural Network

- 來源：PDF pp.10–13（slides8–11）、pp.17–19（slides14–16）、pp.22–25（slides18–21）；p.18反傳鏈式公式已視覺核對；逐頁文字Markdown全文讀至EOF。
- 教材：MLP逐層學非線性轉換，backprop高效計算梯度；非凸優化對初始化敏感，weight decay與validation early stopping控制過擬合。
- 本題應用：小型MLP為第三種辨識度明確候選：train-only scaler／imputer、固定seed、weight decay、時間驗證early stopping，與線性／樹同fold。
- 限制：教材使用tanh與平方誤差示範，不能據此宣稱SGD必達全域最小或深網勝過表格樹模型。

### 213 — Deep Learning

- 來源：PDF pp.4–7（slides3–6）、pp.17–19（slides14–16）、pp.22–26（slides18–22）；逐頁文字Markdown全文讀至EOF。
- 教材：深層結構帶來計算、初始化與正則化挑戰；autoencoder重建輸入，denoising加入人工噪音；PCA以保留變異作線性降維。
- 本題應用：若指數高度共線，可把train-only PCA作消融；只有在資料量、序列品質與成本足夠時才擴展深模型。
- 限制：這是舊MOOC的pre-training框架，非現代ML必經流程；重建或高變異不保證保留預測return訊號；本講未教授GRU。

### 214 — Radial Basis Function Network

- 來源：PDF pp.11–13（slides9–11）、pp.16–20（slides13–17）、pp.36–41（slides20–23）；逐頁文字Markdown全文讀至EOF。
- 教材：RBF以對prototype的距離形成特徵；full RBF可精確插值但有過擬合風險；k-means交替更新分群與中心，中心數和正則化影響複雜度。
- 本題應用：可把過去市場狀態的prototype距離作次要候選；中心與scaler只能以訓練日期fit，新增特徵仍以消融決定保留。
- 限制：距離相似不是經濟機制；k-means對尺度、k與初始化敏感；先完成四種核心pipeline，不把全RBF插值當作泛化成功。

### 215 — Matrix Factorization

- 來源：PDF pp.4–6（slides3–5）、pp.9–13（slides7–11）、pp.17–19（slides14–16）、p.24（slide20）；逐頁文字Markdown全文讀至EOF。
- 教材：以低秩共享表徵建模user–movie矩陣；已知項平方損失，可用ALS／SGD；教材時間排序案例明示train／test mismatch需依任務處理。
- 本題應用：股票ID是類別而非連續數值，可先one-hot或適當embedding；歷史多股票共享因子列為後續研究，與時間外泛化一起驗證。
- 限制：不可把未來日期×股票return矩陣補齊後回填成當時特徵；推薦系統低秩假設不直接證明金融因子有效。

### 216 — Finale

- 來源：PDF pp.9–15（slides7–12）、pp.18–22（slides14–18）；逐頁文字Markdown全文讀至EOF。
- 教材：課程統整特徵開發、優化、正則化與誠實validation；競賽案例結合domain features與不同模型，重點是適當融合避免過擬合。
- 本題應用：以可重現資料與時間驗證為骨架；先單模型、再特徵消融、最後以時間有效OOF融合，保留訓練與推論截止成本。
- 限制：歷史冠軍或2006熱門演算法列表不是2026工具排名；多放模型／特徵不等於提高本題score。

## return-ratio的直接決策方向（本專案推導）

以下依專案官方score定義自行推導，並非聲稱MOOC提供金融報酬定理。設`p ∈ {0,1}`、`q=2p-1`、`r=(adj_close-adj_open)/adj_open`、`y=1[r>0]`，則每一列（包含r=0）：

```text
|r| · 1[p ≠ y] = (|r| - q·r) / 2
score = mean(q·r)
      = mean(|r|) - 2·mean(|r| · 1[p ≠ y])
```

因此，在**同一股票全集、同一批日期與同一列權重**上，最大化官方score與最小化絕對報酬加權的0/1錯誤完全等價。「錯一筆大波動」比「錯一筆小波動」代價更高。教材208 p.13支持樣本加權的實作觀念；205支持LogReg替代損失，並沒有直接證明金融樣本上能改善score。

| 方向 | 實際候選 | 對score的意義與限制 |
| --- | --- | --- |
| 分類基準 | 普通Logistic／GBDT分類 | 衡量只學漲跌的基準，accuracy高不等於score高 |
| 成本加權分類 | sample_weight=abs(r)的分類損失 | 加權0/1精確對應；加權cross-entropy是可優化替代，有限模型與樣本仍需驗證 |
| 報酬回歸 | Ridge／GBDT平方損失回歸r，輸出1[predicted_r>0] | 理想平方風險估計條件平均；期望score的相應決策取條件平均正負，估計誤差與分布漂移仍在 |
| 序列／融合 | 小型GRU；時間有效OOF融合 | 學歷史序列或多模型互補，增益必須實驗；GRU不在這16講範圍內 |

不以accuracy、AUC、MSE或校準分數代替官方score；它們只供診斷。Huber、SVR、截尾return、class_weight、時間衰減都會改變學習目標或樣本重要度，另立候選、記錄理由與消融，不能冒稱與原評分精確等價。每日期或每股票各自正規化abs(r)權重也會改變原目標。

## 實驗與資料處理的落地順序（proposed）

1. **先固定可用時間與資料版本**：指數在原生交易日算return，再依available_at對齊盤前；殖利率用bp差、signed OI用差分；保留50檔與missing／age，目標return只在labels。這是專案資料合約，不是MOOC查證結果。
2. **固定共同walk-forward日期fold**：同日50檔不拆fold。內層選參數，外層只報分；scaler、imputer、PCA、選特徵與權重規則均在訓練期決定。保留最後一段未選模日期；大量比較候選須報告比較次數與日期分數穩定性。
3. **四種pipeline同條件比較**：正則化線性→GBDT→小型MLP→GRU。先普通／加權分類或return回歸的少量預先列明設定；序列模型依窗口、缺值與成本實作。成熟sklearn／樹套件／PyTorch優先，不重寫solver。
4. **分離資料與演算法增益**：固定模型比較教師資料→加額外指數→加return／diff／age，再固定資料比較模型。報官方score、逐日期分數、seed、時間／記憶體與輸出完整度；日期為單位的依賴感知不確定性估計須標明假設。
5. **最後才融合與每日運作**：以時間有效OOF學融合權重，與最強單模型同fold比較；每日候選訓練設deadline與相容舊模型fallback。研究報告不代表訓練、排程、提交已部署。

## 可重現來源清單

官方索引與PDF於2026-10-29 UTC取得；完整SHA256、工具版本、轉換與閱讀雜湊在checkout外manifest中。下表列來源、PDF頁數與來源hash前16碼；正常TLS與官方索引連結檢查由共用collector執行。

| 講義 | 官方PDF | PDF頁數 | SHA256前16碼 |
| --- | --- | ---: | --- |
| 201 | [201_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/201_handout.pdf) | 35 | `74717a1c69ee58b3` |
| 202 | [202_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/202_handout.pdf) | 28 | `2b1d6ea59a599798` |
| 203 | [203_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/203_handout.pdf) | 27 | `52599890d576de49` |
| 204 | [204_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/204_handout.pdf) | 27 | `5fe9d392bfc13be0` |
| 205 | [205_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/205_handout.pdf) | 26 | `28987d438ba50d44` |
| 206 | [206_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/206_handout.pdf) | 28 | `f4ae238872d96999` |
| 207 | [207_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/207_handout.pdf) | 28 | `b2debd38777551e7` |
| 208 | [208_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/208_handout.pdf) | 37 | `350744752c5bd73f` |
| 209 | [209_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/209_handout.pdf) | 37 | `b81f841293db93fd` |
| 210 | [210_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/210_handout.pdf) | 45 | `a53e92df8928605f` |
| 211 | [211_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/211_handout.pdf) | 33 | `03be6c706c8b4882` |
| 212 | [212_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/212_handout.pdf) | 28 | `432aabddf6aeaff9` |
| 213 | [213_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/213_handout.pdf) | 29 | `2a18a13669687c66` |
| 214 | [214_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/214_handout.pdf) | 42 | `c64eb85eb7e7114d` |
| 215 | [215_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/215_handout.pdf) | 27 | `bac05225d8e9b17a` |
| 216 | [216_handout.pdf](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/216_handout.pdf) | 26 | `59881adfb349130c` |

工具來源：[Microsoft MarkItDown](https://github.com/microsoft/markitdown)；技能來源：[K-Dense markitdown](https://github.com/K-Dense-AI/claude-scientific-skills/tree/main/scientific-skills/markitdown)。本地固定版本與安裝記錄見上層`.agents/skills/markitdown/INSTALLATION.json`。工具／技能是閱讀輔助，不提供其他ChatGPT Project內容的存取權。
