# 每日自動化、提交介面與部署查核

本輪已完成提交程式、合成測試及部署設定檔；**沒有在Codex容器或學校主機啟用排程，也沒有向競賽網站提交任何預測**。模型與資料是否足以進正式提交，由整合pipeline的證據判定，不能用這份文件或HTTP成功代替。

## 已核實的競賽介面

來源為課程站正常TLS登入後的公開前端JavaScript及唯讀`GET /api/state`。只保留路由與去識別metadata；帳密／cookie只在記憶體。來源JS雜湊及當時slot／模板摘要在checkout外`/workspace/shared/research/automation/endpoint_evidence.json`。

| 介面 | 核實內容 |
|---|---|
| `GET /api/state` | `activePhase2Day`及`phase2Days`含`tradingDate/openAt/deadline/enabled/isCompetition`；`mySubmissions`為目前版本、`submissionHistory`為歷史；另有`uploadQuota` |
| `GET /api/sample-submission?phase=2&tradingDate=YYYY-MM-DD` | 直接實讀當時官方模板：`id,日期`及50檔股票 |
| `POST /api/submissions` | 前端已核實JSON契約：`phase:2, tradingDate, fileName, payload:{stockIds,predictions}, note`；本輪沒有呼叫POST，尚未實證正式server接受或回執 |
| `GET /api/submissions/{id}?record=current` | 前端目前提交的CSV下載連結；完成POST後須由目前state取ID再下載比對，不能猜receipt ID |

最近唯讀查核：官方active slot為2026-10-30，openAt `2026-10-29T07:00:00Z`、deadline `2026-10-30T01:00:00Z`（台北09:00），enabled=1、isCompetition=0；13個已公布slots。這是當時狀態，不把它硬編碼成今後交易日曆。正式執行每次重讀官方state，不以星期一到五代替官方session。

## 提交與驗證介面

`finpred.submission.CourseSubmissionClient`沿用既有HTTPS／記憶體登入，提供`state()`及`daily_template(target_date)`。

`validate_prediction_csv(csv_bytes, template_bytes, target_date)`保留股票字串與前導零，檢查正確日期、恰50個唯一ID、模板順序與文字整數0/1；拒絕機率、`1.0`、漏股、重複與附加欄。

`execute_submission(client, csv_bytes, target_date, runtime_dir, *, dry_run=True, generated_at=None, readiness=None, ...)`的real submit須有可信pipeline交付：

```json
{
  "model_validated": true,
  "feature_availability_verified": true,
  "feature_cutoff": "2026-10-30T08:10:00+08:00"
}
```

此結構是整合介面，不是要求使用者手填true來跳過驗證；root pipeline必須從已驗證模型與特徵manifest建立它。研究用／時間假設未核實的模型不得填為production-ready。

執行先讀state與官方模板；只在目標日台北04:00～09:00、官方openAt之後、官方deadline之前及配額可用時POST。時鐘須timezone-aware，截止邊界採嚴格小於；取得persistent lock後再查一次時間。學生帳戶須有官方隊伍。`dry_run`只驗證並回傳阻礙，沒有POST或建立提交ledger。

真正POST使用正常TLS、明確禁止redirect、無自動POST重試；伺服器2xx僅作acknowledgement。成功必須取得目前`mySubmissions`記錄，並由已核實CSV下載端點逐一比對50檔預測。score尚未算出可標`scoring_status:pending`，但只有CSV比對成功才標`status:verified`。

runtime內每個日期有POSIX檔案鎖及原子更新`latest.json`，檔案600／日期目錄700。舊job不得覆蓋生成時間較新的版本；已存在相同目前預測則不重複POST。先保存`post_in_flight`，網路失敗、程序死亡或沒有可核實回執時保留`unverified`，後續先與state／目前CSV對帳，不能盲目重試耗盡配額。鎖／ledger須放持久POSIX儲存；換成多主機或不支援flock的物件儲存前，須換成跨runner有效鎖。

CLI預設dry run（憑證只從環境讀取）：

```bash
uv run --locked python scripts/submit_predictions.py \
  --csv /private/prediction.csv --target-date 2026-10-30 \
  --runtime-dir /private/finpred-runtime --readiness /private/readiness.json
```

通過工程驗證的pipeline才加`--submit`；單純產生CSV不會自動提交。CLI使用同一開啟檔案的bytes與fstat mtime，避免上游原子替換檔名後把舊內容錯標為新版本。異常只輸出受控錯誤類型，不輸出cookie、帳密或來源response。

## 持久Linux主機部署設定

`deployment/finpred@.service`與五個`.timer`已建立，`run-stage.sh`呼叫實際Python pipeline入口。每日以Asia/Taipei觸發：

| stage | 時間 | 目的 |
|---|---|---|
| collect | 04:17／05:17／06:17／07:17 | 更新來源及快照 |
| train | 07:20 | 候選訓練；pipeline須在07:50停止，不靠service的35分鐘總上限替代 |
| predict | 08:10 | 凍結特徵並產生今日預測 |
| submit | 08:20 | 提交驗證後的50檔CSV |
| verify | 08:35 | 核對有效版本與回執 |

timer採`Persistent=false`，不在重新開機後補跑錯過的過期提交；資料是否需工作由pipeline依官方session判定。服務用`UMask=0077`、`PrivateTmp`及整組程序超時清理。沒有啟用任何service/timer。

