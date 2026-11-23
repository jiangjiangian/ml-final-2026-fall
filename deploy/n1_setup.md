# n1 影子跑的環境（oop）

N1 影子跑（`src/models/m7_n1_js_online.py`，使用者 2026-11-23）要 torch，正式的 `.venv` 不裝。n1 用自己的環境 `.venv-n1`，套件鎖在 `requirements-n1.txt`（和 Kaggle KD 05、UB 04 一樣的版本）。`run_daily.py` 收尾時用 `.venv-n1/bin/python` 開子程序跑 n1；`.venv-n1` 不在時只記一行 WARNING，交件照常。

照下面的順序做：裝環境、把還沒推的程式帶到 oop、在獨立的 worktree 測試、試跑一次今天的資料、最後才推。排程用的 clone 在推之前只多一個 `.venv-n1/`（Git 不追蹤，現在的程式也不會用到），要接 oop 自己的起點時再多 `.cache/n1/`。

## 1. 在 Mac 下載套件

oop 連不到 pypi.org，和 `memory/reference/06-runner-hosts.md` 一樣在 Mac 下載 Linux 版。torch 要 CPU 版，從 PyTorch 自己的套件庫拿：

```bash
uvx --from pip==24.3.1 pip download -r requirements-n1.txt \
  --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple \
  --python-version 3.12 --implementation cp --abi cp312 --abi abi3 --abi none \
  --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
  --platform any --only-binary=:all: -d wheels-n1
ls wheels-n1 | grep -E '^(torch|numpy|pandas|scipy|pytest)-'   # torch-2.11.0+cpu、numpy-2.1.3、pandas-2.3.3、scipy-1.16.3、pytest-9.1.1
scp -r wheels-n1 nccuoop:~/wheels-n1
```

`wheels-n1/` 大約 200 MB，不要 commit。相依的套件（pytest 的 pluggy、iniconfig，torch 的 sympy、networkx 等）`pip download` 會一起抓。

## 2. 在 oop 建 `.venv-n1`

裝在排程用的 clone 裡，因為 config 的 `daily_model.n1.python` 是相對於 repo 的 `.venv-n1/bin/python`：

```bash
cd ~/ml-final-2026-fall
~/.local/bin/uv venv --python 3.12 --allow-existing .venv-n1
~/.local/bin/uv pip install --python .venv-n1/bin/python --no-index --find-links ~/wheels-n1 -r requirements-n1.txt
.venv-n1/bin/python -c "import torch, numpy, pandas, scipy; print(torch.__version__, numpy.__version__, pandas.__version__, scipy.__version__, torch.get_num_threads())"
```

最後一行印出的前四個值要是 `2.11.0+cpu 2.1.3 2.3.3 1.16.3`。第五個是 torch 預設的執行緒數（大約是 CPU 核心數），不用對；m7 跑的時候自己設成 4。版本不同時 n1 每天都會停下（回傳碼 3，log 寫「狀態檔或套件版本對不上」）。`.venv-n1/` 已經在 `.gitignore`（`.venv-*/`）。

## 3. 把還沒推的程式帶到 oop

規則是測完才推、不推別的分支，所以 oop 上還沒有這個 commit。在 Mac 上 commit 之後用 git bundle 帶過去（bundle 會帶上 `models/n1/` 的 `.pt`、`tests/fixtures/n1/` 的 `.gz` 這些二進位檔）：

```bash
# Mac，在 commit 了 n1 的那個 worktree
git fetch origin claude/stock-market-challenger
git bundle create ~/n1.bundle origin/claude/stock-market-challenger..HEAD
scp ~/n1.bundle nccuoop:~/n1.bundle
```

```bash
# oop
cd ~/ml-final-2026-fall
git bundle verify ~/n1.bundle            # 最後一行要是 okay
git fetch ~/n1.bundle HEAD               # 只更新 FETCH_HEAD，不建分支、不動排程的檔
git worktree add --detach ~/mlfinal-n1-test FETCH_HEAD
```

bundle 的起點（Mac 上的 `origin/claude/stock-market-challenger`）要是 oop 已經有的 commit。排程每次都推資料，所以 Mac 上 fetch 到的一定是 oop 推過的。

## 4. 在 oop 測試

在獨立的 worktree 測，不碰排程用的 clone。避開台北 07:00～08:40（排程在跑）。直接用排程 clone 裡兩個環境的 Python 絕對路徑，不在測試的 worktree 建 `.venv` 連結（連結會在 `git status` 顯示成沒追蹤的檔）：

```bash
cd ~/mlfinal-n1-test
~/ml-final-2026-fall/.venv/bin/python -m pytest -q tests/                        # 正式環境：test_n1_model.py 整個跳過（沒有 torch）
~/ml-final-2026-fall/.venv-n1/bin/python -m pytest -q tests/test_n1_model.py     # n1 環境：重現、每天的步驟
~/ml-final-2026-fall/.venv-n1/bin/python -m src.models.m7_n1_js_online --replay-check
git status --porcelain                                                            # 要是空的
```

