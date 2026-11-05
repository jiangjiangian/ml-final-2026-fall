"""Build frozen R1 feature tables from immutable private source snapshots."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.features.research_expansion import build_research_expansion  # noqa: E402


def _latest(root, pattern):
    if root is None:
        return []
    selected = []
    for directory in sorted(root.glob(pattern)):
        paths = sorted(directory.glob('*.json'))
        if paths:
            selected.append(paths[-1])
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock-table', type=Path, required=True)
    parser.add_argument('--history-root', type=Path, required=True)
    parser.add_argument('--external-root', type=Path)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--mode', choices=('strict', 'research'), default='strict')
    parser.add_argument('--allow-research', action='store_true')
    args = parser.parse_args()
    if args.mode == 'research' and not args.allow_research:
        parser.error('research requires --allow-research')
    if args.out_dir.exists() and any(args.out_dir.iterdir()):
        parser.error('out-dir must not exist or must be empty; frozen results cannot be overwritten')
    try:
        raw_table = args.stock_table.read_bytes()
        result = build_research_expansion(json.loads(raw_table),
                                         _latest(args.history_root, 'yahoo-*/manifests'),
                                         _latest(args.external_root, 'fred_*/manifests'),
                                         mode=args.mode, allow_research=args.allow_research)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        hashes = {}

        def save(name, value):
            payload = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode()
            (args.out_dir / name).write_bytes(payload)
            hashes[name] = hashlib.sha256(payload).hexdigest()

        save('frozen_schema.json', result['schema'])
        for group, table in result['tables'].items():
            save(group + '.json', table)
        if result['market_rows']:
            path = args.out_dir / 'market_features.csv'
            with path.open('w', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(result['market_rows'][0]))
                writer.writeheader()
                writer.writerows(result['market_rows'])
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        result['report'].update(input_table_bytes_sha256=hashlib.sha256(raw_table).hexdigest(),
                                artifact_sha256=hashes)
        save('expansion_report.json', result['report'])
        print(json.dumps({'readiness': result['report']['readiness'],
                          'groups': result['report'].get('group_status'),
                          'stock_rows': result['report'].get('stock_rows', 0),
                          'schema_sha256': result['schema']['schema_sha256'], 'out_dir': str(args.out_dir)}))
        return 2 if result['report']['readiness'] == 'blocked' else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
