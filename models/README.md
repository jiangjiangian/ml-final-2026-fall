# models/

放訓練好、存成檔案的模型（例如 `.pkl`、LightGBM 的 `.txt`），讓預測時可以直接載入、不用重訓。

現在每天交件的模型都不用這裡：`src/models/` 的每個模型都在預測那天早上用 t 之前的答案從頭訓練，算完就丟，不存檔。這樣每天都用到最新的答案，也不會有「檔案是哪一版訓練的」的問題。

模型的程式在 `src/models/`，選哪一個看 `configs/config.yaml` 的 `daily_model`。之後如果有模型訓練太久、要改成先訓練好存檔，檔案放這裡，並在 `src/models/` 的程式裡寫清楚檔名和訓練的日期。

## n1/

N1 影子跑（只記不交，使用者 2026-11-23）的起始狀態：Kaggle 訓練好的 JS_ONLINE 權重，人 commit、只讀。說明在 `models/n1/README.md`。
