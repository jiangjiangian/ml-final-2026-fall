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
python -m pytest               # 目前 116 passed、1 skipped
```

- 套件版本：`requirements.txt` 每個套件都鎖在發布滿兩週的版本。新加套件也照這個規則。

## 分支

| 分支 | 用途 |
|---|---|
| `claude/stock-market-challenger` | 比賽主程式（這個分支）。只在這裡 commit 和 push |
| `claude/data-collection` | 凍結的對照（使用者 2026-11-06 決定不再爬、不再更新）：資料整合成果（到 2026-11-04）和查證紀錄，`archive/` 封存了其他分支。`data/` 已搬到這個分支的 `data/raw/teacher*` 和 `data/reference/data-collection/`。原名 `claude/peaceful-babbage-09xeie`，使用者 2026-11-05 改名 |
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
- `data/transform/panel_lag.csv.gz`：整理好的 50 個 lag 特徵（2020-01-02～2026-11-04）。這個分支的 `data/reference/data-collection/transform/` 有同一份。

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
