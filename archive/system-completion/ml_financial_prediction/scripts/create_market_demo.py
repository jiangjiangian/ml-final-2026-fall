"""Write deterministic SYNTHETIC inputs for the market-feature CLI, never real data."""

import argparse
import csv
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    observations, calendars = [], {}
    series_values = {
        "ixic": [100, 110, 99], "gspc": [200, 210, 231],
        "twii": [1000, 1020, 1010], "ks11": [100, 100, 101],
        "vix": [20, 22, 21], "tx_foreign_net_oi": [-10, 0, 15],
    }
    for series, values in series_values.items():
        us = series in {"ixic", "gspc", "vix"}
        dates = ["2026-07-01", "2026-07-02", "2026-07-06"] if us else [
            "2026-07-02", "2026-07-03", "2026-07-06"]
        calendars[series] = {"source": "synthetic_demo", "session_dates": dates,
                             "calendar_evidence": "SYNTHETIC example calendar; not production evidence"}
        for day, value in zip(dates, values):
            event = day + ("T20:00:00+00:00" if us else "T06:00:00+00:00")
            available = day + ("T20:10:00+00:00" if us else "T06:10:00+00:00")
            observations.append({
                "source": "synthetic_demo", "series_id": series, "session_date": day,
                "event_time": event, "published_at": event, "available_at": available,
                "availability_basis": "conservative_assumption",
                "availability_evidence": "SYNTHETIC 10-minute delay, not a verified source schedule",
                "fetched_at": "2026-10-25T00:00:00+00:00", "value": value,
                "unit": "contracts" if series == "tx_foreign_net_oi" else "index_point",
                "revision_id": "synthetic-v1", "source_url": "https://example.org/synthetic",
                "payload_sha256": hashlib.sha256(f"synthetic:{series}:{day}:{value}".encode()).hexdigest(),
            })
    for name, data in (("observations.json", observations), ("sessions.json", calendars)):
        (args.out_dir / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    with (args.out_dir / "targets.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["target_date", "feature_cutoff"])
        for day in ("2026-07-03", "2026-07-06", "2026-07-07"):
            writer.writerow([day, day + "T08:10:00+08:00"])
    print("SYNTHETIC inputs written to", args.out_dir)


if __name__ == "__main__":
    main()
