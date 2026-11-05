"""Predict from an explicitly trusted local model bundle; no fitting or submission."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finpred.inference.predict import predict_rows
from finpred.training.fit import load_model_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trusted-model-dir",
        type=Path,
        required=True,
        help="Only locally controlled bundles produced by this project; joblib is executable serialization",
    )
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--require-production", action="store_true")
    args = parser.parse_args()
    try:
        if args.out.resolve() in {
            args.features.resolve(),
            (args.trusted_model_dir / "manifest.json").resolve(),
            (args.trusted_model_dir / "model.joblib").resolve(),
        }:
            raise ValueError("output must not overwrite model or feature inputs")
        if args.out.exists():
            raise ValueError("prediction output already exists")
        bundle = load_model_bundle(args.trusted_model_dir, trusted=True)
        table = json.loads(args.features.read_bytes())
        predictions = predict_rows(
            bundle,
            table["rows"],
            feature_columns=table["feature_columns"],
            feature_version=table["feature_version"],
            require_production=args.require_production,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        args.out.write_text(
            json.dumps({"predictions": predictions, "model": bundle.metadata}, indent=2)
            + "\n"
        )
        args.out.chmod(0o600)
        print(
            json.dumps(
                {
                    "status": "predicted",
                    "rows": len(predictions),
                    "production_eligible": bundle.metadata["production_eligible"],
                }
            )
        )
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
