# 比賽和課程網站

## 要做什麼

每個台股交易日的台北 09:00 前，預測 50 檔股票當天的 y，上傳 0/1 到 https://final.html2026.csie.org 。哪些日子是交易日，以 `/api/state` 的 `phase2Days` 為準，不用星期幾推算。

## Phase 1 的結果（2026-11-04 交）

- 官方分數：0.000968。
- 模型：因果 TCN（只看過去資料的卷積網路），recipe `M3-2`，50 檔共用權重。目標是盤中報酬 ×100，輸出 > 0 判為 1。
- 特徵：15 個（7 個個股 lag、8 個市場特徵），其中 `tx_foreign_net_oi` 兩欄 100% 缺值，實際有資訊的是 13 個。
- 選模時的比較：2025 四季合併分數 M3-2 是 0.000869，全猜 0 是 0.000447；逐季只有 2 季贏過全猜 0。
- 細節：`../ml-final-archive/memory/projects/data-folder.md` 第 26 條。

Phase 2 用什麼模型還沒決定，見 `memory/context/open-questions.md`。

## 課程網站的 API

網址都寫在 `configs/config.yaml` 的 `course_site`，程式裡不要寫死。

| 用途 | 路徑 | 備註 |
|---|---|---|
| 登入 | `POST /api/auth/login` | JSON 帶 `email`、`password` |
| Training ZIP | `GET /downloads/fin_pred_data.zip` | ZIP 裡的路徑開頭多一層 `data/` |
| 當天範本 | `GET /api/sample-submission?phase=2&tradingDate={date}` | 用 `utf-8-sig` 讀，開頭可能有 BOM |
| 狀態 | `GET /api/state` | `phase2Days`、`openAt`、`deadline`、`uploadQuota`、`mySubmissions` |
| 上傳 | `POST /api/submissions` | JSON 格式見 `src/submit.py`；舊程式研究出來的，還沒實際送過 |
| 下載目前的提交 | `GET /api/submissions/{id}?record=current` | id 來自 `mySubmissions` |

`/api/state` 回傳的時間沒帶時區，當成 UTC。

## 上傳的規矩

- 截止：過了 t 當天台北 09:00 就不上傳。`submit.py` 自己用 08:50（`competition.upload_cutoff`），留時間核對。網站的截止更早時以網站為準。
- 順序照 `src/submit.py` 開頭：先查 `/api/state`（休市就結束，不算失敗；要在 `openAt` 和網站的 deadline 之間；`uploadQuota` 要有剩）。網站目前的有效提交和這份 CSV 一樣就不送。要送時，先在 `data/submission/upload_log.jsonl` 寫「準備上傳」，再 POST。
- 全新的雲端機器：這筆「準備上傳」要先 commit 並 push 成功才 POST，push 失敗就不上傳。不然下一次執行看不到紀錄，可能重送。
- POST 失敗或逾時：不自動重試。回去查網站有沒有收到。每天的上傳次數有上限。
- 核對：POST 拿到 200 也要把網站上的版本下載回來逐格比對，一致才算完成。
- 開關：`configs/config.yaml` 的 `submit.enabled` 是 `false` 時只印出要送的內容。改成 `true` 之前，要先跟使用者確認舊系統的排程已經停了（見 `memory/context/open-questions.md`）。
