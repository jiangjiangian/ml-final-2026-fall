# 官方Return-ratio：學習目標與可重現模型研究

本輪實作以本課正式分數為主，而不是以accuracy代替分數。這是研究與程式驗證；教師原始資料的日期、發布、還原價修訂等證據尚不完整，任何使用保守時間假設的實驗均標記`research_assumption`，不能升級正式模型。

## 來源與推導

- 林軒田[基石第08講Noise and Error](https://www.csie.ntu.edu.tw/~htlin/mooc/doc/08_handout.pdf)：PDF頁9–14比較不同loss的ideal target，頁21–24討論weighted classification。公開講義是方法來源，不是金融增益證據；完整閱讀／視覺核對紀錄見FOUNDATIONS。
- [scikit-learn LogisticRegression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html)、[MLPClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.neural_network.MLPClassifier.html)、[HistGradientBoostingClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html)：成熟fit／sample_weight／predict介面。
- [PyTorch GRU](https://docs.pytorch.org/docs/stable/generated/torch.nn.GRU.html)：小型CPU時序模型；不需要Ray、Kubernetes或GPU叢集。

令`r=(adj_close-adj_open)/adj_open`，`y=1{r>0}`，完整50檔的官方score為平均`(2p-1)r`。逐樣本有

`abs(r) * 1{p != y} = (abs(r) - (2p-1)*r)/2`。

所以最小化abs(r)加權的錯分率與最大化原score等價；`r=0`時兩邊都是0。這是本專案依官方公式作的代數推導，不是宣稱講義證明過本競賽策略。加權logistic／neural cross-entropy仍是替代loss，有限容量與有限樣本下不保證分數改善。平方誤差的ideal target為`E[r|x]`，二元決策按其正負取值；回歸預測恰為0時輸出0。

## 固定實驗矩陣

| 維度 | 本次固定設定 |
|---|---|
| 學習目標 | 普通方向分類；以abs(r)加權分類；直接報酬回歸後取正負 |
| 四類模型 | 正則化logistic／Ridge；HistGradientBoosting；單隱藏層MLP；5步stock-specific GRU |
| 訓練前處理 | train-only中位數填補＋缺值indicator＋StandardScaler；保存完整順序與版本 |
| 收益權重 | 每個train fold的abs(r)除以該fold平均；全零時任意決策均同score，使用均勻權重 |
| 時間切分 | 每個2025季度以前的2020起樣本訓練，整季驗證；同日股票不跨train/validation |
| 選擇 | 以四季合併、按觀測數加權的官方score選configuration；不以accuracy選模 |
| 保留檢查 | 固定winner後，2026年1–5月一次評估；不對該結果繼續選參 |
| 基準 | 全0、全1、僅依該fold訓練標籤決定的多數類別 |
| 再現性 | seed42；CPU；GRU8epoch／16hidden／5lookback；主要套件版本／訓練表／程式hash留manifest |

sklearn各族使用固定小型設定，沒有先做超參數搜尋。HistGradientBoosting60輪、15leaf，MLP32hidden／最多80iter；不收斂警告完整記錄而不隱藏。GRU序列只含同股之前及當期的輸入，邊界以最早已知向量padding，預測不fit。加入更晚日期不能改變更早預測；這已列回歸測試。

## 輸入、產物與實際執行

`training-table-v1`使用明示feature_columns／feature_version／readiness／availability_evidence及stock-date rows。y、當日OHLC、target_intraday_return是outcome，禁止選為feature。verified要求label_available_at；research_assumption需要CLI顯式`--research-if-unverified`。即使提供verified聲明，程式也只能檢查格式及時序，不能替代來源證據查核。

實驗入口（從業務目錄）：

```bash
uv sync --locked --extra models --extra neural --extra data --group dev
uv run --locked --no-sync python scripts/run_experiments.py \
  --table /workspace/shared/research/experiments/course-stock-table.json \
  --out-dir /workspace/shared/research/experiments/E00-stock-v1 \
  --research-if-unverified --include-holdout --epochs 8
```

輸出report.json保存每fold／configuration／baseline score、accuracy、逐日score、警告與選擇；predictions.json保存相同鍵的OOF／保留預測。E01起另記原始載入buffer與canonical table兩種hash、七份實驗／模型／評分程式hash、套件／Python版本、時間、逐月score、fold鍵hash與訓練缺值率；開始與結束比對程式hash，期間被改動則不完成報告。執行中progress.json提供每模型checkpoint，完成後移除；有內容的結果目錄不能覆寫。保留檢查只評估由validation先選定的一組configuration，並保存該模型包；不可把重開另一個輸出目錄當成反覆調holdout的許可。

model-bundle-v1保存前處理、參數、feature schema／順序、train_end_date、fit_cutoff、readiness、資料與程式hash、套件版本、seed。推論拒絕欄位錯誤、過去target、晚於預測cutoff才fit的模型、非有限輸出，以及未經驗證模型的production模式。joblib屬可執行序列化；只載入明示可信、此專案建立、當前使用者擁有且不可由其他人寫入的本地模型庫，hash僅驗完整性，不宣稱提供對惡意模型的安全隔離。

## 每日候選模型的公平比較

`train_candidate`以最近60個完整日期作validation，更早至少252日期訓練。現有模型的recent artifact可能已讀過這60天，不能拿它直接算假OOF；比較時重新訓練其configuration於相同更早train，再對相同validation鍵評分。報告標明`configuration_retrained_on_same_time_split`。選好configuration後才用截止前全部已完成歷史重fit。初始配置／不同配置需score嚴格提高；已核准的相同配置則可在**新增完成歷史日期**時更新，不要求它虛構勝過自己的相同重訓：需要verified incumbent metadata、相同欄位順序／版本／可用性政策及相同fold非退步。沒有新完成日期、metadata不足、政策變更或驗證退步皆不更新；研究／合成模型一律不能promotion。報告分開`candidate_improved`與`promotion_reason`，相同配置更新不冒稱演算法勝出。這種方法比較的是配置選擇，不假稱評估了正式artifact在未知資料的表現。

## 本次結果與限制

實際E00使用82674個Top50完成股票日期樣本、7個前期個股特徵；前期是前一個觀測列，未宣稱每列皆相鄰native session。50個10/23 pending樣本由上游明列排除。來源可用性採明示保守假設，標準化還原價仍可能有事後修訂，因此結果不是certified point-in-time績效，也不是投資策略淨利。實際數值如下；原始個股／逐列預測留在checkout外。

### E00實際結果（研究假設條件下）

2025四季60筆配置／基準結果，共48次模型fit；同一組7個前期個股特徵，沒有加市場特徵。

| 模型 | 普通分類score | abs(r)加權分類score | 報酬回歸score |
|---|---:|---:|---:|
| linear | 0.000471648311 | 0.000482249960 | 0.000526636554 |
| hist_gbdt | 0.000849905671 | 0.000640850741 | 0.000524987400 |
| mlp | 0.000854985259 | 0.000498627855 | 0.000179339973 |
| gru | 0.000832172751 | 0.000838222003 | 0.000564604555 |

2025全0／train-majority基準score為0.000447093446；全1為其相反數。固定validation選到MLP普通分類（0.000854985259）。不是加權分類必然較好，這次普通MLP與樹也高於其加權版本。

在看到保留結果前固定的E00 winner，2026年1–5月4750鍵score=0.001275711605，accuracy=0.570315789474；同鍵全0 baseline=0.001549845039。**winner在保留期未超過全0基準**，不能因2025驗證勝出就宣稱穩定增益。這是一次描述性保留檢查，未計交易成本、尚無顯著性保證，不能作正式PIT／實際交易收益宣稱。

MLP警告：80次迭代上限內尚未收斂，原文留在report。這些參數未依holdout再調整。E01市場消融只先比較2025validation，不用E00holdout選特徵。

真實研究推論CLI亦已通過：用E00內部模型包對最新完整日期50檔輸出0/1，產物E00-predict-check/predictions.json；production_eligible=false，沒有上傳競賽。

驗證：12項training與5項inference測試通過，包含四族三目標fit、GRU未來不變性、train-only前處理、晚label、backdated prediction、欄位版本、可信模型hash及相同配置更新／拒絕反例；另有3項實驗版本／切分測試，Ruff通過。sklearn／PyTorch主要介面文件本次正常TLS HTTP200查核。

### E01–E03市場特徵消融：實際負結果

固定linear、abs(r)加權分類、seed42、原四個2025季度，只改輸入欄位。每表都是相同82674個完成鍵；驗證共同12140鍵，四季分別2750／3050／3242／3098。程式逐鍵核對，而非只比較列數；共同排序鍵hash為`c69c1fa7e0088ebe4f07f47c8f1b83eccda77c7cbe88f798bee03dae00decb1f`。E01–E03沒有再讀取holdout來計分或選參。

| 輸入 | 2025合併score | accuracy | 相對同配置E00 score變化 |
|---|---:|---:|---:|
| E00：前期個股7欄 | 0.000482249960 | 0.494316310 | 0 |
| E01：個股＋M0 | 0.000356441216 | 0.489703460 | -0.000125808745 |
| E02：個股＋M0＋SOX | 0.000249487724 | 0.485831960 | -0.000232762237 |
| E03：個股＋M0＋TSM ADR／NVDA | 0.000388784462 | 0.492915980 | -0.000093465499 |

這三組市場輸入均低於相同linear加權個股基準，也低於全0基準0.000447093446；E03雖高於E01，仍未超過E00。故本輪沒有特徵／正式模型升級依據。此結論限於這組模型、欄位、切分與明示時間假設，不能推論所有市場資訊無用。M0的OI兩欄仍100%缺值；額外市場來自最新歷史版本與close＋2h假設，尚未認證歷史vintage。沒有用這些負結果反覆調整2026保留期。

四季score：

| 輸入 | Q1 | Q2 | Q3 | Q4 |
|---|---:|---:|---:|---:|
| E00 linear weighted | 0.000410166945 | 0.001218422509 | -0.000472219995 | 0.000820304711 |
| E01 | 0.000208485370 | 0.001358061232 | -0.000242727361 | 0.000128694945 |
| E02 | 0.000138041497 | 0.001212546849 | -0.000337697664 | 0.000014756225 |
| E03 | -0.000136938004 | 0.001147253627 | -0.000268422559 | 0.000796489752 |

E01／E02／E03整體執行約18.12／16.83／17.09秒，沒有收斂警告；E02與E03同機並行，耗時只作這次CPU環境的描述，非受控效能排名。逐月／逐日score、missing與每fit時間在原report。

完整來源與canonical table hash、重跑方式、未完成E04／E05，見[EXPERIMENTS](../EXPERIMENTS.md)。私有彙總`/workspace/shared/research/experiments/ablation-summary-v1.json`保留共同鍵核對及E00追溯限制。E00舊report沒有實驗腳本hash或原始buffer hash，維持原檔；本次僅確認現存table canonical hash相符及selected_model checksum有效，不能倒推48次歷史fit都有完整程式版本證明。

### 正式每日執行的限制

四家族可研究fit／序列推論，並不代表四者皆已接成正式每日模型。GRU批次驗證會讀取各驗證日期當時已知的特徵；若每天只提供今天50列、而舊模型缺少中間日期的已核實context，序列會與研究驗證不同。正式daily approval因此阻擋GRU，直到保存並驗證中間推論歷史；目前每日候選預設linear。來源歷史時間證據、正式verified訓練／預測表與常駐排程仍需完成，研究模型不提交競賽。
