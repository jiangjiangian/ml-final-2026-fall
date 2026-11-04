# 台股盤中方向預測：資料整合分支

本分支 `claude/peaceful-babbage-09xeie` 只放**資料**：老師資料、yfinance 額外指標、lag 轉換特徵，以及整合好、可直接訓練的長表。
完整的模型與每日提交程式在預設分支 `system-completion`。

預測目標：台股日 t 的 `y = 1{adj_close_t > adj_open_t}`（盤中上漲）；官方分數＝`mean((2p − 1) × 盤中報酬)`。

## 檔案樹

```text
.
├── README.md                         # 本檔：檔案說明＋組員使用方式
├── CLAUDE.md                         # 給 Claude Code 的專案記憶（重點摘要）
├── memory/                           # 詳細記憶
│   ├── glossary.md                   #   術語表
│   ├── context/data-decisions.md     #   資料決策：定義、清理規則、時間對齊證據
│   ├── context/environment.md        #   環境、分支、skills 安裝方式
│   └── projects/data-folder.md       #   本分支的需求歷程、兩輪審查、已知限制
├── crawler.py                        # 唯一程式：yfinance 限流爬蟲 → 清理 → 整合 → lag 轉換 → 長表 → schema
├── schema.json                       # 所有欄位的定義、單位、lag 規則、清理紀錄、hash（老師＋額外＋transform＋panel）
├── data/
│   ├── teacher/                      # 老師 Training ZIP 原樣（逐位元組，sha256 已核對）
│   │   ├── info.json                 #   Top50@Y（50 檔預測目標）／Top100@Y（100 檔）
│   │   ├── global/global_data.csv    #   ^VIX ^IXIC ^GSPC ^TWII ^KS11 TX_OI；1,506 列
│   │   └── market/<stock_id>.csv     #   100 檔個股，各 21 欄（還原價、量、法人、技術指標、y）
│   ├── extra/
│   │   ├── manifest.json             #   爬蟲紀錄：取得時間、限流設定、重試、清理、hash
│   │   └── yfinance/<series_id>.csv  #   19 個額外指標日K（date, open, high, low, close, adj_close, volume）
│   ├── features/
│   │   └── market_features.csv       #   as-of 市場特徵：1,618 天 × 104 欄（1／5／20 日累積報酬、匯率、殖利率…）
│   └── transform/
│       ├── panel_lag.csv.gz          # ★ 組員直接用這個：100 股 × 1,618 天 ＝ 161,800 列 × 56 欄（7 MB）
│       ├── lag2/<feature>.csv        #   124 檔，每檔兩欄：date, <feature>_ret_lag2
│       └── lag5/<feature>.csv        #   124 檔，每檔兩欄：date, <feature>_ret_lag5
├── .agents/skills/                   # 既有 skills（gh-fix-ci、graphify、markitdown、rtk、security-best-practices）
├── .gitattributes                    # data/、schema.json、skills 不做換行轉換，hash 才對得上
└── .gitignore
```

19 個額外指標（全部經 yfinance，範圍 2020-01-01～2026-08-31）：

| 類別 | series_id（ticker） |
|---|---|
| 半導體 | sox（^SOX） |
| 海外個股 | tsm_adr（TSM）、nvda（NVDA） |
| 匯率、利率 | usd_twd（TWD=X，台幣匯率）、dxy（DX-Y.NYB）、us10y（^TNX）、us13w（^IRX） |
| 台灣 | etf_0050、etf_0052（電子代理）、etf_0055（金融代理）、etf_006201（櫃買代理） |
| 全球指數 | dji、n225、hsi、sse（上證）、stoxx50e、gdaxi |
| 商品 | wti（CL=F）、gold（GC=F） |

## 組員怎麼用

### 1. 取得資料（擇一）

**A. 不用 clone，直接讀網址**（最快）：

```python
import pandas as pd

BASE = "https://raw.githubusercontent.com/jiangjiangian/ml-final-2026-fall/claude/peaceful-babbage-09xeie"
df = pd.read_csv(f"{BASE}/data/transform/panel_lag.csv.gz", dtype={"stock_id": str}, parse_dates=["date"])
```

**B. 只抓這個分支**：

```bash
git clone --branch claude/peaceful-babbage-09xeie --single-branch --depth 1 https://github.com/jiangjiangian/ml-final-2026-fall.git
```

```python
df = pd.read_csv("ml-final-2026-fall/data/transform/panel_lag.csv.gz", dtype={"stock_id": str}, parse_dates=["date"])
```

`stock_id` 一定要用字串讀，否則代號會變成數字。若之後本分支合併到 `system-completion`，把網址或 `--branch` 換成新分支名即可。

### 2. 切成特徵 X 與答案 y

