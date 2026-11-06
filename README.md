# stock-market-challenger

## 每天的流程

每天台北 07:10 之後跑兩步：

1. 爬蟲 `python -m src.crawler --date <t>`：下載老師的 Training、Live、yfinance 19 個指標和期交所的台指期，原樣存進 `data/raw/`。匯率另外存 1 小時K棒；匯率和台指期都和舊檔合併。
2. 特徵 `python -m src.features`：清理 yfinance，算每檔股票和各指標的 lag1、lag2，一列是一檔股票的一天。台指期分日盤和夜盤，夜盤清晨 05:00 收盤，當天開盤前就知道。結果一個月一檔，存在 `data/processed/features/`，每天只更新最後兩個月。

訓練、預測、上傳還沒寫好。

## 組員怎麼拿資料

```python
import json, urllib.request
import pandas as pd

BASE = "https://raw.githubusercontent.com/jiangjiangian/ml-final-2026-fall/claude/stock-market-challenger/data/processed"
info = json.load(urllib.request.urlopen(f"{BASE}/manifest.json"))
df = pd.concat(pd.read_csv(f"{BASE}/features/{m}.csv.gz", dtype={"stock_id": str}, parse_dates=["date"])
               for m in info["months"])
train = df[df["label_y"].notna()]   # 預測日 t 那列還沒有答案
X, y = train[info["model_columns"]], train["label_y"]
```

`label_` 開頭的欄是答案，不能放進 X。驗證要按日期切，不能隨機拆列。`data/raw/yfinance/` 是 Yahoo 的原樣，沒有清理（0052 分割前的價格沒除），要用就用特徵表。

## 檔案樹

```text
ml-final-2026-fall/            （分支 claude/stock-market-challenger）
├── README.md                  流程、組員怎麼拿資料、檔案樹（這份）
├── CLAUDE.md                  給 Claude Code：規則和 memory/ 的索引
├── memory/                    給 Claude Code 的專案記憶，一個主題一個檔
│   ├── glossary.md            名詞
│   ├── context/
│   │   ├── competition.md     比賽規則、課程網站 API、上傳的規矩、Phase 1 結果
│   │   ├── pipeline.md        每天的流程、指令、失敗時怎麼手動交
│   │   ├── data-rules.md      時間對齊、美股日期、-1、交易日曆、資料存放
│   │   ├── environment.md     本機環境、分支、舊系統封存、skills
│   │   └── open-questions.md  還沒決定的事
│   └── projects/
│       ├── crawler.md         src/crawler.py 的設計和進度
│       └── features.md        src/features.py 的規劃：清理規則、交易日、lag、對照測試
├── .claude/
│   ├── settings.json          Claude Code 專案設定（輸出風格用 team-docs）
│   ├── output-styles/
│   │   └── team-docs.md       回覆和文件的寫法
│   └── skills/                graphify、humanizer（只在本機，不進 Git）
├── requirements.txt           套件和鎖定的版本
├── .gitignore                 哪些檔案不進 Git
├── .gitattributes             data/raw/、tests/fixtures/ 的檔案 Git 不改換行，sha256 才對得上
├── .env.example               帳號密碼的範例；真的值放 .env（不進 Git）
├── run_daily.py               一個指令跑完一天：爬蟲 → 特徵 → 訓練 → 預測 → 上傳
├── configs/
│   ├── config.yaml            網站網址、yfinance 代號、特徵、模型參數、截止時間
│   └── live_ca.pem            Live 原本網址的自簽憑證，爬蟲只信任這一張（公開的，不是密碼）
├── data/
│   ├── raw/                   爬蟲寫的，和來源一模一樣
│   │   ├── teacher/
│   │   │   ├── training/      網站的 Training ZIP 解開（不會再變）
│   │   │   └── live/          網站的 Live ZIP 解開，每天整包換新（Live 本身每天多一列）
│   │   ├── yfinance/          19 個額外指標，一個序列一個 CSV；usd_twd_1h.csv 是匯率的 1 小時K棒
│   │   ├── taifex/            tx.csv：期交所的台指期，日盤和夜盤，只留單月合約
│   │   ├── phase2_days.json   課程網站的交易日清單（/api/state 的 phase2Days）
│   │   └── manifest.json      下載紀錄
│   ├── processed/             特徵表，組員從這裡拿資料
│   │   ├── features/          YYYY-MM.csv.gz，一個月一檔，每天只更新最後兩個月
│   │   └── manifest.json      有哪些月份、模型用哪些欄、清理紀錄
│   └── submission/            每天的產出
│       ├── submission_YYYY-MM-DD.csv   要上傳的 0/1
│       ├── upload_log.jsonl            上傳紀錄
│       └── run_YYYY-MM-DD.log          執行紀錄，失敗時先看這個
├── models/                    model.txt（模型）、feature_columns.json（欄位順序和訓練資訊）
├── notebooks/
│   └── README.md              實驗的檔名和注意事項；每天的自動流程不會讀這裡
├── src/
│   ├── __init__.py
│   ├── crawler.py             下載老師資料和 yfinance 額外指標
│   ├── features.py            原始資料 → 特徵表；訓練和預測用同一個函式
│   ├── train.py               按日期切分、驗證、訓練、存模型
│   ├── predict.py             下載當天範本，產生 t 那天 50 檔的 submission CSV
│   ├── submit.py              上傳 CSV，再下載回來核對
│   └── utils.py               讀設定和帳密、台北時間、截止檢查、log
└── tests/
    ├── fixtures/data-collection/  舊分支 data-collection 的凍結資料，只給對照測試用，不要改
    │   ├── extra/                 清理過的 yfinance 19 個序列和 manifest.json（清理紀錄）
    │   ├── yfinance_raw_0820473/  還沒清理的 Yahoo 原樣（到 2026-08-31），測清理用
    │   ├── teacher_live/          舊長表用的那份 Live（eea89fce，9/1～11/5）
    │   ├── transform/             舊長表 panel_lag.csv.gz（2020-01-02～2026-11-04），對照測試 (a) 的標準答案
    │   └── schema.json            舊長表所有欄位的定義和驗證紀錄
    ├── test_crawler.py            爬蟲的離線測試（假伺服器、假時鐘）
    ├── test_features.py           清理、交易日、lag，以及和 data-collection 凍結資料的對照測試
    ├── test_no_future_data.py     特徵只能用 t 之前的資料
    └── test_submission_format.py  CSV 的欄位、列數、0/1
```
