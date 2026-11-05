# 每日資料更新、候選訓練與提交

更新：2026-11-03，Asia/Taipei。使用者工作窗口為每日04:00～09:00；GitHub-hosted入口、Public／default branch及課程Secrets均已落實，手動完整採集成功。第一個真實schedule事件、正式模型及競賽提交仍待驗收，不能稱整套服務每天準時運作。

## 現況與驗收範圍

已實作教師／Live及外部下載、不可變快照、原生日曆對齊、研究表、模型fit／候選比較、固定模型推論、提交與目前有效CSV回執核對。hosted collect有15個下載job，training另產template，因此共16來源：教師3、外部4、Yahoo8、TWSE產業1；41584330745及後續41593199735全數成功，研究特徵已匯出。每日CLI有collect、train、predict、submit、verify五個stage，預設dry run；尚無真實預測POST、正式模型或五個交易日演練。

raw→daily表橋接已實作：train／predict未供表路徑時自動從私有課程快照準備七個個股滯後特徵。今日預測可用08:10前實際取得的bytes作observed_fetch證據，available_at必須等於fetched_at；這不證明歷史發布／調整vintage。strict歷史訓練仍blocked，顯式研究opt-in才準備research_assumption表，研究模型永不進approved或提交；也支援顯式verified表。市場額外來源有採集及消融，但未自動提升為正式daily特徵。

configs/daily.json是可審查的政策計畫，不是scheduler讀取的執行設定。實際stage程式及systemd timers各自帶有時段；修改計畫不會改變程式、啟動服務或觸發提交，需一併對照。

隔離research shadow與固定cron-stage修正已隨`05eb17e`推送並通過CI41593711392；shadow41593711368與正式41593199708 attempt2還原演練成功，無預測POST。研究排程為07:25固定linear／weighted_classification／seed42 fit、08:13 shadow，不寫approved；研究queue為finpred-research-shadow、正式／collect為finpred-private-runtime，所有寫回仍共用durable Git lease／CAS。還原成功不代表實際盤前前瞻日或五日已完成。

## 真實時鐘與時程

| 台北時間 | stage／動作 | 已實作門檻及未完成驗收 |
|---|---|---|
| 04:17／05:17／06:17／07:17 | hosted collect，補抓來源並保存版本 | 原始採集獨立於官方競賽session與模型；正常TLS、來源schema／hash；下游預測另查官方session |
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

本機runtime保存raw快照、candidates、approved.json、predictions、runs及提交ledger，目錄0700、檔案0600。各次run有唯一ID／來源版本與輸出hash，持久POSIX鎖避免並行覆蓋。hosted另依使用者公開共享授權，把portable raw／derived及通過allowlist／credential掃描的持久狀態保存到`live-data`；不打包環境、session或cookie，不另公開Actions raw artifacts。

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
| GitHub-hosted Actions（目前採用） | hosted workflows、持久Git狀態、跨runner lease及default入口已接入；41584330745手動全16來源採集成功，首個schedule及正式模型／回執待驗收 |
| Kaggle | 只作比較，未登入或上傳課程資料；MCP不提供每日09:00前完成保證 |

使用者希望不依靠學校主機；SSH資訊不再是唯一部署路徑的前提。雲端替代仍需真正執行器和持久狀態，不是把聊天設提醒就等同完整管線。

GitHub schedule只從default branch執行；目前已實查為含workflow的`system-completion`，main仍空樹。使用者設定的Actions課程Secrets已由Training／Live實際下載驗證，不再列為待設定。下一個資料cron名義時點為台北2026-11-04 04:17（UTC11/03 20:17），尚須核對event=`schedule`的實際run。schedule可能延遲或丟棄，保留09:00硬停止，不將手動dispatch成功當作定時準時保證。GitHub cache或短命runner不是長期資料庫。

若選持久Linux主機，deployment/run-stage.sh接收FINPRED_PROJECT_ROOT、FINPRED_RUNTIME_ROOT，verified table路徑可選，不供即自動準備；歷史證據門檻仍不可繞過。憑證由主機secret提供，runtime.env.example只含示意值。以systemd-analyze檢查設定、確認時鐘／TLS／磁碟／登出後運行，再先演練。timers的Persistent=false防止重開機補跑過期提交。

正式模型／提交啟用前仍需歷史發布／vintage證據、官方前一交易日行情覆蓋、相容正式模型／fallback、持續運行與恢復驗收、五個官方交易日dry run，以及真實可提交時段回執。當日表橋接與原始bytes數值重建已完成，不將取得證據冒充歷史核實或供應商已更新。這些是未完成工程，並非再次索取已授權上傳或既有帳密；程式、快照及結果依規範保存至2027-01-31。

參考：[GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)、[systemd.timer](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)。完整部署解析檢查與API證據以AUTOMATION、最終整合測試以STATUS為準。
