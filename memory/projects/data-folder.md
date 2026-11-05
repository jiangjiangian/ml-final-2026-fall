# 專案：data 資料夾整合（本分支）

**狀態**：完成，已推送到 `claude/peaceful-babbage-09xeie`
**也叫**：yfinance 爬蟲、額外指標、data folder、schema、transform

## 使用者的要求（依時間）
1. 用 yfinance 匯入老師以外的全部額外指標，寫成爬蟲腳本；範圍 2020-01-01～2026-08-31；要台幣匯率。
2. 輸出一個 schema：所有特徵＝老師的＋額外的。
3. 全部資料整合成一個 `data/` 資料夾。
4. 爬蟲要**限流**。
5. 分支只推三樣：schema、完整 data 資料夾、crawler.py。
6. 開放 Yahoo 網域後跑爬蟲並推送。
7. 回答：額外指標是否全用 yfinance？→ 是，19 個都是（老師資料則是從 live-data 取 ZIP）。
8. 新增 `data/transform/lag2`、`lag5`：每個特徵各一個 CSV（close 的 return），先說定義讓使用者確認。
9. 分支只保留 data、schema、既有 skills，其他先不要放到 GitHub；寫 CLAUDE.md 與記憶文件。
10. `crawler.py` 也保留；等審查結果出來再修。
11. lag 定義改為 `(close_i − close_{i−k}) / close_{i−k}`，i＝前一個台股交易日（使用者選擇 i−2 與「前一個台股交易日」）。
12. 問：`features/` 資料夾是什麼？→ as-of 對齊的市場特徵表（見 CLAUDE.md）。使用者 2026-11-04 決定：先保留。
13. 在 root 做檔案樹並說明如何提供組員使用 → 新增 `README.md`（檔案樹、取得方式、X/y、lag 定義、注意事項）。
14. 問：100 股的 lag2／lag5 有包含當前的 y 嗎？→ 沒有：t 那列只用 t−1 以前的收盤；合併後 corr(y_t, stock lag2)＝−0.017，若誤用當日收盤則為 0.373。
15. 整合 lag2、lag5 成可直接用的 dataframe → `data/transform/panel_lag.csv.gz`（長表、100 股＋is_top50、label_ 前綴、CSV.gz）。
16. 驗證老師與額外指標的時間對齊 → 用 Yahoo 原始日K、小時K逐值比對，沒有對齊錯誤或洩漏，資料不需修改（證據見 `data-decisions.md` 的「時間對齊驗證」）。
17. 更新 schema → `timing_verification`（含 verified_against 資料指紋、applies_to_current_data）與 `extra.series.<id>.timing`；第三輪審查（3 審查者＋3 反駁者）的發現已修：TX_OI 改判疑似同日並在文件警告、DXY 時段與 15:00 ET close、老師個股不一致日的標籤、小時K範圍的措辭、跳空測試鑑別力分類、TWD=X 跨年證據、「08:00 前」改成「07:00 以前收完」。資料檔沒變。
18. deep-research：Phase 2 自動流程怎麼準時 → `deploy/README.md`（推薦 GCP Cloud Scheduler＋Cloud Run Job 為主、GitHub dispatch／Claude 雲端排程任務為備援、Healthchecks 監控；11/04 GitHub schedule 延遲 3h42m～6h17m 全被時鐘擋下）。待使用者決定：開不開 GCP、實作分支、能否建 Claude 排程任務、告警通道。
19. TX_OI 改前一列 → market_features 的 `TX_OI` 換成 `TX_OI_prev_row`；長表與 lag 檔本來就沒有 TX_OI，不受影響。
20. 資料範圍延長到 2026-09-30 → yfinance 19 序列限流重抓；9/1～9/30 的老師資料接 Live ZIP（`data/teacher_live/`）；接縫與 Live 慣例逐值驗證；timing_verification 的數字與資料指紋全部重算。Phase 2 自動化使用者說「等下再問」。
21. 第四輪審查（延長到 9/30；3 審查者＋3 反駁者，23 個發現去重約 12 項）已修：layout 的 TX_OI 文字、美股欄說法限定 Training、-1 待定值 fail closed（含 TX_OI）、Live 結構檢查（日期唯一、接縫重疊／間隔）、--keep-teacher 缺 Live 資料夾時報錯、CLI 參數組合檢查、date_range.data_end、指紋改用實際使用列、wti／us13w 相關係數改用 transform 的空值規則、memory 舊數字。資料檔沒變。
22. deep-research 第二輪（Phase 2 免費方案、raw→模型輸入、Mermaid）→ `deploy/README.md` 新增第 10～12 節。
    - 107 個 agent；25 條宣稱 3 票驗證，全部確認。
    - 全免費版（不綁卡）：Cloudflare Workers Cron＋cron-job.org 觸發 workflow_dispatch，GitHub runner 執行，Healthchecks 監控。
    - 綁卡版：GCP 只用 3 個 Scheduler job，仍是 0 元。
    - 第 11 節：同一個轉換函式；pandas merge_asof 和 Feast 已核對原文；11/04 待定列與 10/23 永遠不補的列。
    - 第 11.5 節的 5 個缺口等使用者確認。
    - 三張 Mermaid 圖已用 mermaid 11.12 渲染驗證。
