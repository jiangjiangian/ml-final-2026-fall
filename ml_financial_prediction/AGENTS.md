# Codex 專案工作指引

## 開始工作

先讀 `README.md`、`docs/ARCHITECTURE.md`、`docs/PROJECT_CONTEXT.md`、`docs/STATUS.md`、`docs/DECISIONS.md`。修改特徵時另讀 `docs/FEATURE_SPEC.md`、`docs/DATA_CONTRACT.md`；修改排程時另讀 `docs/OPERATIONS.md`。本文要求讀取的文件是專案記憶，不假設不同聊天自動共享上下文。

使用繁體中文說明，公式和程式採清楚一致的符號。先說成果與證據；區分老師規範、資料觀察、研究提案、尚未驗證的推論。

## 任務與評分

預測台股當日 adjusted close > adjusted open，輸出 0/1。主要評估為 `mean((2*p-1)*(close-open)/open)`；accuracy、rank correlation 只作輔助。每個指定股票都要預測，不能自行改為只選 top-k。

正式 final 規範優先於較早簡報或會議筆記。每日截止為 Asia/Taipei 09:00；08:10 特徵凍結與08:20初次提交是提案，並非老師規定。不要把網站約04點更新的說法寫成已查證事實。

## 時間與資料

- 不可盲目套 `shift(2)`；先確認來源日期、交易時區、發布時間與現有位移。
- 僅使用 `available_at <= feature_cutoff` 的版本。即使同一天，當日收盤、最高最低、成交量、法人盤後資料也不可用於當日盤前輸入。
- 同一來源先在完整原生交易序列計算報酬，再按可用時間對齊目標日期。不得在多國日期 inner join 後假稱相鄰列就是連續來源交易日。
- `TX_OI` 是有正負號的淨部位，使用水準、差分或因果標準化；禁止直接用一般價格報酬百分比。
- VIX 的百分比變化是波動率指數變化，不能稱為可交易 VIX 資產報酬。
- 不得使用 bfill、centered rolling、全資料標準化、未來資料插值或事後修訂值冒充歷史可用值。
- 目標日期與股票全集保留；缺來源用 NaN / missing / age 等欄位處理，不靜默刪除目標列。

## 開發與驗證

目前只有 `scripts/audit_dataset.py` 可執行；其他 pipeline 尚待實作。建立必要的實際命令後才更新 README，禁止虛構已成功執行或已部署。

先用 `rg` 搜尋。每次只完成可審查的一段工作。對特徵計算加入必要測試：未來與晚發布資料不能進入、不同休市日、缺原生日期、零分母、負 TX_OI、重複鍵、版本修訂與跨時區。以預測日期分組做時間切分，同一天的不同股票不得分到 train / validation 兩邊。標準化、缺值填補、特徵選擇只用訓練資料 fit；堆疊使用時間有效的 OOF 預測。

保留資料與程式雜湊、欄位版本、參數、seed、切分、執行環境、官方 score。每次有意義的實驗更新 `docs/EXPERIMENTS.md`。至少比較四種有辨識度的可重現 ML pipelines。

## 儲存與外部操作

程式與文件適合私人團隊 Git repository；課程原始資料、帳密、cookie、token 不加入 Git 或 log。沿用來源授權與老師資料分享規則。不自動發布資料、不變更 repository 可見性。

依使用者已授權的範圍完成實作與測試。現在的排程是範本，尚未獲得啟用部署的指示；不得宣稱排程已啟用。競賽網站未驗證的 URL、登入方法、session 或提交 API 不得猜造。若後續使用者指示自動提交，先完成端點辨識、dry run、格式檢查、截止檢查與回執驗證，再按該授權執行。

## 收工

更新 `docs/STATUS.md` 的完成項、未完成項、實際執行的命令與下一個具體任務。只有確定的決策寫為 accepted；研究建議保留 proposed。資料來源或日期語意有新證據時，更新 `docs/DECISIONS.md` 與來源文件，不讓不同記憶檔彼此矛盾。