- `test_n1_model.py` 用 `git archive` 拿 `f02b89d` 的老師檔和 yfinance 檔。worktree 和排程的 clone 共用同一份 Git 資料，拿得到。約 2～4 分鐘。
- `.venv-n1` 裝的只有 n1 的套件，不要用它跑其他測試。
- `--replay-check` 把暫存檔寫在測試 worktree 的 `.cache/n1/`（Git 不追蹤），跑完就刪。

### 重現檢查（`--replay-check`）

只換平台：老師檔和 `sox`、`tsm_adr`、`vix` 用 `f02b89d` 的版本，`gspc` 用 `tests/fixtures/n1/gspc_yahoo_d06.csv`，從 `state_2026-11-12_kd05` 照每天早上的做法逐日走 11-13～11-20，再補更新 11-20。印出的 JSON 要 `unmatched` 是 0、`max_abs_diff` 是 0（不超過 1e-12）、`state_identical` 是 true，回傳碼 0。這三項就是 `test_n1_model.py` 的重現測試。

重現檢查沒過時：

- `max_abs_diff` 很小（例如 1e-7 以下）、`state_identical` 是 false：多半是 oop 的 CPU 和 Kaggle 不同，矩陣運算的最後幾位不一樣。照 UB 04 報告第 8 節第 3 步，改用 oop 自己走出來的 11-20 狀態當起點。要不要接由 Ian 決定。排程用的 clone 推之前還沒有 m7，所以從測試的 worktree 跑，把狀態寫進排程 clone 的 `.cache/n1/`；要在推之前做完，不然第一個早上 n1 會先從 Kaggle 的狀態接上：
  ```bash
  cd ~/mlfinal-n1-test
  ~/ml-final-2026-fall/.venv-n1/bin/python -m src.models.m7_n1_js_online --replay-check --adopt \
    --cache-dir ~/ml-final-2026-fall/.cache/n1
  ```
  `.cache/n1/ub04_v5/` 還沒有 `current.json` 時，才會把走出來的狀態存成起點（`meta.json` 記 `kaggle_state_identical: false` 和最大差）。之後 Kaggle 的核對用容忍度，25/25 和 N1 的猜法要一樣。

  接了以後，這台的 `test_replay_from_kd05_matches_ub04_bit_for_bit` 會一直沒過（它比的是 Kaggle 的狀態）。之後重測時，把它印的 `max_abs_diff` 和 `.cache/n1/ub04_v5/state_2026-11-20/meta.json` 的 `replay_max_abs_diff` 比：一樣是接受過的平台差異，變大就是程式改壞了。`test_the_54_inputs_and_update_targets_match_ub04` 只用 pandas、numpy，要照樣通過。
- 差很大、或 `unmatched` 不是 0：程式或資料有錯，不要上線，先查。

UB 04 報告第 8 節「第一次在 oop 跑之前」的第 2 步（用 oop 當天的資料重播 11-13～11-20、量差多少）不做：沒有工具，下面第 5 節的試跑已經用今天的資料走過整條路，5 天後的 Kaggle 核對也會逐日用同一個 commit 的檔比到逐位元。

## 5. 試跑今天的資料（不寫核對檔）

在台北 08:45～16:10 之間、交易日做（那天的 `data/raw/manifest.json` 和 `shadow_<t>.csv` 已經寫好，傍晚打分還沒開始）。狀態和輸出都寫到暫存資料夾，排程用的 clone 和它的 `.cache/n1/` 都不碰：

```bash
T=$(TZ=Asia/Taipei date +%F)
D=$(mktemp -d ~/n1-dry.XXXX)
git -C ~/ml-final-2026-fall status --porcelain > $D.before     # 跑完要和這份一樣
mkdir -p $D/raw $D/submission $D/cache
ln -s ~/ml-final-2026-fall/data/raw/teacher $D/raw/teacher                 # m7 只讀
cp -r ~/ml-final-2026-fall/data/raw/yfinance ~/ml-final-2026-fall/data/raw/manifest.json $D/raw/
[ -f $D/raw/yfinance/gspc.csv ] || cp $D/raw/yfinance/sox.csv $D/raw/yfinance/gspc.csv   # 上線前還沒有 gspc.csv：只測流程
cp ~/ml-final-2026-fall/data/submission/shadow_$T.csv $D/submission/
cd ~/mlfinal-n1-test
time ~/ml-final-2026-fall/.venv-n1/bin/python -m src.models.m7_n1_js_online --date $T \
  --raw-dir $D/raw --submission-dir $D/submission --cache-dir $D/cache
echo "回傳碼 $?"
git -C ~/ml-final-2026-fall status --porcelain | diff $D.before - && echo "排程的 clone 沒變"
git -C ~/mlfinal-n1-test status --porcelain       # 要是空的
ls $D/submission/n1                               # n1_<t>.csv、inputs_<t>.npz
```

