# 還沒決定的事

需要時問使用者。有答案後，把結果和日期寫進對應的檔，再從這裡刪掉那一節。

## 雲端主機的細節

- 使用者 2026-11-06 決定用雲端小主機跑 cron（見 `memory/context/pipeline.md`），不用 GitHub Actions。理由：GitHub 的 `schedule` 11/04 晚了 3 小時 42 分到 6 小時 17 分，11/05 16 個時點只觸發 5 個。
- 還沒定：用哪一家（提議 GCP 免費的 e2-micro，要綁卡）、誰的帳號、主機怎麼推資料到 GitHub（只能推這個分支的金鑰）、Healthchecks.io 的通知接在哪。
- 要先查：Yahoo 會不會擋雲端主機的 IP。

## 舊系統的排程停了沒

- 2026-11-05：GitHub 預設分支已經是空的 `main`，使用者因為 GitHub Actions 一直延遲而換掉。`system-completion` 最後一次排程是 11/05 台北 11:39，之後沒有再跑。使用者 2026-11-06 決定改用雲端小主機跑 cron。
- 換之前的狀況：`system-completion` 的 `course-benchmark.yml` 每天照排程跑，上傳開關寫死成開，舊模型也通過了上傳前的檢查。台北 08:20、08:27 這兩個排程準時觸發時，它會真的上傳。
- 這個分支把 `submit.enabled` 改成 `true` 之前，要先跟使用者確認舊排程已經停了。不然兩套程式會搶著交答案、用掉上傳次數。
- `system-completion`、`dev`、`deep-research` 使用者 2026-11-05 已在 GitHub 刪掉；`live-data` 還在。

## 每天的資料誰 commit、push

- 現在沒有任何步驟會 commit 或 push `data/raw/`、`data/processed/`。README 給組員的網址要等有人 push 之後才讀得到。
- 雲端主機上的 `run_daily.py` 要在 features 之後 commit、push 這兩個資料夾（只加這兩個路徑），寫到排程那一步再問。

## 組員的腳本要改讀新資料

- 組員的 `build_dataset.py` 和 Kaggle 的 `notebooks/kaggle/data/twfeat.py` 還在讀 data-collection 的 `panel_lag.csv.gz`（欄名 `ticker`、lag2 和 lag5、日K的 `usd_twd`）。
- 要改成 README 的網址，欄名是 `stock_id`、lag1 和 lag2、`usd_twd_am`，模型欄看 manifest 的 `model_columns`。第一次連網試跑、push 特徵表之後再通知組員。

## 正式流程用哪位組員的帳號

還沒決定。帳號密碼只放 `.env` 或執行環境的 secret。

## Phase 2 用哪個模型

- `configs/config.yaml` 先寫 LightGBM，之後依驗證結果換。
- Phase 1 的模型見 `memory/context/competition.md`。
- `claude/hopeful-brahmagupta-wikys1` 有 11/04 的 R4 模型研究，commit 訊息寫選了 E1 線性模型、LightGBM 沒贏 E1。選模型時可以參考。
