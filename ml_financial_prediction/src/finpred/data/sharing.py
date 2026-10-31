"""Portable content-addressed raw snapshots for the private live-data branch.

Transfer times are separate from source acquisition times. Sharing a snapshot
does not certify historical publication time, adjustment vintages or model use.
"""

import hashlib
import json
import os
import re
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit

from finpred.data.snapshots import _exclusive_write

MAX_OBJECT_BYTES = 100 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
SOURCE_PATTERN = r'[a-z][a-z0-9_-]{0,63}'
HASH_PATTERN = r'[a-f0-9]{64}'
BOOLEAN_METADATA_FIELDS = {
    'tls_verified', 'tls_verification', 'historical_vintage_verified',
    'publication_times_verified', 'native_calendar_verified',
}
AUDIT_COUNTS = {
    'row_count', 'stock_rows', 'stock_count', 'member_count', 'missing_values',
    'complete_labels', 'pending_labels', 'selected_row_count',
}
READINESS_VALUES = {
    'validated', 'complete', 'partial', 'unverified', 'blocked_pending_time_evidence',
    'raw_research_only', 'current_raw_snapshot_only', 'raw_downloaded_needs_publication_evidence',
}
SECRET_KEY = re.compile(r'password|cookie|token|secret|authorization|credential|email|api.?key|private.?key', re.I)


class SharingError(ValueError):
    """A safe error whose message never includes source contents or credentials."""


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode()


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _aware(value):
    try:
        if not isinstance(value, str):
            raise ValueError
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.utcoffset() is None:
            raise ValueError
        return parsed
    except (ValueError, TypeError):
        raise SharingError('source time must be an aware ISO timestamp') from None


def _safe_root(value, *, private=False):
    path = Path(value).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise SharingError('storage roots must not contain symlinks')
    if private and any((p / '.git').exists() for p in (path, *path.parents)):
        raise SharingError('consumer runtime must remain outside Git')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if private:
        path.chmod(0o700)
    return path.resolve()


def _inside(root, relative):
    if not isinstance(relative, str):
        raise SharingError('object key must be a portable relative path')
    key = PurePosixPath(relative)
    if key.is_absolute() or '..' in key.parts or '\\' in relative or not key.parts:
        raise SharingError('object key must be a portable relative path')
    path = root.joinpath(*key.parts)
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.resolve().is_relative_to(root):
        raise SharingError('source path escaped storage root or used a symlink')
    return path


def _read(path, *, limit=MAX_METADATA_BYTES):
    if path.is_symlink():
        raise SharingError('expected a bounded regular data file without symlinks')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, 'rb') as stream:
            details = os.fstat(stream.fileno())
            if not stat.S_ISREG(details.st_mode) or details.st_size > limit:
                raise SharingError('expected a bounded regular data file without symlinks')
            payload = stream.read(limit + 1)
            if len(payload) > limit:
                raise SharingError('expected a bounded regular data file without symlinks')
            return payload
    except OSError:
        raise SharingError('expected a bounded regular data file without symlinks') from None


def _immutable(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        if _read(path, limit=max(len(data), MAX_METADATA_BYTES)) != data:
            raise SharingError('immutable object or manifest has conflicting bytes')
        return False
    try:
        _exclusive_write(path, data)
    except FileExistsError:
        if _read(path, limit=max(len(data), MAX_METADATA_BYTES)) != data:
            raise SharingError('concurrent immutable write has conflicting bytes') from None
        return False
    path.chmod(0o600)
    return True


def _replace(path, data, *, limit=MAX_METADATA_BYTES):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() and _read(path, limit=limit) == data:
        return False
    descriptor, name = tempfile.mkstemp(prefix='.sharing-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
    return True


def _public_url(value):
    parts = urlsplit(value)
    if parts.scheme != 'https' or not parts.netloc or parts.username or parts.password:
        raise SharingError('source URLs must use HTTPS without credentials')
    return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))


