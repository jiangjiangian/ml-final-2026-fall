import csv
import io
import json
import unittest
import zipfile

from finpred.data.course_schema import (
    GLOBAL_COLUMNS,
    STOCK_COLUMNS,
    CourseSchemaError,
    audit_course_zip,
    compare_course_archives,
    partition_stock_row,
)


def csv_bytes(columns, rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def stock_row(day='2026-10-22', label='1', **updates):
    row = dict.fromkeys(STOCK_COLUMNS, '1')
    row.update({'date': day, 'etl:adj_open': '10', 'etl:adj_close': '11', 'y': label, 'MACD': '-1'})
    row.update(updates)
    return row


def make_zip(kind='training', rows=None, mutate=None):
    members = {
        'data/market/0050.csv': csv_bytes(STOCK_COLUMNS, rows or [stock_row()]),
        'data/market/2330.csv': csv_bytes(STOCK_COLUMNS, [stock_row()]),
        'data/global/global_data.csv': csv_bytes(GLOBAL_COLUMNS, [dict.fromkeys(GLOBAL_COLUMNS, '1') | {'date': '2026-10-22', 'TX_OI': '-1'}]),
    }
    if kind == 'training':
        members['data/info.json'] = json.dumps({'Top50@Y': ['0050'], 'Top100@Y': ['0050', '2330']}).encode()
    if mutate:
        mutate(members)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return output.getvalue()


class CourseSchemaTests(unittest.TestCase):
    def audit(self, payload, kind='training', **kwargs):
        return audit_course_zip(payload, kind, expected_stock_count=2, expected_target_count=1, **kwargs)

    def test_full_audit_keeps_string_ids_signed_values_and_time_block(self):
        report = self.audit(make_zip())
        self.assertEqual(report['stock_ids'], ['0050', '2330'])
        self.assertEqual(report['complete_labels'], 2)
        self.assertEqual(report['global']['minus_one_by_column']['TX_OI'], 1)
        self.assertEqual(report['stocks']['0050']['minus_one_by_column']['MACD'], 1)
        self.assertEqual(report['readiness']['training'], 'blocked_pending_time_evidence')

    def test_live_pending_label_does_not_become_binary(self):
        report = self.audit(make_zip('live', [stock_row(label='-1')]), 'live')
        self.assertEqual(report['pending_labels'], 1)
        self.assertEqual(report['pending_label_dates'], ['2026-10-22'])
        self.assertEqual(report['complete_labels'], 1)
        self.assertIsNone(report['info'])

    def test_outcomes_are_physically_excluded_from_candidate_partition(self):
        labels, candidates = partition_stock_row(stock_row(), '0050')
        self.assertEqual(labels['y'], '1')
        self.assertEqual(candidates['stock_id'], '0050')
        self.assertFalse(set(candidates) & {'y', 'etl:adj_open', 'etl:adj_close', 'etl:adj_high', 'etl:adj_low'})

    def test_label_mismatch_and_fixed_pending_are_rejected(self):
        for label in ('0', '-1', 'nan'):
            with self.subTest(label=label), self.assertRaises(CourseSchemaError):
                self.audit(make_zip(rows=[stock_row(label=label)]))

    def test_duplicate_dates_and_nonfinite_values_are_rejected(self):
        variants = ([stock_row(), stock_row()], [stock_row(MACD='inf')])
        for rows in variants:
            with self.subTest(rows=rows), self.assertRaises(CourseSchemaError):
                self.audit(make_zip(rows=rows))

    def test_traversal_unexpected_member_and_universe_drift_are_rejected(self):
        for name in ('../escape', 'unexpected.txt'):
            with self.subTest(name=name), self.assertRaises(CourseSchemaError):
                self.audit(make_zip(mutate=lambda m: m.update({name: b'bad'})))
        with self.assertRaises(CourseSchemaError):
            self.audit(make_zip('live'), 'live', expected_stock_ids=['2330', '1101'])

    def test_html_and_schema_changes_are_rejected(self):
        with self.assertRaises(CourseSchemaError):
            self.audit(b'<html>login</html>')
        with self.assertRaises(CourseSchemaError):
            self.audit(make_zip(mutate=lambda m: m.update({'data/market/2330.csv': b'date,y\n2026-10-22,1\n'})))

    def test_missing_numeric_cells_reported_without_filling(self):
        report = self.audit(make_zip(rows=[stock_row(MACD='nan')]))
        self.assertEqual(report['stocks']['0050']['missing_by_column']['MACD'], 1)

    def test_production_target_count_cannot_shrink_with_consistent_bad_metadata(self):
        with self.assertRaisesRegex(CourseSchemaError, 'target stock universe size'):
            audit_course_zip(make_zip(), expected_stock_count=2)

    def test_snapshot_diff_counts_late_completion_as_revision_not_append(self):
        before = make_zip('live', [stock_row(label='-1')])
        after = make_zip('live', [stock_row(label='1')])
        result = compare_course_archives(before, after, expected_stock_count=2)
        self.assertEqual(result['stocks']['added_keys'], 0)
        self.assertEqual(result['stocks']['changed_keys'], 1)
        self.assertEqual(result['stocks']['changed_by_column'], {'y': 1})
        self.assertEqual(result['stocks']['pending_to_complete'], 1)
        self.assertEqual(result['global']['changed_keys'], 0)

    def test_snapshot_diff_preserves_added_removed_and_changed_keys_separately(self):
        before = make_zip('live', [stock_row('2026-10-21'), stock_row('2026-10-22')])
        after = make_zip('live', [stock_row('2026-10-22', MACD='-2'), stock_row('2026-10-23')])
        result = compare_course_archives(before, after, expected_stock_count=2)
        self.assertEqual(result['stocks']['added_keys'], 1)
        self.assertEqual(result['stocks']['removed_keys'], 1)
        self.assertEqual(result['stocks']['changed_keys'], 1)
        self.assertEqual(result['stocks']['changed_by_column'], {'MACD': 1})

    def test_identical_snapshot_diff_is_empty_and_invalid_input_rejected(self):
        payload = make_zip('live')
        result = compare_course_archives(payload, payload, expected_stock_count=2)
        for section in ('stocks', 'global'):
            self.assertEqual(result[section]['added_keys'], 0)
            self.assertEqual(result[section]['removed_keys'], 0)
            self.assertEqual(result[section]['changed_keys'], 0)
        with self.assertRaises(CourseSchemaError):
            compare_course_archives(payload, b'not a zip', expected_stock_count=2)


if __name__ == '__main__':
    unittest.main()
