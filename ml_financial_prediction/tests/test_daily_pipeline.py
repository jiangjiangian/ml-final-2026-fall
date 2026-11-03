"""Deadline, evidence and fallback contracts; no network or prediction POST."""

import hashlib
import json
import tempfile
import time
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from finpred.pipelines.daily import (
    HISTORY_SERIES, SOURCE_SPECS, PipelineBlocked, _approved, _collect,
    _prediction_table, _submit, _train, bounded_training, run_stage, window,
)


def clock(value):
    return lambda: datetime.fromisoformat('2026-11-02T' + value + '+08:00')


class Client:
    def state(self):
        return {'phase2Days': [{'tradingDate': '2026-11-02', 'enabled': True}]}


def feature_evidence(root, *, columns=None, fetched_at='2026-11-02T08:00:00+08:00'):
    """Private synthetic source bytes and matching snapshot, never a real source claim."""
    from finpred.data.daily_tables import SOURCE_URLS

    source = Path(root) / 'source.json'
    payload = b'{"fixture_lag": 1}\n'
    source.write_bytes(payload)
    source.chmod(0o600)
    manifest = Path(root) / 'source-manifest.json'
    manifest.write_text(json.dumps({'schema_version': 'snapshot-v1', 'source': 'course-live',
        'source_url': SOURCE_URLS['course-live'], 'metadata': {'tls_verified': True},
        'sha256': hashlib.sha256(payload).hexdigest(), 'payload_path': str(source),
        'size_bytes': len(payload), 'fetched_at': fetched_at}))
    manifest.chmod(0o600)
    return {'source': 'course-live', 'payload_sha256': hashlib.sha256(payload).hexdigest(),
            'snapshot_manifest': str(manifest),
            'snapshot_manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
            'feature_columns': columns or ['lag'],
            'availability_basis': {'kind': 'verified_release_policy', 'reference': 'synthetic test contract'},
            'available_at': '2026-11-02T07:00:00+08:00', 'fetched_at': fetched_at}


def canonical_prediction_table(root, *, fetched_at='2026-11-02T07:00:00+08:00', **live_options):
    """Exercise the trusted builder using audited synthetic 100-stock ZIPs."""
    from finpred.data.daily_tables import prepare_prediction_table
    from test_daily_tables import DAY, acquire, index

    training = acquire(root, 'training', DAY + 'T06:00:00+08:00')
    live = acquire(root, 'live', fetched_at, **live_options)
    index(root, [training, live])
    result = prepare_prediction_table(root, DAY)
    if result['status'] != 'prepared':
        raise AssertionError('canonical synthetic fixture should prepare')
    return json.loads(Path(result['table_path']).read_bytes())


