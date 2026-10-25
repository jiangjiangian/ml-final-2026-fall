# 資料與特徵交接格式

## 原始觀測紀錄

| 欄位 | 型別 | 定義 |
|---|---|---|
| source | string | 資料提供者 |
| series_id | string | 穩定的語意代碼；provider ticker 另存 |
| session_date | date | 原市場歸屬交易日，不能當可用時間 |
| event_time | timezone-aware datetime | 收盤、fixing或事件發生時間 |
| published_at | timezone-aware datetime / null | 可驗證的首次發布時間 |
| available_at | timezone-aware datetime | 此版本可進入模型的時間及保守延遲 |
| availability_basis | string | observed / documented / conservative_assumption；附依據 |
| fetched_at | timezone-aware datetime | 這次下載時間，不可冒充歷史發布時間 |
| value | numeric / null | 原始值 |
| unit | string | index_point / contracts / percent / decimal等 |
| revision_id | string | 此一資料版本 |
| source_url | string | 公開來源頁或資料集識別，不含token |
| payload_sha256 | string | 對應原始快照的雜湊 |

歷史版本鍵至少為 `(source, series_id, session_date, revision_id)`；同時保留發布時間。若同一session有多個版本，對每個預測時點選當時已可用的最後版本，再從可用session中取所需序列。不能用最新修訂值覆蓋全部歷史。

未有實際發布時間的舊資料應標記假設，經核實日期語意與保守可用時點後才進入回測。只有一個 date 欄不足以證明盤前可用。若缺少原生session日期，不得假裝能重建完整單日報酬。

## 市場特徵表

唯一鍵：`(target_date, feature_cutoff, feature_version)`。

主要數值：`ixic_ret_1s`、`gspc_ret_1s`、`twii_ret_1s`、`ks11_ret_1s`、`vix_level`、`vix_change_points`、`tx_foreign_net_oi`、`tx_foreign_net_oi_change`。名稱中的1s代表原市場一個session，只有完整原生序列才可使用此名稱。

每個來源另附 `source_session_date`、`source_available_at`、`age_hours`、`is_missing`、`is_new_session_since_previous_tw_target`。這些來源追溯欄不必全進模型，但必須可查。

休市與下載失敗分開標記。`latest_available` 特徵可攜帶上一個來源session的報酬並附age/fresh標記；若使用「自前個台股目標日以來的新資訊」定義，休市時可有另一個明確定義的零新增欄位。兩種不可混用，不能默默重複計數多日衝擊。

遇到停更或過舊值依來源自己的session日曆判斷，而非固定超過24小時就視為錯誤。週末正常陳舊與來源中斷不同。

## 個股訓練表

唯一鍵：`(stock_id, target_date)`。`stock_id` 保留字串，避免丟前導零；目標日期以當期模板為準。市場表以 `target_date` 與此次採用的cutoff/version left join 至個股表。fit imputer / scaler / encoder時僅使用該fold train資料。

`target_intraday_return`、`y`、當日收盤與盤後資料只能放label/evaluation區，不可混進輸入欄位。當日開盤價在09:00提交截止前也不應視為已完成的開盤成交價。

## 提交格式

Phase 1：完整50檔，第一欄id，其餘84個日期欄，完全沿用模板順序。Phase 2：第一欄id，第二欄是該次session日期，50列。值只能是整數0或1，沒有index附加欄、空值或機率。輸出後重新讀檔比對header、ID順序、列欄數、重複與值域。

本次模板首欄含UTF-8 BOM，讀取可用 `encoding='utf-8-sig'`；輸出是否保留BOM依網站可接受格式測試，不能把BOM誤當ID的一部分。

每次推論需另存 model_id、code_commit、feature_version、資料雜湊、cutoff、generated_at、CSV雜湊。提交後另存accepted/pending狀態與回執識別，HTTP 200本身不是有效提交的證據。
