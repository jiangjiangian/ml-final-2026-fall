# Kaggle四模型研究與可重跑Notebook

Kaggle能在同一Notebook依次訓練多個模型，再按固定validation的官方score選擇設定。本專案已接上同一份比較程式：Ridge、HistGradientBoosting、causal TCN、市場引導跨股attention。每日例行更新只刷新研究選定的recipe，避免每天重新挑四種模型、反覆消耗同一段validation。

目前工具列表沒有Kaggle MCP，也沒有此使用者的Kaggle帳戶token；本輪採Kaggle官方CLI備援，**未登入、未上傳資料、未執行遠端kernel**。Notebook本地從頭執行與Kaggle遠端執行分開驗收。Kaggle排隊、runtime與quota不提供台北09:00前完成保證，適合研究訓練，不作唯一每日提交執行器。

## 已交付與實際驗證

- `notebooks/financial_model_comparison.ipynb`：三種模式demo／compare／report；只呼叫`finpred.training.architecture_comparison`，不複製訓練邏輯。輸出僅展示設定、分數、耗時與來源hash，不展示逐股原始資料或逐列預測。
- `scripts/prepare_kaggle_bundle.py`：離線建立或驗證不可覆寫的私人資料／程式包，不會自行呼叫Kaggle API。完整50股feature slots與labels分離，原始取得時間及readiness不改寫；準備成功不表示歷史vintage已核實。
- `configs/kaggle/kernel-metadata.json`：私人Notebook、CPU、無網路；username與dataset ID由準備指令填入。沒有複製課程帳密，資料license使用`copyright-authors`，不將原作者資料重新標成CC0。
- 已實跑12項bundle驗證測試，涵蓋固定版本、篡改、缺股、label混入、額外上傳檔、symlink／ZIP traversal、credentials、公開kernel與重新授權；Ruff通過。Notebook六個code cells已在本機從頭執行，demo為合成工程smoke，**不能算完整48-fit金融比較**。執行證據在Git外`/workspace/shared/research/completion-20261030/kaggle/`。

## 安裝：獨立於ML訓練環境

已驗證的選用工具為Kaggle2.2.5、nbformat5.11.1、nbclient0.11.0、ipykernel7.4.0；Kaggle2.2.5需要Python3.11以上，不放進支援Python3.10的核心ML依賴。從repo根目錄重建：

```bash
uv venv /workspace/.tools/finpred-notebook --python 3.12
uv pip sync --python /workspace/.tools/finpred-notebook/bin/python tools/kaggle-requirements.txt
```

Notebook執行還需既有ML環境的numpy／scikit-learn／PyTorch。請沿用專案locked環境，勿在模型實驗運行途中同步或更新共用venv。Kaggle無網路模式使用其預裝套件；遠端第一次啟動仍須核對實際版本／依賴可用性，沒有聲稱已驗收目前Kaggleimage。比較report會記錄實際Python與套件版本；版本不同不可宣稱結果必定逐位元一致。

## Notebook三種使用方式

| 模式 | 輸入 | 會做什麼 |
|---|---|---|
| `demo` | 固定合成50股資料 | 每架構一設定、一fold、神經網路一epoch，共4 fits；僅驗工程路徑 |
| `compare` | 鎖定training table、獨立全50股feature document、model config | R2十二設定×2025四季共48 fits；保存全部結果、baseline及負結果 |
| `report` | 既有`report.json` | 不重新fit，檢查48-fit／四架構／共同計分列數後呈現比較 |

未提供私人bundle時預設demo；Kaggle掛載已固定hash的bundle時預設compare。`FINPRED_QUICK_SMOKE=1`只作工程檢查，不能把四次fit標成完整研究。每次compare必須使用新的空輸出目錄；report模式讀舊輸出即可，不需重訓。

從業務目錄執行已完成實驗的報表模式：

```bash
FINPRED_NOTEBOOK_MODE=report \
FINPRED_RUN_DIR=/private/research/R2-four-architectures \
python - <<'PY'
import nbformat
from nbclient import NotebookClient

notebook = nbformat.read('notebooks/financial_model_comparison.ipynb', as_version=4)
NotebookClient(notebook, kernel_name='python3', timeout=600).execute()
nbformat.write(notebook, '/private/research/executed-comparison.ipynb')
PY
```

以上`/private/...`是使用者的Git外目錄示意；請使用具備ML套件與ipykernel的kernel。此處實際完整研究的report路徑為`/workspace/shared/research/completion-20261030/R2-f0-m0-four-architectures-v1/report.json`，最終完成狀態以report存在及STATUS為準，不以預期路徑冒稱已完成。

