"""Offline schema audit. Does not infer release timestamps or generate features."""

import argparse
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path


def read_rows(archive, name):
    return list(csv.DictReader(io.StringIO(archive.read(name).decode('utf-8-sig'))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', required=True, type=Path)
    parser.add_argument('--template', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    with zipfile.ZipFile(args.zip) as archive:
        global_rows = read_rows(archive, 'data/global/global_data.csv')
        stock_rows = read_rows(archive, 'data/market/2330.csv')
        info = json.loads(archive.read('data/info.json').decode('utf-8-sig'))
    if not global_rows or not stock_rows:
        raise ValueError('Expected nonempty global and 2330 datasets')
    dates = [row['date'] for row in global_rows]
    stock_dates = [row['date'] for row in stock_rows]
    missing_dates = sorted(set(stock_dates) - set(dates))
    oi = [float(row['TX_OI']) for row in global_rows if row['TX_OI'].strip().lower() not in {'', 'nan', 'null'}]
    result = {
        'archive_sha256': hashlib.sha256(args.zip.read_bytes()).hexdigest(),
        'global_rows': len(global_rows),
        'global_date_min': min(dates),
        'global_date_max': max(dates),
        'global_columns': list(global_rows[0]),
        'global_duplicate_dates': len(dates) - len(set(dates)),
        'global_dates_sorted': dates == sorted(dates),
        'global_missing_values': {
            key: sum(row[key].strip().lower() in {'', 'nan', 'null'} for row in global_rows)
            for key in global_rows[0]
        },
        'stock_2330_rows': len(stock_rows),
        'stock_2330_date_min': min(stock_dates),
        'stock_2330_date_max': max(stock_dates),
        'dates_in_stock_2330_absent_global_count': len(missing_dates),
        'dates_absent_examples': missing_dates[:15],
        'tx_oi_min': min(oi) if oi else None,
        'tx_oi_max': max(oi) if oi else None,
        'tx_oi_zero_count': sum(value == 0 for value in oi),
        'info_json_keys': list(info),
        'availability_semantics': 'UNVERIFIED; date alone does not establish publication time or existing shifts',
        'warning': 'Consecutive global rows are not proven consecutive native sessions for each market',
    }
    if args.template:
        with args.template.open(encoding='utf-8-sig', newline='') as stream:
            template = list(csv.reader(stream))
        if not template or len(template[0]) < 2:
            raise ValueError('Empty or malformed template')
        ids = [row[0] for row in template[1:]]
        expected_ids = [str(value) for value in info.get('Top50@Y', [])]
        result['template'] = {
            'stock_count': len(ids),
            'target_date_count': len(template[0]) - 1,
            'unique_stock_count': len(set(ids)),
            'all_rows_same_width': all(len(row) == len(template[0]) for row in template),
            'stock_order_matches_info_top50': ids == expected_ids,
            'header_first': template[0][0],
            'date_min': min(template[0][1:]),
            'date_max': max(template[0][1:]),
            'unique_placeholder_values': sorted({value for row in template[1:] for value in row[1:]}),
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.out), 'global_rows': len(global_rows), 'missing_global_dates_vs_2330': len(missing_dates)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
