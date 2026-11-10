# 環境、分支和工具

## 本機開發

- 電腦：macOS，zsh。系統 Python 是 3.14，專案要 3.12，用 uv 建虛擬環境。
- repo 的預設分支是空的 `main`，clone 時要用 `-b` 指定這個分支。

```bash
git clone -b claude/stock-market-challenger https://github.com/jiangjiangian/ml-final-2026-fall.git
cd ml-final-2026-fall
uv venv --python 3.12 .venv    # 或 python3.12 -m venv .venv
source .venv/bin/activate      # Windows PowerShell：.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt   # 沒有 uv：pip install -r requirements.txt
cp .env.example .env           # 填課程網站的 email 和密碼；COURSE_LIVE_KEY 先留空
python -m pytest               # 目前 117 passed、1 skipped
```

- 套件版本：`requirements.txt` 每個套件都鎖在發布滿兩週的版本。新加套件也照這個規則。

## 在這台 Mac 跑 notebook（2026-11-10）

- VSCode 要 `ipykernel`。根目錄 `.venv` 2026-11-10 加了：`uv pip install --python .venv/bin/python -c <當時的 freeze> --exclude-newer 2026-10-27T00:00:00Z ipykernel`，多 22 個套件，原本 60 個沒變，測試照樣通過。uv 建的 venv 沒有 pip，VSCode 的「安裝 ipykernel」按鈕會失敗；使用者原本因此選到 `/usr/local/bin/python`（Homebrew 3.10，沒有 numpy），第一格就出錯。
- `notebooks/.venv`（pyvenv.cfg 的 prompt 是 `nb-torch`，`.gitignore` 的 `.venv/` 會蓋到，VSCode 預設會找 `*/.venv`）：給要 torch、shap 的 notebook。這台是 Intel Mac，PyTorch 最後一個 x86_64 macOS wheel 是 2.2.2，用 numpy 1.x 編的；配 `.venv` 的 numpy 2.5.4 時 `tensor.numpy()` 丟 `Numpy is not available`。裡面是 numpy 1.26.4、scipy 1.17.1、pandas 3.0.6、scikit-learn 1.9.1、torch 2.2.2、shap 0.49.1、matplotlib 3.11.2、ipykernel 7.4.0。重建：`uv venv notebooks/.venv --python 3.12 --prompt nb-torch`，再 `uv pip install --python notebooks/.venv/bin/python --exclude-newer 2026-10-27T00:00:00Z --no-build pandas==3.0.6 scikit-learn==1.9.1 tqdm==4.70.1 'numpy<2' torch shap matplotlib ipykernel`（沒有 `--no-build` 會選到要用 cmake 編的 llvmlite）。
- 組員的 `notebooks/build_model.ipynb`、`feature_switch.ipynb`（沒進 Git）照組員自己的資料夾找檔案。2026-11-10 在 `notebooks/` 放了它們要的東西，都列在 `.git/info/exclude`，不進 Git：`tw_top100_industry.csv`（`notebooks/kaggle/data/` 那份，表頭改成 代號、名稱、市場別、產業別）、`sample_submission.csv`（`data/submission/submission_phase1_2026-11-07.csv` 的表頭和代號，值全 0）、`data/market`（連到 `data/raw/teacher/training/market`）、`data/data/market`（連到 `data/raw/teacher/live/market`）、`train_data_v2.csv`（254 MB，`build_model.ipynb` 產生）、`submission_holdout.csv`。`build_model.ipynb` 只改一行：`GITHUB` 網址的分支名從 `claude/peaceful-babbage-09xeie` 改成 `claude/data-collection`（分支改過名，舊網址 404）。
- 驗證（用 `.venv` 當 kernel、工作目錄 `notebooks/`，和 VSCode 一樣）：`build_model` 約 2 分鐘，165,946 列到 2026-11-04，兩個檢查都過；組員存的輸出是 163,746 列到 09-30，多的 2,200 列是長表後來補的 10 月以後（老師資料只讀到 `LAST_DATE`，這些列的個股特徵應該是空的，要用得把 `LAST_DATE` 往後改）。`feature_switch` 第 1～7 節 30 秒，和組員存的輸出 56 行裡 48 行相同，其餘是列數和小數第 5、6 位；第 6 節 ALL 那列完全相同（score 0.002053）。torch、SHAP 那幾格沒有完整跑完驗證，只確認同一組套件裡 torch 和 `.numpy()` 可用。

