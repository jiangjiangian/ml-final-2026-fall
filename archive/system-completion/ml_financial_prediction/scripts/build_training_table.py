"""Build explicitly exploratory stock lags from audited course snapshots."""

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.data.training_table import build_research_table, canonical_table_hash, read_course_archives


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--training-zip', type=Path, required=True)
    parser.add_argument('--live-zip', type=Path, action='append', default=[])
    parser.add_argument('--market-csv', type=Path)
    parser.add_argument('--market-report', type=Path)
    parser.add_argument('--market-feature', action='append', help='Explicit selected numeric market columns; default all M0')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--allow-research-assumptions', action='store_true', required=True)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[2]
    if args.out.resolve().is_relative_to(checkout):
        parser.error('training tables must remain outside Git checkout')
    if bool(args.market_csv) != bool(args.market_report):
        parser.error('market CSV and report must be provided together')
    stocks, sources = read_course_archives(args.training_zip.read_bytes(), [p.read_bytes() for p in args.live_zip])
    market, report = None, None
    if args.market_csv:
        payload = args.market_csv.read_bytes()
        report = json.loads(args.market_report.read_text())
        expected = report.get('manifest', {}).get('output_csv_sha256', report.get('output_csv_sha256'))
        if not isinstance(expected, str) or hashlib.sha256(payload).hexdigest() != expected:
            parser.error('market CSV hash must match its alignment report manifest')
        market = list(csv.DictReader(io.StringIO(payload.decode('utf-8-sig'), newline='')))
    table = build_research_table(stocks, provenance=sources, market_rows=market, market_report=report, market_features=args.market_feature)
    args.out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=args.out.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(table, stream, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
        os.replace(temporary, args.out)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(json.dumps({'status': table['readiness'], 'audit': table['audit'],
                      'sha256': canonical_table_hash(table), 'out': str(args.out)}))


if __name__ == '__main__':
    main()
