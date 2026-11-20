# DoubleAdapt DA：增量元學習能不能對抗大幅波動（Kaggle DA 01～）

## 狀態

- 2026-11-20 20:50 使用者交辦（這個 session）：「請你把這個實驗跑通在 Kaggle，這個方法可以幫我們對抗大幅波動嗎」，附 `~/Downloads/Untitled.ipynb`（Colab）。
- 使用者那本停在 DoubleAdapt 那步：`main.py` 不收 `--config`（那份 yaml 是自己寫的，DoubleAdapt 不讀），`main.py` 的資料和模型都綁 Qlib。DoubleAdapt 的 `src/`（`IncrementalManager`、`DoubleAdaptManager`、滾動任務的工具）不需要 Qlib，這條線直接用 `src/`，自己做資料和模型。
- 2026-11-20 DA 01 跑完（Kaggle `da-01-doubleadapt-volatility-check`，version 1 smoke、version 2 full，T4，14.9 分鐘）：照登記判讀「這批資料上看不出能對抗大幅波動」，轉接器在 8 組裡也沒有一組比 naive 好。結案，只報告，正式流程不改。細節在「DA 01 的結果」。
- Kaggle collection 還沒建：建議「ML 2026 Fall｜13 DoubleAdapt（DA）」，放 DA 01。

## DoubleAdapt 是什麼

- 論文：Zhao 等，KDD 2023，<https://arxiv.org/abs/2306.09862>；程式 <https://github.com/SJTU-DMTai/DoubleAdapt>（用 commit `e20b6e4`）。
- 做法：每 step 天一個任務。模型先用前 step 天的資料小幅更新（MAML 的內圈），再預測接下來 step 天；預測完、答案出來後，再更新兩個「轉接器」：特徵轉接器（把特徵做幾組線性轉換）和標籤轉接器（把標籤的尺度、偏移換掉）。目的是讓模型跟上分布的變化。
- 對照組是同一個架構的「naive 增量學習」：每個任務只用前 step 天更新模型，沒有轉接器（`IncrementalManager`）。

## 設計（2026-11-20 20:55 寫，跑之前）

- 資料：GitHub commit `5d8dc4c` 的長表，特徵是 manifest 的 `model_columns`（55 欄，使用者那本用的同一組，都是 t 開盤前就有的）。每欄用元訓練期（2020-03-02～2022-12-30）的平均和標準差標準化，截在 ±5，缺值補 0。
- 兩種標籤：
  - `rank`：當天 100 檔盤中報酬的橫斷面 z 分數，截 ±3。猜法是每天前 25 名猜 1（和 `X_price` 一樣，不押大盤）。
  - `raw`：盤中報酬 × 100，截 ±10。猜法是預測 > 0 就猜 1，猜漲檔數不設限（這是「會不會在大跌日自己少猜漲」的那一種）。
- 期間：元訓練 2020-03-02～2022-12-30、元驗證 2023、線上測試 2024-01-02～2026-11-19。step = 5 個交易日（README 建議 2～5 天）。訓練段最後一天的答案在下一段開始前就有了，所以 `trunc_days` = 1、H = 1；預測一段之後才用那段的答案更新。
- 模型：MLP（55 欄）和 GRU（前 20 天的 55 欄序列）。
- 跑法：2 種模型 × 2 種標籤 × {DoubleAdapt, naive} = 8 組，full 每組 2 個種子取平均。參數照 README 的預設：lr 0.001、lr_da 0.01、num_head 8、tau 10、first_order、reg 0.5。
- 比較（只用 Top50，只報告）：
  - `rank`：DoubleAdapt − naive、DoubleAdapt − `X_price`（35 的每月重訓，到 2026-11-12）。
  - `raw`：DoubleAdapt 的不設限猜法 − c2v2d（44，到 2026-10-08）、− 全猜 0；大跌日（m < −2%）平均猜幾檔漲。
  - 大幅波動的日子分三種看：事後 |m| 前 20% 的日子、m < −2% 的大跌日、事前的高波動期（前 20 天 m 的標準差在測試期的前三分之一，只用 t 以前的資料）。
