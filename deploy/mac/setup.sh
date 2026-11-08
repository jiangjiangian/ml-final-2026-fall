#!/usr/bin/env bash
# 在使用者的 Mac 上跑一次：另外 clone 一份（不要用平常改程式的那份），每天 08:15、08:25、08:35 跑備援。
# 網站上已經有今天的提交（主機交成了）就直接結束。Mac 睡著時 launchd 會在醒來後補跑，過了截止就不上傳。
# 這份 clone 用 HTTPS 推，帳密來自 macOS 鑰匙圈（平常那份 repo 能推就有）。裝完照最後印的指令手動試跑一次。
set -euo pipefail
BRANCH=claude/stock-market-challenger
REPO_DIR="${REPO_DIR:-$HOME/ml-final-runner}"
case "$REPO_DIR" in "$HOME/Desktop"*|"$HOME/Documents"*|"$HOME/Downloads"*)
  echo "不要放在桌面、文件、下載：macOS 的隱私保護會擋 launchd 讀這些資料夾"; exit 1;; esac
PLIST="$HOME/Library/LaunchAgents/com.mlfinal.backup.plist"

if [ ! -d "$REPO_DIR/.git" ]; then
  git clone --branch "$BRANCH" --single-branch https://github.com/jiangjiangian/ml-final-2026-fall.git "$REPO_DIR"
fi
cd "$REPO_DIR"
git config user.name "ml-final-runner (Mac)"
uv venv --python 3.12 --allow-existing .venv
uv pip install --python .venv/bin/python -q -r requirements.txt
[ -f .env ] || { echo "請把平常那份 repo 的 .env 複製到 $REPO_DIR/.env"; }
mkdir -p .cache
sed "s#__REPO__#$REPO_DIR#g" deploy/mac/com.mlfinal.backup.plist > "$PLIST"
launchctl bootout "gui/$(id -u)/com.mlfinal.backup" 2>/dev/null || true
for i in 1 2 3 4 5; do launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null && break; sleep 2; done
launchctl print "gui/$(id -u)/com.mlfinal.backup" >/dev/null
echo "裝好了：每天 08:15、08:25、08:35 跑 $REPO_DIR/run_daily_test.py --sync，紀錄在 $REPO_DIR/.cache/launchd.log"
echo "現在手動試跑一次（確認鑰匙圈的 GitHub 帳密能用）：launchctl kickstart -k gui/$(id -u)/com.mlfinal.backup"