在選定且已驗證的主機：

1. 同步完整dev程式、鎖定安裝環境；確認時鐘同步、正常TLS連線、持久磁碟及重開機後執行能力。
2. 將`deployment/runtime.env.example`複製到該帳戶`~/.config/finpred/runtime.env`，設實際業務專案／runtime絕對路徑，chmod600；帳密由該主機secret提供。初始`FINPRED_ENABLE_SUBMIT=0`。
3. 將unit／timers放`~/.config/systemd/user/`，檢查`systemd-analyze verify`；先手動執行各stage並驗收dry run。學校帳戶若登出後user manager會停止，需由該主機政策支援linger或等效常駐機制，不在Codex中假裝完成。
4. 完成五個官方目標日dry run後，按既有授權配置正式提交release及啟用timers；逐次檢查journal與private manifests／回執。主機未配置時保持未部署狀態。

使用者後續希望不依靠學校主機；上述units同樣可用於其他常開Linux主機。正式執行器／持久儲存尚未選定或連線驗證；本輪不以缺學校SSH作為停止其餘工作的理由。密鑰不能貼入Git或日誌。

## GitHub Actions與Kaggle的邊界

根目錄`.github/workflows/daily.yml`提供**manual workflow_dispatch設定檔**，沒有schedule；預設使用`self-hosted,linux,finpred`的持久runner及明確`FINPRED_RUNTIME_ROOT`。它沒有raw／模型／回執artifact公開上傳步驟。正式提交還須repository release旗標、人工選擇本次submit input以及pipeline證據全部通過；此旗標是工程啟用狀態，不是要求重新授權已同意的行動。

GitHub官方文件規定`workflow_dispatch`與schedule的workflow都須存在default branch。當前main空樹，workflow已隨11d7614推送dev，但不在default branch，所以不能宣稱UI/API已可觸發或每日已上線；dev push的CI已實跑通過。這輪不更改main、default branch或repository可見性。現有CI的dev push事件則與此不同。

若改用GitHub-hosted runner，必須先實作受控持久資料／模型／ledger儲存、跨runner鎖及備援；不能把短命runner或cache當資料庫。排程可能延遲／丟棄，仍須09:00截止檢查；目前沒有Codex Tasks/排程MCP工具可將這次聊天直接變成常駐服務。

Kaggle依使用者選擇只作比較，不接帳戶、不上傳課程資料。官方[kaggle-cli](https://github.com/Kaggle/kaggle-cli)可push並啟動notebook、查status及取輸出；MCP只提供連接介面，不提供可靠的每日deadline。未發現當前已連接的Kaggle MCP；第三方套件不能冒稱官方。若日後接入，課程資料第三方使用範圍須先核實，且不可照抄公開notebook範例的privacy設定。

## 實際驗證

- 19項提交合成／mock測試通過、Ruff通過，沒有真實POST。包括全集／順序／機率拒絕、deadline／時區、配額、模型／時間證據、ack無回執、未知網路結果、對帳、舊job保護、同檔bytes／mtime原子替換競態及redirect不重送。
- `bash -n deployment/run-stage.sh`、`systemd-analyze calendar`五種時點與`systemd-analyze verify`service／timers均通過。這是設定解析驗證，不是主機部署或五日演練已完成。
- 官方session及50股template取得成功，POST接受與實際回執留待具備有效模型／資料／時段後驗證。

參考：[GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)、[systemd.timer](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)、[Kaggle kernels](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md)。課程API證據來自實際登入前端與state，未猜造提交URL。

## 整合後的資料表與版本閘門

每日CLI在未提供表路徑時，已可從private runtime的實際教師／Live快照準備七個個股lag。選每個來源cutoff前最新manifest，檢查私有路徑、正常TLS紀錄、原始payload hash／大小，保留pending與觀測間距；今天的輸入只使用今天之前的個股列。observed_fetch以實際取得時間作available_at，並綁定原manifest及payload，不把本次取得時間回填到歷史。原七欄研究表重建82674列完全相同，無訓練／推論公式分岔。

訓練表仍缺歷史publication／vintage證據，strict會blocked；顯式研究opt-in只產research_assumption，不能升級正式模型。已完成的市場消融沒有勝過相同個股基準，故初始每日自動表採個股七欄；collect仍保存八個Yahoo市場日序列、四個官方外部來源與三類TWSE產業水準供後續研究。

候選cache綁定incumbent manifest／metadata、實際訓練表、相關程式及套件版本。初始／換配置要嚴格改善；已有verified同配置在新完成歷史、相同schema／政策及同fold不退步時可刷新。套件版本不符時拒載正式模型；GRU尚缺中間日期context，daily暫阻擋。模型／表／CSV完整性皆以實際使用的buffer綁定，不重讀檔名後將另一版本誤標成同一輸入。

`build_daily_tables.py --runtime-dir /private/runtime --target-date YYYY-MM-DD --kind prediction`可獨立準備目前輸入；training用`--kind training`，歷史未核實會exit2，研究才可加`--allow-research`。2026-10-30真實重抓在16:58台北，準備當日08:10表正確blocked；沒有假造當日盤前已取得。Python3.12整合188測試通過；3.10同數通過、選用GRU跳過1項。19項提交測試是其中一部分，非額外真實POST。
