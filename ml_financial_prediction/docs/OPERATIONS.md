# 每日資料更新、候選訓練與提交

更新：2026-10-30，Asia/Taipei。使用者工作窗口為每日04:00～09:00；下列時程已有程式門檻／部署設定，尚未常駐啟用，耗時仍需實測。

## 現況與驗收範圍

已實作教師／Live及外部下載、不可變快照、原生日曆對齊、研究表、模型fit／候選比較、固定模型推論、提交與目前有效CSV回執核對。collect包含原四個外部來源、八個原生Yahoo序列及三類TWSE產業當日水準；取得成功仍不等於正式特徵可用。每日CLI有collect、train、predict、submit、verify五個stage，預設dry run；沒有實際POST、正式模型、常駐排程或五個交易日演練。

raw→daily表橋接已實作：train／predict未供表路徑時自動從私有課程快照準備七個個股滯後特徵。今日預測可用08:10前實際取得的bytes作observed_fetch證據，available_at必須等於fetched_at；這不證明歷史發布／調整vintage。strict歷史訓練仍blocked，顯式研究opt-in才準備research_assumption表，研究模型永不進approved或提交；也支援顯式verified表。市場額外來源有採集及消融，但未自動提升為正式daily特徵。

configs/daily.json是可審查的政策計畫，不是scheduler讀取的執行設定。實際stage程式及systemd timers各自帶有時段；修改計畫不會改變程式、啟動服務或觸發提交，需一併對照。

## 真實時鐘與時程

| 台北時間 | stage／動作 | 已實作門檻及未完成驗收 |
|---|---|---|
| 04:17／05:17／06:17／07:17 | collect，補抓來源並保存版本 | 正常TLS、來源schema／hash；先讀官方session，不靠星期推定 |
| 07:20～07:50 | train，候選訓練與驗證 | 僅完成且截止前可用歷史label；子程序限時終止，超時保留先前approved |
| 07:50前 | 模型比較與原子升級 | 候選、現有配置於相同更早train重訓並比相同validation鍵；只verified可升級 |
| 08:10起 | predict，凍結特徵與推論 | 08:10前已可用且已取得的私有快照證據；恰50股、欄位版本相容；禁止fit |
| 08:20 | submit | 官方開放／截止／配額、最新模型及CSV版本、持久鎖、先寫ledger；未實際提交 |
| 08:35 | verify | 從目前state取得記錄ID，下載有效CSV逐股比對；HTTP成功或ack不足以當回執 |
| 09:00 | 停止 | stage與提交在截止後拒絕執行，不將過期重跑算準時 |

07:55決策原為時間分配提案；目前train在07:50之前完成比較與升級，沒有另設promote stage。service層總上限不取代訓練子程序07:50停止門檻。

美股一般16:00 ET收盤，冬令對應台灣05:00、夏令04:00；提早收盤與VIX時點另核。因此04:17並非所有來源完整的保證。08:10是本版本操作cutoff，不是老師規定；晚發布／08:30後MIS不可塞入此版本。

07:20的訓練cutoff與08:10當日特徵cutoff不同。當日未知的OHLC／y不能因每日重訓而成為輸入；Live y=-1不能訓練；signed OI的-1另需逐格有效性證據，不能全表替換。

## CLI與私有runtime

以下均從業務目錄執行；CLI使用真實時鐘、預設當日台北日期。--target-date不能跳過04:00～09:00、官方session或資料檢查。runtime必須為Git外、目前使用者擁有的0700持久目錄，檔案0600。

~~~bash
uv run --locked --no-sync python scripts/run_daily_pipeline.py --runtime-dir /private/finpred-runtime --stage collect --dry-run
uv run --locked --no-sync python scripts/run_daily_pipeline.py --runtime-dir /private/finpred-runtime --stage train --dry-run
uv run --locked --no-sync python scripts/run_daily_pipeline.py --runtime-dir /private/finpred-runtime --stage predict --dry-run
uv run --locked --no-sync python scripts/run_daily_pipeline.py --runtime-dir /private/finpred-runtime --stage submit --dry-run
uv run --locked --no-sync python scripts/run_daily_pipeline.py --runtime-dir /private/finpred-runtime --stage verify --dry-run
~~~

這是依序在各合法時段執行的入口範例，不是已有正式模型或可一口氣執行的宣告。未供表即自動準備，但strict train會因歷史證據不足blocked；顯式--training-table／--prediction-table仍可覆寫來源選擇，須通過相同門檻。dry run禁止POST，仍允許已授權讀取、訓練與私有寫入。研究train加--allow-research-training才自動建研究表，結果永不升級；不能用於predict／submit。

獨立表準備可用scripts/build_daily_tables.py，接受--runtime-dir、--target-date、--kind training或prediction；training另可--allow-research。本次2026-10-30新快照在台北16:58取得，重建該日prediction正確blocked，因為晚於08:10。這是實際來源負向檢查，不是準時執行或五日演練；不改寫fetched_at繞過。

