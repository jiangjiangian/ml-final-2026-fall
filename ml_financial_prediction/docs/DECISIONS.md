# 決策與待確認事項

更新：2026-10-30，Asia/Taipei。accepted代表有明確規範、授權或已驗證事實；proposed代表建議，不代表已部署。資料／程式實測不等於歷史可用性認證。

| ID | 狀態 | 內容 | 證據 / 影響 |
|---|---|---|---|
| D001 | accepted | 目標是盤中close>open，09:00截止 | final.pdf pp.1-2,4 |
| D002 | accepted | 官方score為方向乘盤中報酬 | final.pdf p.2；rank不是官方主指標 |
| D003 | accepted | 正式competition stage 11/16起 | final.pdf p.2；更新較早簡報日期 |
| D004 | accepted | 全球表已有6序列，TX_OI為淨部位 | 原始CSV及簡報p.11 |
| D005 | accepted | 舊global表少於2330表112個日期 | 離線資料稽核；不是NaN就能發現的缺漏 |
| D006 | accepted | 第一版M0採4股價報酬+VIX水準/變化+OI水準/變化 | 八欄引擎已實作；研究真實表已產出，OI兩欄因證據不足全缺，消融結果見EXPERIMENTS |
| D007 | proposed | 特徵固定08:10、08:20初次提交、08:35核對 | 保留到09:00的操作時間 |
| D008 | proposed | 使用私人團隊repo，raw資料不入Git | 老師分享限制、來源授權、版本控制需求 |
| D009 | proposed | 有常開主機則systemd，否則Actions+人員備援 | 排程精準度、維護成本與可用資源 |
| D010 | accepted | 正式M0僅接受有證據的版本化觀測＋明示原生日曆；研究假設需另標readiness | strict拒絕未核實歷史vintage；研究入口不改寫為verified，來源匹配不能取代發布證據 |
| D011 | accepted | 第一版一目標日一cutoff，cutoff不晚於該日09:00 Asia/Taipei | 遵官方截止；不硬碼08:10提案；跨時區實刻比較 |
| D012 | accepted | available_at決定可用資格，同session按此版本published_at選新版；全無發布時間才按available排序 | 混有／無發布與平手歧義fail closed；修訂id不當排序鍵 |
| D013 | accepted | 在dev工作；main目前空檔案樹且保留歷史 | 使用者明確要求；完整專案已保存dev，不改寫提交歷史 |
| D014 | accepted | Training與Live分開保存快照，不用Live取代完整歷史 | 固定包截至8/31；最新2026-10-30的Live涵蓋9/1～10/30共40日期，無info.json；較早研究版本原樣保留 |
| D015 | accepted | Live採助教新網域及正常TLS；curl -k僅作此次對照診斷 | 新網域POST /login及GET /data.zip成功；原IP加-k仍503、proxy上游TLS失敗，不保存insecure設定 |
| D016 | accepted | Live的-1與真值歧義須保留取得狀態，未完成列不能當有效label／feature | 服務頁明示；3700股票列有200個y=-1，10/23及10/27未齊；group狀態不是逐欄mask |
| D017 | accepted | 擴充市場序列、每日04:00～09:00更新教師與外部資料、候選重訓及指數報酬是整體開發目標 | 2026-10-27使用者重申；每日各階段分配為proposed，沒有啟用排程／自動提交 |
| D018 | accepted | 依ML生命週期分離資料取得、特徵／labels、訓練／評估、推論與監控；成熟現成工具優先 | 使用者要求及ARCHITECTURE參考；pyproject／uv.lock、Ruff與CI已完成；主要實作11d7614的遠端Python3.10／3.12檢查通過，run41031916837 |
| D019 | accepted | Live重抓需比較修訂，不能假設永遠只append | 新快照506233bytes、3600完整／100待完成，只10/23未齊；相對D016時點，10/27的100個股鍵及1個global鍵更新，沒有新增鍵；舊快照保留 |
| D020 | accepted | 本輪使用者明確要求每日自動取得教師與額外資料、訓練、提交競賽預測CSV並核實回執 | 更新較早人工提交的範圍；沿用本授權，不重問相同行動。端點／格式／截止／版本／回執驗證仍須完成，尚未部署；不包含公開raw資料 |
| D021 | accepted | 公開基石／技法32份講義抽取文字已完整讀至EOF，公式圖像僅關鍵頁另核對 | 基石495頁、技法503頁；報告與來源hash在docs/research，不冒稱本學期未提供教材或所有圖片已審閱 |
| D022 | accepted | 四族×三目標E00研究完成；研究模型不能正式升級／提交 | 48次2025向前fit及固定winner一次保留檢查；research_assumption，結果／警告及負結果見RETURN_RATIO |
| D023 | accepted | 提交程式／五階段CLI及部署設定已實作，尚未正式部署 | session／模板唯讀取得、前端POST契約與合成驗證；未POST、無真實回執；當日表橋接後續已完成，見D028 |
| D024 | accepted | 使用者希望可不靠學校主機；不以缺SSH阻止本地工作 | 最新要求保留雲端替代路徑；目前無對話Tasks排程工具，不承諾代理離線自行常駐 |
| D025 | proposed | 無學校主機時評估GitHub-hosted執行器＋私有持久儲存與備援 | 先補default branch入口、持久ledger／鎖及deadline延遲問題；未改main／default branch、未啟用cron |
| D026 | accepted | 官方技能來源固定版本、授權與逐檔hash，成熟工具優先 | Graphify／MarkItDown及OpenAI gh-fix-ci／security-best-practices已下載；不把安裝當CI／安全／部署驗收 |
| D027 | accepted | 初始／換配置須嚴格提高score；既有同配置可依受控規則新增歷史重訓 | 同配置refresh須verified incumbent、schema／政策相容、新完成歷史及同fold不退步；不要求勝過自己相同refit；仍非部署完成 |
| D028 | accepted | 每日stage未供表時自動從私有raw準備七個個股滯後特徵；當日與歷史證據分開 | observed_fetch的available_at=fetched_at，兩者皆須不晚於08:10；只能證明當日bytes已可得。strict歷史訓練仍blocked，研究opt-in只產研究表 |
| D029 | accepted | 最新資料取得不改寫已凍結研究版本；晚到來源必須blocked | 2026-10-30 Live541298bytes／40日期／3900完成＋100個10/23待完成；16:58台北取得不能重建當日08:10預測 |
| Q001 | partially verified | 固定美股三欄匹配前一教師global列日期；台韓欄同日close；Live美股兩欄前一native session | 逐欄匹配表及反例見DATA_ALIGNMENT；完整原生日曆已有第三方排程，但歷史發布／vintage仍未核實 |
| Q002 | partially verified | 固定ZIP截至8/31，最新Live9/1～10/30、40日期；網站宣稱00:00新增後逐欄更新 | 實際取得時間有manifest；完整發布排程／來源延遲／逐欄有效mask仍未提供，不把16:58取得當08:10已取得 |
| Q003 | pending | 04點更新的是session模板、行情、標籤還是排行榜？ | 使用者描述尚未驗證；不同任務排程不同 |
| Q004 | partially verified | 登入／下載、每日state／template及前端提交JSON契約已核實 | AUTOMATION記錄來源；未對真實server POST或驗收實際回執，不能以mock成功冒稱正式提交 |
| Q005 | partially verified | 已選jiangjiangian/ml-final-2026-fall與目前Codex Cloud；常開排程／長期儲存政策待定 | dev為工作分支，課程資料在checkout外；未啟用排程 |
| Q006 | partially verified | SOX／TSM／NVDA公開歷史已取，FRED raw已取，三類台灣產業有當日水準 | Yahoo並非已簽SLA／商用授權介面；歷史發布／vintage與產業歷史尚缺，不能宣稱全來源已正式接入 |
| Q007 | blocked | Google AI Mode分享頁內容 | 本次無法取得；待可讀文字或截圖，不推測清單 |

後續決策格式：日期、狀態、決策、理由、來源、被替代決策與版本影響。不要把待確認事項寫進穩定背景當成既定事實。
