# 實驗紀錄

更新：2026-10-30。以下為已執行的真實資料研究；全數`readiness=research_assumption`，不代表歷史發布／修訂版本已認證，也不作投資淨利或正式模型升級證據。細節見[RETURN_RATIO](research/RETURN_RATIO.md)及[DATA_ALIGNMENT](research/DATA_ALIGNMENT.md)。

## 固定設定與資料

官方score=`mean((2*p-1)*(adj_close-adj_open)/adj_open)`；所有指定股票都有0/1決策。前期個股7欄僅使用之前觀測列；不以當日OHLC／答案作輸入。Fixed＋Live共有82674個Top50完成股票日期鍵，50個10/23 pending鍵單獨排除。市場以target-date／08:10 cutoff left join，沒有因缺市場資訊刪目標。

訓練起點2020-01-01；2025Q1～Q4各以更早資料fit、整季驗證，同日股票不跨fold。驗證12140鍵（四季2750／3050／3242／3098），seed42。E00比較四家族×三目標×四fold共48個fit及12個baseline；E01–E03每個只增加四個fixed linear加權fit，沒有用額外模型搜尋掩蓋負結果。

研究假設：個股前一觀測列／label於來源日23:59台北可用；外部市場採原生日曆close＋2h延遲。教師還原價與Yahoo歷史是本次下載的最新版本，未驗證所有歷史vintage。OI兩欄缺少有效性／來源證據，維持100%缺值。完整假設隨表與模型保存，不能改標verified。

CPU環境：Python3.12.14、scikit-learn1.9.1、NumPy2.5.4、joblib1.6.0、PyTorch2.8.0+cpu（GRU）；具體套件版本以原report／bundle manifest為權威。

| ID | 輸入及配置 | 2025合併score | 狀態／解讀 |
|---|---|---:|---|
| E00 | 個股7欄；四家族×三目標 | 最佳MLP普通分類0.000854985259 | 完成；所有12組結果見RETURN_RATIO |
| E00-LW | 同E00，固定linear加權分類 | 0.000482249960 | E01–E03的相同配置對照 |
| E01 | E00個股＋M0；linear加權分類 | 0.000356441216 | 完成；比E00-LW下降0.000125808745 |
| E02 | E01＋SOX；相同配置 | 0.000249487724 | 完成；比E01下降0.000106953492 |
| E03 | E01＋TSM ADR／NVDA；相同配置 | 0.000388784462 | 完成；比E01增加0.000032343246，仍低於E00-LW |
| E04 | E01＋USD/TWD／利率 | 未計分 | raw已取得；發布／修訂時間及特徵接入未完成 |
| E05 | E01＋台灣產業／交互作用 | 未計分 | 取得三類單日水準；尚無完整歷史報酬／消融 |

2025同鍵全0／train-majority score=0.000447093446。E01–E03均未超過它，也未超過E00-LW；目前無市場擴充增益證據，不升級模型。這只代表本組配置／時間切分的結果，不是所有市場資訊無用的證明。

E00在2025選定MLP普通分類後，**只評估一次**2026年1–5月4750鍵：score=0.001275711605，accuracy=0.570315789474；同鍵全0=0.001549845039，winner未超過該基準。E01–E03沒有重跑這段holdout，也沒有依其表現選特徵。MLP80iter未收斂警告保留原文，沒有依holdout再調整。

## 版本與產物

私有產物根目錄`/workspace/shared/research/experiments/`；研究資料與逐列預測不入Git。

| 產物 | 目錄／檔名 | canonical training table SHA256 |
|---|---|---|
| E00 | `E00-stock-v1/`；`course-stock-table.json` | `163a2bedb2df71cba564e3d323115990313fefe3c16a4c4853e5d9e18331edab` |
| E01 | `E01-stock-m0-v1/`；`course-stock-m0-table.json` | `874590ab49bb06f4344c498a28e7fb09dc9c323f2ba4b8e9a1d48204af04e71c` |
| E02 | `E02-stock-m0-sox-v1/`；`course-stock-m0-sox-table.json` | `2a82157a2d72fa13ec7cfd759209a78f7a38bb2158ead8a6ceb72b8bd1fa27d9` |
| E03 | `E03-stock-m0-adr-v1/`；`course-stock-m0-adr-table.json` | `695f01a9842c5703fe84168eee91b7679d00a20fc4aafaedeaf2df75aa59d8ab` |

