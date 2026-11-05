"""Collect validated public raw series outside Git; no model-ready timing inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finpred.ingestion.external import SOURCE_SPECS, ExternalDataError, download_external


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", choices=sorted(SOURCE_SPECS), required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.out_dir.resolve()
    if any((parent / ".git").exists() for parent in (root, *root.parents)):
        parser.error("--out-dir must be outside a Git checkout")
    results = []
    failed = False
    for source in dict.fromkeys(args.source):
        try:
            manifest = download_external(source, root)
            results.append({
                "source": source,
                "manifest_path": manifest["manifest_path"],
                "sha256": manifest["sha256"],
                "audit": manifest["metadata"]["audit"],
            })
        except (ExternalDataError, OSError, ValueError) as exc:
            failed = True
            # Only controlled adapter messages are safe; OS errors may embed paths.
            message = str(exc) if isinstance(exc, ExternalDataError) else "Snapshot storage failed"
            results.append({"source": source, "status": "failed", "message": message})
    print(json.dumps({"sources": results}, ensure_ascii=False, indent=2))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
