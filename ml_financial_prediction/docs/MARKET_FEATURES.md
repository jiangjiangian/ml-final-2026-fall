# M0 市場特徵：已實作介面

更新：2026-10-25。核心與 CLI 使用 Python 3.10+ 標準函式庫，另需系統有 Asia/Taipei 時區資料。所有測試／demo 都是合成資料，不是模型回測。

## 輸入

observations.json 是觀測物件陣列，每筆需有 DATA_CONTRACT 的全部欄位及非空 availability_evidence。以下僅示意一筆合成觀測：

```json
{
  "source": "synthetic_demo",
  "series_id": "ixic",
  "session_date": "2026-07-02",
  "event_time": "2026-07-02T20:00:00+00:00",
  "published_at": "2026-07-02T20:00:00+00:00",
  "available_at": "2026-07-02T20:10:00+00:00",
  "availability_basis": "conservative_assumption",
  "availability_evidence": "SYNTHETIC example only, not source evidence",
  "fetched_at": "2026-10-25T00:00:00+00:00",
  "value": 110,
  "unit": "index_point",
  "revision_id": "synthetic-v1",
  "source_url": "https://example.org/synthetic",
  "payload_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

source_url 是不帶帳密、query、fragment 的公開識別；範例 hash 為占位，真實輸入須使用實際快照 hash。所有時間帶時區。published_at 可為 null；若有值，指**此版本**首次發布時間。available_at 不早於事件／發布；fetched_at 不早於事件／已知發布，但歷史下載時間可以晚於 cutoff。

允許 series_id：ixic、gspc、twii、ks11、vix、tx_foreign_net_oi。價格／VIX 單位為 index_point，OI 為 contracts。值可為 null，否則必須是有限數字；布林、NaN、Inf 均拒絕。availability_basis 接受 observed、documented 或有依據的 conservative_assumption；引擎不會替呼叫者認證證據真偽。

sessions.json 逐系列提供完整原生日曆，例如：

```json
{
  "ixic": {
    "source": "synthetic_demo",
    "session_dates": ["2026-07-01", "2026-07-02", "2026-07-06"],
    "calendar_evidence": "SYNTHETIC calendar; not production evidence"
  }
}
```

每系列只接受一個來源；日曆唯一且有序，涵蓋所有觀測。呼叫者需提供完整原生 session，包含缺觀測的交易日，不能從交集日期或有資料列倒推日曆。引擎能檢查格式／一致性，不能證明日曆真實完整。完全無觀測的系列可省略日曆，所有目標日期仍保留。

targets.csv 明示目標日與 cutoff：

```csv
target_date,feature_cutoff
2026-07-03,2026-07-03T08:10:00+08:00
2026-07-06,2026-07-06T08:10:00+08:00
```

第一版每個目標日一個 cutoff，重複日期拒絕，輸出按日期排序。cutoff 可以更早，但不得超過該目標日 **09:00 Asia/Taipei**；08:10 是範例選擇，不是硬性預設。比較實際時刻，不靠 UTC 日期字串。

## 計算與版本

1. 僅納入 available_at <= cutoff 的版本。
2. 同 session 選此版本 published_at 最新者，避免較晚可用的舊發布版覆蓋新版；全無 published_at 時才按 available_at 排序。部分有發布時間、部分沒有，或發布／可用時間平手有歧義時，拒絕，不用 revision_id 猜順序。
3. 從可用 session 取最大的 session_date；舊 session 的新修訂不能取代較新 session。
4. 依原生日曆找唯一前一 session，使用同一 cutoff 的版本。缺觀測／缺值／未發布時輸出 missing，不跳過缺口。

| 主欄位 | 計算與單位 |
|---|---|
| ixic_ret_1s、gspc_ret_1s、twii_ret_1s、ks11_ret_1s | (current - previous) / previous，小數報酬；零分母 missing |
| vix_level、vix_change_points | 水準及點數差，不是可交易資產報酬 |
| tx_foreign_net_oi、tx_foreign_net_oi_change | 淨部位水準及口數差，允許負數／零／跨零，不用百分比 |

最新 session／版本為 null 時不回退舊有效值。VIX／OI 水準可在差分缺值時保留。來源休市時 latest_available 攜帶相同來源報酬，附 fresh=false，不改成零新增報酬。

每系列附 `<series>_source_session_date`, `_source_available_at`, `_age_hours`, `_is_missing`, `_is_new_session_since_previous_tw_target`。available_at／age 取此次轉換實際使用版本的最大可用時間；age 不是停更分類器。is_missing 表示系列任一主數值缺失；第一列 fresh 留空，之後只在新來源 session 到來時為 true，修訂不算新 session。

報告保存 current／previous 完整證據、應有前一 session、缺值原因與計數、來源狀態。未提供預期發布排程時，正常休市與下載失敗無法只靠 age 區分，標 unknown。CSV null 為空欄，品質布林為 True／False，不輸出 NaN／Inf。

## 操作與範圍

執行 README 的 demo／CLI 命令，或使用 `from finpred.features.market import build_market_features`；回傳 FeatureResult.rows 與 FeatureResult.report。CSV／報告已以合成資料跑通。

CLI manifest 保存 Python 版本、程式 commit／dirty 狀態、程式雜湊、三個**實際讀入 buffer** 的輸入雜湊與 CSV 雜湊。輸入只讀一次，避免同時更新造成 hash 對不上。非法輸入非零退出且保留既有輸出；輸出不可覆寫輸入。特徵 CSV 重跑相同，報告 generated_at 可不同。

configs/features.yaml 只是規格對照，不由 CLI 讀取。M1–M4、填補、標準化、個股 join、訓練與提交尚未實作。教師接入限制見 SOURCE_ALIGNMENT.md；未確認時間語意前不產生正式訓練表或宣稱模型增益。
