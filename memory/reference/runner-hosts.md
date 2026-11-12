# 排程主機

每天的流程在哪幾台主機跑、怎麼裝。排程的時間和決定的經過在 `memory/context/pipeline.md` 的「什麼時候跑」。

## oop（主跑）

`oop.cs.nccu.edu.tw`：Ubuntu 22.04、16 核、24 GB、時區台北。沒有 root，不能用 Docker。cron 在台北 07:10、07:25、07:40、07:55、08:05、08:25 跑 `run_daily_test.py --sync`（`deploy/crontab.txt`）。

1. 從校外要先連政大 SSL VPN（Ivanti Secure Access，伺服器 `https://sslvpn.nccu.edu.tw`）才 SSH 得進去。cron 在主機上自己跑，不需要 VPN。
2. 2026-11-06 在 oop 上用 pip 連不到 pypi.org，所以套件在 Mac 上下載 Linux 版，再複製過去：
   ```bash
   uvx --from pip==24.3.1 pip download -r requirements.txt --python-version 3.12 --implementation cp \
     --abi cp312 --abi abi3 --abi none --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 \
     --platform manylinux_2_28_x86_64 --platform any --only-binary=:all: -d wheels
   scp -r wheels nccuoop:~/wheels
   ```
3. 在 oop 上：
   ```bash
   curl -fsSL https://raw.githubusercontent.com/jiangjiangian/ml-final-2026-fall/claude/stock-market-challenger/deploy/runner_setup.sh -o runner_setup.sh
   WHEELS=~/wheels bash runner_setup.sh
   ```
   第一次會建 deploy key 並印出公鑰。到 GitHub repo → Settings → Deploy keys 加上它，勾 Allow write access，再跑一次。
4. 填 `~/ml-final-2026-fall/.env`，試跑 `.venv/bin/python run_daily_test.py --dry-run`。

`requirements.txt` 改了以後，要重做第 2、3 步重裝套件。

## Mac（備援）

`bash deploy/mac/setup.sh`：另外 clone 到 `~/ml-final-runner`，launchd 每天 08:15、08:25、08:35 跑。網站上已經有今天的提交就直接結束。2026-11-09 還沒裝，現在只有 oop 在跑。

## GCP（備用）

`deploy/gcp_setup.sh`：e2-micro 免費主機只有 1 GB 記憶體，流程高峰約 750 MB，要靠 swap，所以改用 oop。