- 要看的：回傳碼 0；印出的一行有「補更新 2026-11-23 …」（到 t 的前一個交易日）和「JS 50 檔」；`time` 的秒數。上線前的 `shadow_<t>.csv` 還沒有 c2v2d 的成員分數，所以「N1 空白（shadow 沒有 ridge_c2v2d）」是對的。
- 這次要從 `models/n1/` 複製起始狀態、補好幾天，比平常的早上慢，可以當逾時的上限參考。
- 回傳碼 2：多半是那天的爬蟲紀錄不是 t（休市、爬蟲停下）。換一個交易日再試。
- 試完 `rm -rf $D $D.before`。

## 6. 第一個早上要看的

1. `data/raw/manifest.json` 的 `yfinance_extra.gspc.status` 是 `ok`。不是時，那天 n1 每個時段都回傳碼 2（log 寫「沒有 yfinance/gspc.csv」），隔天爬蟲再抓，不用處理。抓到過一次以後，抓不到就沿用舊檔照算、記 `stale_us_n1`。
2. `data/submission/run_<t>.log` 有「n1 完成（N 秒）」，`data/submission/n1/n1_<t>.csv` 有 50 列、`pred_n1` 有值。
3. 用第二個早上起的 N 調 `daily_model.n1.timeout_seconds`，設成 N 的 2～3 倍（Kaggle 量的大約 10～20 秒，所以大約 60 秒）。第一個早上要接起始狀態、補好幾天，比較慢，不要用它調。逾時也不會超過「到下一個排程時段的秒數減 210 秒」（`next_slots`、`slot_margin_seconds`：一次 git 呼叫卡到 180 秒的逾時、等 15 秒再推一次，也趕得上下一個時段），剩不到 30 秒時 log 寫「這次不算」，下一個時段再算。
4. 傍晚打分後 `data/submission/shadow_scores.csv` 有 `n1`、`js_n1` 兩個模型，log 有「n1 影子跑 N 天：累計 n1 − c2v2d」。

## 7. 上線（推）

1. 時間：避開台北 07:00～08:40（早上的排程）和 16:10、20:00 前後幾分鐘（傍晚打分也會推）。
2. 在 Mac 上先 `git fetch origin claude/stock-market-challenger`，把 n1 的 commit rebase 到最新的 origin 上（排程每次都推資料，origin 一定比 bundle 的起點新），再推到 `claude/stock-market-challenger`。程式、`models/n1/ub04_v5/`、`requirements-n1.txt`、config、測試要同一次推。
3. 排程下一次 pull 就生效。crontab 不用改。
4. 測完的 worktree 收掉：`git -C ~/ml-final-2026-fall worktree remove ~/mlfinal-n1-test`，`rm ~/n1.bundle`。
5. 要停：`configs/config.yaml` 的 `daily_model.n1.enabled` 改成 `false` 推上去。同一個 commit 把 `tests/test_n1_shadow.py` 的 `test_the_n1_config_block` 裡 `conf["enabled"] is True` 改成 `is False`。

## 5 天後在 Kaggle 核對

- 每天的 `n1_<t>.csv`、`inputs_<t>.npz` 逐日核對（UB 04 報告第 8 節「5 天後在 Kaggle 核對」）。
- 讀 `shadow_<t>.csv` 要用 `pd.read_csv(..., float_precision="round_trip")`，和 m7 讀的方法一樣。預設的讀法可能差最後一位，N1 的分數就不會逐位元一樣。

## 檔案在哪

| 路徑 | 內容 | Git |
|---|---|---|
| `models/n1/ub04_v5/` | 起始狀態（Kaggle UB 04 第 5 版），只讀 | 追蹤 |
| `.cache/n1/ub04_v5/` | 每天更新後的狀態（`current.json`、`state_<最後更新日>/`） | 不追蹤，只在 oop |
| `.cache/n1/n1.lock`、`last_error.txt` | n1 自己的鎖、上一次意外錯誤的 traceback | 不追蹤 |
| `data/submission/n1/` | 每天的 `n1_<t>.csv`、`inputs_<t>.npz`（寫到一半的 `.*.tmp` 在 `.gitignore`） | 排程每次 commit |

`.cache/n1/` 不見時不用手動處理：n1 從 `models/n1/ub04_v5/` 重來，用 `data/submission/n1/inputs_*.npz` 重播以前的每次更新，核對每次更新前後的內容雜湊，再補更新到 t 的前一天。用 `--adopt` 接的起點不在 `models/n1/` 裡，`.cache/n1/` 不見後要先再跑一次 `--replay-check --adopt`。
