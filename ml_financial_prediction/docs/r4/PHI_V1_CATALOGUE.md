> **狀態：locked（2026-11-04，使用者核可照 16 個鎖定）。** 資料來源決定：C1 用 yfinance `^GSPC`（與 `^SOX`），S5 用 yfinance `^VIX`；兩者已由專案 live-data 每日管線收集（2019-12 起），時間規則同其他 yfinance 序列（session ≤ t−1 日曆日）。之後任何修改都要另立 Φ-v2 並計入嘗試預算。

# 預註冊具體特徵目錄 Φ-v1：從 raw 到 concrete

- 狀態：proposed，屬預註冊。決定 Φ 時沒有讀取任何標籤、報酬結果、回測或先前的實驗紀錄。本目錄不沿用先前任何模型或特徵選擇。
- 依據：林軒田 ML Foundations L3/L12/L16。Φ 由領域知識事先決定，在 Z 空間用簡單模型，遵守 Occam 原則並避免 data snooping。抽樣情境要和測試情境一致，也就是每天 08:10 前預測同一批 50 檔股票。
- 收錄規則：只收評審判定為 keep 或 revise、而且 `timing_ok=true`、`reproducible_daily=true` 的提案，並套用評審的修正。冗餘的版本合併成最好解釋的一個。
- 凍結原則：以下所有窗長、權重、門檻、clip 界限與預期符號，在看任何標籤之前就固定。之後不能依驗證結果增刪或調整。如果真的要改，必須另立 Φ-v2，並計入試驗預算。

## 0. 總覽

| # | 名稱 | 層級 | scope | 主要 raw | 預期符號 | 信心 |
|---|---|---|---|---|---|---|
| C1 | `us_overnight_shock_z` | CORE | market_state | ^SOX、^GSPC 收盤，XNYS 日曆 | 不預設（雙向） | low–medium |
| C2 | `mkt_foreign_flow_z` | CORE | market_state | 外陸資買賣超、成交金額、成交股數（100 股） | + | medium |
| C3 | `tx_foreign_net_oi_change_z` | CORE | market_state | TX_OI | + | low–medium |
| C4 | `tug_of_war_20d` | CORE | stock_relative | adj_open、adj_close | + | medium–low |
| C5 | `attention_shock` | CORE | stock_relative | 成交金額、adj_close | − | medium |
| C6 | `foreign_flow_persistence` | CORE | stock_relative | 外陸資買賣超、成交股數 | + | medium |
| S1 | `lottery_max5e` | SECONDARY | stock_relative | adj_close | − | low |
| S2 | `trust_flow_persistence` | SECONDARY | stock_relative | 投信買賣超、成交股數 | + | low |
| S3 | `trust_quarter_end_dressing` | SECONDARY | interaction | 投信買賣超、成交股數、日曆 | + | low |
| S4 | `foreign_clientele_x_us_shock` | SECONDARY | interaction | 外資持股比率、C1、`b_on` | + | low |
| S5 | `vix_regime` | SECONDARY | market_state | ^VIX 收盤 | 約 0（調節用） | low |
| S6 | `mkt_intraday_lag_z` | SECONDARY | market_state | 50 股 adj_open、adj_close | +（平靜期） | low |
| S7 | `lagged_move_x_vix` | SECONDARY | interaction（市場） | S6 × S5 | − | low |
| S8 | `pre_long_closure` | SECONDARY | market_state（日曆） | 官方預公告休市表 | + | low |
| S9 | `closure_length_log` | SECONDARY | market_state（日曆） | TWSE 日曆 | 不確定 | low |
| S10 | `us_shock_x_long_gap` | SECONDARY | interaction（市場） | C1 × 長休市指標 | 不確定（calm-down 假說為 +） | low |

合計 16 個：CORE 6 個，SECONDARY 10 個。
- 市場層級特徵有 9 個（C1–C3、S5–S10）。它們的有效樣本數大約等於交易日數（約 1,600），而不是 日數×50。
- 個股相對特徵與橫斷面交互作用有 7 個（C4–C6、S1–S4）。

---

## 1. 共用記號與積木（各特徵共用，只定義一次）

**日曆**
- `t`：目標交易日。
- `D1`：t 之前的 TWSE 交易日（等同文中的 p）。`D2`：D1 之前的交易日。
- `TW(k)`：t 之前第 k 個 TWSE 交易日，所以 `TW(1)=D1`。
- 往回看的特徵用實際交易日曆，往前看的特徵只用 t 當時已預公告的官方休市表。
- `days(a-b)`：日曆天數差。

**股票集合與欄位**
- `U50`：50 檔目標股。`U100`：教師資料的 100 檔股票。
- `O,H,L,C` 為 `etl:adj_open/high/low/close`；`VAL` 為 `price:成交金額`；`SH` 為 `price:成交股數`。
- `F` 為 `外陸資買賣超股數(不含外資自營商)`；`IT` 為 `投信買賣超股數`；`FOWN` 為 `全體外資及陸資持股比率`。

**報酬分解**
```
prev_i(d) = 個股 i 在 d 之前的上一個 TWSE 交易日列；如果該列不存在（停牌），就不跨缺口，相關項目記為 NaN
r_on[i,d] = ln(O[i,d] / C[i,prev_i(d)])      # 隔夜／開盤段
r_id[i,d] = ln(C[i,d] / O[i,d])              # 盤中段（與標籤同型，但只用 d <= D1）
r_cc[i,d] = ln(C[i,d] / C[i,prev_i(d)]);  R[i,d] = exp(r_cc[i,d]) - 1
```

**市場因子**：只對 U50 計算，當日有效股數須 ≥ 40，否則記 NaN。
```
m_on[d] = median_i r_on[i,d];   m_id[d] = median_i r_id[i,d];   m_cc[d] = mean_i R[i,d]
```

