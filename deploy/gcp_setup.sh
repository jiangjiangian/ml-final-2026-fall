#!/usr/bin/env bash
# 在 GCP 主機上跑一次（之後重跑也安全）：時區、swap、套件、clone、venv、git 設定、cron。
# 備用方案（主跑改成學校的 oop，見 deploy/runner_setup.sh）。用法：先照 README「排程主機」建好 deploy key
# （~/.ssh/ml_final_deploy，GitHub 上要勾 Allow write access），然後
#   curl -fsSL https://raw.githubusercontent.com/jiangjiangian/ml-final-2026-fall/claude/stock-market-challenger/deploy/gcp_setup.sh | bash
main() {
set -euo pipefail

BRANCH=claude/stock-market-challenger
REPO_URL=git@github.com:jiangjiangian/ml-final-2026-fall.git
REPO_DIR="${REPO_DIR:-$HOME/ml-final-2026-fall}"
KEY="$HOME/.ssh/ml_final_deploy"
SSH_CMD="ssh -i $KEY -o IdentitiesOnly=yes -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4"

[ -f "$KEY" ] || { echo "找不到 $KEY：先做 deploy key 那一步"; exit 1; }
chmod 600 "$KEY"

echo "== 1. 時區改台北（cron 照台北時間跑）、加 2 GB swap（主機只有 1 GB 記憶體）"
sudo timedatectl set-timezone Asia/Taipei
if ! sudo swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "== 2. 系統套件和 uv（裝 Python 3.12 用）"
APT="sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300"
$APT update -y -qq
$APT install -y -qq git curl ca-certificates cron
command -v "$HOME/.local/bin/uv" >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
UV="$HOME/.local/bin/uv"

echo "== 3. clone 這個分支（只抓這個分支）"
mkdir -p "$HOME/.ssh" && touch "$HOME/.ssh/known_hosts"
grep -q '^github.com ' "$HOME/.ssh/known_hosts" || ssh-keyscan -t ed25519 github.com >> "$HOME/.ssh/known_hosts" 2>/dev/null
if [ ! -d "$REPO_DIR/.git" ]; then
  GIT_SSH_COMMAND="$SSH_CMD" git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"
git config core.sshCommand "$SSH_CMD"
git config user.name "ml-final-runner (GCP)"
git config user.email "ml-final-runner@users.noreply.github.com"
git pull --rebase --autostash origin "$BRANCH"
git push --dry-run origin "HEAD:$BRANCH" >/dev/null 2>&1 || { echo "deploy key 不能寫入：GitHub 上要勾 Allow write access"; exit 1; }

echo "== 4. Python 環境"
"$UV" venv --python 3.12 --allow-existing .venv
"$UV" pip install --python .venv/bin/python -q -r requirements.txt

echo "== 5. 帳密"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "   已建立 $REPO_DIR/.env，請用 nano 填入三個值"
fi
chmod 600 .env

echo "== 6. 排程（台北 07:10、07:25、07:40、07:55、08:05）"
mkdir -p .cache
# 換掉舊的 run_daily_test 行和 crontab.txt 自己的 SHELL、PATH 兩行（重跑才不會一直多一組），別的行留著
{ crontab -l 2>/dev/null | grep -v -x -F -f <(grep -v '^#' deploy/crontab.txt | grep '=') | grep -v 'run_daily_test.py' || true
  grep -v '^#' deploy/crontab.txt | sed "s#__REPO__#$REPO_DIR#g"; } | crontab -
sudo systemctl restart cron
crontab -l

echo "== 完成。填好 .env 後試跑：cd $REPO_DIR && .venv/bin/python run_daily_test.py --dry-run"
}
main "$@"
