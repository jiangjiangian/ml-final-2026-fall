"""Download private research history; no historical availability claims."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finpred.ingestion.market_history import (  # noqa: E402
    HISTORY_SERIES, download_market_history, download_twse_sector_snapshot,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", action="append", choices=sorted(HISTORY_SERIES), required=True)
    parser.add_argument("--start", default="2019-12-01")
    parser.add_argument("--end", required=True, help="Exclusive ISO date")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--include-twse-sectors", action="store_true")
    args = parser.parse_args()
    root = args.out_dir.resolve()
    if any((p / ".git").exists() for p in (root, *root.parents)):
        parser.error("raw history must remain outside Git")
    results, failed = [], False
    for series in dict.fromkeys(args.series):
        try:
            m = download_market_history(series, args.start, args.end, root)
            results.append({"series_id": series, "status": "raw_research_only",
                            "manifest_path": m["manifest_path"], "sha256": m["sha256"],
                            "audit": m["metadata"]["audit"]})
        except (ValueError, OSError):
            failed = True
            results.append({"series_id": series, "status": "failed",
                            "detail": "network, schema or storage validation failed"})
    if args.include_twse_sectors:
        try:
            manifest = download_twse_sector_snapshot(root)
            results.append({"series_id": "twse_sectors", "status": "current_raw_snapshot_only",
                            "manifest_path": manifest["manifest_path"], "sha256": manifest["sha256"],
                            "audit": manifest["metadata"]["audit"]})
        except (ValueError, OSError):
            failed = True
            results.append({"series_id": "twse_sectors", "status": "failed"})
    print(json.dumps({"sources": results}, ensure_ascii=False, indent=2))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