**收縮 beta**：不使用標籤，依 Vasicek/Blume 的作法事先收縮。
```
b = 0.5*b_hat + 0.5;   b_hat = 含截距 OLS 斜率；樣本不足時 b_hat 視為 1（即 b = 1，市場平均）
b_on[i,t], b_id[i,t]: r_on[i,d] ~ m_on[d]（r_id ~ m_id），d ∈ TW(80)..TW(21)，至少 40 個有效值
b_cc[i,t]:            R[i,d] ~ m_cc[d],                    d ∈ TW(140)..TW(22)，至少 60 個有效值
```
殘差一律只扣 `b*m`，不扣截距。截距正是要測量的個股持續漂移。

**橫斷面運算**
- `csrank(x)`：在 U50 的有效股中計算百分位排名，同分取平均名次，`(rank-0.5)/n_valid ∈ (0,1)`。
- 所有橫斷面運算都要求 `n_valid ≥ 40`。不足時，該特徵當日全部記 0。

**美股視窗**：依 XNYS 的排定交易日。
```
W_t = {XNYS session s : D1 <= date(s) <= t-1（日曆日）};  n_t = |W_t|
b_t = date(s) < D1 的最後一個 XNYS session（它的收盤在 D1 台股開盤前就已知，已反映在 D1 價格中）
```

---

## 2. CORE tier（6 個）

### C1 `us_overnight_shock_z`
- **scope**：market_state，同一天 50 檔取同一個值。
- **raw**：
  - yfinance `^SOX` 收盤。
  - `^GSPC` 收盤。repo 的 `market_history.HISTORY_SERIES["gspc"]` 已有原生日線，資料從 2019-12 開始。這裡把它列為來源清單 C 的明示增列，同樣遵守 `date <= t-1` 規則。
  - XNYS 日曆與 TWSE 日曆。
- **公式**
```
For X in {SOX, GSPC}:
  if n_t == 0（依 XNYS 為美國休市）:            R_X = 0
  elif W_t 中任一 session 或 b_t 缺 yfinance bar:  R_X = NaN，記 us_shock_missing = 1
  else: R_X = ln C_X(W_t 最後一個 session) - ln C_X(b_t)
  sigma_X = X 的日 log 收盤報酬標準差，取到 b_t 為止的 60 個原生 session（暖身期用 expanding，至少 20 個）
  z_X = clip(R_X / (sigma_X * sqrt(max(n_t,1))), -4, 4)
us_overnight_shock_z = 0.5*z_SOX + 0.5*z_GSPC          # 權重事先固定，不擬合
```
- **正規化**：除以自身過去的單 session 波動。資訊主要在開市時間產生（French & Roll 1986），所以休市越久，以 `sqrt(n_t)` 依交易 session 數放大分母。不扣平均值。
- **物理意義**：台股 D1 收盤後到 t 開盤前，美股（半導體加大盤）新增的消息有幾個標準差大。
- **機制**：
  - 外國日間報酬主要傳入本地的開盤價（Lin, Engle & Ito 1994；Hamao, Masulis & Ng 1990）。因此 open-to-close 只剩下「開盤定價誤差」的修正。
  - 反轉力量：TAIEX 開盤對 E-mini Nasdaq 急漲過度反應（Chang et al. 2011）。TWSE 日間報酬傾向與隔夜報酬反號，而且隔夜幅度越大越明顯（Tsai, Lih & Ko 2012）。亞洲指數期貨在美股極端日之後會盤中反轉（Fung, Lam & Lam 2010）。
  - 延續力量：外資對全球報酬做正回饋交易，美股上漲的隔天買進（Richards 2005）；法人偏好在盤中執行（Lou, Polk & Skouras 2019）。
  - TAIFEX 自 2017-05-15 有夜盤，開盤價因此有錨。韓國的類比顯示，夜盤期貨推出後開盤過度反應大致消失（Han, Hwang & Ryu 2015）。
- **預期符號**：不預設（雙向），淨效果預期很弱。這個特徵主要作為市場狀態變數，以及 S4、S10 的主效果。
- **已知限制**：
  - `b_t` 收盤到 W_t 首個 session 開盤之間的美股隔夜缺口，和台股 D1 盤中時段重疊（非同步交易），含有部分已被 D1 收盤吸收的資訊。
  - 不使用指數開盤價，因為指數開盤值會沿用尚未開盤成分股的前收，容易過時。
- **來源**：
  - Lin, Engle & Ito (1994) RFS 7(3):507-538, doi:10.1093/rfs/7.3.507
  - Hamao, Masulis & Ng (1990) RFS 3(2):281-307
  - Chang, Cheng, Huang & Huang (2011) Managerial Finance 37(1):47-71, doi:10.1108/03074351111092148
  - Tsai, Lih & Ko (2012) Physica A 391(24):6497-6505
  - Fung, Lam & Lam (2010) JEF 17(3):428-440
  - Han, Hwang & Ryu (2015) Applied Economics 47(54):5868-5885
  - Richards (2005) JFQA 40(1):1-27（RBA RDP 2004-05）
  - French & Roll (1986) JFE 17(1):5-26
  - TAIFEX 盤後交易 2017-05-15 上線

### C2 `mkt_foreign_flow_z`
- **scope**：market_state。
- **raw**：U100 在 D1 的 `F`、`VAL`、`SH`。
- **公式**
```
有效股 i ∈ U100：SH[i,D1] > 0、VAL[i,D1] > 0、該列不是 pending（見 4.3）
vwap_i = VAL[i,D1] / SH[i,D1]                         # 當日未調整的 TWD/股，與還原因子無關
FF_D1  = Σ_i F[i,D1]*vwap_i / Σ_i VAL[i,D1]            # 分子、分母用同一組股票；有效股須 ≥ 80，否則 NaN
s      = std(FF，取到 D2 為止的 60 個 TWSE 交易日)       # 暖身期 expanding，至少 20 個
mkt_foreign_flow_z = clip(FF_D1 / s, -4, 4)            # 不扣平均值，保留買超/賣超的正負意義
```
- **物理意義**：外資前一天在權值股的淨買超，佔大型股成交值的比例，再以自身近期波動標準化。
- **機制**：
  - 國際資金流的持續性遠高於報酬的持續性，流入能預測新興市場報酬（Froot, O'Connell & Seasholes 2001）。
  - 外資在亞洲（含台灣）是正回饋交易者，價格衝擊大，而且大多發生在交易當天（Richards 2005）。台灣的日資金流同時受國內與全球報酬推拉（Griffin, Nardari & Stulz 2004）。
  - 推論鏈：D1 的流量具持續性，所以 t 日會續流，續流在 t 日盤中造成衝擊。
