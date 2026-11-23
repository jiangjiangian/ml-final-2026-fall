# models/n1/

N1 影子跑（`src/models/m7_n1_js_online.py`，使用者 2026-11-23）的起始狀態。人 commit，之後只讀：排程和 n1 都不寫這裡。

## ub04_v5/

Kaggle UB 04 第 5 版（`modelnovice/ub-04-n1-js-online-replay-for-shadow-run`）輸出的 `n1_state/`，原樣複製。

- `meta.json`：54 個輸入的名字和順序、Top50 和 100 檔的清單、KD 05 的常數、每份狀態的最後更新日和內容雜湊、Kaggle 的套件版本。n1 每天核對常數和欄跟程式一樣。
- `norm.npz`：標準化的平均和標準差（float32）。
- `sha256.json`：UB 04 輸出的每個檔的 sha256，原樣保留。裡面還列了 `state_2026-11-20/` 和各資料夾的 `weights.npz`，這兩樣沒有複製（`state_2026-11-20/` 的 gspc 是暫代的定義，`weights.npz` 是給沒有 torch 時核對的）。n1 只核對用到的檔。
- `state_2026-11-12_kd05/`：和 KD 05 一模一樣的那份（11-12 更新完）。重現測試從這裡重播 11-13～11-20。
- `state_2026-11-20_yahoo_gspc/`：gspc 用 Yahoo ^GSPC、11-20 更新完。`.cache/n1/` 是空的時候 n1 從這份接。

每份狀態是 `seed0.pt`～`seed4.pt`（5 個種子的權重）和 `rng.pt`（torch 的亂數狀態，更新時的 dropout 要用）。

## 會變的狀態不在這裡

每天更新後的狀態寫在 `.cache/n1/ub04_v5/`（Git 不追蹤，只在 oop 本機）。每天的核對檔 `n1_<t>.csv`、`inputs_<t>.npz` 在 `data/submission/n1/`，排程和其他資料一起推。換起點或改特徵、美股的定義時，另外 commit 一個資料夾（例如 `models/n1/ub05_v1/`），config 的 `daily_model.n1.initial_dir` 改過去，`.cache/n1/` 會開新的一條。
