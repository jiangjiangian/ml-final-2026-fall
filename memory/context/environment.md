# 執行環境與分支

## 雲端環境（Claude Code on the web）
- 對外 HTTPS 經 agent proxy；網域不在允許清單會回 403（CONNECT tunnel failed）。
- **Yahoo 需要開放**：`finance.yahoo.com`、`query1.finance.yahoo.com`、`query2.finance.yahoo.com`、`fc.yahoo.com`、`guce.yahoo.com`。2026-11-04 使用者已在環境設定開放。
- 裸 curl 打 Yahoo 會回 429，這是 Yahoo 擋非瀏覽器的正常回應；yfinance 用 curl_cffi 模擬 Chrome，所以可正常取得。
- 容器是暫時的；要保留的東西必須 commit＋push。

## Python
- 爬蟲用的套件版本（Python 3.12 venv 實測）：`yfinance==1.7.0`、`pandas==3.0.6`、`curl_cffi==0.16.3`。
- 版本挑選原則：發布滿兩週以上（yfinance 1.8.0 在 2026-11-03 才發布，所以不用）。
- yfinance 時區快取放 `~/.cache/finpred-yfinance`，不可放進 `data/`。

## Git
- remote：`https://github.com/jiangjiangian/ml-final-2026-fall`（Public）。
- 只推 `claude/peaceful-babbage-09xeie`；push 用 `git push -u origin claude/peaceful-babbage-09xeie`。
- 老師 ZIP 需要 `git fetch origin live-data`。
- 2026-11-04 依使用者要求，本分支移除了 `ml_financial_prediction/`、`.github/`、`graphify-out/`、`tools/`、`.codex/`、`README.md`、`AGENTS.md`、`RTK.md`；它們仍在 `system-completion` 與 git 歷史中。

## Skills（`.agents/skills/`，保留）
| skill | 用途 |
|---|---|
| gh-fix-ci | 檢查／修 GitHub Actions CI |
| graphify | 產生程式／文件架構圖（輸出 `graphify-out/` 已從本分支移除） |
| markitdown | 把各種文件轉 Markdown |
| rtk | 壓縮指令輸出以省 token |
| security-best-practices | 安全最佳實務參考 |