def _readiness(value):
    if isinstance(value, str):
        return value if value in READINESS_VALUES else None
    if isinstance(value, dict):
        allowed = {'raw_schema', 'labels', 'historical_availability', 'training'}
        return {k: v for k, v in value.items()
                if k in allowed and isinstance(v, str) and v in READINESS_VALUES}
    return None


def _summary(value):
    """Only typed coverage counters/dates are shared from arbitrary audit JSON."""
    if not isinstance(value, dict):
        return {}
    result = {k: v for k, v in value.items() if k in AUDIT_COUNTS and type(v) is int and v >= 0}
    for key in ('date', 'date_min', 'date_max'):
        value_at_key = value.get(key)
        if isinstance(value_at_key, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value_at_key):
            result[key] = value_at_key
    if value.get('kind') in {'training', 'live'}:
        result['kind'] = value['kind']
    if isinstance(value.get('zip_crc_checked'), bool):
        result['zip_crc_checked'] = value['zip_crc_checked']
    if 'readiness' in value:
        result['readiness'] = _readiness(value['readiness'])
    if 'global' in value:
        result['global'] = _summary(value['global'])
    dates = value.get('pending_label_dates')
    if isinstance(dates, list):
        result['pending_label_dates'] = [s for s in dates if isinstance(s, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', s)]
    return result


def _metadata(value):
    # Free-text notes, nested arbitrary dictionaries, request fields, local paths
    # and authentication material are deliberately not part of the share contract.
    result = {k: v for k, v in value.items() if k in BOOLEAN_METADATA_FIELDS and isinstance(v, bool)}
    if 'audit' in value:
        result['audit'] = _summary(value['audit'])
    if 'readiness' in value:
        result['readiness'] = _readiness(value['readiness'])
    return result


def _portable_record(raw, payload_size, suffix, source_manifest_bytes):
    source = raw.get('source')
    if (raw.get('schema_version') != 'snapshot-v1'
            or not isinstance(source, str) or not re.fullmatch(SOURCE_PATTERN, source)
            or not re.fullmatch(r'\.[a-z0-9]{1,8}', suffix)
            or not re.fullmatch(HASH_PATTERN, str(raw.get('sha256', '')))
            or raw.get('size_bytes') != payload_size):
        raise SharingError('source snapshot identity or integrity failed')
    _aware(raw.get('fetched_at'))
    metadata = raw.get('metadata')
    if not isinstance(metadata, dict):
        raise SharingError('source snapshot needs explicit metadata')
    clean = _metadata(metadata)
    result = {'schema_version': 'portable-snapshot-v1', 'source': source,
              'source_url': _public_url(raw['source_url']), 'fetched_at': raw['fetched_at'],
              'sha256': raw['sha256'], 'size_bytes': payload_size,
              'object_key': 'objects/' + raw['sha256'] + suffix,
              'source_manifest_sha256': raw.get('source_snapshot_manifest_sha256', _digest(source_manifest_bytes)),
              'metadata': clean}
    if not re.fullmatch(HASH_PATTERN, str(result['source_manifest_sha256'])):
        raise SharingError('original source manifest hash is malformed')
    encoded = _json_bytes(result)
    # Do not expose active source secrets even if an upstream audit accidentally
    # placed one in a free-text field. Values are never interpolated into errors.
    secrets = {v.encode() for k, v in os.environ.items() if len(v) >= 8
               and any(t in k.upper() for t in ('PASSWORD', 'TOKEN', 'SECRET', 'COOKIE', 'COURSE_EMAIL'))}
    if any(value in encoded for value in secrets):
        raise SharingError('snapshot export contains an active credential literal')
    return result


def _load_catalog(root):
    pointer_path = _inside(root, 'catalog/latest.json')
    if not pointer_path.exists():
        return None, {'schema_version': 'live-data-catalog-v1', 'sources': {}}
    pointer = json.loads(_read(pointer_path))
    digest = pointer.get('catalog_sha256', '')
    if (pointer.get('schema_version') != 'live-data-pointer-v1'
            or not re.fullmatch(HASH_PATTERN, digest)
            or pointer.get('catalog_key') != 'catalog/versions/' + digest + '.json'):
        raise SharingError('invalid portable catalog pointer')
    content = _read(_inside(root, pointer['catalog_key']))
    if _digest(content) != digest:
        raise SharingError('catalog failed its content hash')
    catalog = json.loads(content)
    if catalog.get('schema_version') != 'live-data-catalog-v1' or not isinstance(catalog.get('sources'), dict):
        raise SharingError('invalid portable catalog schema')
    return pointer, catalog


def _validate_record(root, key, source, *, verified_objects=None):
    if not re.fullmatch(SOURCE_PATTERN, source):
        raise SharingError('invalid source identifier in catalog')
    if not re.fullmatch('manifests/' + re.escape(source) + '/' + HASH_PATTERN + r'\.json', key):
        raise SharingError('invalid manifest key in catalog')
    content = _read(_inside(root, key))
    if _digest(content) != PurePosixPath(key).stem:
        raise SharingError('portable manifest failed its content hash')
    record = json.loads(content)
    if record.get('schema_version') != 'portable-snapshot-v1' or record.get('source') != source:
        raise SharingError('portable manifest source or schema differs from catalog')
    digest = record.get('sha256', '')
    if not re.fullmatch(HASH_PATTERN, digest):
        raise SharingError('portable payload hash is invalid')
    object_key = record.get('object_key', '')
    if not re.fullmatch('objects/' + digest + r'\.[a-z0-9]{1,8}', object_key):
        raise SharingError('invalid portable payload key')
    _aware(record.get('fetched_at'))
    if _public_url(record['source_url']) != record['source_url']:
        raise SharingError('portable source URL contains private query data')
    cache = verified_objects if verified_objects is not None else {}
    if object_key not in cache:
        payload = _read(_inside(root, object_key), limit=MAX_OBJECT_BYTES)
        if _digest(payload) != digest:
            raise SharingError('portable payload failed its content hash or size')
        cache[object_key] = len(payload)
    if cache[object_key] != record.get('size_bytes'):
        raise SharingError('portable payload failed its content hash or size')
    if (not re.fullmatch(HASH_PATTERN, record.get('source_manifest_sha256', ''))
            or not isinstance(record.get('metadata'), dict)):
        raise SharingError('portable source provenance is malformed')
    if _metadata(record['metadata']) != record['metadata']:
        raise SharingError('portable metadata contains unsupported private or free-text fields')
    return record


def _source_catalog(root, source, keys, *, verified_objects=None):
    records = [(key, _validate_record(root, key, source, verified_objects=verified_objects))
               for key in sorted(set(keys))]
    records.sort(key=lambda pair: (_aware(pair[1]['fetched_at']), pair[0]))
    newest_time = _aware(records[-1][1]['fetched_at'])
    if len({r['sha256'] for _, r in records if _aware(r['fetched_at']) == newest_time}) != 1:
        raise SharingError('same-time conflicting source revisions are ambiguous')
    key, record = records[-1]
    audit = record['metadata'].get('audit', {})
    return {'latest_manifest': key, 'latest_sha256': record['sha256'],
            'fetched_at': record['fetched_at'], 'history': [k for k, _ in records],
            'readiness': record['metadata'].get('readiness', audit.get('readiness')),
            'pending_labels': audit.get('pending_labels'),
            'complete_labels': audit.get('complete_labels'),
            'date_min': audit.get('date_min', audit.get('global', {}).get('date_min')),
            'date_max': audit.get('date_max', audit.get('global', {}).get('date_max'))}


def export_snapshot_bundle(runtime_root, destination, *, raw_roots=(), required_sources=()):
    """Export validated acquisitions and keep previous successful source versions.

    Sources are existing snapshot-v1 stores. Invalid new inputs fail before the
    latest pointer changes; immutable intermediate objects are safe to retry.
    No training, downloads, Git operation or historical certification occurs.
    """
    runtime = _safe_root(runtime_root)
    bundle = _safe_root(destination)
    roots = [runtime / 'raw', runtime / 'market-history', *map(Path, raw_roots)]
    for raw_root in roots:
        if any(p.is_symlink() for p in (raw_root.absolute(), *raw_root.absolute().parents)):
            raise SharingError('source stores must not contain symlinks')
    roots = sorted({p.resolve() for p in roots if p.exists()})
    _, old = _load_catalog(bundle)
    histories = {s: list(info['history']) for s, info in old['sources'].items()}
    prepared, objects, checked_inputs = [], {}, {}
    secrets = {v.encode() for k, v in os.environ.items() if len(v) >= 8
               and any(t in k.upper() for t in ('PASSWORD', 'TOKEN', 'SECRET', 'COOKIE', 'COURSE_EMAIL'))}
    for raw_root in roots:
        if any(p.is_symlink() for p in (raw_root, *raw_root.parents)):
            raise SharingError('source stores must not contain symlinks')
        for manifest in sorted(raw_root.glob('*/manifests/*.json')):
            if manifest.is_symlink() or manifest.parent.is_symlink() or manifest.parent.parent.is_symlink():
                raise SharingError('source manifests must not use symlinks')
            content = _read(manifest)
            record = json.loads(content)
            source = manifest.parent.parent.name
            if record.get('source') != source:
                raise SharingError('source manifest differs from containing source directory')
            digest = record.get('sha256', '')
            if not re.fullmatch(HASH_PATTERN, digest):
                raise SharingError('source snapshot digest is invalid')
            declared = Path(record.get('payload_path', ''))
            suffix = declared.suffix
            expected = _inside(raw_root, source + '/objects/' + digest + suffix)
            if declared.absolute() != expected:
                raise SharingError('source payload path differs from its content object')
            if expected not in checked_inputs:
                payload = _read(expected, limit=MAX_OBJECT_BYTES)
                if _digest(payload) != digest or any(value in payload for value in secrets):
                    raise SharingError('source payload integrity or credential check failed')
                checked_inputs[expected] = len(payload)
                del payload
            portable = _portable_record(record, checked_inputs[expected], suffix, content)
            encoded = _json_bytes(portable)
            key = 'manifests/' + source + '/' + _digest(encoded) + '.json'
            prepared.append((key, portable, encoded))
            objects.setdefault(portable['object_key'], expected)
    if not prepared and not histories:
        raise SharingError('no source snapshots available for sharing')
    objects_written = manifests_written = 0
    for object_key, source_path in objects.items():
        objects_written += _immutable(_inside(bundle, object_key), _read(source_path, limit=MAX_OBJECT_BYTES))
    for key, portable, encoded in prepared:
        manifests_written += _immutable(_inside(bundle, key), encoded)
        histories.setdefault(portable['source'], []).append(key)
    verified_objects = {}
    sources = {source: _source_catalog(bundle, source, keys, verified_objects=verified_objects)
               for source, keys in sorted(histories.items())}
    required = sorted(set(required_sources) | set(old.get('required_sources', [])))
    if any(not re.fullmatch(SOURCE_PATTERN, source) for source in required):
        raise SharingError('invalid required source identifier')
    collection_path = runtime / 'latest_collection.json'
    failures = []
    collection_status = 'not_provided'
    if collection_path.exists():
        collection = json.loads(_read(collection_path))
        collection_status = collection.get('status') if collection.get('status') in {'partial', 'collected'} else 'unknown'
        for failure in collection.get('failures', []):
            if (re.fullmatch(SOURCE_PATTERN, str(failure.get('source', '')))
                    and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,100}', str(failure.get('error_type', '')))):
                failures.append({'source': failure['source'], 'error_type': failure['error_type']})
    missing = sorted(set(required) - sources.keys())
    catalog = {'schema_version': 'live-data-catalog-v1', 'sources': sources,
               'required_sources': required, 'missing_required_sources': missing,
               'status': 'partial' if missing or failures or collection_status == 'partial' else 'complete',
               'collection': {'status': collection_status, 'failures': failures},
               'availability_scope': 'source fetched_at retained; sharing does not certify historical vintages'}
    content = _json_bytes(catalog)
    digest = _digest(content)
    catalog_key = 'catalog/versions/' + digest + '.json'
    _immutable(_inside(bundle, catalog_key), content)
    changed = _replace(_inside(bundle, 'catalog/latest.json'), _json_bytes({
        'schema_version': 'live-data-pointer-v1', 'catalog_sha256': digest, 'catalog_key': catalog_key}))
    return {'status': catalog['status'], 'catalog_sha256': digest, 'catalog_path': catalog_key,
            'source_count': len(sources), 'manifest_count': sum(len(s['history']) for s in sources.values()),
            'objects_written': objects_written, 'manifests_written': manifests_written,
            'catalog_changed': changed, 'latest': sources}


def import_snapshot_bundle(bundle_root, runtime_root, *, revision=None, received_at=None):
    """Verify a pinned bundle before restoring local private snapshot-v1 records."""
    bundle = _safe_root(bundle_root)
    runtime = _safe_root(runtime_root, private=True)
    pointer, catalog = _load_catalog(bundle)
    if pointer is None:
        raise SharingError('bundle has no successful catalog pointer')
    if revision is not None and not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise SharingError('transport revision must be a resolved Git commit SHA')
    received = received_at or datetime.now(timezone.utc).isoformat()
    received_time = _aware(received)
    prepared, latest_by_source, verified_objects = [], {}, {}
    for source, info in catalog['sources'].items():
        history = info.get('history')
        if not isinstance(history, list) or not history or len(set(history)) != len(history):
            raise SharingError('catalog source history is invalid')
        expected_info = _source_catalog(bundle, source, history, verified_objects=verified_objects)
        if expected_info != info:
            raise SharingError('catalog latest selection differs from immutable source history')
        for key in history:
            record = _validate_record(bundle, key, source, verified_objects=verified_objects)
            if received_time < _aware(record['fetched_at']):
                raise SharingError('consumer cannot receive data before source acquisition')
            prepared.append((key, record))
        latest_by_source[source] = info['latest_manifest']
    restored, latest_paths, restored_objects = [], [], set()
    for key, record in prepared:
        source, digest = record['source'], record['sha256']
        suffix = PurePosixPath(record['object_key']).suffix
        object_path = _inside(runtime, 'raw/' + source + '/objects/' + digest + suffix)
        manifest_path = _inside(runtime, 'raw/' + source + '/manifests/shared_' + PurePosixPath(key).stem + '.json')
        local = {'schema_version': 'snapshot-v1', 'source': source, 'source_url': record['source_url'],
                 'fetched_at': record['fetched_at'], 'sha256': digest, 'size_bytes': record['size_bytes'],
                 'payload_path': str(object_path), 'manifest_path': str(manifest_path),
                 'metadata': record['metadata'],
                 'source_snapshot_manifest_sha256': record['source_manifest_sha256'],
                 'portable_manifest_sha256': PurePosixPath(key).stem}
        if object_path not in restored_objects:
            _immutable(object_path, _read(_inside(bundle, record['object_key']), limit=MAX_OBJECT_BYTES))
            restored_objects.add(object_path)
        _immutable(manifest_path, _json_bytes(local))
        restored.append(str(manifest_path))
        if latest_by_source[source] == key:
            latest_paths.append(str(manifest_path))
    receipt = {'schema_version': 'snapshot-transfer-v1', 'catalog_sha256': pointer['catalog_sha256'],
               'git_revision': revision, 'consumer_received_at': received,
               'source_times_preserved': True, 'manifest_count': len(restored)}
    receipt_key = 'sharing/transfers/' + _digest(_json_bytes(receipt)) + '.json'
    _immutable(_inside(runtime, receipt_key), _json_bytes(receipt))
    _replace(_inside(runtime, 'latest_collection.json'), _json_bytes({
        'status': 'partial' if catalog['status'] == 'partial' else 'collected',
        'manifests': sorted(latest_paths), 'failures': catalog['collection']['failures'],
        'shared_catalog_sha256': pointer['catalog_sha256'], 'transport_receipt': receipt_key}))
    return {'status': 'imported', 'catalog_status': catalog['status'], 'catalog_sha256': pointer['catalog_sha256'],
            'source_count': len(catalog['sources']), 'manifest_count': len(restored),
            'transport_receipt': str(runtime / receipt_key), 'git_revision': revision}


def import_shared_feature_exports(bundle_root, runtime_root, *, revision=None):
    """Restore only fixed, hash-verified research exports alongside imported raw.

    A blocked/missing export records that outcome separately. Raw snapshots stay
    usable and no model approval or historical-availability certification occurs.
    """
    from finpred.data.shared_features import OUTPUTS, validate_shared_feature_exports

    bundle = _safe_root(bundle_root)
    runtime = _safe_root(runtime_root, private=True)
    if revision is not None and not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise SharingError('feature transport revision must be a resolved Git commit SHA')
    pointer, _ = _load_catalog(bundle)
    catalog_id = pointer['catalog_sha256'] if pointer else None
    receipt = {'schema_version': 'shared-research-feature-transfer-v1',
               'git_revision': revision, 'raw_catalog_sha256': catalog_id,
               'readiness': 'research_assumption', 'production_eligible': False}
    try:
        if pointer is None:
            raise SharingError('shared features need a versioned raw catalog')
        lineage = validate_shared_feature_exports(bundle)
        if (set(lineage['files']) != set(OUTPUTS)
                or lineage.get('production_eligible') is not False
                or lineage.get('readiness') != 'research_assumption'):
            raise SharingError('feature exports need the full fixed research contract')
        planned = {}
        for name in (*OUTPUTS, 'features/lineage.json', 'features/build_status.json'):
            payload = _read(_inside(bundle, name), limit=MAX_OBJECT_BYTES)
            if name in lineage['files']:
                expected = lineage['files'][name]
                if (_digest(payload) != expected['sha256']
                        or len(payload) != expected['size_bytes']):
                    raise SharingError('feature output changed during transfer')
            planned[name] = payload
        copied_lineage = json.loads(planned['features/lineage.json'])
        copied_status = json.loads(planned['features/build_status.json'])
        if (copied_lineage != lineage
                or copied_status.get('lineage_sha256') != _digest(planned['features/lineage.json'])
                or copied_status.get('raw_catalog_sha256') != catalog_id
                or copied_status.get('status') != 'exported'):
            raise SharingError('feature metadata changed during transfer')
        destinations = {name: _inside(runtime, 'shared-data/' + name) for name in planned}
        # Verify all source bytes before replacing any local research output.
        for name, payload in planned.items():
            _replace(destinations[name], payload, limit=MAX_OBJECT_BYTES)
        receipt.update(status='imported', files=sorted(planned),
                       lineage_sha256=_digest(planned['features/lineage.json']))
    except (OSError, ValueError, TypeError, KeyError):
        receipt.update(status='blocked', files=[],
                       reason='shared_feature_exports_missing_failed_stale_or_corrupt')
    _replace(_inside(runtime, 'shared-data/transfer.json'), _json_bytes(receipt))
    return {**receipt, 'output_root': str(runtime / 'shared-data')}