class DailyTests(unittest.TestCase):
    def test_exact_window_and_timezone_required(self):
        for value in ('03:59:59', '09:00:00'):
            with self.assertRaises(PipelineBlocked):
                window(clock(value)(), '2026-11-02')
        window(clock('04:00:00')(), '2026-11-02')
        window(datetime.fromisoformat('2026-11-02T00:59:59+00:00'), '2026-11-02')
        with self.assertRaises(ValueError):
            window(datetime(2026, 11, 2, 8), '2026-11-02')

    def test_official_dates_not_weekday_heuristic(self):
        class Closed(Client):
            def state(self):
                return {'phase2Days': []}
        with tempfile.TemporaryDirectory() as root, patch('finpred.pipelines.daily._collect') as collect:
            with self.assertRaises(ValueError):
                run_stage(root, 'collect', target_date='2026-11-02', client=Closed(), clock=clock('04:17:00'))
            collect.assert_not_called()
            log = json.loads((Path(root) / 'runs/2026-11-02/collect.json').read_text())
            self.assertEqual(log['status'], 'blocked')

    def test_freeze_requires_fetch_before_cutoff(self):
        with tempfile.TemporaryDirectory() as root:
            table = canonical_prediction_table(root)
            _prediction_table(table, '2026-11-02', clock('08:10:00')())
            with self.assertRaises(PipelineBlocked):
                _prediction_table(table, '2026-11-02', clock('08:09:59')())
            table['feature_evidence'] = [feature_evidence(root, columns=table['feature_columns'],
                                                       fetched_at='2026-11-02T08:10:01+08:00')]
            with self.assertRaisesRegex(PipelineBlocked, 'after freeze'):
                _prediction_table(table, '2026-11-02', clock('08:20:00')())

    def test_evidence_binds_private_actual_payload_and_covers_all_features(self):
        with tempfile.TemporaryDirectory() as root:
            for mutation in ('missing_column', 'payload_changed', 'public_file', 'no_release_basis', 'bare_times'):
                with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(dir=root) as case_root:
                    table = canonical_prediction_table(case_root)
                    manifest = json.loads(Path(table['feature_evidence'][-1]['snapshot_manifest']).read_bytes())
                    payload = Path(manifest['payload_path'])
                    if mutation == 'missing_column':
                        table['feature_columns'].append('another_lag')
                    elif mutation == 'payload_changed':
                        payload.write_bytes(b'changed')
                    elif mutation == 'public_file':
                        payload.chmod(0o644)
                    elif mutation == 'no_release_basis':
                        table['feature_evidence'][0]['availability_basis'] = {}
                    else:
                        table['feature_evidence'] = [{'available_at': '2026-11-02T07:00:00+08:00',
                                                     'fetched_at': '2026-11-02T08:00:00+08:00'}]
                    with self.assertRaises(PipelineBlocked):
                        _prediction_table(table, '2026-11-02', clock('08:20:00')())

    def test_observed_fetch_proves_current_availability_without_backdating(self):
        with tempfile.TemporaryDirectory() as root:
            table = canonical_prediction_table(root)
            evidence = table['feature_evidence'][-1]
            _prediction_table(table, '2026-11-02', clock('08:20:00')())
            evidence['available_at'] = '2026-11-01T08:00:00+08:00'
            with self.assertRaisesRegex(PipelineBlocked, 'cannot backdate'):
                _prediction_table(table, '2026-11-02', clock('08:20:00')())

    def test_explicit_prediction_values_must_rebuild_from_bound_zip_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            trusted = canonical_prediction_table(root, pending=True)
            _prediction_table(trusted, '2026-11-02', clock('08:20:00')())
            feature = 'stock_prev_intraday_return'
            self.assertIsNone(trusted['rows'][0][feature])
            for mutation in ('feature_value', 'missing_mask', 'stock_order', 'feature_order',
                             'feature_version', 'schema', 'cutoff', 'current_label',
                             'provenance', 'transform'):
                with self.subTest(mutation=mutation):
                    table = deepcopy(trusted)
                    if mutation == 'feature_value':
                        table['rows'][0]['stock_previous_observation_gap_days'] = 1
                    elif mutation == 'missing_mask':
                        table['rows'][0][feature] = 0.0
                    elif mutation == 'stock_order':
                        table['rows'][:2] = reversed(table['rows'][:2])
                    elif mutation == 'feature_order':
                        table['feature_columns'].reverse()
                    elif mutation == 'feature_version':
                        table['feature_version'] = 'external-v1'
                    elif mutation == 'schema':
                        table['schema_version'] = 'training-table-v1'
                    elif mutation == 'cutoff':
                        # The same instant with a different representation is
                        # not the output of the canonical trusted transform.
                        table['rows'][0]['feature_cutoff'] = '2026-11-02T00:10:00+00:00'
                    elif mutation == 'current_label':
                        table['rows'][0]['y'] = 1
                    elif mutation == 'provenance':
                        table['provenance'][0]['sha256'] = '0' * 64
                    else:
                        table['transform_code_sha256'] = {}
                    with self.assertRaisesRegex(PipelineBlocked, 'trusted course-source reconstruction'):
                        _prediction_table(table, '2026-11-02', clock('08:20:00')())

    def test_valid_source_hash_cannot_certify_arbitrary_or_external_input_values(self):
        with tempfile.TemporaryDirectory() as root:
            table = canonical_prediction_table(root)
            table['rows'][0]['stock_prev_intraday_return'] = 500.0
            with self.assertRaisesRegex(PipelineBlocked, 'trusted course-source reconstruction'):
                _prediction_table(table, '2026-11-02', clock('08:20:00')())
            table = canonical_prediction_table(root)
            table['feature_columns'].append('external_index_return')
            for row in table['rows']:
                row['external_index_return'] = 0.25
            for item in table['feature_evidence']:
                item['feature_columns'].append('external_index_return')
            with self.assertRaisesRegex(PipelineBlocked, 'trusted course-source reconstruction'):
                _prediction_table(table, '2026-11-02', clock('08:20:00')())

    def test_explicit_prediction_table_cannot_bypass_live_fetch_window(self):
        with tempfile.TemporaryDirectory() as root:
            table = {'readiness': 'verified', 'availability_evidence': 'current observed bytes',
                     'feature_columns': ['lag'],
                     'rows': [{'stock_id': str(n), 'target_date': '2026-11-02',
                               'feature_cutoff': '2026-11-02T08:10:00+08:00'} for n in range(50)]}
            for fetched in ('2026-10-30T23:47:00+08:00', '2026-11-02T03:59:59+08:00'):
                with self.subTest(fetched=fetched):
                    table['feature_evidence'] = [feature_evidence(root, fetched_at=fetched)]
                    with self.assertRaisesRegex(PipelineBlocked, 'target-day'):
                        _prediction_table(table, '2026-11-02', clock('08:20:00')())
            # Sunday 20:00 UTC is Monday 04:00 Taipei, and the Friday source
            # observation remains legitimate over the weekend. This only proves
            # fetch freshness; the test does not certify provider updates.
            table = canonical_prediction_table(root, fetched_at='2026-11-01T20:00:00+00:00')
            _prediction_table(table, '2026-11-02', clock('08:20:00')())

    def test_explicit_prediction_table_requires_matching_live_manifest_and_tls(self):
        with tempfile.TemporaryDirectory() as root:
            table = {'readiness': 'verified', 'availability_evidence': 'observed bytes',
                     'feature_columns': ['lag'],
                     'rows': [{'stock_id': str(n), 'target_date': '2026-11-02',
                               'feature_cutoff': '2026-11-02T08:10:00+08:00'} for n in range(50)]}
            for mutation in ('missing_live', 'missing_tls', 'wrong_url'):
                with self.subTest(mutation=mutation):
                    item = feature_evidence(root)
                    path = Path(item['snapshot_manifest'])
                    manifest = json.loads(path.read_bytes())
                    if mutation == 'missing_live':
                        item['source'] = manifest['source'] = 'fixture'
                    elif mutation == 'missing_tls':
                        manifest['metadata']['tls_verified'] = False
                    else:
                        manifest['source_url'] = 'https://wrong.invalid/data.zip'
                    path.write_text(json.dumps(manifest))
                    item['snapshot_manifest_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                    table['feature_evidence'] = [item]
                    with self.assertRaises(PipelineBlocked):
                        _prediction_table(table, '2026-11-02', clock('08:20:00')())

    def test_automatic_training_preparation_keeps_historical_blocker(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = {'status': 'blocked', 'table_path': None,
                        'report': {'historical_vintage_verified': False}}
            with patch('finpred.pipelines.daily.prepare_training_table', return_value=prepared) as prepare, patch(
                'finpred.pipelines.daily.bounded_training'
            ) as worker:
                with self.assertRaisesRegex(PipelineBlocked, 'historical training availability'):
                    run_stage(directory, 'train', client=Client(), clock=clock('07:20:00'), train_worker=worker)
                prepare.assert_called_once_with(Path(directory), '2026-11-02', allow_research=False)
                worker.assert_not_called()
            manifest = json.loads((Path(directory) / 'runs/2026-11-02/train.json').read_bytes())
            self.assertEqual(manifest['preparation'], prepared)

    def test_timeout_terminates_worker(self):
        def slow(*args, **kwargs):
            time.sleep(10)
        with patch('finpred.pipelines.daily.train_candidate', slow):
            start = time.monotonic()
            result = bounded_training({}, 'unused', {}, 0.05)
        self.assertEqual(result['status'], 'timeout')
        self.assertLess(time.monotonic() - start, 3)

    def test_timeout_retains_incumbent_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table = root / 'table.json'
            table.write_text(json.dumps({'readiness': 'verified'}))
            pointer = root / 'approved.json'
            pointer.write_text('{"existing": true}')
            original = pointer.read_bytes()
            class Bundle:
                metadata = {'family': 'linear', 'objective': 'classification', 'seed': 42}
            with patch('finpred.pipelines.daily._approved', return_value=({'manifest_sha256': 'a' * 64}, Bundle())):
                result = _train(root, '2026-11-02', clock('07:20:00')(), clock('07:49:00'),
                                table, False, lambda *args: {'status': 'timeout'})
            self.assertEqual(result['status'], 'fallback')
            self.assertEqual(pointer.read_bytes(), original)

    def test_research_never_promotes_or_submits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table = root / 'table.json'
            table.write_text(json.dumps({'readiness': 'research_assumption'}))
            result = _train(root, '2026-11-02', clock('07:20:00')(), clock('07:21:00'), table, True,
                            lambda *args: {'ok': True, 'report': {'eligible_for_promotion': True,
                                                                  'readiness': 'verified'}})
            self.assertEqual(result['status'], 'candidate_not_promoted')
            self.assertFalse((root / 'approved.json').exists())
            with patch('finpred.pipelines.daily.execute_submission') as submit:
                with self.assertRaises(PipelineBlocked):
                    run_stage(root, 'submit', client=Client(), clock=clock('08:20:00'), dry_run=False)
                submit.assert_not_called()

    def test_prediction_uses_frozen_bundle_in_official_order(self):
        from finpred.training.fit import fit_model, save_model_bundle

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table = canonical_prediction_table(root)
            stock_ids = [row['stock_id'] for row in table['rows']]
            history = {'schema_version': 'training-table-v1', 'readiness': 'verified',
                       'availability_evidence': 'mock source contract',
                       'feature_columns': table['feature_columns'],
                       'feature_version': table['feature_version'], 'rows': []}
            for n, sid in enumerate(stock_ids):
                y = n % 2
                history['rows'].append({'stock_id': sid, 'target_date': '2026-10-30',
                    'feature_cutoff': '2026-10-30T08:10:00+08:00',
                    'label_available_at': '2026-10-30T14:00:00+08:00',
                    'y': y, 'adj_open': 100, 'adj_close': 100 + (1 if y else -1),
                    'target_intraday_return': 0.01 if y else -0.01,
                    **{name: n for name in table['feature_columns']}})
            bundle = fit_model(history, fit_cutoff='2026-11-02T07:20:00+08:00')
            model = root / 'candidates/model'
            save_model_bundle(bundle, model)
            (root / 'approved.json').write_text(json.dumps({'model_path': str(model),
                'manifest_sha256': hashlib.sha256((model / 'manifest.json').read_bytes()).hexdigest()}))
            source = root / 'prediction-table.json'
            source.write_text(json.dumps(table))
            template = ('id,2026-11-02\n' + ''.join(f'{sid},0\n' for sid in reversed(stock_ids))).encode()
            class TemplateClient(Client):
                def daily_template(self, day):
                    return template
            before = (model / 'model.joblib').read_bytes()
            original_table = source.read_bytes()
            read_bytes = Path.read_bytes
            table_reads = []
            def replace_after_read(path):
                payload = read_bytes(path)
                if path == source:
                    table_reads.append(path)
                    source.write_bytes(b'changed after the only input read')
                return payload
            with patch('finpred.pipelines.daily.train_candidate') as fit, patch.object(Path, 'read_bytes', replace_after_read), patch(
                'finpred.pipelines.daily.prepare_prediction_table', return_value={'status': 'prepared', 'table_path': str(source)}
            ) as prepare:
                result = run_stage(root, 'predict', client=TemplateClient(), clock=clock('08:20:00'))
                fit.assert_not_called()
                prepare.assert_called_once_with(root, '2026-11-02')
            self.assertEqual(len(table_reads), 1)
            self.assertEqual(result['feature_table_sha256'], hashlib.sha256(original_table).hexdigest())
            self.assertEqual(result['status'], 'predicted')
            lines = Path(result['csv_path']).read_text().splitlines()
            self.assertEqual([line.split(',')[0] for line in lines[1:]], list(reversed(stock_ids)))
            self.assertEqual((model / 'model.joblib').read_bytes(), before)
            self.assertEqual(Path(result['csv_path']).stat().st_mode & 0o077, 0)

    def test_submit_passes_the_same_csv_buffer_it_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            day_dir = root / 'predictions/2026-11-02'
            day_dir.mkdir(parents=True)
            source = day_dir / 'prediction.csv'
            original = b'id,2026-11-02\n0011,0\n'
            source.write_bytes(original)
            (day_dir / 'latest.json').write_text(json.dumps({'csv_path': str(source),
                'csv_sha256': hashlib.sha256(original).hexdigest(), 'model_manifest_sha256': 'a' * 64,
                'generated_at': '2026-11-02T08:10:00+08:00', 'readiness': {}}))
            read_bytes = Path.read_bytes
            csv_reads = []
            def replace_after_read(path):
                value = read_bytes(path)
                if path == source:
                    csv_reads.append(path)
                    source.write_bytes(b'replaced')
                return value
            bundle = SimpleNamespace(metadata={'production_eligible': True})
            with patch.object(Path, 'read_bytes', replace_after_read), patch(
                'finpred.pipelines.daily._approved', return_value=({'manifest_sha256': 'a' * 64}, bundle)
            ), patch('finpred.pipelines.daily.execute_submission', return_value={'status': 'dry_run'}) as submit:
                _submit(root, '2026-11-02', Client(), clock('08:20:00'), True, None, False)
            self.assertEqual(csv_reads, [source])
            self.assertEqual(submit.call_args.args[1], original)

    def test_candidate_cache_binds_incumbent_and_current_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table = root / 'table.json'
            table.write_text(json.dumps({'readiness': 'verified'}))
            (root / 'approved.json').write_text('{}')
            bundle = SimpleNamespace(metadata={'family': 'linear', 'objective': 'classification', 'seed': 42})
            record = {'manifest_sha256': 'a' * 64}
            destinations = []
            def worker(table, destination, kwargs, timeout):
                destinations.append(destination)
                destination.mkdir(parents=True)
                report = {'eligible_for_promotion': False, 'readiness': 'verified'}
                (destination / 'candidate_report.json').write_text(json.dumps(report))
                return {'ok': True, 'report': report}
            def run():
                return _train(root, '2026-11-02', clock('07:20:00')(), clock('07:21:00'), table, False, worker)
            with patch('finpred.pipelines.daily._approved', return_value=(record, bundle)), patch(
                'finpred.pipelines.daily._hash', return_value='code-a'
            ):
                run()
                run()
                self.assertEqual(len(destinations), 1)
                record['manifest_sha256'] = 'b' * 64
                run()
            with patch('finpred.pipelines.daily._approved', return_value=(record, bundle)), patch(
                'finpred.pipelines.daily._hash', return_value='code-b'
            ):
                run()
            self.assertEqual(len(set(destinations)), 3)

    def test_daily_gru_blocks_until_intervening_context_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / 'candidates/gru'
            model.mkdir(parents=True)
            manifest = model / 'manifest.json'
            manifest.write_text('{}')
            (root / 'approved.json').write_text(json.dumps({'model_path': str(model),
                'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest()}))
            bundle = SimpleNamespace(metadata={'production_eligible': True, 'readiness': 'verified', 'family': 'gru'})
            with patch('finpred.pipelines.daily.load_model_bundle', return_value=bundle):
                with self.assertRaisesRegex(PipelineBlocked, 'intervening feature history'):
                    _approved(root)

    def test_approved_model_blocks_incompatible_package_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / 'candidates/linear'
            model.mkdir(parents=True)
            manifest = model / 'manifest.json'
            manifest.write_text('{}')
            (root / 'approved.json').write_text(json.dumps({'model_path': str(model),
                'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest()}))
            bundle = SimpleNamespace(metadata={'production_eligible': True, 'readiness': 'verified',
                'family': 'linear', 'package_versions': {'scikit-learn': '0.0.0'}})
            with patch('finpred.pipelines.daily.load_model_bundle', return_value=bundle):
                with self.assertRaisesRegex(PipelineBlocked, 'package versions'):
                    _approved(root)

    def test_collection_includes_extra_indices_and_preserves_partial_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            def history(series, start, end, root):
                self.assertEqual(start, '2019-12-01')
                self.assertEqual(end, '2026-11-03')
                if series == 'sox':
                    raise ValueError('controlled fixture failure')
                return {'manifest_path': series + '.json'}
            with patch('finpred.pipelines.daily.download_course_sources', return_value=[{'manifest_path': 'course'}]), patch(
                'finpred.pipelines.daily.download_external', side_effect=lambda source, root: {'manifest_path': source}
            ) as external, patch('finpred.pipelines.daily.download_market_history', side_effect=history) as markets, patch(
                'finpred.pipelines.daily.download_twse_sector_snapshot', return_value={'manifest_path': 'sectors'}
            ):
                result = _collect(Path(directory), '2026-11-02')
            self.assertEqual({call.args[0] for call in markets.call_args_list}, set(HISTORY_SERIES))
            self.assertEqual({call.args[0] for call in external.call_args_list}, set(SOURCE_SPECS))
            self.assertEqual(result['status'], 'partial')
            self.assertEqual(result['failures'], [{'source': 'yahoo-sox', 'error_type': 'ValueError'}])
            self.assertIn('nvda.json', result['manifests'])

    def test_unknown_stage_rejected(self):
        with self.assertRaises(PipelineBlocked):
            run_stage('/unused', 'arbitrary', clock=clock('04:17:00'))


if __name__ == '__main__':
    unittest.main()