來源Fixed ZIP SHA256=`7433b27103107c630e293708a7ca4b7bfcec524e91ea6dc5be3e9b7d885b90e2`；Live=`2ea21246910eb3fd84561f9c5a5cd9c52c4c71c8a677268ae13bf4c27db39b5d`。市場CSV及hash、原生日曆與假設在`/workspace/shared/research/alignment/market_report.json`。E02選M0八欄＋`sox_ret_1s`；E03選M0八欄＋`tsm_adr_ret_1s`／`nvda_ret_1s`。

每個已完成目錄有不可覆寫的report.json／predictions.json；E00另有selected_model，研究推論測試產物在E00-predict-check。跨實驗逐鍵核對的彙總在`ablation-summary-v1.json`，共同排序validation鍵hash=`c69c1fa7e0088ebe4f07f47c8f1b83eccda77c7cbe88f798bee03dae00decb1f`；其report_sha256欄是對報告JSON canonical化後計算，並非檔案buffer hash。

E01起report保存七份相關程式hash、原始輸入buffer hash及canonical table hash、版本、每fold缺值／標籤排除／鍵hash、逐月／逐日分數及fit／inference時間；來源程式於執行首尾需相符。E00原report沒有實驗腳本hash、載入buffer hash與完整耗時，因此不回填成虛構的當時記錄。現存E00表的canonical hash及selected_model checksum已再次核對，但這不證明48個舊fit皆有完整版本鏈。此批執行時程式尚未提交，不能填寫虛構Git commit；模型及E01起報告以實際檔案hash追溯。

E01／E02／E03共耗18.12／16.83／17.09秒；後兩者同機並行，非受控效能排名。所有新linear fits沒有警告。後續daily refresh修正形成新training/fit.py版本；不可用其新hash替換原研究artifact的歷史hash。私有`source-snapshots/manifest.json`另保存與原E01–E03七份程式hash完全相符的source object；fit.py以逆轉後續patch重建後驗hash，其餘由當前檔案驗hash複製，明示為事後保存，不冒稱開跑時已有snapshot。舊report不改寫。

## 重跑與驗證

業務目錄執行；輸出改為全新私有目錄，已存在且有內容的實驗目錄會拒絕覆寫：

```bash
uv run --locked --no-sync python scripts/run_experiments.py \
  --table /workspace/shared/research/experiments/course-stock-m0-table.json \
  --out-dir /workspace/shared/research/experiments/E01-repeat-new-directory \
  --families linear --objectives weighted_classification \
  --research-if-unverified --seed 42 --epochs 8
```

E02／E03只替換對應table與全新out-dir，不加`--include-holdout`。`build_training_table.py`可從上述兩個ZIP與市場CSV／report重建；E02／E03要以重複`--market-feature`明列M0八欄與該組額外欄位，不能只列新增欄而漏掉M0。這次表亦使用相同`build_research_table`介面核對來源hash建立。

實驗專用三項反例測試通過：重疊fold或holdout污染被拒、實際buffer與表內容綁定、共同目標鍵與原始版本證據保存；Ruff通過。模型／推論／daily全套整合結果由STATUS更新，這裡不把局部測試當整體系統上線。

後續先補來源時間與vintage證據、建立正式表，再預註冊E04／E05或缺值／age／交互作用等新研究；不把已看過的2026保留期重新當未看測試集。GRU仍缺每日舊模型的中間日期context接入，正式daily approval暫阻擋；研究四家族比較已完成，部署狀態另看STATUS。
