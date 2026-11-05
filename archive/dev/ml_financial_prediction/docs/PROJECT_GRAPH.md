# Graphify 專案圖

已使用官方 [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) 的 graphifyy==0.9.95，先讀文件並完成第一版圖，再開始市場特徵實作。Codex 技能與 references 下載到 repository 根目錄 `.agents/skills/graphify/`，固定來源 commit、版本與技能 hash 見其中 INSTALLATION.json。

圖索引 ml_financial_prediction/ 的程式／設定與文件；排除技能本身、帳密、課程原始資料。根目錄輸出：

- graphify-out/graph.html：互動圖，瀏覽器直接開啟，無須 server。
- graphify-out/graph.json：節點、全部不同證據邊與來源位置。
- graphify-out/GRAPH_REPORT.md：社群、核心節點、跨文件連結與建議問題。
- graphify-out/semantic.json：文件語意片段、完整閱讀行數與來源 hash。
- graphify-out/health.json、raw_health.json、normalization.json：原始／正規化圖完整性稽核。

本機工具環境為 /workspace/.tools/graphify。若不存在，可從 repository 根目錄安裝：

```bash
UV_CACHE_DIR=/workspace/.cache/uv uv venv /workspace/.tools/graphify
UV_CACHE_DIR=/workspace/.cache/uv uv pip sync --python /workspace/.tools/graphify/bin/python tools/graphify-requirements.txt
```

已有環境時直接重建與查詢：

```bash
/workspace/.tools/graphify/bin/python tools/build_project_graph.py
/workspace/.tools/graphify/bin/graphify query 'available cutoff native session market'
```

文件更動後，先依技能重新萃取變動文件並更新 semantic.json 的內容／coverage／source_hashes。不能只改 hash 掩蓋舊語意。腳本拒絕尚未重新萃取的文件；程式 AST 在重建時刷新。

語意由現有代理萃取，未另用 Gemini key 或向外部 LLM API 上傳課程資料。代理工具不提供 usage，token／成本未知；工具的零值 placeholder 不是實測零消耗。社群採官方 NetworkX Louvain fallback。

正規化只刪整筆 JSON 一致的重複邊，並用官方 API 為明確 import 加 external stub。不同 relation／context／來源的同端點紀錄全部保留在 JSON／HTML；聚類採簡單連通拓撲，其合併計數不代表匯出證據遺失。HTML 顯示關係與 confidence，完整 context／位置查 JSON。

圖中的planned／proposed／blocked是文件狀態，不是已部署能力。真實研究特徵及四類模型已有結果，歷史date／shift／calendar／available_at與vintage證據仍限制正式接入，見SOURCE_ALIGNMENT.md及docs/research中的報告。

研究記憶包含32份公開講義閱讀、實際市場消融負結果、每日快照轉表／模型／提交邊界及尚未部署的執行器條件。圖用來追蹤依賴與證據，不替代實驗分數、來源認證或真實回執；當日observed_fetch與歷史PIT驗證必須分開。
