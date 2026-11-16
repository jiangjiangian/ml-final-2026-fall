"""每日台股盤中方向預測的程式碼。入口是 repo 根目錄的 run_daily.py。

pipeline/：每天的流程，照執行順序編號。
    step1_crawler       爬蟲：老師的資料、yfinance、期交所、證交所和櫃買 → data/raw/
    step2_features      特徵：data/raw/ → data/processed/ 的特徵表（每列一檔一天，只用 t 之前的資訊）
    step3_train_predict 訓練和預測：照 config 選模型，用 t 之前的答案訓練，預測 t 的 50 檔
    step4_submit        上傳：寫 data/submission/submission_<t>.csv，送到課程網站再核對
    step5_merge_raw     合併原始資料：data/raw/ → data/merged/（給組員研究，模型不看）
    site_api、utils     課程網站的 API、各步驟共用的小工具（沒有編號，不是一個步驟）
models/：每天交件可以選的模型，照做出來的日期編號（m1 最早）。說明在 src/models/__init__.py。
"""

import importlib

# 2026-11-15 整理資料夾前的舊名字。只有 `from src import features` 這種寫法還能用（給組員舊的 notebook）；
# `import src.features`、`from src.features import X`、`python -m src.features` 都不能用，要改成新路徑
# （例如 `python -m src.pipeline.step2_features`）。新程式請直接寫新路徑。
OLD_NAMES = {
    "crawler": "src.pipeline.step1_crawler",
    "features": "src.pipeline.step2_features",
    "submit": "src.pipeline.step4_submit",
    "merge_raw": "src.pipeline.step5_merge_raw",
    "site_api": "src.pipeline.site_api",
    "utils": "src.pipeline.utils",
    "online_lr": "src.models.m1_online_lr",
    "persist_rule": "src.models.m2_persist_rule",
    "rank_ensemble": "src.models.m3_rank_ensemble",
    "c2_tilt": "src.models.m4_c2_tilt",
}


def __getattr__(name):
    if name in OLD_NAMES:
        return importlib.import_module(OLD_NAMES[name])
    raise AttributeError(f"module 'src' has no attribute {name!r}")
