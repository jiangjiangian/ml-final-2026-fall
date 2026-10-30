# Lauren Tan與官方工程師：如何少盯流程，仍拿到可驗證的成果

## 找到的是誰、哪些原始來源

已交叉核對React官方team頁列出的Lauren Tan／Cursor與GitHub `poteto`，以及Cursor官方plugins repo中的`pstack` README；README以作者第一人稱說明這是她在Meta／Netflix／Cursor經驗下使用的技能組。[AGT01](SOURCES.md#agt01)、[AGT03](SOURCES.md#agt03)、[AGT12](SOURCES.md#agt12)

任職頁面可能不同步：本次React頁列Cursor，而GitHub profile的company為`@xai-org`。本研究核對的是作者身份與工作流原文，不將其中一頁當成目前僱主已獨立證實。

官方來源：[cursor/plugins/pstack](https://github.com/cursor/plugins/tree/main/pstack)、[Cursor marketplace](https://cursor.com/marketplace/cursor/pstack)。本輪固定上游commit `4dd1d05818d19792e7cd6e818f1667f95f7e1dbe`閱讀核心原則與playbooks。這是**研究來源，不是已安裝或啟動pstack**。影片連線受代理限制，沒有把轉述的PR數量／agent數量當已核實效能。

作者的verification-skill-example明說產品Atlas／Harbor Labs是虛構範例，且省略driver。[AGT14](SOURCES.md#agt14) 我們借用其「功能入口→可跑驗收→證據」形狀，不將這個repo當成已驗證真實產品的案例。

## 她的核心思維

| 思維 | 原始來源支持 | 我們如何落地 |
|---|---|---|
| 先可靠地做好一件，再平行放手 | pstack README先談品質與可驗證性，再談parallelism | 先把官方score、資料時點與重跑命令做好；再分資料／模型／review |
| Lazy不是省略驗證 | Laziness Protocol偏向整合重複決策、縮小改動 | 共享資料契約，不在每個branch複製一套爬蟲／判斷規則 |
| 驗真實結果，而非「看起來完成」 | Prove It Works要求檢查實物，鼓勵可重跑檢查 | hash／逐鍵評分／實際deadline／有效回執分開驗收，CI綠不代表模型有效 |
| 用工具減少人力盯梢 | build-the-lever、verification skill、watcher與autonomous-run | 已知可檢查目標交給程序；人只看取捨、失敗與重要變更 |
| 控制主對話的context | Guard the Context Window要求分段限範圍 | 主代理保存摘要與決策，原始來源／長log放文件；代理只拿必要檔案 |
| 小步改、測量、保留或撤回 | Hillclimb要求固定量測與逐次決策紀錄 | ML需要再加研究次數上限、時間外資料與保留期保護，不能無限追validation |

原則與playbook原文已讀：AGT18–22。沒有因為外部技能寫了自動merge／Slack／指定模型，就替本會話新增這些操作權限或假裝工具可用。

**一個容易混淆的差異：** Lauren的README說自己不預設長篇planning，偏好可執行程式作規格；Cursor的Lee Robinson官方文章則建議複雜任務先規劃。[AGT12](SOURCES.md#agt12)、[AGT04](SOURCES.md#agt04) 不將兩人的偏好混成同一句話。本專案採「短任務契約＋可跑驗收＋分階段紀錄」：需要多步研究時寫計畫，簡單可逆修正直接做，不把寫長計畫當成果。

## AI公司官方材料提供的共同方向

- **OpenAI／Ryan Lopopolo：** 工程師的工作轉向提供意圖、環境與回饋迴路；AGENTS作導航，知識留在可版本化repo，架構與不變條件交給可執行檢查。[AGT05](SOURCES.md#agt05) 文中團隊的工時／PR數是其案例自述，不能當本專案生產力預測。
- **Anthropic官方實務文件：** 補模型看不到的資訊、給可跑的完成檢查；必須每次成立的規則用hook／權限／CI，而不是多寫幾個「IMPORTANT」。[AGT06](SOURCES.md#agt06) 這是產品文件建議，不是調查所有員工後的統計。
- **Google CLI context文件：** 專案／目錄層級context，讓必要規則就近載入。[AGT24](SOURCES.md#agt24) 本輪只引用context機制；不假設此Codex介面能使用其CLI功能。

三者的可移植部分：**人定義成功與取捨，agent自己找上下文、執行、用工具證明；重要規則有程式執行，不只靠口頭提醒。** 少盯不等於無人負責，也不等於對模型效能給成功保證。

## 適合你的最小操作方式

你提供三項即可：

```text
目標：讓各branch每天取得同一份最新且可追溯的課程＋市場資料。
驗收：乾淨checkout能下載指定版本並核對hash；連續記錄真實採集結果。
限制：原始資料不入Git、不改main；只問會影響成本、外部權限或研究目標的決定。

請自主完成。可獨立工作用subagent／隔離worktree；工具或用量不足就記錄並改用可行路徑。
每一階段提供實際證據，失敗不得改門檻充數。
回報300字內，固定「結論／完成／下一步」；長內容存文件，列清楚需要我決定的事。
```

模型研究改用：

```text
目標：比較四種金融預測架構，改善本課官方score。
驗收：相同股票日期全集、時間切分、完整baseline／負結果、來源與模型版本。
限制：R1特徵比較最多8設定，R2四架構最多12設定；不看未來、不重用已看過的holdout、不以加試直到贏作結束條件。
請先固定實驗契約，再分工執行；完成一組就核對、記錄，最後給我三點決策摘要。
```

上面的「限制」不表示每次都要你重複批准已授權的下載／提交；只把尚未決定的外部服務、費用與repo設定清楚列出。

## 主代理與子代理各負責什麼

主代理維護一份任務卡：目標、資料／程式版本、當前證據、下一步與真正阻礙。子代理各有檔案／問題範圍，並行時用隔離worktree或互不重疊檔案，不能只用不同branch名稱卻同時改同一工作目錄。

builder提交程式與可重跑證據；reviewer盡量拿新context獨立挑反例；主代理重跑關鍵檢查並整合。研究者可並行讀文獻，但主代理要檢查引用是否真的支撐結論、是否把月度／排名成果誤用到盤中方向。模型角色只在目前工具確實支援時配置，不能照抄pstack的模型名稱當成我們已具備那些模型。

前段文獻子代理遇到用量限制，由主代理接手蒐集；後續已恢復獨立子代理查核。只記錄實際完成的審查／萃取，不把失敗的分工算完成；具體驗證以STATUS為準。

## ML研究要修正一般coding的「一直試到贏」

功能修正通常有相對明確的真值，例如過去會壞的流程現在成功。金融validation分數則有噪音；越看同一段資料、越多次嘗試，越可能挑到偶然贏家。所以本專案不照抄無上限hillclimb，也不用「至少提升50%」之類任意數字強迫結果。

完成條件是**在固定預算內得到可重現、含負結果的比較與可決策結論**，不是保證一定打敗baseline。保留尚未見過的後續session，真的無增益時如實回報，避免agent為了完成指令偷改資料、metric或測試。

## 建議的三層完成標準

| 層次 | 完成證據 | 不能混為一談 |
|---|---|---|
| 工程 | 可重跑測試、乾淨checkout、真實輸入／輸出hash | 程式能跑不表示訊號有效 |
| 研究 | 同鍵時間外score、baseline、來源可用性、所有嘗試 | 歷史高分不表示已部署或能獲利 |
| 運作 | 真實定時執行、更新／回退、截止前提交與匹配回執 | workflow檔存在不表示每天已跑 |

context在一個可驗收階段結束、文件與下一步保存後再壓縮／開新會話；不要只留下「已完成」或一整坨聊天。Agent能自動找repo中的導航，無需每次將全部講義、log與舊對話塞回prompt。