```python
feature_cols = [c for c in df.columns if "_ret_lag" in c]   # 50 個特徵欄
label_cols = ["label_y", "label_intraday_return"]           # 答案，絕不可放進 X

train = df[df["has_teacher_row"] == 1]                      # 有答案的列
X, y = train[feature_cols], train["label_y"]
```

- **按日期切訓練／驗證**（例如 `date < "2025-01-01"` 訓練、之後驗證）。同一天的市場特徵 100 股都一樣，隨機拆列會把同一天同時放進訓練和驗證。
- 訓練可用全部 100 股；**提交只預測 `is_top50 == 1` 的 50 股**。
- Phase 1 要預測 2026-06-01～09-30，訓練時要排除 `date >= "2026-06-01"` 的答案。
- 空白＝缺值（`NaN`），佔全部特徵約 3.7%。可用能處理 NaN 的模型（如 `HistGradientBoostingClassifier`），或只用訓練期的資料做補值。
- 評分：`score = ((2 * pred - 1) * df["label_intraday_return"]).mean()`。

### 3. 長表 `panel_lag.csv.gz` 的欄位

| 欄位 | 數量 | 說明 |
|---|---|---|
| `date`、`stock_id` | 2 | 索引鍵：台股交易日 t、股票代號 |
| `is_top50` | 1 | 1＝官方預測目標 50 股 |
| `has_teacher_row` | 1 | 1＝老師該股該日有資料（54 格為 0，答案空白） |
| `stock_ret_lag2`、`stock_ret_lag5` | 2 | 這一列股票**自己**的 lag2、lag5（用 `etl:adj_close`） |
| `<市場特徵>_ret_lag2`、`_ret_lag5` | 48 | 19 個額外指標＋老師 5 指數（`teacher_vix`、`teacher_ixic`、`teacher_gspc`、`teacher_twii`、`teacher_ks11`）；同一天所有股票相同 |
| `label_y`、`label_intraday_return` | 2 | **答案**：`y` 與 `adj_close/adj_open − 1`；只用於訓練和評分 |

每一欄的完整定義在 `schema.json` 的 `panel.columns`。

### 4. lag 的定義

台股日 t 那一列：

```
ret_lag{k}(t) = (close_i − close_{i−k}) / close_{i−k}，k = 2、5
i   ＝ t 的前一個台股交易日（只用 t 開盤前已知的收盤，不含 t 當天）
i−k ＝ 該序列往回第 k 個「自己的」交易日
```

例：SOX 收盤 01-16＝100、01-17＝102、01-21＝99（01-20 美股休市）。
- 列 01-22：i＝01-21，lag2＝99/100 − 1＝−1.00%。
- 列 01-21：i＝01-20，SOX 那天沒有資料，所以空白。

所以 lag 特徵**不含當天的 y**：t 那一列只用到 t−1 以前的收盤，y(t) 用的是 t 當天的開盤和收盤。

### 5. 想加其他特徵時

- 老師個股的其他欄位（成交量、法人、RSI…）都是**收盤後才知道**。要先在每檔股票內往前移一列（`groupby("stock_id").shift(1)`），再用 `(stock_id, date)` 和長表合併。
- 老師 `^TWII`、`^KS11` 是當日收盤，不能直接當輸入。`^VIX`、`^IXIC`、`^GSPC` 已被老師移到前一個 global 列的日期。
- `data/features/market_features.csv` 另有 1／5／20 日累積報酬、匯率水準、殖利率基點變化，用 `date` 合併。

## 重建資料

```bash
pip install yfinance==1.7.0      # 環境要能連 finance.yahoo.com
git fetch origin live-data       # 老師 ZIP 的來源
python crawler.py                # 下載＋整合＋transform＋panel＋schema，約 1 分鐘
python crawler.py --skip-download --keep-teacher   # 不連網，只用現有檔案重算
```

爬蟲有限流：每個 HTTP 請求間隔至少 2 秒（另加 0～1 秒隨機），被 Yahoo 限流時指數退避並自動冷卻。

## 注意事項

- **時間對齊是研究假設**：假設美股前一天的收盤在台股 09:00 前已可取得；沒有驗證過歷史上的實際發布時間。
- **資料清理**（每筆都記在 `data/extra/manifest.json`）：
  - 0052 的分割與股利調整已修正。
  - 刪掉台灣 ETF 的佔位K棒、TWD=X 的 2 筆壞報價、殖利率在美國債市休市日的平盤K棒。
- **已知限制**：
  - TWD=X 的 close 常常就是倫敦日的第一筆報價。
  - STOXX50E 依瑞士假日缺 21 天。
  - 殖利率（尤其 us13w）在接近 0 的期間，百分比報酬會非常大。
- 老師資料與 Yahoo 資料的公開再散布授權沒有核實，僅供課程研究使用。
