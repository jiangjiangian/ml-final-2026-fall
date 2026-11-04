# 執行環境、分支與 skills

## 雲端環境（Claude Code on the web）
- 對外 HTTPS 經 agent proxy；網域不在允許清單會回 403（CONNECT tunnel failed）。
- **Yahoo 需要開放**：`finance.yahoo.com`、`query1.finance.yahoo.com`、`query2.finance.yahoo.com`、`fc.yahoo.com`、`guce.yahoo.com`。2026-11-04 使用者已在環境設定開放。
- 裸 curl 打 Yahoo 會回 429，這是 Yahoo 擋非瀏覽器的正常回應；yfinance 用 curl_cffi 模擬 Chrome，所以可正常取得。
- 容器是暫時的；要保留的東西必須 commit＋push（但本分支只能放允許的檔案，見 CLAUDE.md）。

## Python
- 爬蟲用的套件版本（Python 3.12 venv 實測）：`yfinance==1.7.0`、`pandas==3.0.6`、`curl_cffi==0.16.3`。
- 版本挑選原則：發布滿兩週以上（yfinance 1.8.0 在 2026-11-03 才發布，所以不用）。
- yfinance 時區快取放 `~/.cache/finpred-yfinance`，不可放進 `data/`。
- 測試：曾寫 50 個 unittest（限流、重試、清理、transform、老師 hash），但使用者要求分支不放其他檔案，所以沒有存放，已隨 session 消失。

## Git
- remote：`https://github.com/jiangjiangian/ml-final-2026-fall`（Public）。
- 只推 `claude/peaceful-babbage-09xeie`；push 用 `git push -u origin claude/peaceful-babbage-09xeie`。
- 老師 ZIP 需要 `git fetch origin live-data`。
- 2026-11-04 依使用者要求，本分支移除了 `ml_financial_prediction/`、`.github/`、`graphify-out/`、`tools/`、`.codex/`、`README.md`、`AGENTS.md`、`RTK.md`；它們仍在 `system-completion` 與 git 歷史中。

## Skills（`.agents/skills/`，保留，內容與 system-completion 逐位元組相同）
這些是 Codex／agents 格式的 skill，Claude Code **不會自動載入**；需要時直接讀對應的 `SKILL.md`。

| skill | 用途 | 依賴已移除的檔案 |
|---|---|---|
| gh-fix-ci | 檢查／修 GitHub Actions CI | 無 |
| graphify | 產生程式／文件架構圖，輸出到 `graphify-out/` | `tools/setup_graphify.sh`、`tools/graphify-requirements.txt`；輸出目錄已在 `.gitignore` |
| markitdown | 把各種文件轉 Markdown | `tools/setup_markitdown.sh`、`tools/markitdown-requirements.txt` |
| rtk | 壓縮指令輸出以省 token | `tools/setup_rtk.sh`、`RTK.md`、`AGENTS.md`、`.codex/hooks.json` |
| security-best-practices | 安全最佳實務參考 | 無 |

要安裝這些 CLI 時，在本機從 system-completion 取回 `tools/`（已在 `.gitignore`，不會被 commit）：
```bash
git fetch origin system-completion
git checkout origin/system-completion -- tools   # 取回安裝腳本（會被加入 index）
git restore --staged tools                       # 取消暫存，留在工作目錄
bash tools/setup_rtk.sh                          # rtk init 會產生 RTK.md、AGENTS.md、.codex/（也已 ignore）
```