## 準備私人Kaggle輸入包

先取得本人Kaggle username，與API token分開。從業務目錄執行；下列`YOUR_KAGGLE_USERNAME`及`/private/...`必須替換，不能把token填進owner參數：

```bash
python scripts/prepare_kaggle_bundle.py \
  --table /private/research/training_table.json \
  --feature-rows /private/research/feature_rows.json \
  --config configs/research/model_families.json \
  --owner YOUR_KAGGLE_USERNAME \
  --out-dir /private/kaggle/immutable-run-v1
python scripts/prepare_kaggle_bundle.py \
  --out-dir /private/kaggle/immutable-run-v1 --verify-only
```

準備指令接受`training-table-v1`及`sequence-feature-table-v1`，必須保留每個日期50股feature slots，即使當日label未完成也不能刪除該股feature。data目錄只能有以下六個檔；kernel目錄只有Notebook與metadata，避免Kaggle CLI把同目錄不相關檔案一起上傳：

```text
immutable-run-v1/
├── data/
│   ├── training-table.json
│   ├── feature-rows.json
│   ├── model-config.json
│   ├── finpred-code.zip
│   ├── bundle-manifest.json
│   └── dataset-metadata.json
└── kernel/
    ├── financial_model_comparison.ipynb
    └── kernel-metadata.json
```

每個輸入／程式檔記錄bytes及SHA256；kernel內固定`bundle-manifest.json`的SHA256。資料集更新後若內容不同，舊kernel會停止，不會靜默改用新的latest。現有dataset_sources本身按slug取用，因此manifest pin負責偵測版本漂移；需切回精確對應版本或產生新的研究包，不能刪掉hash檢查。

## 帳戶設定與遠端執行

官方CLI支持`kaggle auth login`的瀏覽器OAuth，或在執行環境的**secret欄位**設定`KAGGLE_API_TOKEN`，亦兼容本人私有`~/.kaggle/access_token`／legacy `kaggle.json`。token不要貼聊天、放Notebook、寫Git或傳給課程網站；課程密碼不需要進入訓練kernel。設定來源：[Kaggle API token頁](https://www.kaggle.com/settings/api)。

帳戶可用且課程／來源授權允許私人雲端研究時，從選用工具環境執行：

```bash
# create預設private；不要加--public。保留JSON檔而不自動轉CSV。
kaggle datasets create --path /private/kaggle/immutable-run-v1/data --keep-tabular
kaggle kernels push --path /private/kaggle/immutable-run-v1/kernel
kaggle kernels status YOUR_KAGGLE_USERNAME/financial-model-comparison
kaggle kernels output YOUR_KAGGLE_USERNAME/financial-model-comparison \
  --path /private/kaggle/downloaded-run-v1
```

後續版本可用`kaggle datasets version --path ... --message '固定資料版本說明' --keep-tabular`；不要刪舊版本。先重跑`--verify-only`，再更新kernel中固定的manifest。`kernels push --no-run`只保存版本，**不會訓練**；不能以其成功當遠端執行證據。GPU沒有啟用，現有小型CPU模型也不會因設定GPU自動改成CUDA；若之後加速，另做版本／資源／結果相容驗收。

## 選模型與每日流程的界線

R2只在既有2025探索fold內選設定；同日股票同側、前處理只fit更早train。2026年1～5月已看過，不重稱unseen test。額外特徵R1、確認seed、融合都另立有限預算，不能一直增加嘗試直到勝過baseline。完整輸出會保留全0／全1／train-majority比較；未勝出也保存。

選到validation第一名不等於得到正式模型：歷史發布／vintage、向前未見session、daily schema、相容模型回退及有效回執仍要過門檻。Kagglekernel不登入競賽官網、不抓當日Live，也不呼叫提交端點。

官方來源已實讀並存URL／SHA256於Git外`/workspace/shared/research/completion-20261030/kaggle/`：

- [Kaggle CLI](https://github.com/Kaggle/kaggle-cli)、[authentication與使用方式](https://github.com/Kaggle/kaggle-cli/blob/main/docs/README.md)
- [Kernel metadata](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md)
- [Dataset metadata與license選項](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets_metadata.md)
- [PyPI版本](https://pypi.org/project/kaggle/)

目前剩下的遠端阻礙是本人Kaggle帳戶／token及首個實際remote run驗收，沒有要求再提供已存在的課程key。
