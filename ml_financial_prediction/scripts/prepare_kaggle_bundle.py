"""Prepare and verify a private, hash-pinned Kaggle input/kernel bundle offline.

No API calls, authentication, dataset creation or kernel submission occurs here.
Run from any directory; all private inputs/outputs must stay outside this checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import stat
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

PROJECT = Path(__file__).resolve().parents[1]
SENSITIVE_KEYS = {
    'password', 'course_password', 'course_email', 'cookie', 'cookies',
    'authorization', 'api_key', 'access_token', 'refresh_token', 'kaggle_api_token',
    'course_live_key', 'secret', 'token',
}
PAYLOAD_FILES = {'training-table.json', 'feature-rows.json', 'model-config.json', 'finpred-code.zip'}
OUTCOME_FIELDS = {'y', 'target_intraday_return', 'adj_open', 'adj_close', 'label_available_at'}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def reject_credentials(value):
    """Reject credentials in inputs rather than silently changing their hashes."""
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                raise ValueError('private credentials must not appear in a training bundle')
            reject_credentials(item)
    elif isinstance(value, list):
        for item in value:
            reject_credentials(item)
    elif isinstance(value, str) and value.startswith(('https://', 'http://')):
        parsed = urlsplit(value)
        if parsed.username or parsed.password or any(k.lower() in SENSITIVE_KEYS for k, _ in parse_qsl(parsed.query)):
            raise ValueError('credential-bearing URLs must not appear in a training bundle')


def _read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('input must be a regular non-symlink file')
    payload = path.read_bytes()
    value = json.loads(payload)
    reject_credentials(value)
    return payload, value


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    path.chmod(0o600)


def _safe_code_files(project):
    src = project / 'src/finpred'
    candidates = list(src.rglob('*.py')) + [project / 'scripts/compare_architectures.py']
    if not src.is_dir() or not candidates:
        raise ValueError('comparison source is missing')
    for path in sorted(candidates):
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(project):
            raise ValueError('code inputs must be regular project files')
        yield path


def validate_input_contract(table, feature_rows, config):
    """Check the separate 50-stock feature transport before any remote upload.

    This validates layout and isolation, not historical publication/vintage proof.
    The comparison runner still performs its date/preprocessing checks.
    """
    columns = table.get('feature_columns', [])
    if not columns or len(columns) != len(set(columns)) or set(columns) & OUTCOME_FIELDS:
        raise ValueError('feature columns must be unique and exclude outcomes')
    if table.get('schema_version') != 'training-table-v1' or not table.get('rows'):
        raise ValueError('a nonempty training-table-v1 input is required')
    if table.get('readiness') not in {'synthetic', 'research_assumption', 'verified'}:
        raise ValueError('training input needs explicit readiness')
    if not isinstance(feature_rows, dict) or feature_rows.get('schema_version') != 'sequence-feature-table-v1':
        raise ValueError('separate sequence-feature-table-v1 metadata and rows are required')
    if feature_rows.get('feature_columns') != columns:
        raise ValueError('feature input columns must match the training contract')
    stocks, dates = feature_rows.get('stock_ids', []), feature_rows.get('target_dates', [])
    if len(stocks) != 50 or len(set(stocks)) != 50 or any(not isinstance(s, str) or not s for s in stocks):
        raise ValueError('complete fixed 50-stock feature universe is required')
    if not dates or dates != sorted(set(dates)):
        raise ValueError('explicit ordered unique target dates are required')
    from datetime import date
    if any(date.fromisoformat(d).isoformat() != d for d in dates):
        raise ValueError('target dates must use canonical ISO dates')
    universe = {(s, d) for s in stocks for d in dates}
    seen = set()
    for row in feature_rows.get('rows', []):
        if set(row) & OUTCOME_FIELDS:
            raise ValueError('feature rows must not carry current outcome fields')
        key = row['stock_id'], row['target_date']
        if key not in universe or key in seen:
            raise ValueError('unexpected or duplicate feature key')
        seen.add(key)
        if not isinstance(row.get('feature_present', True), bool):
            raise ValueError('feature presence must be an explicit boolean')
        for name in columns:
            value = row.get(name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError('features must be finite numeric values or null')
    if seen != universe:
        raise ValueError('all target-date stock slots must be retained, even without labels')
    label_keys = [(r['stock_id'], r['target_date']) for r in table['rows']]
    if len(label_keys) != len(set(label_keys)) or set(label_keys) - universe:
        raise ValueError('labels must be unique and within the feature universe')
    models = config.get('models', [])
    if [m['id'] for m in models] != ['M1', 'M2', 'M3', 'M4']:
        raise ValueError('comparison config must include the four registered architectures in order')
    if config.get('objective', {}).get('expected_stocks') != 50:
        raise ValueError('configuration must retain the official 50-stock universe')
    budget = config.get('validation', {}).get('initial_configuration_budget')
    if budget != 12 or sum(len(m['initial_tuning']['values']) for m in models) != budget:
        raise ValueError('R2 must keep its predeclared twelve-configuration budget')


def prepare_bundle(table_path, feature_rows_path, output, *, owner, project=PROJECT,
                   config_path=None, dataset_slug='finpred-private-inputs'):
    project = Path(project).resolve()
    output = Path(output).resolve()
    if output.is_relative_to(project.parent):
        raise ValueError('private bundle output must be outside the Git checkout')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{2,39}', owner) or owner in {'replace-me', 'yourusername'}:
        raise ValueError('a real Kaggle username slug is required, never an API token')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,49}', dataset_slug):
        raise ValueError('invalid dataset slug')
    if output.exists() and any(output.iterdir()):
        raise ValueError('bundle output is immutable; choose a new empty directory')
    table_bytes, table = _read_json(table_path)
    feature_bytes, feature_rows = _read_json(feature_rows_path)
    config_path = Path(config_path or project / 'configs/research/model_families.json')
    config_bytes, config = _read_json(config_path)
    validate_input_contract(table, feature_rows, config)
    code_files = list(_safe_code_files(project))
    notebook_path = project / 'notebooks/financial_model_comparison.ipynb'
    _, notebook = _read_json(notebook_path)
    _, kernel = _read_json(project / 'configs/kaggle/kernel-metadata.json')
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    data_dir, kernel_dir = output / 'data', output / 'kernel'
    data_dir.mkdir(mode=0o700)
    kernel_dir.mkdir(mode=0o700)
    for filename, payload in [('training-table.json', table_bytes), ('feature-rows.json', feature_bytes),
                              ('model-config.json', config_bytes)]:
        (data_dir / filename).write_bytes(payload)
        (data_dir / filename).chmod(0o600)
    with zipfile.ZipFile(data_dir / 'finpred-code.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in code_files:
            info = zipfile.ZipInfo(str(path.relative_to(project)), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    (data_dir / 'finpred-code.zip').chmod(0o600)
    try:
        code_commit = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'],
                                              text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        code_commit = None
    manifest = {
        'schema_version': 'kaggle-private-input-bundle-v1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'code_commit': code_commit,
        'readiness': table['readiness'],
        'production_eligible': False,
        'training_rows': len(table['rows']),
        'feature_columns': table.get('feature_columns', []),
        'files': {name: {'sha256': sha256((data_dir / name).read_bytes()),
                         'bytes': (data_dir / name).stat().st_size} for name in sorted(PAYLOAD_FILES)},
        'privacy': 'private_course_research_only; no course credentials; no competition submission',
        'validation': config.get('validation', {}),
    }
    _write_json(data_dir / 'bundle-manifest.json', manifest)
    manifest_hash = sha256((data_dir / 'bundle-manifest.json').read_bytes())
    replacement_count = 0
    for cell in notebook['cells']:
        if cell.get('cell_type') != 'code':
            continue
        source = ''.join(cell['source']) if isinstance(cell['source'], list) else cell['source']
        if 'EXPECTED_BUNDLE_MANIFEST_SHA256 = ""' in source:
            source = source.replace('EXPECTED_BUNDLE_MANIFEST_SHA256 = ""',
                                    'EXPECTED_BUNDLE_MANIFEST_SHA256 = ' + json.dumps(manifest_hash))
            replacement_count += 1
        cell['source'] = source
        cell['outputs'] = []
        cell['execution_count'] = None
    if replacement_count != 1:
        raise ValueError('notebook must expose exactly one pinned manifest parameter')
    _write_json(kernel_dir / 'financial_model_comparison.ipynb', notebook)
    kernel.update({'id': owner + '/financial-model-comparison', 'is_private': True,
                   'enable_gpu': False, 'enable_internet': False,
                   'dataset_sources': [owner + '/' + dataset_slug]})
    _write_json(kernel_dir / 'kernel-metadata.json', kernel)
    _write_json(data_dir / 'dataset-metadata.json', {
        'id': owner + '/' + dataset_slug,
        'title': 'Finpred Private Inputs',
        'licenses': [{'name': 'copyright-authors'}],
        'description': 'Private course-team research input; copyright remains with the original authors. '
                       'Not a public release or relicensing. Preserve all source terms. '
                       'Exact bytes are locked by the kernel bundle manifest SHA256.',
    })
    validate_bundle(output)
    return {'bundle_root': str(output), 'manifest_sha256': manifest_hash,
            'remote_uploaded': False, 'kernel_executed_remotely': False,
            'dataset_id': owner + '/' + dataset_slug, 'readiness': table['readiness']}


def validate_bundle(output):
    output = Path(output)
    manifest_path = output / 'data/bundle-manifest.json'
    _, manifest = _read_json(manifest_path)
    if set(manifest.get('files', {})) != PAYLOAD_FILES:
        raise ValueError('bundle must contain exactly the registered input/code payloads')
    for directory, allowed in [('data', PAYLOAD_FILES | {'bundle-manifest.json', 'dataset-metadata.json'}),
                               ('kernel', {'kernel-metadata.json', 'financial_model_comparison.ipynb'})]:
        folder = output / directory
        if folder.is_symlink() or {p.name for p in folder.iterdir()} != allowed:
            raise ValueError('upload directories must contain only registered bundle files')
        if any(p.is_symlink() or not p.is_file() for p in folder.iterdir()):
            raise ValueError('upload inputs must be regular non-symlink files')
    for filename, expected in manifest['files'].items():
        path = output / 'data' / filename
        if path.is_symlink() or sha256(path.read_bytes()) != expected['sha256'] or path.stat().st_size != expected['bytes']:
            raise ValueError('bundle payload hash/size mismatch')
    _, kernel = _read_json(output / 'kernel/kernel-metadata.json')
    if kernel.get('is_private') is not True or kernel.get('enable_internet') is not False:
        raise ValueError('kernel must be private with internet disabled')
    _, dataset = _read_json(output / 'data/dataset-metadata.json')
    if dataset.get('licenses') != [{'name': 'copyright-authors'}] or kernel.get('dataset_sources') != [dataset.get('id')]:
        raise ValueError('private dataset identity/license must match the kernel input')
    if kernel.get('competition_sources') or kernel.get('kernel_sources') or kernel.get('model_sources'):
        raise ValueError('unregistered external inputs must not alter this comparison')
    _, table = _read_json(output / 'data/training-table.json')
    _, feature_rows = _read_json(output / 'data/feature-rows.json')
    _, config = _read_json(output / 'data/model-config.json')
    validate_input_contract(table, feature_rows, config)
    _, notebook = _read_json(output / 'kernel/financial_model_comparison.ipynb')
    sources = '\n'.join(''.join(c['source']) if isinstance(c['source'], list) else c['source']
                        for c in notebook['cells'] if c['cell_type'] == 'code')
    if json.dumps(sha256(manifest_path.read_bytes())) not in sources:
        raise ValueError('kernel does not pin the exact input manifest')
    with zipfile.ZipFile(output / 'data/finpred-code.zip') as archive:
        names = archive.namelist()
        if (not names or len(names) != len(set(names))
                or sum(entry.file_size for entry in archive.infolist()) > 16 * 1024 * 1024):
            raise ValueError('code archive must have unique source members')
        for entry in archive.infolist():
            path = Path(entry.filename)
            if (path.is_absolute() or '..' in path.parts or path.suffix != '.py'
                    or stat.S_ISLNK(entry.external_attr >> 16)
                    or not (entry.filename.startswith('src/finpred/') or entry.filename == 'scripts/compare_architectures.py')):
                raise ValueError('code archive contains an unsafe or unexpected path')
    return {'status': 'passed', 'files_checked': len(PAYLOAD_FILES), 'private': True,
            'input_manifest_pinned': True, 'remote_validation': 'not_run'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--table', type=Path)
    parser.add_argument('--feature-rows', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--owner')
    parser.add_argument('--dataset-slug', default='finpred-private-inputs')
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        result = validate_bundle(args.out_dir)
    else:
        if not all((args.table, args.feature_rows, args.owner)):
            parser.error('--table, --feature-rows and --owner are required to prepare a bundle')
        result = prepare_bundle(args.table, args.feature_rows, args.out_dir, owner=args.owner,
                                config_path=args.config, dataset_slug=args.dataset_slug)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