- **預期符號**：+。
- **限制**：
  - 部分衝擊會落在 t 日開盤集合競價。
  - 與 C3 可能正相關也可能負相關（現貨與期貨互相避險）。
  - 2020–22 外資連續賣超，使這個特徵帶有部分時期效應。
  - T86 與 `成交股數` 涵蓋的交易類型可能不同，所以比例只是近似有界。
- **來源**：
  - Froot, O'Connell & Seasholes (2001) JFE 59(2):151-193
  - Richards (2005) JFQA 40(1):1-27
  - Griffin, Nardari & Stulz (2004) REStat 86(3):641-657, doi:10.1162/0034653041811725

### C3 `tx_foreign_net_oi_change_z`
- **scope**：market_state。
- **raw**：教師 global `TX_OI`，只用列 ≤ D1。
- **公式**
```
有效條件：global 列 D1 與 D2 都存在，值不是 placeholder，
          且 available_at(TX_OI 列 D1) <= t 08:10（需有證據；歷史上無法證明時標記 research_assumption）
若 D1 是 TX 最後結算日（每月第三個星期三，遇休市順延至次一營業日）：NaN，settle_flag = 1
dOI = TX_OI(D1) - TX_OI(D2)                # 不跨 global 表缺日差分（global 表比個股表少 112 個日期）
s   = std(dOI，取到 D2 為止的前 60 個有效非結算日列)   # 暖身期 expanding，至少 20 個
tx_foreign_net_oi_change_z = clip(dOI / s, -4, 4)
```
- **正規化**：只看差分，不看水準。水準不平穩，而且主要反映外資現貨持股的避險部位。不做百分比變化，因為序列有正負號並會穿越 0。只依自身波動縮放，不扣平均值。
- **物理意義**：外資在臺指期淨多單上一個交易日加減了多少口，相對平常的每日調整幅度。
- **機制**：
  - 在臺指期市場，外資交易對期貨報酬的預測力優於本土法人；散戶較像雜訊交易者（Kuo, Chung & Chang 2015）。
  - 外資的選擇權交易能預測標的報酬（Chang, Hsieh & Lai 2009）。
  - 指數套利把期貨與現貨權值股連在一起，大部位會分多日建立。
- **預期符號**：+。
- **限制**：
  - 兩篇證據都早於夜盤普及，D1 的部位資訊可能已在夜盤反映。
  - 教師 TX_OI 的日期語意尚未核實。如果列 d 其實是前一天的值，特徵仍然因果，但會再舊一個 session。
- **來源**：
  - Kuo, W.-H., Chung & Chang (2015) J. Futures Markets 35(3):222-244, doi:10.1002/fut.21683
  - Chang, Hsieh & Lai (2009) JBF 33(4):757-764
  - TAIFEX TX 契約規格：https://www.taifex.com.tw/cht/2/tX

### C4 `tug_of_war_20d`
- **scope**：stock_relative。
- **raw**：`etl:adj_open`、`etl:adj_close`，只用 ≤ D1。
- **公式**
```
for d in TW(20)..TW(1):
  e_on[i,d] = r_on[i,d] - b_on[i,t]*m_on[d]      # 扣掉市場（主要是美股）驅動的隔夜成分
  e_id[i,d] = r_id[i,d] - b_id[i,t]*m_id[d]
n_valid = e_on 與 e_id 都有效的天數；n_valid < 15 時記 NaN
sigma20 = max(sd(r_cc[i,d], d ∈ TW(20)..TW(1)), 0.005)
T20     = Σ_d (e_id - e_on) / (sigma20 * sqrt(n_valid))      # 以 sqrt(n_valid) 縮放，缺日不會被壓向 0
tug_of_war_20d = csrank(T20) - 0.5                            # NaN → 0
```
- **正規化**：先做 beta 殘差化。台灣的隔夜報酬主要反映美股，不殘差化的話，排名其實是在排 beta。接著做波動縮放，再取橫斷面排名。
- **物理意義**：過去一個月，這檔股票扣掉市場因素後，價格主要在盤中形成（法人客群），還是在開盤缺口形成（散戶或隔夜客群），並與同儕相比。
- **機制**：
  - 客群需求具持續性。過去盤中贏家之後的盤中報酬較高；過去隔夜贏家之後的盤中報酬較低（Lou, Polk & Skouras 2019）。依隔夜報酬排序的 10−1 組合盤中報酬為 −3.24%/月，依盤中報酬排序的為 +2.19%/月，九個非美國市場也有相同現象。
  - 台灣證據：投資人對盤中資訊反應不足、對隔夜資訊反應過度（Ho et al. 2023）。散戶比重會強化隔夜報酬的情緒持續性（Zhang et al. 2023）。
- **預期符號**：+。反向機制：Akbas et al. (2022) 發現「隔夜漲、日間跌」拉鋸越強，未來（月）報酬越高，這意味負向關係。
- **信心**：medium–low。文獻證據是月度期間，延伸到下一日 open-to-close 屬外推。
- **來源**：
  - Lou, Polk & Skouras (2019) JFE 134(1):192-213, doi:10.1016/j.jfineco.2019.03.011
  - Ho, Hsiao, Lo & Yang (2023) PBFJ 82:102151, doi:10.1016/j.pacfin.2023.102151
  - Zhang, Tsai, Weng & Tsai (2023) PBFJ 80:102093, doi:10.1016/j.pacfin.2023.102093
  - Akbas, Boehmer, Jiang & Koch (2022) JFE 145(3):850-875, doi:10.1016/j.jfineco.2021.09.019（反向機制）

