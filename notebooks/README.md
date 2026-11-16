# notebooks

組員做實驗的地方。每天的自動流程（`run_daily.py`）不會讀這個資料夾，所以在這裡怎麼試都不會影響當天的上傳。

## 整理原則

### 放什麼

- `teammate/`：組員的 notebook。檔名 `NN_名稱.ipynb`，NN 是做的順序，新的一本用下一個號碼（現在到 `05`）。html 匯出放 `teammate/exports/`。
- `kaggle/`：在 Kaggle 上跑的研究。一個系列一個資料夾，名字是 `YYYY-MM-DD_vN_描述`；裡面一本一個資料夾，放 `notebook.ipynb` 和 `kernel-metadata.json`。
- 新的一類實驗：開一個新的子資料夾，裡面先放一份 `README.md`，寫這裡放什麼、檔名怎麼取。
- 試出來確定要用的特徵，搬進 `src/pipeline/step2_features.py`；確定要交件的模型，搬進 `src/models/`。訓練和每天的預測才會用同一份程式。

### 不放什麼

- 環境：只用 repo 根目錄的 `.venv`，做法在下面「在 VSCode 跑 notebook」。不要在這裡另外建 `.venv`（2026-11-16 刪掉了這裡一份 1.1 GB 的）。
- 資料：從 `data/` 讀，不要複製一份。notebook 要用 `data/market` 這種相對路徑時，在 notebook 旁邊建捷徑連到 `data/raw/`（`teammate/data/` 就是這樣做的）。組員給的輸入檔放在用它的 notebook 旁邊，不進 Git。
- 輸出：從 Kaggle 下載回來的 `output/` 是暫存，結果記進 `memory/` 之後就刪；要再看時用 `kaggle/pull_outputs.sh` 重新下載。
- 快取：`__pycache__/`、`.ipynb_checkpoints/`、`.DS_Store`，看到就刪。

### 什麼進 Git

現在只有這份 README 在 Git 裡，`teammate/`、`kaggle/` 只在本機。輸入檔、捷徑、Kaggle 的輸出就算之後要 commit 這兩個資料夾，也不會進 Git（`.gitignore`）。

## 寫 notebook 的注意事項

驗證要按日期切：先取出不重複的日期，對日期清單做切分（例如 `TimeSeriesSplit`），再把列對回去。直接對資料列用 `TimeSeriesSplit` 的話，切點可能落在某一天中間，同一天的 50 檔會被拆到兩邊。

notebook 裡用到的資料一律從 `data/` 讀，不要在 notebook 裡另外爬一份。老師資料在 `data/raw/teacher/training/` 和 `data/raw/teacher/live/`，特徵表在 `data/processed/features/`（讀法見根目錄 README）。data-collection 的舊長表在 `tests/fixtures/data-collection/transform/panel_lag.csv.gz`，只給測試當對照，只讀不改。

## 在 VSCode 跑 notebook

VSCode 只需要 `ipykernel`（Jupyter 的 Python 核心）。它不在 `requirements.txt` 裡，自己裝：

```bash
uv pip install --python .venv/bin/python -c requirements.txt ipykernel   # -c 讓 requirements.txt 鎖的版本不被動到
```

- 用 uv 建的 `.venv` 裡沒有 pip，VSCode 跳出來的「安裝 ipykernel」會失敗，要用上面的指令。用 `python -m venv` 建的可以直接 `pip install ipykernel`。
- 開 notebook 後，右上角的 kernel 選 `.venv`。選到系統的 Python 會在第一格 `import numpy` 就出錯。
