# R3 嘗試紀錄格式

`attempts.jsonl` 每行一次嘗試（成功與失敗都記），由 `scripts/run_r3_experiment.py` 自動附加，行數＝總嘗試次數。

| 欄位 | 意義 |
|---|---|
| `attempt` | 第幾次嘗試（從 1 起算） |
| `name`、`stage`、`hypothesis` | 設定名稱、階段（R3-0…）、對應假設 |
| `config`、`config_sha256` | 完整設定（含預設值）與其雜湊 |
| `code` | git HEAD、R3 檔案是否有未提交修改、各檔 SHA256 |
| `packages` | 套件版本 |
| `data` | 資料分支、panel／market_features SHA256、readiness |
| `status` | `ok` 或 `failed`（附錯誤摘要） |
| `official` | 用 `official_score.py` 重算的分數、準確率、鍵數（必須等於快速分數） |
| `summary` | 開發期分數、依日期 block bootstrap（5 日、2000 次）95% CI、市場擇時／個股相對拆解、逐年、2022–2024 與 2025、最差月份 |
| `paired_vs_baselines` | 與同一組鍵上各基準的成對差與 95% CI |
| `key_hash` | 計分鍵集合雜湊；只有雜湊相同才做成對比較 |

逐鍵預測、每日表與特徵快取放在 Git 外的 `--out-root`，不 commit。
