"""每天交件可以選的模型，一個檔一個模型，檔名照做出來的日期編號。

| config 的名字 | 檔案 | 做出來 | 做法 |
|---|---|---|---|
| online_lr | m1_online_lr.py | 2026-11-05 | 組員的邏輯迴歸，每天早上重新 fit |
| persist | m2_persist_rule.py | 2026-11-12 | 持續性規則：過去一段日子比同伴強的一半猜漲，不用訓練 |
| rank_ensemble | m3_rank_ensemble.py | 2026-11-12 | 排名集成（Kaggle notebook 16 的 X_price）：ridge、kernel ridge、LightGBM 每天早上重訓 |
| c2、c2v2d | m4_c2_tilt.py | 2026-11-15 | rank_ensemble 再依大盤方向換高低 β（組員的 C2）；c2v2d 的方向模型多 6 個狀態 |
| overnight_up | m5_overnight_up.py | 2026-11-20 | 只給影子跑：前一晚美股大跌（隔夜訊號排進過去 250 天最極端的 10%）就全猜漲，其他日子照 rank_ensemble |
| rank_inst | m6_rank_inst.py | 2026-11-20 | 只給影子跑：rank_ensemble 的 41 欄加法人 23 欄（Kaggle notebook 33 的 X_inst）；早上法人資料沒到就傍晚補算 |

每個模型的 predict 都是同一個樣子：

    predict(data, cfg, dates, stocks) -> DataFrame
    輸入  data：step3_train_predict.load_model_input 的表（特徵表接上個股特徵）
          cfg：configs/config.yaml；dates：要預測的日子（YYYY-MM-DD 的 list）；stocks：股票代號的 list
    輸出  每個 date × stock 一列，至少有 date、stock_id、pred（1 = 猜收盤高於開盤），通常還有 prob（排名分數）
    訓練  在 predict 裡做，只用 t 之前有答案的列，每天早上從頭訓練、不存檔，所以 repo 根目錄的 models/ 是空的

算不出來就丟錯（各檔自己的 Error 類別），step3_train_predict 照 config 的 daily_model.fallback 換下一個。
新增模型：多一個 m7_<名字>.py，在下面的 MODEL_KINDS 加一行，config 的 daily_model.kind 就能填它。
只給影子跑、不能交件的模型再加進 SHADOW_ONLY。
"""

# config 的 daily_model.kind、fallback 可以填的名字 → 「模組:函式」。step3_train_predict 用到才載入。
MODEL_KINDS = {
    "online_lr": "src.models.m1_online_lr:predict",
    "persist": "src.models.m2_persist_rule:predict",
    "rank_ensemble": "src.models.m3_rank_ensemble:predict",
    "c2": "src.models.m4_c2_tilt:predict_c2",
    "c2v2d": "src.models.m4_c2_tilt:predict_c2v2d",
    "overnight_up": "src.models.m5_overnight_up:predict",
    "rank_inst": "src.models.m6_rank_inst:predict",
}

# 只能填在 daily_model.shadow 的名字（使用者 2026-11-20）：還在累積證據的規則和模型，填在 kind 或 fallback 會被擋下，不會交出去。
SHADOW_ONLY = frozenset({"overnight_up", "rank_inst"})
