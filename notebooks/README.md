# notebooks

組員做實驗的地方。每天的自動流程（`run_daily.py`）不會讀這個資料夾，所以在這裡怎麼試都不會影響當天的上傳。

建議的檔名，前面的編號是做的順序：
- `1.0_eda.ipynb`：看資料長什麼樣、缺值在哪裡、休市日怎麼表示。
- `2.0_feature_research.ipynb`：試新特徵。確定要用時，搬進 `src/features.py`，訓練和預測才會用同一份程式。
- `3.0_model_tuning.ipynb`：比較模型。驗證要按日期切（例如 `TimeSeriesSplit`），不要隨機拆列。

notebook 裡用到的資料一律從 `data/` 讀，不要在 notebook 裡另外爬一份。