## 分支

| 分支 | 用途 |
|---|---|
| `claude/stock-market-challenger` | 比賽主程式（這個分支）。只在這裡 commit 和 push |
| `claude/data-collection` | 凍結的對照（使用者 2026-11-06 決定不再爬、不再更新）：資料整合成果（到 2026-11-04）和查證紀錄，`archive/` 封存了其他分支。`data/` 已搬到這個分支的 `data/raw/teacher/` 和 `tests/fixtures/data-collection/`。原名 `claude/peaceful-babbage-09xeie`，使用者 2026-11-05 改名 |
| `claude/hopeful-brahmagupta-wikys1` | 11/04 的 R4 Phase 2 模型研究（commit 訊息寫選了 E1 線性模型、LightGBM 沒贏 E1），含舊 workflows。只在選模型時參考 |
| `main` | 空的，預設分支（2026-11-05 查到已換好，等使用者確認） |
| `live-data` | 舊系統的共用資料分支，還在 GitHub 上；已逐位元封存在 data-collection 的 `archive/` |
| `system-completion`、`dev`、`deep-research` | 使用者 2026-11-05 已在 GitHub 刪掉；逐位元封存在 data-collection 的 `archive/` |

`hw6-jiangjiangian` 是無關的舊作業，不要碰。

## 舊系統（唯讀）

不要切到 data-collection 分支，用唯讀的 worktree（同一個 repo 的第二個工作資料夾）看：

```bash
git fetch origin claude/data-collection
git worktree add ../ml-final-archive origin/claude/data-collection
```

2026-11-05 已經建好在 `../ml-final-archive`（detached HEAD，2026-11-05 更新到 `a806959`，資料到 11/4）。需要時讀：

- `CLAUDE.md`、`memory/`：舊分支的規則和紀錄。
- `memory/context/data-decisions.md`：時間對齊驗證、限流的做法、Live 的慣例。
- `memory/projects/data-folder.md` 第 23～26 條：分支封存、寫作規則、這個分支的由來、Phase 1 的模型。
- `archive/README.md`：每個封存分支的 commit SHA 和還原方法。
- `archive/system-completion/`：舊程式。
- `data/transform/panel_lag.csv.gz`：整理好的 50 個 lag 特徵（2020-01-02～2026-11-04）。這個分支的 `tests/fixtures/data-collection/transform/` 有同一份。

使用者希望新流程不要被舊研究牽著走，只在需要時查。

## Claude Code 設定

- 輸出風格：`.claude/output-styles/team-docs.md`，由 `.claude/settings.json` 的 `outputStyle` 啟用。改了風格檔要重開 Claude Code 才會讀到。輸出風格不會傳給 subagent，所以 `CLAUDE.md` 也放了一份短版寫作規則。
- skills：裝在 `.claude/skills/`，已加進 `.gitignore`，不上傳 GitHub。雲端 session 沒有這兩個 skill，要用時照下面重裝。

| skill | 來源和版本 | 重裝方式 |
|---|---|---|
| graphify | PyPI `graphifyy==0.9.93`（2026-10-20 發布） | 見下方指令 |
| humanizer | `github.com/blader/humanizer`，commit `0ef9fe5`（2026-10-28） | `git clone https://github.com/blader/humanizer .claude/skills/humanizer && git -C .claude/skills/humanizer checkout 0ef9fe5` |

```bash
uv tool install --python 3.12 graphifyy==0.9.93
PY=$(uv tool dir)/graphifyy/bin/python
"$PY" -I -c 'from pathlib import Path; from graphify.install import _copy_skill_file; _copy_skill_file("claude", project=True, project_dir=Path("."))'
```

- 不要用 `graphify install`（會改全域的 `~/.claude/CLAUDE.md`）、`graphify install --project`、`graphify claude install` 或 `--strict`。它們會在 `CLAUDE.md` 或 `.claude/CLAUDE.md` 加一段，並在 `.claude/settings.json` 裝 PreToolUse hook，每次 Bash、Grep、Read、Glob 前都會觸發。
- graphify 的輸出 `graphify-out/` 也在 `.gitignore`。
