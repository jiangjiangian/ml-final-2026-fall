"""一個指令跑完一天：爬蟲 → 特徵 → 訓練 → 預測 → 上傳。

用法：
    python run_daily.py                    預測日 t 自動取 /api/state 裡還沒過截止的下一個交易日
    python run_daily.py --date 2026-11-17  指定預測日 t
    python run_daily.py --skip-train       沿用 models/ 裡的模型，不重新訓練

失敗時：
    - crawler 的 yfinance 某個序列失敗，會記在 manifest，流程繼續。
    - 其他步驟失敗就停下，在 data/submission/run_YYYY-MM-DD.log 寫原因；已經產生的檔案留著，方便人工接手。
截止檢查在 predict 和 submit 裡做（見 src/utils.check_deadline）。
"""

import argparse

STEPS = ["crawler", "features", "train", "predict", "submit"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="一個指令跑完一天：爬蟲 → 特徵 → 訓練 → 預測 → 上傳")
    parser.add_argument("--date", help="預測日 t（YYYY-MM-DD）；不給就自動找下一個交易日")
    parser.add_argument("--skip-train", action="store_true", help="沿用 models/ 裡的模型")
    parser.parse_args(argv)
    # 依序 import src.<步驟> 並呼叫它的 main(argv=[...])；各模組的 main 都用 parser.parse_args(argv)，
    # 才不會讀到 run_daily.py 自己的參數。--skip-train 時跳過 train。
    raise NotImplementedError


if __name__ == "__main__":
    main()
