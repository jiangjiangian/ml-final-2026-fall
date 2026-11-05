"""一個指令跑完一天：爬蟲 → 特徵 → 訓練 → 預測 → 上傳。

用法：
    python run_daily.py              正常跑
    python run_daily.py --skip-train 沿用 models/ 裡的模型，不重新訓練

任何一步失敗就停下並在 log 寫原因，不往下跑；已經產生的檔案保留，方便人工接手。
每一步開始前都檢查還沒過台北 09:00。
"""

import argparse

STEPS = ["crawler", "features", "train", "predict", "submit"]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-train", action="store_true", help="沿用 models/ 裡的模型")
    parser.parse_args()
    # 依序 import src.<步驟> 並呼叫它的 main()；--skip-train 時跳過 train。
    raise NotImplementedError


if __name__ == "__main__":
    main()