23. 2026-11-05：只留兩個 claude 分支，其他封存 → `archive/system-completion/`、`live-data/`、`dev/`、`deep-research/`（`git read-tree --prefix`；每個子樹的 tree hash 等於原分支 tree）。
    - main 本來就是空的。分支由使用者自己在 GitHub 刪除，Claude 不刪。
    - 兩個 claude 分支都從 system-completion 的 `2a4c6cb` 長出來，所以 system-completion／dev／deep-research／main 的歷史都還在；只有 live-data（獨立歷史，12 個 commit）刪掉後只剩快照，建議先打 tag。
    - 預設分支是 system-completion：要先改預設才能刪。預設改成 main（空）後，每天的 workflows 會全部停。
    - 舊的 `deploy/README.md`（兩輪研究）依「暫時捨棄過去的研究」移到 `archive/old-research/deploy-README-2026-11-04.md`。
24. 2026-11-05：文件要容易懂、沒有 AI 味 → 找到 Humanizer（blader）plugin，給使用者安裝卡片；寫作規則記在 CLAUDE.md。`deploy/README.md` 重寫成從爬蟲到上傳的簡單說明＋一張流程圖（workflow：3 個讀程式＋1 個查 GitHub 文件 → 撰寫 → 事實／AI 味／新手三方審稿 → 修訂）。
25. 2026-11-05：新開 `claude/stock-market-challenger`（從空的 main），只放骨架和說明。
    - 使用者要求不受舊研究影響，參考一份 Cookiecutter 式的檔案樹。
    - 使用者決定：預設分支用空的 main；自動化方式之後再談，所以先不放 workflows。
    - 資料也放同一個分支，只有 `data/processed/` 不進 Git。
    - 11/05 GitHub 排程又晚約 4 小時：07:20～07:35 的排程到 11:31～11:39 才開始，16 個時點只觸發 5 個。
    - `course-benchmark.yml` 的上傳開關寫死 `'true'`，而且有已核准的模型；預設分支改成空的 main 後才會停。
26. 2026-11-05：查證 Phase 1（11/04 上傳，官方分數 0.000968）用的模型和特徵。來源是 `archive/live-data/runtime/objects/0e5401ee….bin`（產物包），對照逐位元相同的 `archive/system-completion` 程式。
    - 模型：因果 TCN，recipe `M3-2`。1x1 投影 31→32，3 個殘差區塊（kernel 3、dilation 1/2/4），dropout 0.1，head 只看最後一步；50 檔共用權重。
    - 訓練：目標是盤中報酬 ×100，MSE，Adam lr 1e-3，20 epochs，seed 42，只 fit 一次。輸出 > 0 判為 1。
    - 輸入：lookback 20 個日期，31 通道＝15 個標準化特徵＋15 個缺值旗標＋1 個存在旗標。median 補值和標準化只在 6/1 前的訓練日 fit。
    - 資料：訓練 2020-01-02～2026-05-29，77,674 列，Top50。預測 6/1～9/30 時權重固定，每天用該日之前的真實資料當輸入：6～8 月來自 Training ZIP，9 月來自 Live `432e5818…`。
    - 15 個特徵：7 個個股 lag（前兩筆觀測列）＋8 個 M0 市場特徵。市場值來自 Yahoo 原生歷史，以收盤＋2 小時當可用時間，截止 t 的 08:10。`tx_foreign_net_oi` 兩欄 100% 缺值，所以實際有資訊的是 13 個。
    - 選模：R2 共 48 fits＝12 個設定 × 2025 四季。合併分數 M3-2 0.000869，第二名 M4-1 0.000867（只差 1.6e-6），全猜 0 是 0.000447。逐季只有 2 季贏過全猜 0；2025 的 accuracy 51.7%，比全猜 0 的 56.5% 還低。
    - 洩漏檢查：沒有用到 t 當天的資訊。TWII／KS11 的值和同一列的當日報酬吻合 0/1521，US 指數都用前一個美股交易日，TX_OI 沒用到，個股特徵重算 77,674/77,674 一致。
    - 沒驗證的事：歷史 vintage（調整價和 Yahoo 資料都是最新版）、只跑一個 seed、6～9 月真實資料當 lag 輸入在 Phase 1 規則上是否允許。
