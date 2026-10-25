# 當前狀態與交接

更新：2026-10-25。範圍：建議、資料檢查與Codex接續文件。

已完成：讀取正式規範、早期簡報、手寫筆記圖像、Google Docs文字、Phase 1模板與先前資料包；確認目標／score／截止；建立特徵與資料契約、完整ML系統目錄與模組分工；核對免費來源；提供未啟用排程範本。

未完成：來源逐欄時間對照、實際市場特徵引擎、模型訓練／回測、新增指數歷史下載、競賽登入與session更新觀察、GitHub部署、排程啟用與自動提交。沒有宣稱任何模型增益。

下一個任務：確認教師global_data.csv各欄位date和shift語意，使用正常日、台美不同休市日與長假各至少一例。建立可驗證available_at後，再實作M0。

已可執行：README中的 `python scripts/audit_dataset.py --zip ... --template ... --out ...`。範本config與workflow不可當作已完成pipeline執行。

阻礙：未有來源發布時間或位移 metadata；沒有競賽session與提交端點；沒有指定repo或執行主機；AI Mode分享頁不可讀。這些不阻礙文件、離線稽核與基礎特徵轉換設計。