### C5 `attention_shock`
- **scope**：stock_relative。
- **raw**：`price:成交金額`、`etl:adj_close`。該股最新有效列必須是 D1，否則記 NaN。
- **公式**
```
a_v = clip( (ln VAL[i,D1] - median_{k=2..61} ln VAL[i,TW(k)])
            / max(1.4826*MAD_{k=2..61} ln VAL[i,TW(k)], 0.05), -5, 5)   # 只用 VAL > 0；基準至少 40 個有效值
sigma_pre = max(sd(r_cc[i,d], d ∈ TW(21)..TW(2)), 0.005)               # 至少 15 個有效值
a_r = clip( (|r_cc[i,D1]| / sigma_pre - 0.798) / 0.603, -5, 5)          # 半常態分布的理論均值與標準差，不擬合
A   = 0.5*a_v + 0.5*a_r                                                 # 缺一個成分時，該成分記 0
attention_shock = A - mean_{j∈U50 有效} A_j                              # NaN → 0
```
- **正規化**：
  - 成交值用自身 60 日穩健 z 分數，對分割不敏感，基準排除 D1。
  - 絕對報酬以事件前自身波動縮放。
  - 兩者事先等權合成，再扣橫斷面平均。注意力是稀缺資源，會在股票之間分配。
- **物理意義**：昨天這檔股票比平常、也比其他 49 檔更「吸睛」的程度，來源是異常成交值或異常大的漲跌幅。
- **機制**：
  - 散戶是吸睛股票的淨買方（Barber & Odean 2008），他們在 08:30–09:00 委託，推高 09:00 的開盤價。
  - 盤中由法人或套利者修正，形成「隔夜漲、盤中跌」，在高散戶注意力股票最明顯（Berkman et al. 2012）。
  - 台灣散戶比重高，而且輸給法人（Barber, Lee, Liu & Odean 2009）。
  - 漲跌停鎖死時，`a_r` 會飽和，所以這個特徵也涵蓋了漲跌停事件。
- **預期符號**：−。
- **限制**：
  - Berkman 的效果集中在小型、難套利股，在 50 檔權值股中預期較弱。
  - MSCI/FTSE/ETF 調整日（2、5、8、11 月底）的被動成交量會被誤當成注意力。我們沒有調整日行事曆，所以接受這個雜訊，不做過濾。
- **來源**：
  - Barber & Odean (2008) RFS 21(2):785-818, doi:10.1093/rfs/hhm079
  - Berkman, Koch, Tuttle & Zhang (2012) JFQA 47(4):715-741, doi:10.1017/S0022109012000270
  - Barber, Lee, Liu & Odean (2009) RFS 22(2):609-632, doi:10.1093/rfs/hhn046
  - Barber, Lee, Liu & Odean (2014) JFM 18:1-24
  - TWSE 交易制度：https://www.twse.com.tw/en/page/products/trading/introduce.html

### C6 `foreign_flow_persistence`
- **scope**：stock_relative。
- **raw**：`外陸資買賣超股數(不含外資自營商)`、`price:成交股數`。
- **公式**
```
j = 1..10 按 TWSE 日曆編號（不按個股列編號）；w_j = 0.5^((j-1)/2)        # 半衰期 2 個交易日
valid(j)：SH[i,TW(j)] > 0、SH ≠ -1、該列不是 pending
FFP = clip( Σ_{valid j} w_j*F[i,TW(j)] / Σ_{valid j} w_j*SH[i,TW(j)], -1, 1 )
有效天數 < 5 或分母 <= 0 時記 NaN；缺日直接從分子分母剔除，不平移窗口
foreign_flow_persistence = csrank(FFP) - 0.5                             # NaN → 0
```
- **正規化**：用自身成交股數做分母，因此無單位、不受分割影響，也對應價格衝擊與流動性的比例關係。橫斷面排名移除了全市場的外資浪潮（那部分由 C2 負責）。
- **物理意義**：近 1–3 天外資淨買超佔這檔股票成交量的比重，與另外 49 檔相比。
- **機制**：
  - TWSE 個股的委託不平衡因拆單與從眾而逐日正相關（Lee, Liu, Roll & Subrahmanyam 2004），外資流量也高度持續（Froot et al. 2001）。所以 D1 的流量可以預測 t 日的流量。
  - 外資流量的衝擊大多在當日發生（Richards 2005）。外資用 VWAP 或演算法在連續交易時段執行，因此 t 日的續流主要推動 09:00 到 13:30 的價格。
  - 外資是台灣最會賺錢的交易人類別（Barber et al. 2009）。
- **預期符號**：+。
- **限制**：Lee et al. 發現價格壓力在一日內消退，部分效果可能已落在開盤競價。
- **來源**：
  - Lee, Liu, Roll & Subrahmanyam (2004) JFQA 39(2):327-341, doi:10.1017/S0022109000003094
  - Froot, O'Connell & Seasholes (2001) JFE 59(2):151-193
  - Richards (2005) JFQA 40(1):1-27
  - Barber, Lee, Liu & Odean (2009) RFS 22(2):609-632

---

## 3. SECONDARY tier（10 個）

### S1 `lottery_max5e`
- **scope**：stock_relative。**raw**：`etl:adj_close`。
- **公式**
```
e_cc[i,d] = R[i,d] - b_cc[i,t]*m_cc[d],  d ∈ TW(21)..TW(1)        # 扣市場後的特異報酬
MAX5e = 最大 5 個 e_cc[i,d] 的平均；有效值 < 15 時記 NaN
lottery_max5e = csrank(MAX5e) - 0.5                                 # NaN → 0
```
- **正規化**：
  - 先扣 beta 乘市場報酬。不扣的話，排名只是在排 beta 或波動度，會把市場擇時混進橫斷面。
  - 取前 5 大而非單一最大值，可減少 ±10% 漲跌幅上限造成的同分。
  - 樣本不足時沿用 1.的通則：b_hat 視為 1，也就是 b=1。
