# n1 重現測試的參考檔

Kaggle UB 04 第 5 版（`modelnovice/ub-04-n1-js-online-replay-for-shadow-run`）的輸出，給 `tests/test_n1_model.py` 在 oop 的 `.venv-n1` 逐位元核對 `src/models/m7_n1_js_online.py`。原始檔在 UB 04 的輸出資料夾，sha256 對 `sha256_ub04.json`。

| 檔 | 內容 | 從哪來 |
|---|---|---|
| `js_preds_cont.csv` | 2026-11-13～11-20 每天 50 檔的 JS_ONLINE（300 列）。`js_yahoo_gspc` 是 gspc 用 Yahoo ^GSPC 的版本，重現測試比這欄 | `js_preds_ub04.csv.gz`（sha256 6cf4b599…）只留 `variant` 是 `production_inputs` 的列，字串原樣 |
| `gspc_yahoo_d06.csv` | 2020-01-02～2026-11-20 每個台股交易日的 gspc 輸入（Yahoo ^GSPC 照 D06 規則） | `us_compare_ub04.csv`（sha256 960b4b4e…）只留 `date` 和 `gspc\|yahoo:d06_rule` 兩欄，字串原樣 |
| `inputs_cont_ub04.csv.gz` | 11-13～11-20 每天 100 檔的 54 個輸入、K棒數、能不能更新、主目標。`spx_x__yahoo_gspc`、`gspc__yahoo_gspc` 是 Yahoo 版的兩欄 | 原檔複製（sha256 6d23ad12…） |
| `n1_picks_ub04.csv` | 11-17～11-20 的 N1：三個成員、β̃、p、JS、N1 的分數和 0/1 | 原檔複製（sha256 b569fee7…） |

- 老師檔和 `sox`、`tsm_adr`、`vix` 不放這裡：測試用 `git archive f02b89d` 從 Git 拿（正式流程 2026-11-23 凌晨的 commit，資料到 11-20）。
- 數字是 float64 的最短字串，要用 `float_precision="round_trip"` 讀。
- 不要改。UB 04 重跑或換起點時，另外放一個資料夾。
