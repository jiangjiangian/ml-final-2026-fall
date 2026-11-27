"""端到端 smoke 測試：假資料、`patch` 主幹、1 階 1 epoch、`max_train_days` 很小。

跑完要有 `report.json`、`config.json`、`history.csv`、預測檔，預測沒有 NaN，設定存得回來。
另外用 `main` 跑一次命令列（同樣很小的設定），確認參數解析和退出碼。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")

from twfm.config import FinetuneConfig, ModelConfig, PipelineConfig, StageConfig  # noqa: E402
from twfm.data.synthetic import make_synthetic_market  # noqa: E402
from twfm.pipeline import (  # noqa: E402
    main,
    parse_stages,
    run_pipeline,
    split_by_fraction,
    synthetic_pipeline_config,
)

MAX_TRAIN_DAYS = 20


def _small_cfg(out_dir: Path) -> PipelineConfig:
    return PipelineConfig(
        model=ModelConfig(backbone="patch", patch_layers=2, patch_d_model=32, patch_heads=2, head_hidden=32),
        finetune=FinetuneConfig(
            stages=(StageConfig(name="head", trainable="head", epochs=1, warmup_steps=0),),
            batch_days=4,
            num_workers=0,
        ),
        out_dir=str(out_dir),
        device="cpu",
    )


def test_split_by_fraction_orders_dates() -> None:
    days = pd.bdate_range("2020-01-01", periods=50)
    split = split_by_fraction(days)
    assert pd.Timestamp(split.train_start) == days[0]
    assert pd.Timestamp(split.train_end) < pd.Timestamp(split.val_start)
    assert pd.Timestamp(split.val_end) < pd.Timestamp(split.test_start)
    assert pd.Timestamp(split.train_end) == days[29]
    assert pd.Timestamp(split.test_start) == days[40]
    with pytest.raises(ValueError):
        split_by_fraction(days[:5])


def test_parse_stages() -> None:
    stages = parse_stages("head,last_k,lora", epochs=2)
    assert [s.trainable for s in stages] == ["head", "last_k", "lora"]
    assert all(s.epochs == 2 for s in stages)
    with pytest.raises(ValueError):
        parse_stages("head,nope")
    with pytest.raises(ValueError):
        parse_stages("head,head")


def test_pipeline_synthetic_patch(tmp_path: Path) -> None:
    market = make_synthetic_market(n_stocks=24, n_days=260, seed=7)
    cfg = synthetic_pipeline_config(_small_cfg(tmp_path / "out"), market)
    assert cfg.data.universe_refresh == "monthly"
    assert PipelineConfig.from_dict(cfg.to_dict()) == cfg

    report = run_pipeline(cfg, data=market, max_train_days=MAX_TRAIN_DAYS, probe=True, verbose=False)
    out = Path(cfg.out_dir)
    assert report["status"] == "done"
    for name in ("config.json", "report.json", "history.csv", "predictions_val.csv", "predictions_test.csv"):
        assert (out / name).exists(), name
    assert (out / "checkpoints" / "best.pt").exists()

    with open(out / "config.json", encoding="utf-8") as f:
        assert PipelineConfig.from_dict(json.load(f)) == cfg
    with open(out / "report.json", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["status"] == "done"
    assert set(saved["n_samples"]) == {"train", "val", "test"}
    assert 0 < saved["n_days"]["train"] <= MAX_TRAIN_DAYS
    assert saved["n_samples"]["val"] > 0 and saved["n_samples"]["test"] > 0
    assert saved["n_stock_cov"] == len(saved["stock_cov_cols"]) > 0
    assert saved["n_market_cov"] == len(saved["market_cov_cols"]) > 0

    history = pd.read_csv(out / "history.csv")
    assert len(history) == 1
    assert history["stage"].tolist() == ["head"]

    split_days: dict[str, pd.Series] = {}
    for part in ("val", "test"):
        pred = pd.read_csv(out / f"predictions_{part}.csv", dtype={"stock_id": str}, parse_dates=["date"])
        assert len(pred) == saved["n_samples"][part]
        assert np.isfinite(pred["score"].to_numpy(dtype=np.float64)).all()
        assert np.isfinite(pred["label_r"].to_numpy(dtype=np.float64)).all()
        assert not pred.duplicated(["date", "stock_id"]).any()
        split_days[part] = pred["date"]
        r = saved[part]
        assert r["n_rows"] == len(pred)
        assert set(r["modes"]) == {"half_half", "top_bottom_k", "long_top_k"}
        assert "0.28" in r["cost"]["round_trip_rate_by_discount"]
    assert split_days["val"].max() < split_days["test"].min()

    probe = saved["probe"]
    assert probe is not None and probe["val"]["n_rows"] == saved["n_samples"]["val"]
    probe_pred = pd.read_csv(out / "probe_predictions_val.csv")
    assert np.isfinite(probe_pred["score"].to_numpy(dtype=np.float64)).all()


def test_main_cli_synthetic(tmp_path: Path) -> None:
    out = tmp_path / "cli"
    code = main(
        [
            "--synthetic",
            "--synthetic-stocks",
            "12",
            "--synthetic-days",
            "200",
            "--backbone",
            "patch",
            "--stages",
            "head",
            "--epochs",
            "1",
            "--lookback",
            "16",
            "--batch-days",
            "4",
            "--max-train-days",
            "10",
            "--num-workers",
            "0",
            "--device",
            "cpu",
            "--out",
            str(out),
            "--quiet",
        ]
    )
    assert code == 0
    with open(out / "report.json", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["status"] == "done"
    with open(out / "config.json", encoding="utf-8") as f:
        cfg = PipelineConfig.from_dict(json.load(f))
    assert cfg.data.lookback == 16
    assert cfg.model.backbone == "patch"
    assert [s.name for s in cfg.finetune.stages] == ["head"]