- **物理意義**：近一個月這檔股票在散戶眼中有多像彩券，也就是特異性的暴漲日有多大。
- **機制**：
  - 偏好正偏態的投資人（以散戶為主）會高估高 MAX 股票，使其後續報酬偏低（Bali, Cakici & Whitelaw 2011）。
  - 台灣有考慮漲跌停後的驗證（Hung & Yang 2018）。
  - 高特異波動折價完全在盤中實現（LPS 2019 的 IVOL 結果）。從 IVOL 延伸到 MAX5 屬推論。
- **預期符號**：−。
- **限制**：大型股的暴漲日常與月營收公告重疊，這種情況下 MAX 效果較弱（Wang & Lien 2022）。
- **來源**：
  - Bali, Cakici & Whitelaw (2011) JFE 99(2):427-446, doi:10.1016/j.jfineco.2010.08.014
  - Hung & Yang (2018) JFM 41:77-91, doi:10.1016/j.finmar.2018.07.003
  - Wang & Lien (2022) RQFA 59(2):545-600
  - Lou, Polk & Skouras (2019)

### S2 `trust_flow_persistence`
- **scope**：stock_relative。**raw**：`投信買賣超股數`、`price:成交股數`。
- **公式**
```
TFP = clip( Σ_{valid j∈1..5} IT[i,TW(j)] / Σ_{valid j} SH[i,TW(j)], -1, 1 )   # 有效天數至少 3；分母 > 0
trust_flow_persistence = csrank(TFP) - 0.5                                     # NaN → 0
```
有效性與日曆編號規則同 C6。
- **物理意義**：本土投信（基金與 ETF）上週是否淨累積這檔股票，與同儕相比。
- **機制**：法人需求具持續性，法人會跟隨自己與彼此的落後交易（Sias 2004）。TWSE 大型本土法人的交易最具資訊性（Lee et al. 2004）。台灣投信是正回饋交易者（Lai & Wang 2015）。
- **預期符號**：+。
- **限制**：
  - 約 2021 年起，投信流量大量反映 ETF 申購與再平衡等被動流，常在收盤競價執行。這是體制變化，特徵可能不平穩。
  - 引用文獻對日頻的支持只是鬆散支持。
- **來源**：
  - Sias (2004) RFS 17(1):165-206, doi:10.1093/rfs/hhg035
  - Lee et al. (2004) JFQA 39(2)
  - Lai & Wang (2015) J. Behavioral Finance 16(4):311-326, doi:10.1080/15427560.2015.1095751

### S3 `trust_quarter_end_dressing`
- **scope**：interaction（日曆 × 個股）。**raw**：`投信買賣超股數`、`price:成交股數`、TWSE 預公告日曆。
- **公式**
```
W_t = +1：t 是 3/6/9/12 月最後一個「排定」TWSE 交易日
      -1：t 是 1/4/7/10 月第一個排定 TWSE 交易日
       0：其他日子                                     # 只用 t 當時已公告的行事曆
Q = (W_t=+1) 本季第一個交易日 .. D1 的所有 TWSE 交易日
    (W_t=-1) 上一季全部 TWSE 交易日（結束於 D1）
H = Σ_{k∈Q, valid} IT[i,k] / Σ_{k∈Q, valid} SH[i,k]    # 有效天數 < 30 或分母 <= 0 時記 NaN
trust_quarter_end_dressing = W_t * (csrank(H) - 0.5)     # NaN → 0
```
窗口只取季末最後 1 天與季初第 1 天，現在就固定，不再試 2 或 3 天。
- **物理意義**：季底當天，投信本季累積最多的股票正是基金經理人有誘因在收盤拉抬的標的。季初第一天則是同一個量取反號。
- **機制**：
  - 基金在季底以尾盤買進拉抬既有持股，季初反轉（Carhart, Kaniel, Musto & Reed 2002）。
  - 台灣股票型基金有作帳行為（Hung, Lien & Kuo 2020）。
  - TWSE 季底法人影響收盤價，2002 年收盤集合競價改制後仍然存在（Huang & Chan 2010）。
- **預期符號**：+。
- **限制**：每年只有約 8 天非零，2020–2026 大約 50 個事件日，檢定力極低。ETF 被動流也會汙染 H。
- **來源**：
  - Carhart et al. (2002) JF 57(2):661-693, doi:10.1111/1540-6261.00438
  - Hung, Lien & Kuo (2020) QREF 78:338-354, doi:10.1016/j.qref.2020.05.003
  - Huang & Chan (2010) EMFT 46(4):105-125, doi:10.2753/REE1540-496X460407

### S4 `foreign_clientele_x_us_shock`
- **scope**：interaction（市場純量 × 已置中的個股特性，因此是純橫斷面特徵）。
- **raw**：`全體外資及陸資持股比率`（列 D1）、C1、`b_on`。
- **公式**
```
own[i]   = csrank(FOWN[i,D1]) - 0.5                 # FOWN 必須在 [0,100] 內；-1 視為缺值
(a, c)   = 當日 U50 有效股的橫斷面 OLS：own[i] ~ b_on[i,t]   # 不用標籤；有效股至少 40
FOres[i] = own[i] - a - c*b_on[i,t]                 # 外資客群程度，已扣除對美股/隔夜的敏感度
foreign_clientele_x_us_shock = FOres[i] * us_overnight_shock_z_t     # NaN → 0；C1 為 0 時本特徵為 0
```
- **正規化**：
  - 用排名可以容忍部分個股因外資持股上限造成的壓縮。
  - 殘差化是為了把「外資客群延續」和「高 beta 股開盤過度反應」分開。不殘差化的話，兩者是同一個迴歸量但預期符號相反。
- **物理意義**：美股消息落在外資客群相對濃厚的股票時（已控制它本來對美股的敏感度），盤中是否會被外資繼續推動。
- **機制**：
  - 外資在亞洲市場（含 TWSE）是美股上漲隔天的買方，衝擊大（Richards 2005）。
  - 法人偏好盤中執行，散戶集中在開盤（Lou, Polk & Skouras 2019）；散戶主導的股票在開盤吃下過度反應（Berkman et al. 2012）。
  - 「外資買單集中在既有高持股股票、且在連續交易時段執行」這一點沒有直接文獻，屬推論。
