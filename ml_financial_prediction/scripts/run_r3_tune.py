"""Optuna study on the 2022-2023 tuning window, then one full dev run (research only)."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from finpred.training import r3_experiment as rx  # noqa: E402
from finpred.training import r3_tune  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="base config JSON (family/features)")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--attempts-log", default=str(ROOT / "docs" / "r3" / "attempts.jsonl"))
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args(argv)
    out_root = Path(args.out_root).resolve()
    if any((parent / ".git").exists() for parent in (out_root, *out_root.parents)):
        raise SystemExit("--out-root must be outside any Git checkout")
    base = json.loads(Path(args.config).read_text())
    log = Path(args.attempts_log)
    study = r3_tune.tune(base, data_root=args.data_root, out_root=str(out_root), log_path=log,
                         n_trials=args.trials, threads=args.threads)
    print(json.dumps({"attempt": study["attempt"], "best_params": study["best_params"],
                      "best_tuning_score": study["best_tuning_score"]}))
    confirm = {**base, "name": base["name"] + "_tuned", "params": study["best_params"],
               "hypothesis": "Optuna params chosen on 2022-2023 only; 2024-2025 is the confirmation",
               "tuned_by_attempt": study["attempt"]}
    report = rx.execute(confirm, data_root=args.data_root, out_root=str(out_root), log_path=log,
                        threads=args.threads, baseline_daily=rx.load_baseline_reports(str(out_root), confirm, study["data"]))
    print(json.dumps({"attempt": report["attempt"], "name": report["name"],
                      "score": report["summary"]["score"], "ci95": report["summary"]["ci95"],
                      "subperiods": report["summary"]["subperiods"]}))


if __name__ == "__main__":
    main()
