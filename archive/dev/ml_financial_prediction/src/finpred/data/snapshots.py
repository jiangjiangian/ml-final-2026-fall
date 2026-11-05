"""Content-addressed raw payloads with a separate manifest for every acquisition."""

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def _private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _exclusive_write(path, data):
    # Link a complete, fsynced temporary file atomically without overwriting an
    # existing path. Readers never observe a partially written content object.
    descriptor, temporary = tempfile.mkstemp(prefix='.snapshot-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def snapshot_bytes(payload, root, source, source_url, suffix, metadata=None):
    """Save bytes unchanged; metadata must contain only non-sensitive provenance.

    Query parameters and fragments are deliberately omitted from persisted URLs.
    The caller chooses a private, untracked root. Identical payloads share an object,
    but every successful acquisition gets its own immutable manifest.
    """
    if not isinstance(payload, bytes) or not payload:
        raise ValueError('snapshot requires nonempty bytes')
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', source):
        raise ValueError('invalid source identifier')
    if not re.fullmatch(r'\.[a-z0-9]{1,8}', suffix):
        raise ValueError('invalid payload suffix')
    parts = urlsplit(source_url)
    if parts.scheme != 'https' or not parts.netloc or parts.username or parts.password:
        raise ValueError('source URL must be HTTPS without embedded credentials')
    public_url = urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
    base = Path(root).resolve() / source
    objects, manifests = base / 'objects', base / 'manifests'
    for path in (Path(root).resolve(), base, objects, manifests):
        _private_dir(path)
    digest = hashlib.sha256(payload).hexdigest()
    object_path = objects / (digest + suffix)
    try:
        _exclusive_write(object_path, payload)
    except FileExistsError:
        if object_path.is_symlink():
            raise ValueError('existing snapshot must not be a symbolic link')
        if hashlib.sha256(object_path.read_bytes()).hexdigest() != digest:
            raise ValueError('existing snapshot failed integrity check') from None
        object_path.chmod(0o600)
    now = datetime.now(timezone.utc)
    manifest_path = manifests / (now.strftime('%Y%m%dT%H%M%S.%fZ_') + uuid.uuid4().hex + '.json')
    result = {
        'schema_version': 'snapshot-v1', 'source': source, 'source_url': public_url,
        'fetched_at': now.isoformat(), 'sha256': digest, 'size_bytes': len(payload),
        'payload_path': str(object_path), 'manifest_path': str(manifest_path),
        'metadata': metadata or {},
    }
    _exclusive_write(manifest_path, (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode())
    return result