27. 2026-11-05（從 `claude/stock-market-challenger` 的 session 做）：資料延長到 11/4。
    - Live ZIP 換成 live-data 上舊排程最後一次抓的 `eea89fce…`（11/05 08:55，9/1～11/4 填好、11/5 待定）。9/1～11/3 的列和舊的 `7f4c759a…` 完全相同。
    - 10/23 颱風假：使用者確認當休市日跳過，`LIVE_CLOSED_DAYS` 只列這天，其他 -1 照舊 fail closed。
    - yfinance 19 序列限流重抓；9/30 以前的值只有 Yahoo 還原價的浮點漂移（長表 ≤ 8.5e-7、market_features ≤ 9.6e-7，缺值位置不變）。
    - 10/1～11/4 用 Yahoo 核對：個股 2200/2200、^IXIC／^GSPC／^TWII 22/22、^KS11 21/22（韓國休市）。^VIX 13/22 列是前一個美股日的盤中值，不是收盤，開盤前就定下，沒有洩漏，記在 schema。
    - 測試照本分支規則放在 session 暫存區，沒有 commit：10/23 跳過、其他 -1 照舊報錯、休市日被填值時報錯，11 個通過。

## 做法摘要
- 單一 `crawler.py`（只依賴 yfinance＋標準函式庫），一次完成：限流下載 → 清理 → 老師資料 → market_features → transform → schema。
- 一開始把程式拆成 `ml_financial_prediction/` 的多個模組＋測試＋workflow，但使用者要求只推三樣後，合併成單檔，測試只留在 session 暫存區（未保存）。
- 起初環境擋 Yahoo（proxy 403），使用者開放網域後才實際下載。

## 第一輪審查（5 個獨立 agent，26 個發現）已處理
- 高：0052 漏調一拆七 → 分割回補。
- 中：老師 `^TWII／^KS11` 是當日收盤 → market_features 改用前一列；零量佔位K棒、TWD=X 壞報價 → 清理規則；yfinance lru_cache 讓重試沒真的發請求 → 清快取；yfinance 內部 tz/cookie 請求沒被限流 → HTTP 層限流；中斷時 manifest 不同步 → 每檔寫入；必要序列被略過不報錯 → 計入 missing_required；`--keep-teacher` 沒舊 schema 會失敗 → 直接驗證資料夾。
- 低：12 位小數截斷 → 完整精度；schema 文字修正；檔案權限 → 0644；連續被限流 → 熔斷。

## 第二輪審查（5 個獨立 agent）
- transform 248 檔逐格獨立重算：397,338 個非空白值全部一致、無洩漏；老師資料與 ZIP 逐位元組一致。
- 已修：
  - 高：0052 分割前股利調整只做約 1/7，造成除息日假的 −2%～−8% → 股利幅度 ×7。
  - 中：2024-11-20 三檔 ETF 的不完整K棒 → 低量平盤規則；`YFPricesMissingError`／`YFTzMissingError` 不重試 → 重試 1 次；熔斷時仍回報 complete → 新增 stale 狀態、結束碼 3；`--keep-teacher` 不核對 hash → `members_sha256`；schema 的 transform 路徑少 `data/` → 補上；文件說測試在暫存區 → 改成「沒有存放」；skills 依賴已移除的 `tools/` → 在 environment.md 說明取回方式。
  - 低：殖利率在債市假日的平盤K棒 → 刪除；非台股的疑似分割不再自動修改；清理後沒資料會覆蓋舊檔 → 先檢查；重新導向次數上限 5；`--timeout` 範圍寫清楚；最後一檔不再冷卻；`.gitignore` 加 `graphify-out/` 等；`.gitattributes` 對 skills 也設 `-text`；^KS11 證據、global 表描述、分割日期描述、反向分割說明等文字修正。
- 只記錄、未改資料：TWD=X close 常等於 open；STOXX50E 依瑞士假日缺 21 天；台灣 ETF 缺 2021-04-06；殖利率百分比報酬的極端值（使用者選擇保留）。

## 已知限制（交接時要說）
- 日期語意已用 Yahoo 原始資料驗證（2026-11-04）；但歷史上幾點真的抓得到（發布延遲）沒有驗證，所以仍標 research_assumption。
- TWD=X 日期 d 的 close≈倫敦 d 日 00:00～01:00 報價（台北 d 日早上），所以 usd_twd 特徵比名稱舊約一天；若要台北收盤，需另找來源（例如 live-data 的 FRED DEXTAUS，但那不是 yfinance）。
- 老師 global：Training 1,506 列＋Live 42 列（9/1～11/4，不含 10/23）；transform 的 teacher_* 只在「前一個台股日」是 global 日期時有值（lag2 1,545、lag5 1,542 列）。
- 授權：老師 ZIP 與 Yahoo 資料的公開再散布授權未核實。

## 數字
- 老師：Training 100 股、161,746 列、2020-01-02～2026-08-31；global 1,506 列、缺 112 個台股日。Live（9/1～11/4）4,200 列、global 42 列；10/23 颱風假的列不用。
- market_features：1,660 列 × 104 欄（date＋6 個老師市場欄＋97 個額外特徵）。
- transform：124 個特徵 × lag2／lag5 ＝ 248 個 CSV。
- panel：166,000 列 × 56 欄（50 個特徵），有答案 165,946 列，top50 83,000 列，7 MB；老師缺列仍是 54 格。
- data/ 約 72 MB：teacher 45M、transform 20M（含 panel 7M）、extra 3.2M、features 2.5M、teacher_live 1.6M。
