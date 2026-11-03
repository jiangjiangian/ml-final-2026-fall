# 專案背景

更新日期：2026-11-03，Asia/Taipei。此文件保留穩定背景；每日執行證據以STATUS為準。

這是 NTU 2026 Fall Machine Learning 的 final project。團隊建立可重現的台股盤中方向預測系統，結合個股、全球市場、籌碼與新聞資訊。使用者蘇的主要分工是資料爬取與文字分析，現在先建立市場環境特徵。

## 來源權威順序

正式 final 規範與後續官方公告 > 競賽當日 session 與模板 > 老師較早簡報 > 團隊 Docs > 研究提案。若日後官方更新，記錄版本與差異，不沿用過時日期。

已讀來源：final.pdf四頁、Financial_Prediction_with_SDAI_Motivation.pdf二十六頁、Note Oct 14, 2026_compressed.pdf十頁視覺筆記、2026-fall-ML Google Docs可讀文字、模板與資料包。另已完整讀取公開MOOC基石16份495頁與技法16份503頁的抽取文字，關鍵公式／圖像另視覺核對，詳細來源hash／頁碼見docs/research；這不代表本學期所有未提供教材已讀，也不是998頁全部圖片逐頁審閱。

Google Docs URL 與官方查核連結見 SOURCES.md。Google AI Mode 分享連結本次無法讀取；不得推測其中完整指數清單。Docs 中「美國正面評價就台股必漲」等說法是發想，不是可寫死的預測規則或已證明因果。

## 已確認的問題定義

目標是 open-to-close，不是昨收至今收，也不是隔夜跳空。外部市場訊號可能先反映在台股開盤價，因此「能解釋台股跳空」不代表「能預測台股盤中方向」。用相同時點的 walk-forward 驗證檢查增益。

起初使用者希望先看建議與選項；2026-10-25進一步授權在`dev`下載Graphify技能、先建專案圖，再實作市場特徵。2026-10-27明確要求開始既定流程，並重申整體目標為增加經濟／市場序列、每日04:00～09:00自動更新教師與額外資料並建立模型、計算指數報酬特徵。採ML系統生命週期分層；成熟現成工具優先，避免重複造輪子。

每日訓練建立候選模型，僅用已完成且截止前可用的歷史標籤；比較時將現有配置與候選在相同較早train重訓，再對相同validation鍵評分。通過檢查才升級，失敗／超時保留相容且已驗證版本。自動提交50檔預測CSV並核實回執已獲使用者授權，不重問相同行動。使用者後續另明確選擇程式與資料全部公開，憑證始終不得公開。

目前已實作四類模型×三目標研究、每日stage、raw→daily表橋接、推論、提交與回執程式；前端POST契約已核實、官方state／模板已唯讀實測，尚無真實預測POST或正式模型。未提供表路徑時自動準備七個個股滯後特徵；今日08:10前取得的bytes能證明今日可用，不代表歷史調整價當時可用。strict訓練仍blocked，研究opt-in只產research_assumption，不能升級或提交。M0／SOX／ADR消融未顯示增益，額外來源未自動納入正式表。

使用者希望不依靠學校主機，現在採GitHub-hosted Actions及`live-data`持久Git狀態。2026-11-03實查repo為Public、default為`system-completion`，main仍保留空樹；Actions課程Secrets已由完整採集41584330745驗證有效，全部16來源與研究特徵匯出成功。定時入口條件已滿足，下一個資料cron名義時點為台北11/04 04:17，首個event=`schedule`仍待驗收。本對話沒有Tasks工具，聊天代理本身不承諾常駐。

80ac804研究階段的新增要求：每天抓資料後供其他branch成員取得同一版本；另開研究分支蒐集金融競賽、學界／企業方法與至少四種模型；查Lauren Tan如何駕馭agent。對應成果在`deep-research`（使用者名稱含空白，已合法化），由dev@675d662建立，研究索引在docs/deep-research。當時集中採集＋私有快照／portable索引仍是提案，四架構只有藍圖，raw不進Git；這些是歷史狀態，後續實作與公開授權已更新如下。沒有取得ChatGPT Project其他未提供的內容。

## 本輪資料共享與完整系統要求

使用者另明確要求依Lauren Tan工作流完成未完成任務：建立`live-data`保存每天真實同步data，README有file tree及每個return／lag的意義；完成多模型Notebook與每日無學校主機的流程。最終選擇暫時全部公開，因此同一公開repo的`live-data`可保存raw／衍生資料，程式分支不混入raw，帳密永不進Git。教師／Yahoo再散布授權仍未核實，不把使用者選擇說成來源方授權。核心整合與default在`system-completion`，main保留空樹。

共享已實作不可變物件／可攜catalog、固定revision取用、時間／hash／修訂保留，以及features與labels分開的每日研究匯出。最新83000個50股日期格、100pending／26缺觀測label；source fetched_at與consumer receive分開。R1／E04有32個受控真實fits；新的Ridge／提升樹／causal TCN／跨股attention已完成R2全48fit、獨立逐鍵評分及可信模型重播，均為研究假設，不是正式上線模型。

hosted流程已有持久Git lease／CAS、pre-POST ledger、fresh官方state／deadline重查與失敗保存。本會話無建立Codex排程工具，Kaggle無MCP／本人帳戶憑證；官方CLI私人bundle與本地Notebook是已做的備援，真實cron／遠端kernel／合格正式模型／有效回執及五個官方交易日各自驗收。最新狀態、實際命令與外部阻礙見STATUS與COMPLETION_CHECKLIST，歷史PIT證據不足不改標verified。

隔離research shadow已隨`05eb17e`推送，CI41593711392、shadow還原41593711368與正式入口41593199708 attempt2均成功，沒有預測POST。研究排程以固定recipe fit，再用當日取得且通過來源／值重建的表產不可變前瞻預測，不升級或提交；尚未完成真實盤前前瞻日。研究GitHub queue獨立，所有寫回仍共用durable Git lease／CAS。這是累積未見未來的研究證據途徑，不能替代正式歷史PIT政策、approved模型或五個官方交易日驗收；官方state未列的未來日期不得製造。

## 資料觀察

固定資料包截至2026-08-31，2026-11-03雲端重抓內容未變。Live最新42日期09-01～11-03、100股4000完成／200pending，SHA256為`48b16f68beb92f679250a22d6e314f230e675d9d619b45c52048251aa25b78ed`；取得時為台北13:31，不能回填當日盤前證據。原10/27研究版本保持不變。固定global1506列，台積電1618列，後者有112個日期不在global；數值沒有NaN不代表完整日曆。詳細快照與當前來源證據見STATUS。

info.json只提供股票清單，沒有各欄時區／發布／位移說明。實測固定包IXIC／GSPC／VIX各1505/1505可比值匹配前一教師global列日期，不能等同前一美國session；固定TWII／KS11各1506/1506匹配同日收盤。Live IXIC／GSPC各37/37匹配前一美國session，VIX仍有不符此簡單規則的日期。來源匹配是數值觀察，不證明歷史何時發布／有無事後修訂。

已取得完整原生歷史並產出1655目標日研究市場表與SOX／TSM／NVDA報酬，OI因證據不足留空；歷史close＋2小時與個股前筆23:59可用性仍屬明示假設。詳細證據及strict／research界線以DATA_ALIGNMENT為準，不把raw下載成功當成正式可回測認證。
