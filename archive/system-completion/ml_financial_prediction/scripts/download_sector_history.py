"""Acquire a bounded/resumable batch of official TWSE price-sector calendar dates."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.ingestion.sector_history import (  # noqa: E402
    calendar_dates, collect_sector_history,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True, help='Private cache outside Git')
    parser.add_argument('--date', action='append', help='ISO date; repeat for explicit bounded dates')
    parser.add_argument('--start', help='Inclusive ISO calendar-range start, including weekends')
    parser.add_argument('--end', help='Inclusive ISO calendar-range end')
    parser.add_argument('--max-new-dates', type=int, default=3, help='1..30 attempted new dates per invocation')
    parser.add_argument('--interval-seconds', type=float, default=2.0, help='1..30 seconds between GETs')
    args = parser.parse_args()
    if bool(args.date) == bool(args.start or args.end) or bool(args.start) != bool(args.end):
        parser.error('use --date, or both --start and --end')
    try:
        days = args.date or calendar_dates(args.start, args.end)
        result = collect_sector_history(args.out_dir, days, max_new_dates=args.max_new_dates,
                                        interval_seconds=args.interval_seconds)
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__,
                          'detail': 'Sector collection or cached integrity validation failed.'}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result['failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
