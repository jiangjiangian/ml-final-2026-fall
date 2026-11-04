"""Run R3 development walk-forward configurations (research only, never submits).

Per-key predictions and caches go to ``--out-root`` outside Git; aggregate
metrics are appended to the in-repo attempt log (every failure counts too).
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from finpred.training import r3_experiment as rx  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", action="append", default=[], help="config JSON (repeatable)")
    parser.add_argument("--baselines", action="store_true",
                        help="run any missing baselines for the configs' evaluation window first")
    parser.add_argument("--data-root", required=True, help="checkout of the read-only data branch")
    parser.add_argument("--out-root", required=True, help="private output directory outside Git")
    parser.add_argument("--attempts-log", default=str(ROOT / "docs" / "r3" / "attempts.jsonl"))
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args(argv)
    out_root = Path(args.out_root).resolve()
    if any((parent / ".git").exists() for parent in (out_root, *out_root.parents)):
        raise SystemExit("--out-root must be outside any Git checkout")
    configs = [json.loads(Path(p).read_text()) for p in args.config]
    log = Path(args.attempts_log)
    ff = rx.load_features(args.data_root, str(out_root), max_date=rx.DEFAULTS["max_date"])
    windows = configs or [{"name": "window"}]
    if args.baselines:
        for window in windows:
            have = rx.load_baseline_reports(str(out_root), window, ff.meta)
            for name in rx.BASELINES:
                if name in have:
                    continue
                report = rx.execute(rx.baseline_config(name, window), data_root=args.data_root,
                                    out_root=str(out_root), log_path=log, threads=args.threads, ff=ff)
                print(json.dumps({"attempt": report["attempt"], "name": report["name"],
                                  "score": report["summary"]["score"],
                                  "ci95": report["summary"]["ci95"]}))
    for cfg in configs:
        baselines = rx.load_baseline_reports(str(out_root), cfg, ff.meta)
        report = rx.execute(cfg, data_root=args.data_root, out_root=str(out_root), log_path=log,
                            threads=args.threads, baseline_daily=baselines, ff=ff)
        print(json.dumps({"attempt": report["attempt"], "name": report["name"],
                          "score": report["summary"]["score"], "ci95": report["summary"]["ci95"],
                          "vs": {k: {"diff": v.get("diff"), "ci95": v.get("ci95")}
                                 for k, v in report["paired_vs_baselines"].items()}}))


if __name__ == "__main__":
    main()
