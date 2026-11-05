# ML研究工具、技能與Kaggle比較

本輪以官方網站、官方repository與實際本地安裝紀錄查核。下列來源為代理開啟原文核對（agent-checked），不是人類審閱或平台可靠性認證；正式報告的人類審閱仍待完成。未登入Kaggle、未建立Kaggle任務、未上傳課程資料。

## 本專案的採用決定

| 需求 | 採用方式與實際狀態 |
|---|---|
| PDF閱讀 | Microsoft MarkItDown 0.1.9、PDF extra已在獨立環境安裝；K-Dense技能已下載。沿用已驗證工具，不重裝。原PDF仍為公式、圖表及頁碼的查核依據 |
| 架構與文件導航 | 已安裝Graphify；變動文件重新萃取語意後再建圖，不以更新hash取代閱讀 |
| 環境 | 已可用cloud-environment-onboarding:setup，沿用uv／鎖定依賴；工具與ML專案環境分開 |
| 可重跑研究與報告 | 已有jupyter-notebooks、citation-management、scientific-writing技能；按任務使用，未再安裝重複版本。此項表示會話可用，非全部已vendoring到Git |
| CI除錯 | 本輪下載OpenAI官方gh-fix-ci技能；只在實際GitHub Actions PR失敗時使用，需可用gh與授權。未執行其腳本、登入或開PR |
| 安全檢查 | 本輪下載OpenAI官方security-best-practices技能，供下載／憑證／提交程式的有界安全工作；現有references主要是web框架，不能宣稱涵蓋本專案所有batch／ML風險 |
| 正式每日工作流 | 已準備systemd timer及Actions手動入口，尚未啟用。使用者後續希望不依靠學校主機，執行平台待定；此會話沒有Tasks／排程工具，不能把Codex互動環境當常駐服務。若選Actions，仍須處理default branch、受控持久儲存、跨runner鎖及截止延遲 |
| Kaggle | 按使用者決定先比較、不接帳戶；不加入正式09:00截止的依賴 |

## 新增官方技能的來源與驗收

官方來源為[OpenAI skills](https://github.com/openai/skills)，本輪固定commit `49f948faa9258a0c61caceaf225e179651397431`；兩個技能各保留原始Apache-2.0 LICENSE.txt、SKILL.md、所附scripts／references／agent設定及assets。

- `gh-fix-ci`：6個原始檔，在repository根目錄`.agents/skills/gh-fix-ci/`。
- `security-best-practices`：13個原始檔，在`.agents/skills/security-best-practices/`。
- 每個原始檔的上游路徑、固定commit URL、大小及SHA256寫入各自INSTALLATION.json；逐檔驗證相符，原始內容未修改。
- 已讀兩份SKILL.md及完整CI腳本；Python AST解析通過。CI腳本透過subprocess呼叫git／gh讀取PR檢查與log，並非自動安裝hook。沒有執行腳本、登入、外部通知、commit／push或安裝額外CLI。
- 技能中的一般工作流不重置使用者既有授權；仍依AGENTS與本會話範圍執行。安裝技能本身不代表CI、安全審查或部署已完成。

優先官方維護、可追溯版本、適用範圍與實際驗證；星數僅反映關注度，不能證明品質或安全。未找到本會話可呼叫的獨立`@workflow`工具；專案工作流由可執行程式與持久文件承載。

## Kaggle官方CLI與MCP

| 項目 | 本輪核實與限制 |
|---|---|
| 官方工具 | [Kaggle/kaggle-cli](https://github.com/Kaggle/kaggle-cli)的description為Official Kaggle CLI、非archived；舊kaggle-api入口已導向該官方專案 |
| Notebook執行 | 官方文件明示`kaggle kernels push`上傳程式／metadata後執行；`--no-run`僅保存版本。`kernels status`查執行狀態，`kernels output`取得指定版本輸出 |
| 私有與運算設定 | metadata有is_private、enable_gpu、enable_internet；官方文件說未指定is_private預設true，但範例明列false，因此未來接入必須顯式設private，不能直接複製範例。設私有不自動解決課程授權限制 |
| MCP | 目前ALL_TOOLS沒有Kaggle connector／MCP。查詢`Kaggle/kaggle-mcp`得到404，只能說該確切路徑不存在，不能據此宣稱全世界沒有官方或其他MCP |
| 第三方候選 | `arrismo/kaggle-mcp`可讀、非archived，本輪查得39星；未安裝、未審查或連接，不把其功能宣稱為已驗證 |
| 每日截止 | 已核實API功能不提供09:00前排隊、GPU取得或任務完成保證；官方公開文件中的功能存在，不等於本帳戶已具備配額或成功執行 |

官方CLI具備未來研究訓練後端所需的提交、狀態與輸出介面，現階段不需為此先裝第三方MCP。若往後接入，先核對課程資料可否送第三方、私有設定及帳戶配額，再用不含課程資料的小型fixture測試。正式執行平台須實際驗證截止、快照、模型版本、推論與回執，不能由工具名稱推論已具備這些條件。

## 本輪獨立整合查核

再次以INSTALLATION.json逐檔驗證OpenAI兩技能共19個原始檔的大小及SHA256，並解析所附Python腳本AST；均相符，沒有執行這些技能腳本。原本MarkItDown的單份PDF工具試轉與本輪32份公開講義的全文閱讀是不同證據，教材覆蓋與限制以FOUNDATIONS及TECHNIQUES為準。

再次開啟[GitHub官方事件文件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)，確認手動workflow也需要先存在default branch才會出現UI入口；已執行過的workflow才可再以API／CLI選其他ref。schedule亦只從default branch執行，官方明示高負載時可能延遲或丟棄。main保持空樹、程式只在dev的現況，不能靠提交一份dev workflow直接取得每日排程；可在不改main內容的前提下另行選擇default branch，但此輪尚未變更設定。

持久runner需要常開Linux運算環境；GitHub-hosted runner可免自行維護主機，但每次工作通常是新環境，受控原始快照、模型、ledger與跨工作鎖必須另有持久儲存。cache不能取代該資料庫。已準備的systemd／Actions入口與「持續五個交易日dry run成功、真實提交回執已核實」是不同驗收階段；後兩者尚未完成。

## 查核來源

| ID | 原始來源 | 支持事項 |
|---|---|---|
| TOOL-E01 | [OpenAI技能固定來源樹](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.curated) | 技能發布者、內容及授權；本地INSTALLATION.json逐檔hash |
| TOOL-E02 | [Kaggle CLI kernels文件](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md) | push／no-run／status／output功能；本輪原文HTTP200 |
| TOOL-E03 | [Kaggle metadata文件](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md) | 私有、GPU與網路設定；預設及公開範例的差異 |
| TOOL-E04 | [Microsoft MarkItDown](https://github.com/microsoft/markitdown)及本地MarkItDown INSTALLATION.json | 官方工具與K-Dense技能來源分開；已完成的單份公開PDF試轉 |
| TOOL-E05 | [Scientific Agent Skills論文](https://arxiv.org/abs/2609.00065) | K-Dense技能庫的來源引用；未將論文當成工具可靠性的實驗證據 |

TOOL-E05本輪開啟arXiv原頁，citation metadata為：Timothy Kassis、Vinayak Agarwal、Yuhuan He、Darshil Patel、Aubrey M. Brueckner；*Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*；2026；arXiv:2609.00065。頁面citation_date為2026/08/30。以上為代理核對的metadata，尚無人類驗證簽核；引用不附未核實的期刊或版本資訊。
