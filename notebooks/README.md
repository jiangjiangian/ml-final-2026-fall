# notebooks

組員做實驗的地方。每天的自動流程（`run_daily.py`）不會讀這個資料夾，所以在這裡怎麼試都不會影響當天的上傳。

建議的檔名，前面的編號是做的順序：
- `1.0_eda.ipynb`：看資料長什麼樣、缺值在哪裡、休市日怎麼表示。
- `2.0_feature_research.ipynb`：試新特徵。確定要用時，搬進 `src/features.py`，訓練和預測才會用同一份程式。
- `3.0_model_tuning.ipynb`：比較模型。

驗證要按日期切：先取出不重複的日期，對日期清單做切分（例如 `TimeSeriesSplit`），再把列對回去。直接對資料列用 `TimeSeriesSplit` 的話，切點可能落在某一天中間，同一天的 50 檔會被拆到兩邊。

notebook 裡用到的資料一律從 `data/` 讀，不要在 notebook 裡另外爬一份。老師資料在 `data/raw/teacher/training/` 和 `data/raw/teacher/live/`，特徵表在 `data/processed/features/`（讀法見根目錄 README）。data-collection 的舊長表在 `tests/fixtures/data-collection/transform/panel_lag.csv.gz`，只給測試當對照，只讀不改。

Jupyter 不在 `requirements.txt` 裡，要用的話自己 `pip install jupyter`。
