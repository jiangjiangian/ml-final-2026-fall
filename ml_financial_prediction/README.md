# 台股盤中方向預測：ML 系統與 Codex 工作指南

更新：2026-10-25，時區 Asia/Taipei。版本：v0.1 規劃與離線資料稽核。

本套件把老師規範、團隊 Google Docs 與資料結構轉成可實作的工作規格。**尚未訓練模型、接通競賽網站、啟用排程或自動提交。** 目前可執行的程式只有資料稽核工具，排程檔是未啟用範本。

完整ML系統的模組、資料夾分類、介面與建置階段，先讀 `docs/ARCHITECTURE.md`。目前優先實作市場特徵，但資料、模型、訓練、推論、提交與監控各層都已有設計分工。

## 先讀這段

先做好 `X_market` 的時間對齊，再擴充指數。它是一組欄位，而非單一數字。起步採用已提供的四個股價指數報酬、VIX 狀態與外資期貨部位；下一輪依序測試 SOX、TSM ADR / NVDA、USD/TWD、利率與台股產業指數。這是研究建議，尚無驗證結果證明新增欄位有效。

不要先寫死 `shift(2)`。`(P[t-1]-P[t-2])/P[t-2]` 是截至前一期的單期報酬，通常稱 return lag 1。跨國資料應按實際可用時間對齊，並先確認老師資料是否已位移。

## 專案目標與約束

目標為台股當日還原收盤價是否高於還原開盤價：`y[i,t] = 1{adj_close[i,t] > adj_open[i,t]}`。特徵必須在該次預測的資料截止時間之前可取得。

官方評分為 `mean((2 * prediction - 1) * (adj_close - adj_open) / adj_open)`，不是單純 accuracy 或股票排名。所有 50 檔股票都需要 0/1 預測。

| 項目 | 正式規範 |
|---|---|
| Phase 1 | 2026-06-01 至 2026-09-30，50 檔 × 84 日期，4200 個預測 |
| Phase 1 截止 | 2026-12-24 23:59 UTC+8，排行榜保留最高分版本 |
| Phase 2 | 每個 session 50 檔，每天 09:00 UTC+8 截止，採最後有效提交 |
| 計分競賽階段 | 2026-11-16 至 2026-12-24，以官方指定 session 為準 |
| 報告 | 至少比較四個可重現 ML approaches，最多七頁 A4 |
| 報告截止 | 2026-12-30 13:00 UTC+8 |
| 原始碼保存 | 至 2027-01-31 23:59 UTC+8 |

以上依 2026-10-24 發布的 final 規範。較早簡報的 11/30 起始日期已被正式規範更新。報告占 1440/1920 = 75%，實驗與紀錄應與每日競賽並重。

## 團隊分工與交接物

依 Google Docs 目前可讀內容，以下為分工紀錄，交付內容為本套件建議。

| 成員 | 方向 | 建議交接內容 |
|---|---|---|
| 蘇 | Web crawler / text analysis | 每日市場特徵表、來源與可用時間、新聞特徵表 |
| 顏 | Time-series / Transformers | 模型、序列窗口、訓練與推論介面 |
| 戴 | Rank error / meta model | 官方 score、時間驗證、OOF 預測、融合實驗 |
| 楊 | 補充時間序列 | 外部市場序列、歷史補齊、品質檢查 |

市場特徵先交成 `target_date` 一列的表格，與個股特徵以目標日期 left join；不得用 inner join 靜默丟掉缺市場資料的台股交易日。建議 schema 見 `docs/DATA_CONTRACT.md`。

## 特徵矩陣

若有 T 個目標日期、K 個市場欄位，市場表 `G` 的形狀是 `T × K`。某天同一組市場資訊會出現在當日每檔股票的輸入中。

個股原有 P 個特徵時，`x[i,t] = concat(stock_features[i,t], G[t])`。50 檔合併訓練的表格是 `(50*T) × (P+K)`，標籤是長度 `50*T` 的向量。有缺漏個股日期時，實際列數依有效 stock-date pairs 計算。

序列模型常用 `[batch, lookback, P+K]`。其每個市場向量都必須代表該歷史時點當時可知的資訊，而非用今天修訂後的資料回填。具體公式、例子與交互作用見 `docs/FEATURE_SPEC.md`。

## 建議開發順序