- **預期符號**：+。
- **來源**：
  - Richards (2005) JFQA 40(1):1-27
  - Froot et al. (2001)
  - Lou, Polk & Skouras (2019)
  - Berkman et al. (2012)

### S5 `vix_regime`
- **scope**：market_state。
- **公式**
```
V = 原生日期 <= t-1 的最後一個 Cboe session 的 ^VIX 收盤
    來源優先序：Cboe VIX_History.csv（repo cboe_vix）→ yfinance ^VIX → 教師 global 列 <= D1（記錄 vix_age_sessions）
    三者都缺時，只能用過去最後已知值向前延續並記錄 age；禁止 bfill
vix_regime = clip( ln(V/20), -1, 2 )      # 20 是事先固定的長期 VIX 公開水準，不從樣本估計
```
- **正規化**：以固定錨點取 log 比值。VIX 會均值回歸，所以這個量近似平穩；不需暖身，也不會把整年高波動「正常化」掉。不使用教師 VIX，因為它落後 1–9 個 session，而且 Fixed 與 Live 版本的落後程度不同。
- **物理意義**：全球股市的恐慌程度相對於長期常態。
- **機制**：主要角色是 S7 的調節變數，並作為 S7 交互作用的主效果。直接效果呈非單調：只有極高 VIX 預示短期反彈（Giot 2002），線性項大致無效。
- **預期符號**：約為 0（調節用）。
- **來源**：
  - Giot (2002) CORE DP 2002/50
  - LeBaron (1992) J. Business 65(2):199-219
  - Nagel (2012) RFS 25(7):2005-2039

### S6 `mkt_intraday_lag_z`
- **scope**：market_state。**raw**：U50 在 D1 的 `adj_open`、`adj_close`。
- **公式**
```
m_D1 = mean_{i∈U50 有效} r_id[i,D1]                 # 有效股至少 40；與計分方式一樣等權
s    = std(m，取到 D2 為止的 60 個 TWSE 交易日)       # 暖身期 expanding，至少 20 個
mkt_intraday_lag_z = clip(m_D1 / s, -4, 4)           # 不扣平均值
```
- **物理意義**：昨天這 50 檔整體的 open-to-close 走勢，也就是計分中「市場擇時」成分的落後一期值。
- **機制**：
  - 盤中與隔夜由不同客群驅動，盤中客群需求具持續性（LPS 2019）。
  - 台灣投資人對盤中資訊反應不足（Ho et al. 2023）。
  - 低波動時期，指數報酬因正回饋交易者而呈弱正自相關（Sentana & Wadhwani 1992）。
  - 這些都是間接證據：多屬橫斷面或 close-to-close，而且兩個盤中窗口之間隔了一段美股與開盤缺口。
- **預期符號**：+（平靜期）。
- **來源**：
  - Lou, Polk & Skouras (2019)
  - Ho et al. (2023)
  - Sentana & Wadhwani (1992) Economic Journal 102(411):415-425

### S7 `lagged_move_x_vix`
- **scope**：interaction（市場 × 市場）。
- **公式**：`lagged_move_x_vix = clip(mkt_intraday_lag_z * vix_regime, -4, 4)`
- **物理意義**：昨天的市場走勢在平靜期傾向延續，在恐慌期傾向反轉。等效的落後斜率是 `β_S6 + β_S7*ln(V/20)`，在固定、可解釋的 VIX 水準切換符號。
- **機制**：
  - 指數一階自相關隨波動上升而下降，高波動時轉負（LeBaron 1992；Sentana & Wadhwani 1992）。
  - 流動性提供的報酬隨 VIX 上升（Nagel 2012），這是橫斷面證據，對指數層級只是弱支持。
  - 簡單模型不會自行發現這個交互作用，所以由領域知識寫進 Φ。
- **預期符號**：−。
- **來源**：
  - LeBaron (1992)
  - Sentana & Wadhwani (1992)
  - Nagel (2012)

### S8 `pre_long_closure`
- **scope**：market_state（往前看的日曆特徵）。
- **公式**
```
next_t = t 之後下一個「排定」TWSE 交易日（只用 t 當時已預公告的休市表）
pre_long_closure = 1{ days(next_t - t) >= 4 }
```
颱風臨時停市只在 08:10 前已公告時才算。歷史值必須用當時的年度預公告休市表，或用實際交易日扣除已知的颱風停市日（例如 2024-07-24/25、2024-10-02/03、2024-10-31）重建，不能直接用實現的交易日。
- **物理意義**：今天是長假（例如春節、端午、中秋）前的最後一個交易日。
- **機制**：
  - 節前報酬異常偏高，常見解釋是長期無法調整部位前的空頭回補與降槓桿，以及節日情緒（Ariel 1990；Kim & Park 1994）。
  - 台灣有顯著的農曆年前效應（Yuan & Gupta 2014）。
  - 反向力量：年前換現金的賣壓。
- **預期符號**：+。
- **限制**：2020–2026 只有約 30–40 個事件日。
- **來源**：
  - Ariel (1990) JF 45(5):1611-1626
  - Kim & Park (1994) JFQA
  - Yuan & Gupta (2014) QREF 54(4):529-537

### S9 `closure_length_log`
- **scope**：market_state（往回看的日曆特徵，用實際交易日曆）。
- **公式**：`closure_length_log = ln(days(t - D1))`，連續平日為 0，一般週一為 ln 3。
- **物理意義**：台股開盤前已經休市多久，也就是累積待消化消息的時間長度。
- **機制**：休市期間每小時的資訊量少於交易時間（French & Roll 1986）。
  - 修正：Harris (1986) 指出大型股週一的負報酬發生在開盤「之前」，不在盤中，所以不支持主效果為負。
  - 台灣星期效應的文獻是 Huang, Hu & Liao (2010) "Short Sale, Stock Liquidity, and the Day-of-the-Week Effect: Evidence from the Taiwan Stock Market", RPBFMP 13(1):71-90。它是 close-to-close、樣本在 2008 年以前。