- 判讀（事先寫）：寫「能幫忙對抗大幅波動」要同時滿足：`rank` 的 DoubleAdapt 在事前高波動期贏 `X_price`（t > 2）、整段不輸 `X_price`；或 `raw` 的 DoubleAdapt 在大跌日贏 c2v2d、整段不輸 c2v2d。都不滿足就寫「這批資料上看不出能對抗大幅波動」。DoubleAdapt 贏 naive 只代表轉接器有用，不代表贏我們現在的模型。
- 限制：2024 起的日子很多研究看過（不是乾淨的樣本外）；種子只有 2 個；參數沒有調（README 說要調學習率）。結果好也只能當進一步登記的理由。

## DA 01 的結果（2026-11-20，version 2 full，2 個種子）

- 核對：`X_price` 重算的每天分數和 44 的原版差 1e-16；35、44 的 sha256 是凍結的版本（818fbf6f、368ab245）。16 次（8 組 × 2 個種子）都跑完，Top50 測試期 697 天、34,839 格沒有缺值。
- 判讀（照登記）：「這批資料上看不出 DoubleAdapt 能對抗大幅波動。」兩條都沒滿足：

| 條件（每天差 × 1e4） | MLP | GRU |
|---|---|---|
| `rank` DA − `X_price`，事前高波動期 221 天（要 t > 2） | +0.48（t 0.14） | −2.16（t −0.85） |
| `rank` DA − `X_price`，整段 692 天（要 ≥ 0） | −1.99 | −1.58 |
| `raw` DA 不設限 − c2v2d，大跌日 9 天（要 > 0） | −18.25 | −21.44 |
| `raw` DA 不設限 − c2v2d，整段 670 天（要 ≥ 0） | −5.56（t −2.19） | −6.62（t −2.84） |

- 轉接器本身（DA − naive，整段）：`rank` GRU −2.36（t −1.68，|m| 前 20% 的日子 −12.49，t −2.40）、`rank` MLP +0.28、`raw` GRU −0.53、`raw` MLP −3.37（t −2.34）。沒有一組明顯變好，GRU 在大波動的日子反而變差。
- 大跌日不會自己少猜漲：`raw` 的 DA 版在 14 個大跌日平均猜漲 26.3 檔（GRU）、23.8 檔（MLP），比其他日子的 17.4、19.8 檔還多；大跌日的分數比全猜 0 低 0.025／天。原因和 Decider 一樣：大跌當天開盤前的特徵猜不到方向。
- 整段每天分數（× 1e4）：c2v2d 12.95、`X_price` 11.09；8 組裡最高的是 GRU `rank` naive 12.10，DA 版最高 9.92（GRU `raw`，25/25 猜法）。
- 看完結果才注意到的（不能當證據）：GRU `rank` naive 在 |m| 大的日子贏 `X_price` +10.70（t 2.19）、大跌日 +20.96（t 2.34），整段只有 +0.86（t 0.58）。這張表約 80 個比較，|t| > 2 偶然就會出現 4 個左右；smoke（1 個種子）和 full 的同一格差很多（大跌日 84 對 97），種子之間的變動大。要追就要另外登記，用沒看過的期間。
- 沒做的：沒有調學習率再跑。DA 在 8 組裡沒有一組贏 naive，調參數要另外登記，2024 起的資料也已經看過了。
- 技術紀錄：notebook 把 DoubleAdapt clone 在 `/kaggle/working`，輸出包含整個 `.git`，`tools.py pull` 一層一層補資料夾會停在 30 次。下載結果用 `kaggle kernels output modelnovice/da-01-doubleadapt-volatility-check -p <dir> --file-pattern '(_da01\.|\.log$)'`。再跑要 clone 到 `/tmp`。