真正提交只由submit stage加--submit，在既有使用者授權及工程門檻滿足後執行，不重複詢問同一行動。目前尚未具備正式可提交資料／模型；不要手填true或改readiness略過證據。

runtime保存raw快照、candidates、approved.json、predictions、runs及提交ledger。各次run有唯一ID／來源版本與輸出hash，持久POSIX鎖避免並行覆蓋。不要把這些內容放Git或公開Actions artifacts。

## 模型與資料門檻

候選使用最近60個完整日期validation，更早至少252日期訓練。現有配置也在同一早期train重訓，不能拿已見validation的最近權重作假樣本外比較。初始模型須嚴格勝過train-majority基準，換配置須嚴格勝過同fold現有配置；既有同配置在有新增完成歷史、verified incumbent metadata、schema／政策相容且同fold不退步時，可作例行refresh，不要求它勝過自己的相同refit。全部要求verified；選定後才對截止前完整歷史重fit。這是程式接受規則，仍待持續運行驗收。

08:10推論表須恰50個唯一股票、正確目標日／cutoff與欄位版本，來源證據覆蓋模型特徵，綁定真實私有snapshot／payload雜湊及取得／可用時間。單純填available_at或readiness=verified不足以提供來源證據。daily builder的verified僅指當日已觀測bytes可用，不含歷史vintage核實；最新歷史close＋2小時仍屬研究假設。載入approved另檢查執行套件版本相容；GRU還需完整、已核實的中間序列歷史，不能把兩次預測之間的缺期跳過，目前缺此交付時生產推論blocked。

候選失敗／超時或不通過時保留相容且已驗證的approved；無此版本就blocked。預測後approved版本變更必須重新生成CSV，不能上傳舊模型結果。格式錯誤、過時來源、截止已過、缺股或無回執都保留明確失敗狀態。

## 提交與回執

競賽state、當日template已唯讀實測；POST JSON與回執下載路由由官方前端核實，詳細證據見[研究AUTOMATION](research/AUTOMATION.md)。尚未實際驗收server接受與真實回執。

CSV須exact日期、50個唯一ID與模板順序，值只能文字0／1。POST前查官方openAt／deadline／enabled／配額並在持久鎖內重查時間；正常TLS、禁止redirect及自動POST重試。先保存post_in_flight；未知網路結果先對帳，不盲目重送耗配額。已存在相同目前預測則不重複POST。

Phase2採最後有效版本，生成時間較舊的job不得覆蓋較新版本。只有state目前記錄對應下載CSV逐股匹配才標verified；score未算出可另標pending，不把HTTP200或檔案生成當成功。

## 執行器與部署狀態

| 方案 | 現況／條件 |
|---|---|
| 本對話／Codex | 無Tasks／排程工具，聊天結束後不能承諾代理自行常駐；互動workspace不是已驗證長期服務 |
| systemd timer | service及五個timers已建，未安裝／啟用；可在有持久磁碟的Linux執行器運行，不限學校主機 |
| 現有Actions手動設定 | 根目錄daily.yml，使用self-hosted／linux／finpred持久runner；無schedule，尚未啟用 |
| GitHub-hosted Actions替代 | 不需個人電腦，但需受控持久資料／模型／ledger、跨runner鎖、default branch入口與期限備援；尚未接入 |
| Kaggle | 只作比較，未登入或上傳課程資料；MCP不提供每日09:00前完成保證 |

使用者希望不依靠學校主機；SSH資訊不再是唯一部署路徑的前提。雲端替代仍需真正執行器和持久狀態，不是把聊天設提醒就等同完整管線。

GitHub workflow_dispatch和schedule都要求workflow存在default branch。main目前空檔案樹、程式在dev；不擅自改main或default branch，只在dev新增workflow也不會使其自動註冊。push CI的分支事件另論。schedule可能延遲或丟棄，應避開整點、有備援並保留09:00硬停止。GitHub cache或短命runner不是長期資料庫。

若選持久Linux主機，deployment/run-stage.sh接收FINPRED_PROJECT_ROOT、FINPRED_RUNTIME_ROOT，verified table路徑可選，不供即自動準備；歷史證據門檻仍不可繞過。憑證由主機secret提供，runtime.env.example只含示意值。以systemd-analyze檢查設定、確認時鐘／TLS／磁碟／登出後運行，再先演練。timers的Persistent=false防止重開機補跑過期提交。

正式啟用前仍需歷史發布／vintage證據、相容正式模型／fallback、持久執行器與恢復測試、五個官方交易日dry run，以及真實可提交時段回執驗收。當日表橋接已完成，不將當日取得證據冒充歷史核實。這些是未完成工程，並非再次索取已授權上傳或既有帳密；程式、快照及結果依規範保存至2027-01-31。

參考：[GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)、[systemd.timer](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)。完整部署解析檢查與API證據以AUTOMATION、最終整合測試以STATUS為準。