- **預期符號**：不確定。
- **來源**：
  - French & Roll (1986)
  - Harris (1986) JFE 16(1):99-117
  - Huang, Hu & Liao (2010)

### S10 `us_shock_x_long_gap`
- **scope**：interaction（市場 × 日曆），只在這裡定義一次。
- **公式**：`us_shock_x_long_gap = us_overnight_shock_z * 1{days(t - D1) >= 4}`
- **物理意義**：長休市後才到的美股消息，盤中修正方式是否不同。
- **機制**：Fung, Lam & Lam (2010) 發現「冷卻期」之後美股衝擊引起的盤中反轉較小。不過把冷卻期解讀為長休市是我們的推論，而且該檢驗在 TAIFEX 夜盤之前。
- **預期符號**：不確定。在冷卻期假說下為 +，也就是削弱 C1 的反轉。

---

## 4. 設計規則

### 4.1 時間規則
1. **凍結時點**：特徵在 Asia/Taipei 08:10 凍結。`t`、`D1`、`D2` 依 TWSE 官方日曆。
2. **教師個股列**：只能用日期 ≤ D1 的列，包含法人、持股、成交、價格與技術指標。這些都在 D1 盤後才公布。
3. **教師 global 表**：
   - `TX_OI`、`^TWII`、`^KS11` 為同日語意，只能用 ≤ D1 的列。
   - 教師的 `^VIX`、`^GSPC`、`^IXIC` 對齊不穩，落後最多 9 個 session，因此不作為主來源，只當 S5 的最後備援。
4. **yfinance 與 Cboe**：只用原生 session 日期 ≤ t−1（日曆日）的 bar。先在完整的原生序列上計算報酬或波動，再依可用時間對齊到 t。不能在多國日期 inner join 之後把相鄰列當成連續交易日。
   - `TWD=X` 不使用：bar 收盤約在倫敦午夜，換算是台北 07:00 或 08:00，時間語意模糊。
5. **Live ZIP 的新鮮度**：
   - 每個特徵都要檢查所需的 D1 欄位在 08:10 已經填好。若該股或該表最新的有效列不是 D1，則記 NaN。絕對不能把更舊的列當作「昨天」使用。
   - 訓練資料要重現與實盤相同的可得性，以符合抽樣情境。如果歷史上的發布時間無法核實，就標記 `research_assumption`。
6. **日曆特徵**：往前看的特徵（S3 的 W、S8）只用預公告休市表；往回看的特徵（S9）用實際交易日曆。

### 4.2 正規化
1. 只用因果的過去窗口。暖身期用 expanding 窗口並設最小樣本數。禁止全樣本 z 分數、置中 rolling、bfill，以及用未來資料插值。
2. 窗長、權重（0.5/0.5、半衰期 2）、門檻（≥40/50、≥80/100）、clip 界限（±4、±5、[−1,1]、[−1,2]）、VIX 錨點 20、收縮係數 0.5 和 2/3 等，全部在本文件固定。
3. **stock_relative 特徵**：每天在 U50 內置中。厚尾量用 `csrank-0.5`，近常態量用扣平均。置中後只剩橫斷面資訊，不會把市場擇時混進來。需要時先用收縮 beta 扣掉市場成分（C4、S1）。
4. **market_state 特徵**：不扣平均值，因為 0 代表「沒有衝擊」或「沒有淨流量」，正負號有物理意義。以自身過去標準差縮放後 clip。
5. **interaction 特徵**：市場純量乘上已置中的個股特性，結果是純橫斷面特徵（S3、S4）。市場乘市場的交互作用（S7、S10）則屬於擇時。每個交互作用的主效果都已收錄。
6. 只對嚴格為正的量取 log（價格、成交值）。有正負號的量（法人買賣超、TX_OI）只做差分或比例。

### 4.3 缺值與哨兵值
1. **價格、`成交股數`、`成交金額`、`FOWN`**：`-1` 或 ≤0（`FOWN` 為超出 [0,100]）一律視為缺值。
2. **有正負號的欄位**（法人買賣超、`TX_OI`）：`-1` 可能是真實值，因此改用列層級判斷 pending。判準是：`SH ≤ 0` 或 `SH = -1`；或四個法人欄位同時為 `-1`；或網站顯示該組資料未完成。
3. **橫斷面運算**：當日有效股數須 ≥ 40/50，否則該特徵當天全部記 0。
4. **NaN 處理**：置中或縮放後，NaN 一律補 0（中性值），訓練與實盤用同一規則。缺值旗標與 age 只寫入稽核紀錄，不作為模型輸入，以免增加 d_vc。
5. 絕不刪除目標列（股票 × 日期），缺來源時以 NaN 加旗標處理。

### 4.4 橫斷面與市場狀態的分工
1. 計分可以拆成兩部分：「平均預測 × 市場盤中報酬」的擇時部分，以及橫斷面部分。
   - C1–C3、S5–S10 只會影響當天 50 檔的共同傾向。
   - C4–C6、S1–S4 只會影響當天的相對排序。
2. 市場層級的 9 個特徵有效樣本約等於交易日數，不是列數。需要較強的正則化。時間切分以日期分組，同一天的股票不能分到 train 和 validation 兩邊。
3. Z 空間的模型維持簡單：使用正則化線性分數 `p = 1{w·z + b > 0}`。訓練時以 |r| 加權，以對應計分方式。除了本目錄預註冊的交互作用之外，不另加非線性或特徵交叉。
4. 預期符號只用於事後的可解釋性檢查。若學到的符號與預期相反，只記錄並標記，不據此改 Φ。

