# 台股大模型遷移：先凍結主幹，再談暴力美學

2026-11-28 使用者用 `/deep-research` 問：RP 40 這類用遷移學習微調時序大模型的做法合不合理、要多少資料、input 要什麼樣式、符不符合老師的題目、兩種 shift（Kronos 預訓練的市場到台股、台股自己隨時間漂移）怎麼處理。他想用「暴力美學」（超大模型、超多資料），也要查李宏毅的 Transfer Learning、Domain Adaptation 課程和對抗式學習。做法：四條研究線（李宏毅課程、時序基礎模型在金融的實證、跨市場和漂移的領域適應、大模型大資料在低雜訊預測的正反證據）各一個 agent；再用 workflow 讓 6 個 agent 回原始來源核對關鍵數字，1 個寫報告，2 個審稿，1 個修稿。原始筆記和核對檔在 session 的 scratchpad，會被系統清掉，這份檔是唯一的紀錄。RP 40 的狀態截至 2026-11-28 晚上的狀態檔；RP 40 的判法以 `memory/projects/22-ml-research-pipeline.md` 的「`RP 40` 事先登記」為準，這份只是建議。

RP 40 把 Kronos 當 c2v2d 排名集成的第四個成員來檢驗是合理的，把它當成能穩定打敗 c2v2d 的主力則沒有證據。最強的反證是 Rahimikia 等人：他們在美股 1.3122 億筆股票日上完整微調通用 TSFM（時間序列基礎模型，先在大量序列上預訓練的大模型），毛（不扣成本）等權十分位多空 Sharpe（平均報酬除以波動）只有 −3.31～0.07，最好的 Chronos-Large 252 天視窗是 0.07，同視窗的 CatBoost（梯度提升樹）是 6.72（[Rahimikia et al. v2](https://arxiv.org/pdf/2511.18578v2)）。下一步照已登記的 RP 40 走：驗證期的 S1 關卡沒過就停，過了才在 40f 開一次測試期；本報告多出的比較要在讀 40c full 的輸出之前補登記，不然只報告。RP 40 的模型還沒有結果，資料（40a、40b）和速度（40s）已經有，40c full 在排隊（截至 11-28 晚上的狀態檔）。

## 合不合理：設計大致對，期待太高

### 設計上做對和要改的地方

| 設計 | 判斷 | 根據 |
|---|---|---|
| 按日期切，測試期 2025-07-01～2026-11-20 | 對 | Kronos 預訓練資料到 2024 年 6 月，論文的測試從 2024 年 7 月開始（[Kronos 論文](https://arxiv.org/html/2508.02739v1)）。權重 2025-06-30 才上傳到 Hugging Face（[NeoQuasar/Kronos-small](https://huggingface.co/NeoQuasar/Kronos-small)），所以驗證期 2024-07～2025-06 可能不乾淨，只有測試期能公平比較 |
| 從頭訓練的 PatchTransformer 對照組（`twfm` 的 `PatchTransformerBackbone`，吃對數報酬） | 對，而且必要 | 在 Rahimikia 的研究裡，從頭用金融資料預訓練的小模型大幅縮小了差距：美股 Chronos-small 在 252、512 天視窗的毛 Sharpe 是 4.89、5.42，CatBoost 是 6.72、6.39 |
| 先 `head`（`LP`：主幹凍結，只訓練接在主幹後面的頭），再 `last_k`（放開最後 2 層），最後 `lora`（LoRA：主幹不動，只訓練插進去的小矩陣） | 對 | 李宏毅：「最好的後訓練就是不要後訓練」「不到沒有辦法的時候不輕易使用」（[2025 Fall Post.pdf p16](https://speech.ee.ntu.edu.tw/~hylee/GenAI-ML/2025-fall-course-data/Post.pdf#page=16)）。套件另有 ridge（加 L2 懲罰的線性迴歸）閉式解的 `--probe`，RP 40 的登記沒有用它 |
| 還原價格水準，每個視窗 z-score 後裁在 ±5 | 對 | 和 Kronos 的推論程式一樣（[model/kronos.py](https://github.com/shiyu-coder/Kronos/blob/master/model/kronos.py)） |
| tokenizer（把 K 棒切成代碼的前處理模型）從頭到尾凍結 | 可以，但偏離官方範例 | 官方微調範例先用學習率 2e-4 微調 tokenizer，再凍結它、微調預測器（[finetune/config.py](https://github.com/shiyu-coder/Kronos/blob/master/finetune/config.py)）。團隊的理由（重訓 tokenizer 會讓預測器對不上 token）說得通，只是沒測過 |
| 協變量（K 棒以外的輸入，例如法人、美股）進 FiLM head（用協變量去乘、加主幹的特徵） | 只能這樣 | Kronos 只吃 OHLCV（開高低收和成交量）、成交金額和時間戳，沒有協變量入口（[Kronos README](https://github.com/shiyu-coder/Kronos)） |
| 損失 Huber（大誤差只線性懲罰的損失）+ 0.2 × IC（預測分數和實際報酬的相關），用每天 RankIC 選模型 | 對 | RankIC 是每天把預測分數和實際報酬各自排名後算的相關。Rahimikia：「Improved squared-error performance need not improve the selection of stocks entering the extreme forecast deciles.」 |
| 股票池是每年前 500 檔 | 訓練可以，評估不行 | 推論：美股大型股收盤到收盤每天幾乎不可預測（Rahimikia 的大型股結果，見「符不符合老師的題目」），台股 50 檔大型股可能也一樣。最後的判斷要只算 50 檔：登記的 S1 增量和 H1 都用 50 檔的官方分數；`--competition-stocks` 只改比賽分數，50 檔的 RankIC 要從 `predictions_*.csv` 篩出來重算 |
| LoRA 那階的學習率 | 已改（2e-4） | 套件 README 寫預設沿用 4e-5、淺層只剩約 8e-6，LoRA 幾乎不會動，建議改成 1e-4～5e-4。登記和 40d 用學習率 2e-4、r 8、α 16 |

### 期待太高的地方

微調通用 TSFM 在日報酬上沒有成功過。Rahimikia v2 在美股 1990～2022 共 1.3122 億筆上完整微調 Chronos 和 TimesFM，所有參數都可訓練，超參數照開發者的建議，每年擴張視窗重訓。毛多空 Sharpe 落在 −3.31～0.07。最好的是 Chronos-Large 的 252 天視窗，年化報酬 0.23%、Sharpe 0.07；同視窗 CatBoost 是 46.27%、6.72（[Rahimikia et al. v2](https://arxiv.org/pdf/2511.18578v2)）。這篇沒有測 Kronos。

Kronos 自己的論文沒有任何微調實驗，摘要說結果是 zero-shot（不用目標資料訓練就直接預測）（[Kronos 論文](https://arxiv.org/html/2508.02739v1)）。另外兩份報告方向一致。issue #355 用 Kronos-mini 跑 30 分 K，微調穩定降低 token loss（預測下一個代碼的損失），交易結果沒有穩定變好（[issue #355](https://github.com/shiyu-coder/Kronos/issues/355)）。一份預先登記的指數期貨研究裡，Kronos-small 在 NQ（Nasdaq 100 的 E-mini 期貨）的盤中預測上微調後比 zero-shot 更差，誤差是 no-change（預測價格不變）的 1.99 倍，zero-shot 是 1.72 倍（[Upadhyay, arXiv 2611.12141](https://arxiv.org/pdf/2611.12141v1)）。

Kronos zero-shot 的橫斷面訊號很弱。issue #375 在 182 檔美股、2024-07-01～2026-07-07 測試，每 6 天換股、預測 12 天、用收盤價進出，共 85 次換股。Kronos-small 的平均 IC 是 +0.0220（Newey-West t 1.39，這是考慮自我相關的 t 值），5 日反轉因子（過去 5 天跌最多的猜漲）是 +0.0316（t 1.97）。扣掉四個常見因子後只剩 +0.0134（t 1.33）。最好的 5 天貢獻了 91% 的毛損益。這是一位使用者個人的報告，沒有同儕審查，也沒有公開程式（[issue #375](https://github.com/shiyu-coder/Kronos/issues/375)）。另一份個人報告用 Kronos-small 跑 12 檔的日 K（約 2022～2026，每檔約 150 次往前預測）。兩次都是 0/12 檔顯著（p < 0.05）贏過最好的固定方向基準，0/12 檔的 RMSE 贏隨機漫步，0/12 檔有顯著 IC；作者寫明沒有事先登記（[Akiesel1/Honest-Forecast-Eval](https://github.com/Akiesel1/Honest-Forecast-Eval)）。

Kronos 論文裡台股（XTAI）的報酬 RankIC 是 0.0597、0.0584、0.0609（small、base、large）。論文在每個資產類別、每個頻率把所有樣本混在一起算，再對所有測試頻率平均（9 個頻率有 8 個是盤中），算的是多步報酬的相關。論文沒有日 K 單獨的數字，和每天 50 檔的橫斷面 RankIC 不能比。XTAI 的 IC 上，從頭訓練的 DLinear（0.0514）還略高於 Kronos-L（0.0511）（[Kronos 論文 Table 16](https://arxiv.org/html/2508.02739v1)）。

推論：RP 40 要過的是增量的門檻。Kronos 在 RP 40 是 c2v2d 排名集成的第四個成員，單獨的 IC 不必比 c2v2d 高。登記的 S1 要第四成員在驗證期 50 檔每天多 +0.00009 以上，H1 在 340 天的最小可偵測差約每天 +0.000156～+0.000187（`memory/projects/22-ml-research-pipeline.md` 的「`RP 40` 事先登記」）。第四成員要的是和現有三個成員相關低的訊號，和 `X_price` 重疊的部分平均進去不會加分。

c2v2d 本身的水準只當背景。c2v2d 在測試期 340 天的毛分數平均每天 0.150%，只留排名集成、拿掉 β（個股跟著大盤漲跌的幅度）傾斜的 `B4_x_price_25` 是 0.117%（RP 36 的 `daily_rp36.csv`，2025-07-01～2026-11-20，本報告重算）。推論：25 漲 25 跌時，每天分數約等於 0.8 × IC × σ_cs，σ_cs 是當天 50 檔開盤到收盤報酬的橫斷面標準差。σ_cs 是 1.5%～2.0% 時，0.150% 對應每天 IC 約 0.09～0.125，0.117% 對應約 0.07～0.10。c2v2d 含依大盤方向換高低 β 的傾斜，在大盤大漲大跌的日子會經由橫斷面那一半拿分，所以 0.09～0.125 不全是選股能力。上面公開的 Kronos 數字都比這低，但期數都不同：issue #375 每 6 天換股、預測 12 天，論文是混合多步、對多個頻率平均。σ_cs 要用實際量到的值重算。建議直接從 c2v2d 回測算每天 50 檔的 RankIC，再算只留排名集成的版本，當 Kronos 的參考。

團隊自己的前例也要算進事前期待。RP 35 的小 1D-CNN 輸 `X_price`（每天 −0.000355，t −2.62），照登記淘汰小型深度學習。累計閘門 `SPA_c`（對以前所有候選做的多重比較校正）從 RP 30 的 p 0.0796（93 個候選）到 RP 36 的 0.0943（109 個候選），沒有候選過關（`memory/projects/22-ml-research-pipeline.md`）。推論：PatchTransformer 和 c2v2d 加 Kronos 的事前期待要照這個打折。登記也寫了事前預期最可能是「分不出」。

## 需要多少資料：瓶頸是交易日數

列數已經夠微調了，交易日數不夠判斷誰比較好。

| 資料 | 交易日 | 列數（股票日或視窗） |
|---|---|---|
| Kronos 預訓練（[Table 13](https://arxiv.org/html/2508.02739v1)） | 不適用 | 121.1 億根 K 棒，96,569 檔資產 |
| Rahimikia 美股微調（2022 年的模型） | 1990～2022，推論：約 8,300 天 | 1.3122 億 |
| Kronos 官方微調範例（CSI300，2011～2022） | 推論：約 2,900 天 | 推論：約 87 萬 |
| RP 40 訓練期（標籤 2004-01-02～2024-06-30，前 500 檔） | 約 5,040 天（登記的數字） | 2,427,993 個訓練視窗（RP 40b full v6 實測） |
| RP 40 驗證期（2024-07-01～2025-06-30） | 241 天 | 50 檔是 12,050 |
| RP 40 測試期（2025-07-01～2026-11-20） | 340 天 | 50 檔是 17,000 |
| 老師的資料（2020 起） | 到 2026-11 約 1,672 天 | 50 檔約 8.4 萬 |

驗證期、測試期和老師資料的交易日數是用團隊特徵表 `data/processed/features/` 的日期數出來的。

推論：微調的量夠了。RP 40 的 2,427,993 個訓練視窗是 Kronos 官方範例的約 2.8 倍，訓練 24.7M 參數模型的最後 2 層綽綽有餘。Rahimikia 的資料再多約 54 倍，微調還是失敗，所以瓶頸在目標函數和領域。

李宏毅把「目標有大量標註」和「少量有標註」分開處理（[LeeDL §13.2](https://github.com/datawhalechina/leedl-tutorial/releases/download/v1.2.4/LeeDL_Tutorial_v.1.2.4.pdf#page=229)）。推論：台股按列數算是大量，按資訊量算是少量，因為每天漲跌的訊號極弱。所以要用「少量」那格的做法：跑兩三個 epoch、學習率調小、參數不要離預訓練太遠。RP 40 登記的每階最多 2 個 epoch 符合這個做法。

### 推論：量出差距要多少天

假設每天獨立、近似常態。50 檔每天的 RankIC 在沒有訊號時，標準差至少約 1/√49 ≈ 0.14。股票之間有相關，實際更大，所以這些數字是樂觀的下限。

單一模型要和 0 分開：

| 期間 | 天數 | 平均 RankIC 的標準誤 | t = 2 要的平均 RankIC | t = 3 要的平均 RankIC |
|---|---|---|---|---|
| 驗證期 | 241 | 0.0090 | 0.018 | 0.027 |
| 測試期 | 340 | 0.0076 | 0.015 | 0.023 |
| 2020 起 | 1,672 | 0.0034 | 0.0068 | 0.010 |

兩個模型比大小時，看的是每天 RankIC 差的標準差。兩個模型每天 IC 的相關越高，越容易分出來。t = 2 要的天數：

| RankIC 差距 | 每天 IC 相關 0.8 | 每天 IC 相關 0.5 |
|---|---|---|
| 0.02 | 約 80 天 | 約 200 天 |
| 0.01 | 約 310 天 | 約 780 天 |
| 0.0053（Kronos 論文 small 換 large 的混合多步報酬 RankIC 差，和每天橫斷面 RankIC 是不同指標，只當量級參考） | 約 1,100 天 | 約 2,800 天 |

所以每天 IC 相關 0.8 時，340 天的測試期約分得出 RankIC 差 0.01；相關 0.5 時要約 0.015 以上。這些都是樂觀的下限。換成分數，差 0.01 約等於每天 0.012%～0.016%（σ_cs 1.5%～2.0%），是 c2v2d 毛分數的十分之一左右。論文裡 small 換 large 的差距用的是不同指標，不能直接換算成台股要多少天。

大盤方向那一半更難。一天只有一筆，猜對率的標準誤是 0.5/√天數：340 天是 2.7 個百分點，1,672 天是 1.2 個百分點，1998 年起約 7,000 天是 0.6 個百分點。要用 t = 2 分出 52% 和 50%，約要 2,500 天；分出 51% 要約 10,000 天。股票再多也沒用，因為 50 檔共用同一個大盤。

試越多組越容易靠運氣過關。沒有訊號時，K 個獨立候選裡最好的 t 期望約 2.5（K = 100）和 3.2（K = 1,000），上界是 √(2 ln K)；候選互相相關時更低。這和 Harvey、Liu、Zhu 要求新因子 t 超過 3.0 的門檻量級相近（[NBER w20592](https://nber.org/papers/w20592)）。累計閘門現在有 109 個候選（RP 36、37），RP 40 只把驗證期挑出的單一候選 `FT` 加進去；40f 的窗變短後，候選數照實寫。

## input 樣式：主幹只吃 K 棒，其他都進 head

### Kronos 要的和 RP 40 給的

| 項目 | Kronos 預期 | RP 40 現在 | 判斷 |
|---|---|---|---|
| 欄位 | open、high、low、close、volume、amount 共 6 欄；沒有量時補 0（[kronos.py](https://github.com/shiyu-coder/Kronos/blob/master/model/kronos.py)） | 還原 OHLCV 加成交金額 | 一致 |
| 標準化 | 每個視窗、每一欄用自己的平均和標準差 z-score，再裁在 ±5 | 視窗 z-score 裁 ±5，等於 `RevIN(affine=False)`（RevIN：每個視窗自己標準化、輸出再還原，這裡不帶可學的縮放） | 一致。官方 `finetune/`（Qlib 範例）在 2026-04-11 的 [commit 79d6d403](https://github.com/shiyu-coder/Kronos/commit/79d6d403d8999de4aea8b388ca10905c8bf3de33) 之前用了視窗加預測期的統計量，等於偷看未來，現在改成只用視窗。另一支 `finetune_csv/` 還用回看加預測期正規化（issue #227、#228 沒修，`memory/projects/22-ml-research-pipeline.md`） |
| 時間戳 | minute、hour、weekday、day、month 五個嵌入 | `stamps` 是 `[0, 0, weekday, day, month]`，`use_time_stamp` 預設開（`src/twfm/data/dataset.py`） | 一致 |
| 長度 | 上限 512 根；論文日 K 評估用 lookback 40、horizon 12（[issue #375](https://github.com/shiyu-coder/Kronos/issues/375) 引 Table 8）；官方範例 90、10 | L 從 64、128 選（`head` 階段選一個，之後固定），到 i 為止 | 可以。Rahimikia 發現 TSFM 比較會用長視窗。推論：256 根是便宜的對照，要做就補登記 |
| 頻率 | 預訓練至少約 97% 是盤中 K 棒（依 [Table 13](https://arxiv.org/html/2508.02739v1) 推算，日 K 加週 K 最多約 3.0%） | 日 K | 這是第一種 shift 的大頭（見下面） |
| 協變量 | 沒有入口 | FiLM head | 只能這樣 |
| 輸出 | 自己的生成頭，取樣出價格路徑 | 取最後一根的隱藏狀態給 head，不用 `dep_layer` | 對。Kronos 的取樣區間太窄，90% 區間只蓋到 58% 的實際結果（[issue #375](https://github.com/shiyu-coder/Kronos/issues/375)）；套件 README 也發現 `dep_layer` 在 eval 時不是因果的 |

### 什麼資訊放哪裡

| 資訊 | 放哪裡 | 理由 |
|---|---|---|
| 個股自己 i 日以前的 K 棒 | Kronos 主幹 | 主幹預訓練只看過 K 棒 |
| 個股 i 日的法人、融資、beta、漲跌停連續天數、自己的落後報酬 | head，和主幹輸出串接（`stock_cov` 28 欄） | 主幹沒有入口；每檔不同，可以直接改排名 |
| 美股隔夜 SOX、Nasdaq，台股 i 日普通股的等權報酬和漲跌停比例 | head 的 FiLM（`market_cov` 11 欄） | 同一天每檔都一樣，直接相加只會整體平移、排名不變，用乘的才會依個股特性改排名 |
| 加權指數或台指期的 K 棒 | 推論：可以當另一條 Kronos 序列，embedding 進 FiLM | 沒有找到證據，排在後面 |
| t 當天的任何價、量、法人、跳空 | 哪裡都不能放 | 專案規則；只能進 `label_` 和 `exec_` 開頭的欄 |
| 新聞和公告文字 | 另一個模型（LLM）讀，結果進 head | 對開盤到收盤沒有證據，見「建議的做法」最後一段 |

要讓協變量進主幹，只能換模型。Chronos-2 原生支援過去和已知未來的協變量，也能跨序列學，預訓練資料沒有提到金融（[amazon/chronos-2](https://huggingface.co/amazon/chronos-2)）。TimesFM 2.5 透過 XReg（外加的迴歸模組）支援協變量（[timesfm GitHub](https://github.com/google-research/timesfm)）。

目標和評估：`target_z` 是每天 z-score 後的開盤到收盤報酬，比賽照原始報酬算分。用每天 RankIC 選模型對準的是分數裡的橫斷面那一半。報告時另外算 50 檔、25 漲 25 跌的比賽毛分數。Rahimikia 裡 zero-shot Toto 的 R² 是 −110.78%，美股毛多空 Sharpe 卻有 6.10（CatBoost 6.39），所以點預測差的模型也可能排得好，只看 MSE（均方誤差）會選錯。

## 符不符合老師的題目：只碰得到分數的一半

### 目標和資訊時點

比賽要在 t 日 09:00 前預測 t 日「還原收盤 ÷ 還原開盤 − 1」的正負。所有找得到的 TSFM 研究都沒測過這個目標。Rahimikia 的目標是下一天的超額報酬，等於收盤到收盤，非美國股票用美元計、扣美國無風險利率（[v2 Section 3.1、4.2](https://arxiv.org/pdf/2511.18578v2)）。Kronos 測的是從最後一根收盤往後 H 步的報酬，日 K 是 12 步（[Kronos 論文 Appendix D](https://arxiv.org/html/2508.02739v1)）。

主幹只看得到 i 日收盤以前的 K 棒。i 日 13:30 收盤到 t 日 09:00 之間的事，包括美股整個交易時段、16:30 的法人、21:30 的融資、隔夜新聞，主幹都看不到，只能從 head 進來。推論：主幹能貢獻的，只有從過去 K 棒找出的型態。c2v2d 的排名集成本來就用價量特徵（`X_price`），所以 Kronos 要贏，只能靠把同一份歷史抽得更好。

### 分數拆解

每天的分數 = 橫斷面那一半（哪些股票贏過當天 50 檔的等權平均 m）+ 大盤那一半（猜漲的淨檔數乘上 m）。每天 25 漲 25 跌時，大盤那一半剛好抵銷。2026-11-16 的 m 是 −4.58%，全猜 0 拿 +0.0458，40 隊並列第一。c2v2d 在測試期每天平均 0.150% 的優勢都在橫斷面那一半，是那一天的三十分之一。

推論：Kronos 當成每檔一個分數的排名模型，只能改善橫斷面那一半，碰不到像 11-16 那種大盤日。拿大模型去猜大盤也沒有證據支持。Decider 和 MT 用團隊的特徵，結論是開盤前猜不到大盤方向（`memory/projects/07-decider-market-direction.md`、`memory/projects/09-market-timing.md`）。Upadhyay 的研究裡，Kronos-small 在 NQ 指數期貨上的日訊號在盲測集複製成功（IC +0.116，單尾 p = 0.015）。它在 NQ 的盲測集過不了交易條件，賺得比一直做多和隨機方向的 95 百分位都少，NQ 保留期也消失。保留期是事後的，ES（S&P 500 的 E-mini 期貨）那格兩個門檻都過了，作者只報告、沒有主張（[arXiv 2611.12141 Section 5.4](https://arxiv.org/pdf/2611.12141v1)）。

### 股票池

比賽是 50 檔大型股，RP 40 用前 500 檔訓練。Rahimikia 在美股把股票照市值分組：市值前 25% 的大型股，CatBoost 的猜對率平均約 50.80%，毛多空 Sharpe 是 −0.15、−0.15、0.29、0.16（5、21、252、512 天視窗）；從頭用金融資料預訓練的 Chronos-small 在 252、512 天視窗是 0.56、0.82（[v2 Table 5、6](https://arxiv.org/pdf/2511.18578v2)）。全體股票的 CatBoost 毛 Sharpe 是 5.70～6.72，作者認為高 Sharpe 集中在小型股，但沒有拆解、也說市值分組看不出機制。推論：前 500 檔的平均 RankIC 會高估 50 檔的表現，結論只能用 50 檔的結果下。比賽分數加 `--competition-stocks` 就好；套件的 IC 仍然用整個股票池，50 檔的 RankIC 要從 `predictions_val.csv`、`predictions_test.csv` 篩出 50 檔重算。`FT_SMALL`（老師 `info.json` 的 `Top100@Y`，2020 起）比較接近題目，但只有約 1,672 天。

### 交易成本不算分

比賽分數沒有交易成本。套件 README 寫「當沖來回成本在手續費 2.8 折時約 0.23%」，也寫「扣掉真實交易成本後，比賽式的每天多空分數很可能是負的」。這是給真實交易的，和比賽無關。過關標準用 50 檔的毛分數。

### 外部資料和預訓練權重

團隊記錄的課程網站規則裡，沒有禁止外部資料或預訓練模型的條文，也沒找到明文允許。團隊已經在用 yfinance、期交所和交易所資料。用 Kronos 權重前要問助教。上線預測 2026-11 以後的日子時，權重最晚到 2025-06-30（上傳日），不會偷看未來。

### 每天上線

推論：每天交件跑在 oop，Kronos-small 對 50 個視窗做一次前向計算，CPU 也只要幾秒。要先解決的有四件，登記的「上線要先解決的事」都寫了，H1 過了、經 Ian 同意才做：

- 資料：個股協變量是在前 500 檔的股票池裡轉成常態分數，市場協變量（`tw_up_frac_i` 等）要用全市場普通股算，oop 現在只有老師的 100 檔。上線要每天抓兩個市場的全部行情、法人、融資，是正式爬蟲的改動。
- 時間：美股 K 棒台北約 05:00 才收。所以主幹的表示在 t − 1 的 20:00 先算好存檔，頭在 t 的 07:10 讀檔、加上美股、法人、融資再跑。
- 環境：oop 沒有 PyPI，torch 和權重要離線裝。N1 影子跑已經用另一個 `.venv-n1` 子程序，登記寫另開 `.venv-ft`。
- 重現：oop 和 Kaggle 每天名次的 Spearman ≥ 0.9999，0/1 一樣的格子 ≥ 99%。

## 兩種 shift 各自怎麼處理

### 第一種：預訓練的市場到台股

Kronos 沒有只用美股預訓練。它的 121.1 億根 K 棒來自 45 個交易所：美國 Nasdaq 加 NYSE 占 38.1%，上海加深圳占 30.7%（[Table 13](https://arxiv.org/html/2508.02739v1)，比例是查證時依表格算的）。證交所那一列是 1,252 檔、7,162 萬根，從 2020-01-31 開始，沒有 1 分 K；表裡沒有櫃買中心。論文一邊把台灣、印尼、馬來西亞列為「out-of-distribution」（沒看過的市場），一邊又把三國列在預訓練資料表裡，沒說有沒有拿掉。可以確定的只有：台股掛牌的日 K 在 2020 年以前沒看過，2020～2024-06 不確定。推論：台積電、聯電、日月光、中華電的美國 ADR（在美國掛牌的存託憑證）在 NYSE 交易，價格和台股本尊高度連動。Table 13 的 NYSE 那列從 2000 年起收股票，這些 ADR 可能看過。

推論：這個 shift 有三層。第一層是頻率，預訓練至少約 97% 是盤中 K 棒，我們餵日 K。第二層是任務，預訓練是預測下一根 K 棒的 token，我們要的是 t 日開盤到收盤的名次。第三層才是國家。前兩層可能比美國到台灣更大。

跨市場的研究分兩種結果。Choi、Jiang、Zhang 預測的是下個月的報酬，數字來自 2023 年草稿，台灣的測試期是 2012～2017。他們比較美國訓練和各市場自己訓練的神經網路：自己訓練的平均多 0.69～0.77 的等權 Sharpe、0.40～0.52 的市值加權 Sharpe，31 個市場裡 74%～87% 變好（[2023 ABFER 草稿](https://www.abfer.org/media/abfer-events-2023/annual-conference/papers-investment/AC23P3084-Alpha-Go-Everywhere-Machine-Learning-and-International-Stock-Returns.pdf)）。台灣是最弱的市場之一。台灣自己訓練的神經網路，最好的市值加權 Sharpe 只有 0.24，在 32 個市場裡最低。台灣自己訓練的最好模型是隨機森林（等權 1.08、市值加權 0.70），市值加權上連大盤本身的 1.09 都贏不了。Hellum、Pedersen、Rønn-Nielsen 則發現一個共同的全球模型比各國自己的模型好，就算沒用到當地資料也一樣，參數「94% global」（[AQR 工作論文](https://www.aqr.com/insights/research/working-paper/how-global-is-predictability)）。這篇只讀到摘要，頻率、期間和有沒有台灣都沒讀到全文。推論：兩篇測的事不同。直接搬過去不調整會輸；把很多市場一起訓練、再往當地小幅修正會贏。

Rahimikia 的台股表只有從頭預訓練的模型，沒有和現成或微調的模型比。Chronos-small 在 512 天視窗贏全球資料訓練的 CatBoost（1.15）：只用全球報酬 1.30，加 JKP 特徵（Jensen、Kelly、Pedersen 整理的公司特徵）序列一起預訓練 1.88，加合成資料 1.37，R² 卻都是負的。252 天視窗的 CatBoost 是 1.59，只有加 JKP 的版本（1.77）贏它。TimesFM-20M 多半輸：252、512 天視窗下，只用全球報酬 −0.42、−0.58，加 JKP 1.13、1.16，加合成資料 0.85、0.96（[v2 Table 10](https://arxiv.org/pdf/2511.18578v2)）。JKP 特徵在這裡是另外的單變量預訓練序列，沒有當成協變量。這是收盤到收盤、以美元計的超額報酬，股票池很廣，作者也說台灣「remains only weakly predictable for CatBoost」。Chronos-small 三種版本都贏，所以看不出 JKP 特徵本身的效果。推論：這說明金融原生的小模型在台股排得出名次。PatchTransformer 是只用台股的監督式版本，比 Rahimikia 的設定弱，當對照組仍有意義。

照成本排的做法（前兩項和 LoRA 已在 RP 40 登記，繼續預訓練沒有）：

- 凍結 probe：layer transfer（複製預訓練的部分層，只訓練其餘的層）最極端的版本，主幹不動、只訓練後面的頭。RP 40 的 `LP`（`head` 階段）就是這個。
- 最後 2 層小學習率、少跑幾輪：LeeDL 整理的說法是跑兩三個回合、調小學習率（[LeeDL §13.2](https://github.com/datawhalechina/leedl-tutorial/releases/download/v1.2.4/LeeDL_Tutorial_v.1.2.4.pdf#page=229)）。RP 40 的 `last_k` 每階最多 2 個 epoch、學習率 4e-5。
- conservative training（微調時要求新參數不要離預訓練參數太遠）：在損失加 Σ λ(θ − θ⁰)²（[Post.pdf p44](https://speech.ee.ntu.edu.tw/~hylee/GenAI-ML/2025-fall-course-data/Post.pdf#page=44)；[transfer (v3) p7](http://speech.ee.ntu.edu.tw/~tlkagk/courses/ML_2016/Lecture/transfer%20(v3).pdf#page=7)）。LoRA 是限制改動範圍的另一種寫法，RP 40 登記的是 LoRA。
- 在台股日 K 上繼續預訓練：用 Kronos 自己「預測下一根 K 棒」的目標，在證交所加櫃買 2005～2024-06 的日 K 上多跑一段，再接監督式的 head。這對準頻率和市場那兩層，證據很弱。Fu、Hirano、Imajo 把 TimesFM 在約 9,000 萬～1 億個價格點上繼續預訓練，Sharpe 在每個市場都贏原版，但作者自己承認沒有穩定贏過 AR(1)（只用前一期的自我迴歸）：S&P 500 是 1.68 對 1.58，外匯是 0.25 對 0.88（[arXiv 2412.09880](https://arxiv.org/pdf/2412.09880)）。這些模擬交易沒算成本、市場中性，S&P 500 的 1.68 是 128 天期，Sharpe 也沒有顯著性檢定。Upadhyay 測的是 NQ 盤中 5～120 分鐘的誤差比：從頭訓練 Kronos 1.10，在 NQ 上微調 Kronos-small 1.99，zero-shot 1.72，都輸 no-change。推論：最多試一次，要另開一條線、另外登記。

便宜的診斷（推論，不用訓練）：用凍結的 Kronos 算台股日 K 每年的下一根 token 損失，分三段比：

- 2005～2019：台股掛牌的 K 棒沒看過，美國 ADR 可能看過。
- 2020-01～2024-06：可能看過。
- 2024-07～2025-06：論文說沒看過，但權重 2025-06-30 才公開，不確定。

每年的損失也會隨波動高低變，比較時要控制波動，例如看損失對實現波動迴歸後的殘差。控制後 2020～2024-06 仍明顯偏低，才表示台股可能在預訓練裡，驗證期對 Kronos 的優勢要打折。2025-07-01 以後是測試期：登記的 S3 規定測試以前的 notebook 不讀這段的標籤，這段 K 棒的開盤、收盤就是標籤的來源。要看這段，只能放進 40f、只報告。

DANN（domain-adversarial training，讓特徵分不出來自哪個市場）不適合這裡。它的前提是目標市場沒有答案，台股每天都有答案（見「對抗式學習的三種意思和適不適用」）。

### 第二種：台股自己隨時間漂移

這是 concept drift（同樣的特徵在不同時期對應不同的漲跌）。李宏毅的領域適應課只處理輸入分布改變。LeeDL 把「輸入跟輸出……之間的關係變了」這種稱為比較罕見，不在範圍內（LeeDL 原文為簡體；[LeeDL §13.1](https://github.com/datawhalechina/leedl-tutorial/releases/download/v1.2.4/LeeDL_Tutorial_v.1.2.4.pdf#page=228)；[da_v6 p3](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/da_v6.pdf#page=3)）。對得上的是終身學習那堂：模型上線、收到回饋、拿新資料更新（[life_v2 p4](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/life_v2.pdf#page=4)）。他說把全部資料一起訓練是終身學習的上限（[p11](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/life_v2.pdf#page=11)）。

團隊自己的結果和文獻一致。DR 01 發現漂移存在，但沒有事前訊號能預測分數變差（`memory/projects/16-concept-drift.md`）。CT 01～05 發現訓練期越短越差（`memory/projects/14-c2-tuning.md`）。DA 01 的 DoubleAdapt 沒贏單純重訓（`memory/projects/15-doubleadapt.md`）。文獻裡 DoubleAdapt 比滾動重訓多的 IC 是 +0.0004～+0.0067。這是依 Table 1 算的差，作者沒有寫，而且是作者自己的單一切分（2017～2020 中國 A 股）（[DoubleAdapt v3 Table 1](https://arxiv.org/pdf/2306.09862v3)）。Qlib 的 CSI300 表裡，TRA 的 IR（超額報酬除以它的波動）比 GRU（一種循環神經網路）高約 0.3（1.28 對 0.97），AdaRNN（1.02）和 GRU 差不多。這些都只是一個市場、一段 2017～2020 測試期的結果，沒有獨立重現（[Qlib benchmarks](https://github.com/microsoft/qlib/blob/main/examples/benchmarks/README.md)）。

推論：找得到的兩份比賽解法都顯示，用新揭曉的答案定期更新模型有幫助。Jane Street 2024～25 第 8 名的 GRU，每個 `date_id` 拿新揭曉的答案用學習率 0.0003 更新一次，CV（交叉驗證分數）從 0.0112 升到 0.0190（+0.0078）；她的表裡兩列設定只差這一項。集成和多種子只多 +0.0001～+0.0010（[Grigoreva 解法](https://www.kaggle.com/competitions/jane-street-real-time-market-data-forecasting/writeups/evgeniia-grigoreva-private-lb-8th-solution)）。Optiver 第 1 名每 12 天重訓一次，私榜 MAE（平均絕對誤差）從 5.4438 降到 5.4030（[hyd 解法](https://www.kaggle.com/competitions/optiver-trading-at-the-close/writeups/hyd-1st-place-solution)）。

具體做法：

- 尺度漂移：每個視窗自己 z-score 已經處理掉價格水準和波動的變化。
- 重訓時保留全部歷史：對應李宏毅的「全部一起訓練是上限」和 experience replay（混入約 5% 舊資料就夠）（[post_training p29](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2025-course-data/post_training.pdf#page=29)）。CT 的結果也支持長視窗。
- 每天或每週更新 head：Kronos 過關後，在影子跑比較「每週用擴張視窗重訓 head」和「每天用前一天的答案、小學習率更新一次」。
- 不要做：跨時期的 DANN，和用 MSE 評估的測試時調整（TAFAS 這類，[arXiv 2501.04970](https://arxiv.org/html/2501.04970v1)）。

## 暴力美學的證據：加參數沒有用，加資訊要看目標

| 證據 | 方向 | 離我們的題目多遠 |
|---|---|---|
| Edwards et al.：時間序列 transformer 在五個數量級內，損失隨參數、資料、算力呈冪律下降（[arXiv 2405.13867](https://arxiv.org/abs/2405.13867)） | 支持 | 遠。摘要沒提金融資料，量的是預測損失 |
| Kronos small、base、large 的平均報酬 RankIC（混合多步）0.0622、0.0634、0.0675；Kronos-base 在 CSI300、CSI800 回測的超額報酬和 IR 都贏所有對照（[Table 10、16](https://arxiv.org/html/2508.02739v1)） | 小幅支持 | 中。作者自己的基準，對照沒有 GBDT（梯度提升樹，像 LightGBM、CatBoost）。台股 IC 隨模型變大下降（0.0549、0.0524、0.0511），RankIC 沒有一致方向（0.0597、0.0584、0.0609） |
| Kronos-small 在 CSI 回測贏 4 項裡的 3 項，只輸 CSI800 的 IR（1.6050 對 zero-shot TimesFM 的 1.6427） | 小幅支持 | 中。差距很小 |
| Rahimikia：zero-shot 結果不一致。長視窗通常比較好，模型變大不一定比較好：Chronos 以 R² 計最好的是 Mini，TimesFM 2（500M）各視窗多空報酬都是負的。從頭預訓練加資料增強後，512 天視窗的毛 Sharpe 超過 CatBoost（TimesFM-20M 加 JKP 7.62、Chronos-small 加合成資料 6.72，CatBoost 6.39） | 支持「金融原生的預訓練目標加資料增強」。合成資料的效果和真實 JKP 差不多，增益不全來自金融內容 | 中。超過 CatBoost 的都是 ≤ 46M 的小模型；作者結論是「the pre-training domain matters alongside model size」 |
| Kelly、Malamud、Zhou「virtue of complexity」：上萬個隨機特徵、12 個月訓練，擇時 Sharpe 多 0.47（[JF 2024](https://economics.yale.edu/sites/default/files/2024-01/The%20Journal%20of%20Finance%20-%202023%20-%20KELLY%20-%20The%20Virtue%20of%20Complexity%20in%20Return%20Prediction%20%281%29.pdf)） | 支持，但被反駁 | 遠。月資料、大盤擇時、靠 ridge 收縮 |
| Chen、Kelly、Xiu：LLM 讀新聞，2004～2019 樣本外每天五分位等權多空 Sharpe：ChatGPT 4.60、LLaMA3 4.12、BERT 2.99、Word2vec 2.51、SESTM（字詞方法）3.32；市值加權 1.35、0.77、0.66、0.65、0.77（[作者 2025 年 4 月投影片](https://dachxiu.chicagobooth.edu/download/news_2025.pdf)，2026 年 2 月的論文版數字可能不同） | 支持 | 中。加的是新資訊；作者寫「Complexity in LLM models enhances predictive performance up to a certain point」。推論：報酬是每天的組合報酬，含隔夜跳空 |
| Lopez-Lira、Tang：GPT-4 讀新聞標題的預測力隨模型變大增加（[arXiv 2304.07619](https://arxiv.org/abs/2304.07619)） | 支持 | 中。後續漂移的可預測性集中在小型股和壞消息；越多人用 LLM，策略報酬越低 |
| Rahimikia：1.3122 億筆完整微調，毛 Sharpe −3.31～0.07；比較小的金融原生模型贏過大很多的現成模型；全球資料一起訓練讓 CatBoost 在每個視窗都變差；日資料上把 MLP 加寬，結果不單調 | 反對 | 近。日報酬；現成和微調模型的結果只有美股 |
| Nagel：virtue of complexity 的預測其實是波動擇時的動能策略（[NBER w34104](https://www.nber.org/papers/w34104)）。Fallahgoul：常見實作的樣本內標準化改變了核近似（用隨機特徵近似核函數）；在 12,000 個特徵、12 個月視窗、R² 2～3% 的設定下，要逃出資訊下限得有 25～30 年以上的資料（[arXiv 2506.03780](https://arxiv.org/abs/2506.03780)）。Guo et al.：ridge 和 ridgeless（懲罰趨近 0 的 ridge）都贏不了歷史平均，特徵置中後預測力消失（[arXiv 2608.23761](https://arxiv.org/abs/2608.23761)） | 反對 | 中 |
| Gu、Kelly、Xiu：神經網路三層最好（月 R² 0.40%），四、五層沒有更好（[RFS 2020](https://dachxiu.chicagobooth.edu/download/ML.pdf)） | 反對 | 中 |
| 比賽前段解法：Optiver 第 1 名的集成裡有 GRU 和 Transformer（權重 0.3、0.2），作者寫更大的 transformer（「larger transformer, e.g. deberta」）沒用；Jane Street 第 8 名寫 MLP、時間序列 transformer、跨股票注意力都沒用；Ubiquant 第 1 名是 LightGBM 加 TabNet（[解法](https://www.kaggle.com/competitions/ubiquant-market-prediction/writeups/k-i-y-1st-place-solution-our-betting-strategy)）；G-Research 第 2 名是單一 LightGBM（[解法](https://www.kaggle.com/competitions/g-research-crypto-forecasting/writeups/nathaniel-maddux-2nd-place-solution)）；Numerai 的基準模型都是 LightGBM（[Numerai docs](https://docs.numer.ai/numerai-tournament/models)） | 反對 | 近 |
| 李宏毅：大模型微調時沒有比較不忘（1B～7B）（[post_training p18](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2025-course-data/post_training.pdf#page=18)）；有些任務中模型反而最差（[LargeLM-v7 p10～11](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2023-course-data/LargeLM-v7.pdf#page=11)）；算力固定時小模型配大資料贏過大模型配小資料（[p29](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2023-course-data/LargeLM-v7.pdf#page=29)） | 反對「只加參數」 | 遠。語言模型 |

推論：規模在兩種情況下有證據。一是帶來新資訊，像 LLM 讀新聞；但正面的證據都是每天或收盤到收盤的報酬，對開盤到收盤沒有證據（見「建議的做法」最後一段）。二是在金融報酬上從頭預訓練、再加資料增強（合成資料也有效，像正則化）。用更多參數重新讀同一份日 K，在日頻、大型股、方向這三個條件同時成立時，找不到支持的證據。

算力是限制。RP 40s 在 Kaggle T4 上用假資料實測（600 檔、700 天，股票池 500 檔，視窗 128 根，fp16；`memory/projects/22-ml-research-pipeline.md` 的「`RP 40s` 結果」）：

| 設定 | 每秒視窗 | 每天檔數 | 每 epoch（5,040 天） |
|---|---|---|---|
| `head`（主幹凍結） | 678 | 500 | 1.0 小時 |
| `last_k`（最後 2 層） | 265 | 128 | 0.7 小時 |
| `lora` | 139 | 128 | 1.3 小時 |
| `all`（全部微調） | 183 | 128 | 1.0 小時 |

訓練主幹時套件每天只抽 128 檔，所以 `last_k` 一個 epoch 比 `head` 短。換算整個 RP 40 是 T4 約 22～32 小時。Kaggle 一週只有 30 小時，登記的 S2 上限是 Kaggle T4 45 小時加 Colab A100 15 小時，所以要跨週，或把一部分放 Colab A100（狀態檔的安排是 40e 的 `SC` 和種子 1、2；`SC` 是隨機初始化的 Kronos-small 對照）。

## 李宏毅課程怎麼說

### 來源

沒有拿到 YouTube 逐字稿。用的是李宏毅投影片的原文（pdftotext 抽出、逐頁核對），口述內容來自 [LeeDL 教程 v1.2.4](https://github.com/datawhalechina/leedl-tutorial/releases/download/v1.2.4/LeeDL_Tutorial_v.1.2.4.pdf)（Datawhale 依上課錄音整理的簡體中文教材，不是逐字稿）。影片：[領域適應 2021](https://youtu.be/Mnk_oUrgppM)、[舊的遷移學習](https://youtu.be/qD6iD4TFsdQ)、[終身學習](https://youtu.be/rWF9sg5w6Zk)、[後訓練與遺忘 2025](https://youtu.be/Z6b5-77EfGk)、[對抗攻擊 2021](https://youtu.be/xGQKhbjrFRk)。沒找到他談股市預測可不可行。股市只在 2016、2017 迴歸投影片當成「明天的道瓊指數」的例子出現（[Regression ML 2016 p2](http://speech.ee.ntu.edu.tw/~tlkagk/courses/ML_2016/Lecture/Regression%20(v6).pdf#page=2)；[Regression ML 2017](http://speech.ee.ntu.edu.tw/~tlkagk/courses/ML_2017/Lecture/Regression.pdf)）。

### 他的「情況對方法」表，對到這個專案

這張表合併兩份投影片。2021 年的 da_v6 依目標資料多寡和有沒有標註分；2016 年的 transfer (v3) p36 依來源和目標有沒有標註分。推論：用 2016 年的表，Kronos 對台股是 self-taught learning（來源沒標註、目標有標註）那格；用 2021 年的表，按資訊量算是「少量有標註」。兩格都指向預訓練再小步微調。

| 他的情況 | 他給的方法 | 出處 | 對到我們 | 判斷 |
|---|---|---|---|---|
| 目標有大量標註 | 直接用目標資料訓練，不用做領域適應 | [LeeDL §13.2](https://github.com/datawhalechina/leedl-tutorial/releases/download/v1.2.4/LeeDL_Tutorial_v.1.2.4.pdf#page=229) | 台股 2004 年起每天都有答案 | 列數算大量。c2v2d 每天早上重訓就是這格 |
| 目標少量有標註 | 用來源模型初始化再微調；跑兩三個 epoch、學習率小、參數不要差很多；conservative training；layer transfer，資料夠才整個網路微調 | [da_v6 p4](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/da_v6.pdf#page=4)；[transfer (v3) p7、p8](http://speech.ee.ntu.edu.tw/~tlkagk/courses/ML_2016/Lecture/transfer%20(v3).pdf#page=8)；LeeDL §13.2 | 台股的有效資訊很少 | RP 40 的 `head`、`last_k`、`lora` 都在這格；登記每階最多 2 個 epoch，符合少跑幾輪 |
| 來源沒標註、目標有標註 | self-taught learning | [transfer (v3) p36](http://speech.ee.ntu.edu.tw/~tlkagk/courses/ML_2016/Lecture/transfer%20(v3).pdf#page=36)；[bert_v8 p14](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/bert_v8.pdf#page=14) | Kronos 用「預測下一根 K 棒」預訓練，對我們的 y 等於沒標註 | 推論：Kronos 對台股是這一格。現代的對應做法是自督導預訓練再微調（bert_v8 p14 的框架），李宏毅沒有把兩者等同 |
| 目標大量沒標註 | domain adversarial training | [da_v6 p5～8](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/da_v6.pdf#page=7) | 台股有答案 | 前提不成立 |
| 目標很少又沒標註 | testing time training（測試時用沒標註的資料調整模型） | [da_v6 p13](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/da_v6.pdf#page=13) | 開盤前只有當天 50 檔、沒有答案 | 推論：答案收盤就到，用有答案的更新比較好 |
| 對目標一無所知 | domain generalization：訓練資料含多個 domain，或用資料增強造出來 | [da_v6 p15](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/da_v6.pdf#page=15)；LeeDL §13.3 | 未來的市場狀態 | 部分適用：用很多時期一起訓練 |
| 輸入和輸出的關係變了 | 這堂課不處理 | [LeeDL §13.1](https://github.com/datawhalechina/leedl-tutorial/releases/download/v1.2.4/LeeDL_Tutorial_v.1.2.4.pdf#page=228)；[da_v6 p3](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/da_v6.pdf#page=3) | 第二種 shift | 要去終身學習那堂找 |
| 上線後收到回饋再更新 | 全部資料一起訓練是上限；EWC 類正則化（重要參數少動）；experience replay | [life_v2 p4、p11、p19～20](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/life_v2.pdf#page=20)；[post_training p29](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2025-course-data/post_training.pdf#page=29) | 每天收盤拿到新答案 | 每天用全部歷史重訓，就是那個上限的近似 |
| 訓練和測試的分布不同（mismatch） | 「Simply increasing the training data will not help.」 | [overfit-v6 p28](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/overfit-v6.pdf#page=28)；觀看人次例子在 [p26](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/overfit-v6.pdf#page=26)；[LeeDL §2.5](https://github.com/datawhalechina/leedl-tutorial/releases/download/v1.2.4/LeeDL_Tutorial_v.1.2.4.pdf#page=38) | 預訓練資料再多，也不保證對台股的未來有用 | 直接適用 |

p28 是通用的 mismatch 投影片，圖是 HW11 的照片對手繪；觀看人次的表（2017～2020 訓練、2021 測試）在 p26，LeeDL §2.5 用一個假設的「2020 訓練、2021 測試」把兩者連起來。

### 對 RP 40 最有用的幾頁

- 先不要動參數：「最好的後訓練就是不要後訓練」，先考慮後訓練以外的替代方案（[Post.pdf p16～17](https://speech.ee.ntu.edu.tw/~hylee/GenAI-ML/2025-fall-course-data/Post.pdf#page=16)）。對到 RP 40，就是先看 `head` 階段（`LP`）。
- LoRA 可能學不到：LoRA「範圍太小可能會無法達成 Reliability 和 Generality」，接著放「LoRA Learns Less and Forgets Less」（[Post.pdf p41～42](https://speech.ee.ntu.edu.tw/~hylee/GenAI-ML/2025-fall-course-data/Post.pdf#page=41)）。推論：LoRA 比最後 2 層差時，可能是學不到；看訓練期和驗證期的差距才分得出來。
- 參數不要離太遠：R(θ) = Σ λj (θj − θj⁰)²，λ 大就微調前後變化小（[Post.pdf p44](https://speech.ee.ntu.edu.tw/~hylee/GenAI-ML/2025-fall-course-data/Post.pdf#page=44)）。
- 微調強化已知、難學新技能：「在 Alignment 階段往往 LLM 只是強化原來已經知道的事情，難以學習新技能」（[pretrain.pdf p62](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2025-course-data/pretrain.pdf#page=62)）。這頁講的是語言模型的對齊階段。推論：Kronos 預訓練時沒學到的日頻開盤到收盤規律，靠小的 adapter 不容易長出來。
- 忘掉美股不是問題：遷移學習「We don't care whether machine can still do task 1」（[life_v2 p13](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/life_v2.pdf#page=13)）。遺忘只在當成正則化、防止對雜訊資料過擬合時有用。
- 不要用公開榜挑模型：「You are making public set better than private set.」（[overfit-v6 p21～24](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/overfit-v6.pdf#page=23)）。對到這裡，就是測試期只開一次，也不拿 Phase 2 的線上成績挑模型。
- 元學習要很多任務：MAML（學一組容易微調的初始參數）「Isn't it domain adaptation / transfer learning?」，而且訓練任務少會對訓練任務過擬合（[meta_v3 p31、p37](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/meta_v3.pdf#page=37)）。推論：股市能切出的獨立時期不多，和 DA 01 的結果一致。

## 對抗式學習的三種意思和適不適用

| 意思 | 對手 | 目的 | 李宏毅出處 | 金融上的證據 | 適不適用 |
|---|---|---|---|---|---|
| domain-adversarial training（DANN） | 分辨資料來自哪個 domain 的分類器 | 讓兩個 domain 的特徵分不出來 | [transfer (v3) p20～22](http://speech.ee.ntu.edu.tw/~tlkagk/courses/ML_2016/Lecture/transfer%20(v3).pdf#page=22)；[da_v6 p7～8](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/da_v6.pdf#page=8) | 找不到可信的樣本外股市結果 | 不適用 |
| adversarial training（對抗訓練） | 攻擊演算法，在很小的範圍內找最壞的輸入 | 抵抗刻意攻擊，本質是資料增強 | [attack_v3 p35](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/attack_v3.pdf#page=35)；[LeeDL §12.8](https://github.com/datawhalechina/leedl-tutorial/releases/download/v1.2.4/LeeDL_Tutorial_v.1.2.4.pdf#page=227) | Adv-ALSTM 的小樣本、單一切分結果 | 最多當一次正則化對照 |
| GAN（生成對抗網路） | 判別真假的 discriminator | 生成資料 | DANN 投影片上的 Generator／Discriminator 對照；[life_v2 p30](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/life_v2.pdf#page=30) 用生成資料做 replay | 合成資料的好處接近一般正則化 | 現在不用 |

### domain-adversarial training

李宏毅把它比成 GAN：feature extractor 是 Generator，domain classifier 是 Discriminator（[da_v6 p8](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/da_v6.pdf#page=8)）。feature extractor 要騙過 domain classifier，同時還要讓 label predictor 分得對。2021 年的投影片把 feature extractor 的目標寫成 θf* = min L − Ld，旁邊打了問號。gradient reversal layer（反向傳播時把梯度乘上負數）出現在 2016 年遷移學習投影片 p22，那頁引用 Ganin 和 Lempitsky 的圖（[transfer (v3) p22](http://speech.ee.ntu.edu.tw/~tlkagk/courses/ML_2016/Lecture/transfer%20(v3).pdf#page=22)）。他講了三種失敗。第一，騙 domain classifier 的權重太大，隱空間會變差（LeeDL §13.2）。第二，兩邊對齊了，目標資料卻落在決策邊界附近（[da_v6 p10～11](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/da_v6.pdf#page=10)）。第三，兩邊類別不同時硬對齊會出錯（p12）。

不適用的原因有兩個。第一，它是為目標沒有答案設計的，台股每天都有答案，DANN 會丟掉這些資訊。第二，Zhao 等人證明，兩個 domain 的標籤分布不同時，學出「分不出 domain」的特徵和讓兩邊誤差都小，有根本的取捨，越對齊可能越糟（[ICML 2019](https://proceedings.mlr.press/v97/zhao19a.html)）。推論：不同市場和不同時期的上漲比例、特徵和報酬的關係都會變，正好是這個條件。時間序列領域適應的基準 AdaTime 發現，11 篇方法裡有 5 篇用目標 domain 的答案挑超參數，違反了無標註的前提、結果過度樂觀。在它自己的基準裡，用目標答案挑超參數，比用來源風險挑多約 0.9～5.9 個 macro-F1（各類別 F1 的平均）點。只用來源訓練和直接用目標訓練之間差 18～49 點。作者的結論是不用目標答案的挑法也可行（[arXiv 2203.08321](https://arxiv.org/pdf/2203.08321)）。

推論：唯一有用的變形是當診斷，訓練一個分類器分辨訓練期和測試期，量輸入漂移多大。DR 01 已經發現輸入漂移和分數變差對不上。

### adversarial training

李宏毅的定義：用攻擊演算法替每筆訓練資料找出最壞的 x̃，標上原本的答案一起訓練，投影片寫「Data Augmentation」和「Can it deal with new algorithm?」（[attack_v3 p35](https://speech.ee.ntu.edu.tw/~hylee/ml/ml2021-course-data/attack_v3.pdf#page=35)）。LeeDL 補上代價：不一定擋得住新的攻擊方式，而且很花算力（[§12.8](https://github.com/datawhalechina/leedl-tutorial/releases/download/v1.2.4/LeeDL_Tutorial_v.1.2.4.pdf#page=227)）。推論：股價沒有人在微小範圍內刻意改輸入騙模型，所以只剩資料增強的用途。

金融上最常被引用的是 Adv-ALSTM（[Feng et al. IJCAI 2019](https://www.ijcai.org/proceedings/2019/0810.pdf)）。ACL18（88 檔美股，測試約 3 個月）猜對率從 54.90% 升到 57.20%；KDD17（50 檔美股，測試 1 年）從 51.94% 升到 53.05%。Adv-ALSTM 沒有報標準差。用隨機雜訊代替對抗方向的對照組是 55.08% ± 2.0 和 52.43% ± 0.5，落在兩者之間。兩個資料集都事先拿掉漲跌在 −0.5%～+0.55% 之間的日子，猜對率和我們每天全部算的題目不能比。推論：3 個月約 5,000 個股票日，2.3 個百分點約是 3 個標準誤，但還沒算股票之間的相關，也只有一次切分。它比較像加雜訊的正則化。

### GAN 和合成資料

Rahimikia 用高斯過程造的合成序列增強預訓練，效果和加真實的 JKP 特徵差不多，所以好處不完全來自金融內容。TimesFM-20M 的起點很差，R² 多了 11.68 和 13.18 個百分點，但 DM 檢定（Diebold-Mariano，比較兩個預測誤差的檢定）沒有顯示合成資料比較好（[v2 Section 5.2](https://arxiv.org/pdf/2511.18578v2)）。Kronos 論文的合成 K 棒只評估逼真度，沒拿來增強報酬預測。推論：合成資料是給弱的大模型的正則化，現在不必做。

## 建議的做法：照已登記的 RP 40 走

RP 40 的判法已經凍結在 `memory/projects/22-ml-research-pipeline.md` 的「`RP 40` 事先登記」。這份在遠端分支 commit `1a2f75c` 那一版，本機主 worktree 還沒 pull。登記寫明 commit 後不改。`memory/projects/23-recent-prediction-research.md` 也只在遠端分支；RP 40 各本的狀態和 RP 41 列取自 `wt-rp` worktree 裡還沒 commit 的 `memory/projects/21-ml-research-pipeline-state.md`。建議分成登記裡已經有的、要補登記的、只報告的。補登記要在讀 40c full 的輸出之前寫進 `22`，要不要做由 Ian 決定。

### 每一步對到登記的哪一條

| 步驟 | 登記的條文 | notebook | 內容 |
|---|---|---|---|
| 查核 | S0 | 40b（full v6 已過）、40c～40f 開頭 | `twfm` 測試全過；`C2V2D` 對 `daily_rp36.csv` 差 < 1e-12；50 檔名次 Spearman 中位數 ≥ 0.99；資料錨點。任一條沒過就停 |
| 凍結 probe | S1 的一部分 | 40c `rp-40c-kronos-linear-probe-validation` | `head` 階段（主幹凍結，只訓練 FiLM 頭，學習率 1e-3，最多 2 個 epoch），L 從 64、128 選一個 |
| 微調變體 | S1 的一部分 | 40d `rp-40d-kronos-last2-and-lora-validation` | `last_k`（最後 2 層，4e-5，逐層衰減 0.8）、`lora`（r 8、α 16、2e-4），每階最多 2 個 epoch，取驗證期 RankIC 最好的 epoch。變體間驗證期 IC 差 < 0.002 時選較簡單的 |
| 驗證期關卡 | S1 | 40c、40d | 挑出的變體三條都要過：驗證期股票池 IC 平均高於 `REV1`（前一天報酬的反向名次）和 `MOM12_1`（過去 12 個月扣掉最近 1 個月的動能）；第四成員在驗證期 50 檔官方分數的增量 > 0；增量 ≥ +0.00009／天。沒過就停 |
| 最後重訓和對照 | S2（算力上限）、S3（測試期只開一次） | 40e `rp-40e-kronos-final-refit-hidden-test` | `FT`、`LP`、`FT_SMALL`、`SC`、`PATCH`（PatchTransformer 從頭訓練，只試學習率 1e-3）用標籤 ≤ 2025-06-30 重訓；測試期的檔沒有標籤欄 |
| 測試期一次 | H1、名次相關、機制家族、累計閘門 | 40f `rp-40f-kronos-test-period-once` | H1：`C2V2D+FT − C2V2D` 每天官方分數的差，340 天，單邊 p < 0.05；和 `PROXY_L`（過去 L 天平均盤中報酬的名次）的名次相關 < 0.8，就提議影子跑。109 個舊候選加 `FT` 的 `SPA_c` 照算照寫、不擋 |
| 影子跑 | S4 | oop | 5 個交易日只查實作；換不換每天交件的模型由 Ian 決定 |

notebook 都在 `notebooks/kaggle/2026-11-23_v1_research-pipeline/` 底下。凍結 probe 照 40c 跑，不另外下 `--probe` 指令。

### 本報告多出來的比較

- 補登記（要在讀 40c full 的輸出之前寫進 `22`）：
  - 5 日反轉：i 日以前 5 天收盤到收盤報酬，反向排名。登記只有 1 日的 `REV1`。
  - 殘差 IC：把 `LP`、`FT` 的分數對 `REV1`、`MOM12_1` 做橫斷面迴歸，報告殘差的 IC，做法照 issue #375。
  - `PATCH_val` 提到 S1 之前：登記是 40e 才跑、只報告。提前的話多一條關卡，`LP` 或 `FT` 在驗證期股票池的 IC 要高於 `PATCH`。推論：`PATCH` 也贏不了 `REV1`、`MOM12_1` 時，表示深度模型從 K 棒看不出多的東西；`PATCH` 贏、`LP` 輸 `PATCH` 時，表示預訓練沒有遷移過來。
- 只報告（不改判法）：
  - 50 檔在驗證期的 RankIC：只看方向，不當關卡。推論：只看 50 檔時，241 天只分得出 0.01～0.02 以上的 RankIC 差距（見「需要多少資料」）。
  - 污染診斷：「第一種」那三段 token 損失，只到 2025-06-30。
  - c2v2d 每天 50 檔的 RankIC，和只留排名集成的版本。
  - 每一階的訓練期和驗證期差距：分得出 LoRA 是學不到，還是過擬合被壓住。

### 讀結果時要記得的事

- 驗證期可能對 Kronos 有利：權重 2025-06-30 才上傳。`LP` 或 `FT` 只在驗證期贏、到測試期就輸，要當成污染的跡象。
- 套件的選法：每階開始前載入目前最好的權重，全部做完載入 `best.pt`，所以選的是驗證期 RankIC 最好的權重。40d 把 `last_k`、`lora` 分成兩個變體，各自先跑 1 個 epoch 的 head 再跑動主幹的階段（全量前的審查記的）；變體之間照驗證期 IC 差 < 0.002 選較簡單的規則挑。
- S1 沒過：照登記停下，GPU 留給下一條線。推論：之後要再試，便宜的是「第一種」裡的繼續預訓練；證據很弱，要另開一條線、另外登記。
- H1 沒過：登記寫成「340 天分不出」，印單邊 95% 上界。推論：340 天只分得出每天 RankIC 差約 0.01～0.015 以上（每天 IC 相關 0.8～0.5），差距更小時這一步會判定不過。
- 累計閘門：窗是 2025-07-01～2026-10-08（312 天），候選數照實際算出來的寫。

### H1 過了以後：漂移和上線

過關才做。影子跑比較「每週用擴張視窗重訓 head」和「每天用前一天的答案、小學習率更新一次 head」，重訓時保留全部歷史。上 oop 前要先解決「每天上線」那一節的四件事。

### 算力

RP 40 要 T4 約 22～32 小時（見「暴力美學的證據」最後的實測表），Kaggle 一週 30 小時。登記的 S2 上限是 Kaggle T4 45 小時加 Colab A100 15 小時，順序 `LP` → `last_k`、`lora` → S1 → 最後重訓 → `FT_SMALL` → `SC` → `PATCH` → base，超過上限的組記「沒跑」。

### 建議先不做的事（要不要做由 Ian 決定）

- DANN、CORAL、MMD（對齊兩個 domain 特徵分布的損失）這類跨市場或跨時期對齊：前提不成立，也沒有可信的股市結果。
- Adv-ALSTM 式的對抗訓練：證據薄。最多在 S1 過關後做一次「在 embedding 上加雜訊」的對照。
- Kronos-base：登記把 Kronos-base × {`head`, `lora`} 放進驗證期挑選，條件是 Colab A100 有額度；全量前的審查記 40d 沒跑 base。base 在論文的 CSI300、CSI800 模擬裡超額報酬和 IR 都贏所有對照，但那是作者自己的基準；台股（XTAI）的報酬 RankIC，base 的 0.0584 比 small 的 0.0597 低。建議 small 的 S1 結果出來前不花 A100 跑 base。Kronos-large 沒有公開權重。
- 測試時調整（TAFAS 這類）：用 MSE 評估，和排名無關。
- 再做 DoubleAdapt 類的元學習：DA 01 已經沒贏重訓。
- 用大模型猜大盤方向：一天一筆；Decider 和 MT 用團隊的特徵猜不到；Kronos 的日訊號在 NQ 盲測集過不了交易條件。
- 用 Phase 2 的線上成績挑模型：等於用公開榜挑模型。
- Kronos 自己的取樣預測頭：區間太窄，`dep_layer` 在 eval 時不是因果的。

### RP 41 的 Moirai 2.0 和 TimesFM 2.5

Ian 11-28 22:50 為 RP 41 選了 Moirai 2.0 和 TimesFM 2.5 都微調（`memory/projects/21-ml-research-pipeline-state.md` 的 RP 41 列，截至 11-28 晚上的狀態檔）。本報告的證據套到這兩個模型：

- 完整微調：通用 TSFM 在日報酬上完整微調沒有成功過，Rahimikia 的 Chronos、TimesFM 毛 Sharpe 是 −3.31～0.07。
- zero-shot：Upadhyay 的盲測集裡，凍結的 TimesFM 2.5、Moirai 2.0 和另外三個模型在 5～120 分鐘盤中共 160 格，0 格贏 no-change。
- 協變量：TimesFM 2.5 透過 XReg 吃協變量；Moirai 2.0 的協變量入口本報告沒查。

建議的過關條件（推論，要在 40f full 讀測試期之前登記）：

- 先凍結：主幹不動、只訓練頭，驗證期股票池 IC 贏 `REV1`、`MOM12_1` 才往下微調。
- 增量：第四成員在驗證期的增量 ≥ +0.00009／天，照 RP 40 的 S1。
- 測試期：只開一次，和 RP 40 的 `FT` 一起報告。

### 還想要大模型的話：讀新聞先過便宜的檢查

推論：用 LLM 讀新聞和公開資訊觀測站公告，結果當成個股協變量進 head，是唯一會帶來 K 棒以外資訊的大模型用法。對開盤到收盤，目前沒有證據。

- 正面的證據：Chen、Kelly、Xiu 用 LLM 讀美國和另外 15 個國家、13 種語言的新聞，平均贏過字詞方法（[作者 2025 投影片](https://dachxiu.chicagobooth.edu/download/news_2025.pdf)）。Lopez-Lira 和 Tang 發現可預測性集中在小型股和壞消息，而且越多人用 LLM，報酬越低（[arXiv 2304.07619](https://arxiv.org/abs/2304.07619)）。推論：這兩篇測的是每天或隔天的報酬，含隔夜跳空，比賽的開盤到收盤不含。
- 把兩段分開的研究：OLIVIA（[arXiv 2611.03985](https://arxiv.org/abs/2611.03985)，2026-11-02，訓練截止後樣本外）微調的 ModernBERT 編碼器，測試期對收盤到收盤的 IC 是 0.020（t 1.7），對開盤到收盤只有 0.010（t 0.8）。三個商用模型的判讀和隔夜跳空相關，和開盤後的走勢無關。
- 其他負面結果：QLoRA 情緒基準的 28 個檢定在 Newey-West 和 FDR（控制偽發現率的多重檢定）校正後全不顯著（[arXiv 2608.04200](https://arxiv.org/abs/2608.04200)）。arXiv 2611.33458 發現新聞類別的歷史平均勝過嵌入，Llama-2 的優勢到預訓練截止就消失（只讀到摘要）。出處整理在 `memory/projects/23-recent-prediction-research.md`。
- 團隊紀錄：RP 40 的研究也寫「語言模型：開盤到收盤的 IC 約 0（OLIVIA 0.010），不做」（`memory/projects/22-ml-research-pipeline.md`）。

要保留這條路，建議先過一個便宜的 go/no-go（推論）：新聞分數對 50 檔開盤到收盤報酬的每天 RankIC，在 2025-07-01 以前的資料上 t ≥ 2 才做。新聞的截止要和排程一樣：只用到 t 日當次排程開始（07:10，最晚 08:25）為止已發布、帶時間戳的新聞和公告，回測照同一個截止切。`submit.py` 用 08:50 當上傳截止（`competition.upload_cutoff`），08:25 以後的新聞進不了模型。

做之前要處理三件事：

- 偷看未來：LLM 可能記得訓練期之後的結果。Glasserman 和 Lin 匿名公司名稱後樣本內結果變好，他們推論一般知識的干擾比偷看未來大（[arXiv 2309.17322](https://arxiv.org/abs/2309.17322)）。已經有人訓練到 40 億參數、每月一個檢查點（2013～2024）的「point-in-time」LLM 來避開這個問題（[arXiv 2607.11889](https://arxiv.org/abs/2607.11889)）。
- 資料：要有帶時間戳的歷史新聞和公告，才能按日期切、回測。
- 規則：新聞也是外部資料，要一起問助教。

另一種便宜的「暴力」是資料的暴力：在台股自己的長歷史上從頭預訓練一個小模型，像 StockGPT 用約 5,000 萬筆美股日報酬訓練的小 GPT（[arXiv 2404.05101](https://arxiv.org/abs/2404.05101)）。RP 40 的 `PATCH` 和 `SC` 都是只用台股的監督式訓練，和 StockGPT、Rahimikia 先用預測下一筆報酬的目標預訓練不同，只測到這件事的一部分。

## 還不確定的事

- RP 40：模型還沒有結果，對它的判斷都是事前的。資料（40a、40b full）和速度（40s）已經有，40c full 11-28 17:00 推、排隊等 GPU（截至 11-28 晚上的狀態檔）。
- 目標：沒有研究測過開盤到收盤，也沒有研究專測台股 50 檔大型股。
- Kronos 的預訓練資料：有沒有用到台股（和印尼、馬來西亞），論文自相矛盾；表裡沒有櫃買。語料因為授權不能檢查。美國 ADR 有沒有在裡面是推論。
- Kronos 的數字：都是作者自己的基準。Table 17 有好幾格 Moirai 和 MOMENT 到小數第四位相同，XTAI 的 RankIC 剛好差 0.0100，可能抄錯。
- 獨立測試：issue #375、#355 和 Honest-Forecast-Eval 都是個人報告，沒有同儕審查；Upadhyay 是單一作者的預印本。
- Rahimikia：v1 和 v2 的數字不同，數字都取 v2。台股表只有從頭預訓練的模型，報酬用美元計、扣美國無風險利率；台股的 CatBoost 用全球資料訓練。
- 跨市場研究：Choi 的數字來自 2023 年草稿，正式版沒讀到；Hellum 的各國數字和有沒有台灣沒查到。
- 李宏毅：沒有逐字稿，口述內容靠 LeeDL 整理稿；2016 年遷移學習影片是哪一年錄的沒確認。
- 樣本數的算術：假設每天獨立、常態；σ_cs 沒量，c2v2d 隱含 IC 要用實際值重算。
- c2v2d 的分數：測試期 340 天重算是每天 0.150%，和套件 README 寫的約 0.15% 一致；每天 50 檔的 RankIC 還沒算。
- 規則：外部資料和預訓練權重沒找到禁止也沒找到允許，要問助教。
- 上線：oop 能不能離線裝 torch 和 Kronos 權重沒確認。
- 算力：T4 的速度是 RP 40s 在假資料上量的，真資料可能不同；A100 沒實測。
- RP 41：Moirai 2.0 的協變量入口和建議的微調方式本報告沒查。
- Jane Street 2024～25 第 1 名：沒有公開做法，不能說贏在什麼。
- 沒採用的數字：Lopez-Lira 和 Tang 的 Sharpe 3.8 對 3.1 沒查證到原表，所以沒有引用。