1. 跑離線稽核，列出老師資料欄位、日期缺口、樣本格式。現有觀察見 `docs/DATA_AUDIT.json`。
2. 建立每個來源的日期語意、發布時間、是否已位移對照；抽查正常日、跨週末、台美不同休市日。未完成時不宣稱資料已無洩漏。
3. 實作原有市場特徵基準與時間對齊；保留日期、來源、缺值與陳舊標記。
4. 用相同時間切分比較「個股特徵」與「個股 + 市場特徵」，依官方 score 評估。
5. 一次加入一組候選來源，記錄增益與成本；不可只看訓練集或反覆調靜態排行榜。
6. 固定模型與欄位版本，演練每日下載、推論、格式檢查、手動上傳與回執核對，再考慮自動提交。

## 現在可以執行的檢查

環境只需 Python 3.10+，此工具不連網、不修改原始資料。

```bash
python scripts/audit_dataset.py --zip /absolute/path/fin_pred_data.zip --template /absolute/path/sample_submission.csv --out /absolute/path/dataset_audit.json
```

原始資料不包含在本套件。`configs/features.yaml` 是待實作的介面規格，不是已存在的特徵引擎；不要把規劃中的命令說成已可執行。

## 在 Codex 使用

把此目錄放在實際專案根目錄，從該目錄開啟 Codex。`AGENTS.md` 是 Codex 會讀取的指引檔名。其他記憶文件透過其中的閱讀要求使用，不會只因命名為 MEMORY 就自動載入。

第一次交給 Codex 的任務可直接貼上：

> 請讀 AGENTS.md、docs/PROJECT_CONTEXT.md、docs/FEATURE_SPEC.md、docs/DATA_CONTRACT.md 與 docs/STATUS.md。先執行資料稽核，確認每個全球欄位的日期語意與可用時間。不要對整張全球表盲目 shift(2)。先實作原有市場欄位的 return / VIX / TX_OI 轉換與 as-of 對齊，加入針對未來資料、假日、零分母與修訂資料的測試，再交付 market_features 表及來源對齊報告。尚未實作的 API 或網站端點請標記，先完成不依賴該端點的工作。

## GitHub、電腦與每日排程

建議使用僅限組員的私人 GitHub repository 保存程式、設定與實驗紀錄。依老師簡報，課程資料不得分享給未修課者；原始資料不應跟著公開 repository、公開 artifacts 或 CI log 外流。FinMind 亦有原始資料再散布限制。請把原始檔保存在授權的團隊儲存空間，Git 只記錄雜湊與取得方法。

Codex Cloud 接到 repository 後可在雲端工作，不需要一直連著個人電腦；本機程式或 self-hosted runner 則需要主機持續運作。雲端不會自動繼承你電腦的登入狀態。設定與來源見 `docs/OPERATIONS.md`、`docs/SOURCES.md`。

先採「定時腳本產生 CSV + 人工核對提交」最容易演練。若已有學校伺服器，systemd timer 可作主要執行器；否則 GitHub Actions 可作起步方案，但需重試與備援。ChatGPT 排程適合檢查與提醒，競賽資料管線建議使用可重跑、可測試的程式。

## 文件與記憶的分工

| 檔案 | 用途 |
|---|---|
| `AGENTS.md` | 每次工作都要遵守的規則 |
| `docs/ARCHITECTURE.md` | 完整ML系統、專案目錄與分階段建置 |
| `docs/PROJECT_CONTEXT.md` | 穩定背景、團隊目標、來源優先順序 |
| `docs/FEATURE_SPEC.md` | 特徵公式、矩陣、實驗設計 |
| `docs/DATA_CONTRACT.md` | 欄位、時間戳、缺值與交接格式 |
| `docs/DATA_SOURCES.md` | 資料來源選擇與限制 |
| `docs/OPERATIONS.md` | 每日執行、失敗重試與提交核對 |
| `docs/DECISIONS.md` | 已確認事項、提案與待確認事項 |
| `docs/STATUS.md` | 現況、下一步、阻礙；每次收工更新 |
| `docs/EXPERIMENTS.md` | 每次實驗的切分、版本與結果 |
| `docs/SOURCES.md` | 規範頁碼、官方文件與查核日期 |

不需要先建立大量重複的記憶檔。穩定背景、決策、當前狀態各有一個權威檔即可。
