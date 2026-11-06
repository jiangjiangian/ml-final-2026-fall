#!/usr/bin/env bash
# 在排程主機上跑一次（不需要 sudo；重跑也安全）：deploy key、uv、clone、Python 3.12、套件、cron。
# 主跑是學校的 oop.cs.nccu.edu.tw（Ubuntu 22.04，時區台北）。步驟見 README「排程主機」。
#   bash runner_setup.sh                    套件從 PyPI 裝
#   WHEELS=~/wheels bash runner_setup.sh    套件從資料夾離線裝（oop 連不到 pypi.org，見 README）
main() {
set -euo pipefail
BRANCH=claude/stock-market-challenger
REPO_URL=git@github.com:jiangjiangian/ml-final-2026-fall.git
REPO_DIR="${REPO_DIR:-$HOME/ml-final-2026-fall}"
KEY="$HOME/.ssh/ml_final_deploy"
SSH_CMD="ssh -i $KEY -o IdentitiesOnly=yes -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4"

[ "$(date +%z)" = "+0800" ] || { echo "主機時區不是台北（$(date +%Z)），cron 的時間會錯，先停下"; exit 1; }

echo "== 1. GitHub deploy key"
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh" && touch "$HOME/.ssh/known_hosts"
if [ ! -f "$KEY" ]; then
  ssh-keygen -q -t ed25519 -N "" -f "$KEY" -C "ml-final-runner@$(hostname)"
  echo "   新建了 deploy key。把下面這行加到 GitHub repo → Settings → Deploy keys，勾 Allow write access，再重跑這個腳本："
  cat "$KEY.pub"; exit 0
fi
chmod 600 "$KEY"
grep -q '^github.com ' "$HOME/.ssh/known_hosts" || ssh-keyscan -t ed25519 github.com >> "$HOME/.ssh/known_hosts" 2>/dev/null

echo "== 2. uv（裝 Python 3.12 用，放在 ~/.local/bin）"
UV="$HOME/.local/bin/uv"
[ -x "$UV" ] || curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh

echo "== 3. clone 這個分支"
if [ ! -d "$REPO_DIR/.git" ]; then
  GIT_SSH_COMMAND="$SSH_CMD" git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"
git config core.sshCommand "$SSH_CMD"
git config user.name "ml-final-runner ($(hostname))"
git config user.email "ml-final-runner@users.noreply.github.com"
git pull --rebase --autostash origin "$BRANCH"
git push --dry-run origin "HEAD:$BRANCH" >/dev/null 2>&1 || { echo "deploy key 不能寫入：GitHub 上要勾 Allow write access"; exit 1; }

echo "== 4. Python 3.12 和套件"
"$UV" venv --python 3.12 --allow-existing .venv
if [ -n "${WHEELS:-}" ]; then
  "$UV" pip install --python .venv/bin/python -q --no-index --find-links "$WHEELS" -r requirements.txt
else
  "$UV" pip install --python .venv/bin/python -q -r requirements.txt
fi
.venv/bin/python -c "import pandas, sklearn, yfinance, curl_cffi; print('套件 OK')"

echo "== 5. 帳密"
[ -f .env ] || { cp .env.example .env; echo "   建了 .env，請填入三個值"; }
chmod 600 .env

echo "== 6. 排程（台北 07:10、07:40）：保留 crontab 裡別的行"
mkdir -p .cache
{ crontab -l 2>/dev/null | grep -v 'run_daily_test.py' || true; grep -v '^#' deploy/crontab.txt | sed "s#__REPO__#$REPO_DIR#g"; } | crontab -
crontab -l
echo "== 完成。試跑：cd $REPO_DIR && .venv/bin/python run_daily_test.py --dry-run"
}
main "$@"