### 4.5 前置完整性檢查
這些檢查都不使用標籤，只看結構與時間語意，必須在計算特徵前通過。
1. **adj_open 與 adj_close 是否同一還原因子**：在已知除權息日，只檢查開盤相對前收的缺口，絕不看 open-to-close。若不一致，會汙染 C4、S4 與 `b_on`。
2. **TX_OI**：確認 08:10 前已填值，並核實日期語意。
3. **T86 與 `成交股數` 的涵蓋範圍**：鉅額、零股、盤後定價是否一致。
4. **XNYS 排定交易日與 yfinance bar 是否吻合**，用來判斷缺 bar 還是休市。
5. **颱風臨時停市清單與年度預公告休市表**是否已歸檔。
6. **實作驗收測試**：未來或晚發布資料不得進入；不同休市日；缺原生日期；零分母；負的 TX_OI；重複鍵；版本修訂；跨時區。

### 4.6 版本控制
本目錄記為 Φ-v1。程式實作要綁定欄位版本與雜湊。任何修改都要另立新版本並計入試驗預算，不能在 validation 上反覆調整。

---

## 5. 需要但目前沒有的資料

| 想法 | 缺的資料 | 會強化的機制 |
|---|---|---|
| 以夜盤價格當「預期開盤缺口」的錨，量測開盤過度反應 | TAIFEX TX 夜盤（15:00–05:00）收盤 | C1 的雙向機制、ADR 與開盤定價誤差 |
| 開盤競價的委託不平衡 | TWSE 08:30–09:00 試撮價量（也晚於 08:10 凍結時點） | C5 的開盤推升 |
| 散戶當沖強度 | 個股當沖比、當沖成交量 | C5 與 S1 的散戶機制（Barber et al. 2014） |
| 散戶槓桿情緒與賣空限制 | 融資融券餘額 | C5、S1 |
| 週轉率（LPS 的 TURNOVER）與外資持股變化分解 | 流通在外股數 | C5、S4 |
| 乾淨的散戶比重代理變數，用於「注意力 × 散戶客群」交互作用 | 依投資人類別的個股成交值（自然人比重） | C5（Zhang et al. 2023；Aboody et al. 2018） |
| 除權息、填息行為，外資節稅賣壓，還原價完整性 | 除權息與現金增資行事曆 | 4.5 第 1 點、C4 |
| 事件旗標：營收或法說會造成的暴漲日 | 月營收公告日、法說會時間（例如台積電 14:00） | S1（Wang & Lien 2022） |
| 被動調整流量的方向 | MSCI/FTSE/台灣 50/高股息 ETF 生效日與權重變化 | 淨化 C5、S2、S3 |
| 結算日拉抬與轉倉調整後的部位 | 依月份別的 TX_OI、外資 TXO 部位 | C3（結算日 NaN 可改為建模） |
| 自營商避險流量的方向 | 權證發行、到期與避險部位 | 目前不使用 `自營商(避險)` |
| 外資自營商流量 | 外資自營商買賣超（目前不在任何欄位） | C2、C6 |
| 前 30 分鐘動能、漲跌停磁吸效應 | 盤中分時資料 | 屬盤中，08:10 前也不可用 |
| ADR 溢價動態 | ADR 兌回與轉換額度 | 下一版 `tsm_adr_implied_gap_z` |
| 直接的注意力量測 | 新聞、Google Trends、PTT | C5 |
| 主力籌碼 | 分點券商資料 | C6 |

---

## 6. 未收錄與合併紀錄

| 原提案（lens） | 處置 | 理由 |
|---|---|---|
| `us_daytime_shock_z`（overnight） | 併入 C1 | 原稿不可重現：^GSPC 開盤不在來源內，指數開盤價有過時問題。C1 只用收盤。 |
| `us_shock_tail`（overnight） | 依規則濾除 | `reproducible_daily=false`（繼承自上一項）。只在約 5–8% 的日子非零，係數會由少數危機日決定。可在下一版另立預註冊。 |
| `expected_gap_rel`（overnight） | 依規則濾除 | `reproducible_daily=false`。與外資持股交互作用是同一迴歸量但預期符號相反。 |
| `tsm_adr_implied_gap_z`（overnight） | 依規則濾除 | `timing_ok=false`：冬令時 `TWD=X` 約 08:00 才收盤。修正版（FX 改用 ≤ t−2 的 bar、以 dev 自身的標準差縮放、80 天暖身）是 Φ-v2 最強的單一候補。 |
| `us_shock_x_foreign_ownership`（overnight） | drop，殘差化想法併入 S4 | 與高 beta 共線且預期符號相反。S4 改用對 `b_on` 殘差化的外資客群。 |
| `intraday_vs_overnight_tug`（overnight）、`intraday_clientele_tilt`（flows） | 併入 C4 | 同一個 LPS 機制。保留以文獻為錨的 20 日窗口，並加入 beta 殘差化與 `sqrt(n_valid)` 修正。 |
| `retail_attention_open_pressure`（overnight）、`retail_attention_shock`（flows） | 併入 C5 | 同一個 Barber-Odean/Berkman 機制。不用成交筆數，因為受 2020-03-23 連續競價與 2020-10-26 盤中零股的結構斷點影響。 |
| `tug_of_war_1d`（behavioral） | drop | 沒有對應期間的證據，而且是 C4 的 k=1 項。 |
| `limit_lock_prev`（behavioral） | drop | 事件稀少且集中在少數日期，實質上是日期虛擬變數。已被 C5 的 `a_r` 飽和涵蓋。 |
| `attention_x_retail_clientele`（behavioral） | drop | `100−FOWN` 不等於散戶持股（含公股、集團交叉持股）。 |
| `implied_retail_net_demand_5d`（behavioral） | 因冗餘移除 | 近似 −(F+IT+DP)/SH，與 C6、S2 線性相依，而且符號無法預先承諾。「自營商避險不計入法人」的觀點記錄於此。 |
| `foreign_net_delta_market`（flows） | 依規則濾除 | `reproducible_daily=false`：global 表缺 112 天，單位換算路徑也未定。其中的現貨與期貨兩條腿分別由 C2、C3 涵蓋。 |
| `index_expiry_settlement_pressure`（flows） | drop | TX_OI 混合所有月份、事件約 80 個、還有未固定的變體。 |
| `twd_overnight_move_z`（regime） | drop | 時間錯置：可用的 bar 早於 D1 盤中，並且與 C2 冗餘。 |