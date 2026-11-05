"""Content-addressed state with fast-forward Git publication before POST.

The runtime uses a fixed absolute path across hosted runners. This intentionally
does not rewrite timestamps, snapshot evidence, model manifests or pickle bytes.
"""

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

ALLOWED_ROOTS = {'approved.json', 'candidates', 'predictions', 'submission', 'verified', 'runs', 'tables', 'shadow'}
MAX_OBJECT_BYTES = 90 * 1024 * 1024
MAX_STATE_BYTES = 512 * 1024 * 1024
MAX_INDEX_BYTES = 8 * 1024 * 1024
LARGE_TABLE_BYTES = 1024 * 1024
TABLE_SCHEMAS = {'training-table-v1', 'sequence-feature-table-v1', 'prediction-table-v1'}
PRIVATE_NAMES = {'environment', '.env', 'cookies', 'cookies.json', 'cookie.jar',
                 'credentials', 'credentials.json', 'kaggle.json', 'runtime.env'}


class HostedBlocked(ValueError):
    """An actionable explanation that does not expose command output or secrets."""


def write_private(path, payload):
    path = Path(path)
    no_symlink(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.hosted-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(path, value):
    write_private(path, (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode())


def safe_relative(value):
    if not isinstance(value, str) or '\\' in value:
        raise HostedBlocked('portable state requires safe POSIX relative paths')
    parts = PurePosixPath(value)
    if parts.is_absolute() or not parts.parts or any(p in {'', '.', '..'} for p in value.split('/')):
        raise HostedBlocked('unsafe runtime state member')
    return Path(*parts.parts)


def no_symlink(path):
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise HostedBlocked('runtime state must not contain symlinks')


def bounded_bytes(path, limit):
    """Never block on a device/FIFO or read a huge attacker-controlled object."""
    path = Path(path)
    no_symlink(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        details = os.fstat(stream.fileno())
        if not stat.S_ISREG(details.st_mode) or details.st_size > limit:
            raise HostedBlocked('runtime state needs bounded regular files')
        return stream.read(limit + 1)


def allowed_member(relative):
    return (relative.parts[0] in ALLOWED_ROOTS
            and not relative.name.endswith('.lock')
            and not any(part.lower() in PRIVATE_NAMES for part in relative.parts))


def credential_values():
    return {v.encode() for k, v in os.environ.items() if len(v) >= 8
            and any(t in k.upper() for t in ('PASSWORD', 'TOKEN', 'SECRET', 'COOKIE', 'COURSE_EMAIL'))}


def reject_json_credentials(payload):
    """Reject credential-bearing keys independently of currently loaded secrets."""
    try:
        value = json.loads(payload)
        stack = [value]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                for key, child in item.items():
                    normalized = re.sub(r'[^a-z0-9]', '', str(key).lower())
                    if any(word in normalized for word in
                           ('password', 'cookie', 'authorization', 'credential', 'secret',
                            'apikey', 'privatekey', 'accesstoken', 'refreshtoken', 'courseemail')):
                        raise HostedBlocked('runtime JSON contains a credential-bearing key')
                    stack.append(child)
            elif isinstance(item, list):
                stack.extend(item)
        return value
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise HostedBlocked('runtime JSON must parse safely before publication') from None


def github_origin_identity(value):
    """Strip authentication locally; never print an origin that may contain it."""
    if value.startswith('git@github.com:'):
        path = value.partition(':')[2]
    else:
        parsed = urlsplit(value)
        if parsed.scheme not in {'https', 'ssh'} or parsed.hostname != 'github.com':
            raise HostedBlocked('data origin must identify the same GitHub repository')
        path = parsed.path.lstrip('/')
    path = path.removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', path):
        raise HostedBlocked('data origin must identify the same GitHub repository')
    return path.lower()


def _published_state(data_root, runtime_root):
    """Only a known remote commit can authorize removing a local table.

    A preceding call to pack_runtime may have written an index without pushing
    it. Reading that working-tree index would incorrectly treat new data as
    archived. The remote-tracking ref is the last fetched/pushed durable version;
    the caller's Git lease/CAS remains responsible for publication serialization.
    """
    reference = 'refs/remotes/origin/live-data'
    try:
        result = subprocess.run(['git', 'show', reference + ':runtime/state.json'],
                                cwd=data_root, capture_output=True, timeout=10, check=False)
        if result.returncode:
            return {}, set(), None
        if len(result.stdout) > MAX_INDEX_BYTES:
            raise HostedBlocked('published runtime index exceeds its bounded size')
        previous = json.loads(result.stdout)
        if (not isinstance(previous, dict) or previous.get('schema_version') != 'hosted-runtime-v1'
                or previous.get('runtime_root') != str(runtime_root)):
            raise HostedBlocked('published runtime index does not identify this runtime')
        if not isinstance(previous.get('files'), list):
            raise HostedBlocked('published runtime index requires its explicit file list')
        entries = {}
        for entry in previous['files']:
            relative = safe_relative(entry.get('path'))
            digest = entry.get('sha256', '')
            key = 'runtime/objects/' + digest + '.bin'
            if (not allowed_member(relative) or relative.as_posix() in entries
                    or not re.fullmatch('[a-f0-9]{64}', digest) or entry.get('object_key') != key):
                raise HostedBlocked('published runtime index has invalid or duplicate members')
            entries[relative.as_posix()] = entry
        tracked = subprocess.run(['git', 'ls-tree', '--name-only', reference + ':runtime/objects'],
                                 cwd=data_root, capture_output=True, text=True, timeout=10, check=False)
        revision = subprocess.run(['git', 'rev-parse', reference], cwd=data_root,
                                  capture_output=True, text=True, timeout=10, check=False)
        if tracked.returncode or revision.returncode:
            return {}, set(), None
        names = {name for name in tracked.stdout.splitlines() if re.fullmatch('[a-f0-9]{64}\\.bin', name)}
        commit = revision.stdout.strip()
        if not re.fullmatch('[a-f0-9]{40}', commit):
            raise HostedBlocked('published runtime revision is not a commit identity')
        return entries, names, commit
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # Without an established published archive nothing is eligible to prune.
        return {}, set(), None
    except (KeyError, TypeError, json.JSONDecodeError):
        raise HostedBlocked('published runtime index is malformed') from None


def _active_evidence(files, documents, runtime_root):
    """Follow active pointers, not every historical registration left on disk."""
    roots, newest, pending_hashes = set(), {}, set()
    for name, document in documents.items():
        parts = Path(name).parts
        if (name == 'approved.json' or name == 'shadow/model-latest.json'
                or (parts[0] == 'candidates' and parts[-1] == 'approved.json')):
            roots.add(name)
        if parts[0] == 'submission' and isinstance(document, dict):
            if document.get('status') in {'post_in_flight', 'unverified'}:
                roots.add(name)
                digest = document.get('csv_sha256')
                if isinstance(digest, str) and re.fullmatch('[a-f0-9]{64}', digest):
                    pending_hashes.add(digest)
        if parts[0] == 'predictions' and parts[-1] == 'latest.json':
            date_index = next((i for i, part in enumerate(parts)
                               if re.fullmatch(r'\d{4}-\d{2}-\d{2}', part)), None)
            if date_index is not None:
                group, day = parts[:date_index], parts[date_index]
                if group not in newest or day > newest[group][0]:
                    newest[group] = (day, name)
    roots.update(name for _, name in newest.values())
    if pending_hashes:
        roots.update(name for name, document in documents.items()
                     if isinstance(document, dict) and document.get('csv_sha256') in pending_hashes)
    hashes, protected, processed, queue = set(), set(), set(), list(roots)
    by_hash = {}
    for entry in files:
        by_hash.setdefault(entry['sha256'], []).append(entry['path'])
        if entry.get('document_sha256'):
            by_hash.setdefault(entry['document_sha256'], []).append(entry['path'])
    while queue:
        name = queue.pop()
        if name in processed:
            continue
        processed.add(name)
        protected.add(name)
        document = documents.get(name)
        stack = [document] if document is not None else []
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
            elif isinstance(value, str):
                if re.fullmatch('[a-f0-9]{64}', value):
                    hashes.add(value)
                    queue.extend(by_hash.get(value, ()))
                candidate = Path(value)
                if (candidate.is_absolute() and '..' not in candidate.parts
                        and candidate.is_relative_to(runtime_root)):
                    relative = candidate.relative_to(runtime_root).as_posix()
                    if relative in documents:
                        queue.append(relative)
                    # A model directory links its own manifests and the run's
                    # sibling registration/report; older run registrations do
                    # not become roots merely because we retain those reports.
                    prefix = relative.rstrip('/') + '/'
                    queue.extend(item for item in documents if item.startswith(prefix))
                    if candidate.is_dir() and candidate != runtime_root:
                        for sibling in ('registration.json', 'candidate_report.json'):
                            sibling_name = (candidate.parent / sibling).relative_to(runtime_root).as_posix()
                            if sibling_name in documents:
                                queue.append(sibling_name)
                    protected.add(relative)
    return protected, hashes


def pack_runtime(runtime_root, data_root):
    runtime_root, data_root = Path(runtime_root).absolute(), Path(data_root).absolute()
    no_symlink(runtime_root)
    no_symlink(data_root)
    files, documents, total = [], {}, 0
    for prefix in sorted(ALLOWED_ROOTS):
        start = runtime_root / prefix
        candidates = sorted(start.rglob('*')) if start.is_dir() else [start]
        for source in candidates:
            no_symlink(source)
            if not source.exists() or source.is_dir() or source.name.endswith('.lock'):
                continue
            relative = source.relative_to(runtime_root)
            if not allowed_member(relative):
                raise HostedBlocked('credential/session filenames are not runtime state')
            payload = bounded_bytes(source, MAX_OBJECT_BYTES)
            if any(value in payload for value in credential_values()):
                raise HostedBlocked('runtime state contains an active credential literal')
            document = reject_json_credentials(payload) if source.suffix.lower() == '.json' else None
            total += len(payload)
            digest = hashlib.sha256(payload).hexdigest()
            object_key = 'runtime/objects/' + digest + '.bin'
            item = {'path': relative.as_posix(), 'object_key': object_key,
                    'sha256': digest, 'size_bytes': len(payload)}
            if source.suffix.lower() == '.json' and len(payload) <= LARGE_TABLE_BYTES:
                documents[relative.as_posix()] = document
            if (len(payload) > LARGE_TABLE_BYTES and isinstance(document, dict)
                    and document.get('schema_version') in TABLE_SCHEMAS):
                item['large_table'] = True
                item['document_sha256'] = hashlib.sha256(json.dumps(
                    document, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
            files.append(item)
    previous, tracked_objects, archived_commit = _published_state(data_root, runtime_root)
    protected, protected_hashes = _active_evidence(files, documents, runtime_root)
    removed = []
    target = MAX_STATE_BYTES // 2
    for entry in sorted(files, key=lambda item: item['path']):
        if total <= target:
            break
        name, digest = entry['path'], entry['sha256']
        old = previous.get(name, {})
        archived = data_root / entry['object_key']
        if (not entry.get('large_table') or name in protected or digest in protected_hashes
                or entry.get('document_sha256') in protected_hashes
                or old.get('sha256') != digest or old.get('size_bytes') != entry['size_bytes']
                or archived.name not in tracked_objects or not archived.is_file()):
            continue
        if hashlib.sha256(bounded_bytes(archived, MAX_OBJECT_BYTES)).hexdigest() != digest:
            raise HostedBlocked('archived table checksum changed; retention is blocked')
        removed.append(entry)
        total -= entry['size_bytes']
    if total > MAX_STATE_BYTES:
        raise HostedBlocked('private runtime exceeded capacity; active or unpublished evidence cannot be pruned')
    removed_names = {entry['path'] for entry in removed}
    files = [entry for entry in files if entry['path'] not in removed_names]
    for entry in files:
        source = runtime_root / entry['path']
        payload = bounded_bytes(source, MAX_OBJECT_BYTES)
        digest, object_key = entry['sha256'], entry['object_key']
        if hashlib.sha256(payload).hexdigest() != digest:
            raise HostedBlocked('runtime file changed during checkpoint preparation')
        object_path = data_root / object_key
        if object_path.exists():
            no_symlink(object_path)
            if hashlib.sha256(bounded_bytes(object_path, MAX_OBJECT_BYTES)).hexdigest() != digest:
                raise HostedBlocked('existing runtime object checksum mismatch')
        else:
            write_private(object_path, payload)
        entry.pop('large_table', None)
        entry.pop('document_sha256', None)
    record = {'schema_version': 'hosted-runtime-v1', 'runtime_root': str(runtime_root), 'files': files,
              'total_bytes': total, 'created_at': datetime.now(timezone.utc).isoformat(),
              'trust_scope': 'internally_created_finpred_state_in_verified_repository',
              'excluded': ['raw', 'market-history', 'environment', 'HTTP sessions', 'credentials', 'lock files'],
              'retention': {'policy': 'published_unreferenced_large_tables_only-v1',
                            'archived_commit': archived_commit,
                            'pruned_paths': sorted(removed_names)}}
    write_json(data_root / 'runtime/state.json', record)
    for entry in removed:
        source = runtime_root / entry['path']
        if hashlib.sha256(bounded_bytes(source, MAX_OBJECT_BYTES)).hexdigest() == entry['sha256']:
            source.unlink()
    referenced_objects = {Path(entry['object_key']).name for entry in files}
    for name in tracked_objects - referenced_objects:
        path = data_root / 'runtime/objects' / name
        if path.is_file() and hashlib.sha256(bounded_bytes(path, MAX_OBJECT_BYTES)).hexdigest() == name[:-4]:
            path.unlink()
    return record


def restore_runtime(data_root, runtime_root):
    data_root, runtime_root = Path(data_root).absolute(), Path(runtime_root).absolute()
    no_symlink(data_root)
    no_symlink(runtime_root)
    index = data_root / 'runtime/state.json'
    if not index.exists():
        return {'status': 'no_prior_runtime_state', 'files': 0}
    no_symlink(index)
    record = json.loads(bounded_bytes(index, MAX_INDEX_BYTES))
    if record.get('schema_version') != 'hosted-runtime-v1' or record.get('runtime_root') != str(runtime_root):
        raise HostedBlocked('state must restore to the recorded fixed runtime root; no silent path rebasing')
    entries, planned, seen, total = record.get('files'), [], set(), 0
    if not isinstance(entries, list):
        raise HostedBlocked('runtime archive needs an explicit file list')
    for entry in entries:
        relative = safe_relative(entry.get('path'))
        if not allowed_member(relative) or relative.as_posix() in seen:
            raise HostedBlocked('runtime archive member not allowed or duplicated')
        seen.add(relative.as_posix())
        digest = entry.get('sha256', '')
        if not re.fullmatch('[a-f0-9]{64}', digest):
            raise HostedBlocked('runtime object SHA256 missing')
        key = 'runtime/objects/' + digest + '.bin'
        if entry.get('object_key') != key:
            raise HostedBlocked('runtime content object path is not canonical')
        source, target = data_root / key, runtime_root / relative
        no_symlink(source)
        no_symlink(target)
        payload = bounded_bytes(source, MAX_OBJECT_BYTES)
        total += len(payload)
        if (len(payload) != entry.get('size_bytes') or len(payload) > MAX_OBJECT_BYTES
                or total > MAX_STATE_BYTES or hashlib.sha256(payload).hexdigest() != digest):
            raise HostedBlocked('runtime state checksum/size verification failed')
        if target.exists() and bounded_bytes(target, MAX_OBJECT_BYTES) != payload:
            raise HostedBlocked('refusing to overwrite locally newer or unresolved runtime state')
        planned.append((target, source, digest))
    if total != record.get('total_bytes'):
        raise HostedBlocked('runtime archive byte total mismatch')
    # Validate every member before extracting even the first file.
    for target, source, digest in planned:
        payload = bounded_bytes(source, MAX_OBJECT_BYTES)
        if hashlib.sha256(payload).hexdigest() != digest:
            raise HostedBlocked('runtime object changed during restore')
        write_private(target, payload)
    return {'status': 'restored', 'files': len(planned), 'total_bytes': total}


class PrivateGitStore:
    """A fixed live-data branch, shared lease and parent-SHA guarded writes."""

    def __init__(self, data_root, repository, *, privacy_check=None, origin_check=None, clock=None, owner=None,
                 allow_public_data=False):
        no_symlink(Path(data_root).absolute())
        self.root = Path(data_root).resolve()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.owner = owner or uuid.uuid4().hex
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise HostedBlocked('repository must be an owner/name identifier')
        if privacy_check is None:
            def privacy_check():
                value = self.command(['gh', 'api', 'repos/' + repository, '--jq', '.private'])
                if value not in {'true', 'false'}:
                    raise HostedBlocked('repository visibility is unknown; publication is blocked')
                return value == 'true'
        visibility = privacy_check()
        if not isinstance(visibility, bool):
            raise HostedBlocked('repository visibility is unknown; publication is blocked')
        if not visibility and allow_public_data is not True:
            raise HostedBlocked('live data and runtime publishing require the same private repository')
        if origin_check is None:
            def origin_check():
                return github_origin_identity(self.git('remote', 'get-url', 'origin')) == repository.lower()
        if not origin_check():
            raise HostedBlocked('data Git origin differs from the verified private repository')
        if self.git('symbolic-ref', '--quiet', '--short', 'HEAD') != 'live-data':
            raise HostedBlocked('only a checked-out live-data branch may receive state')
        if self.git('status', '--porcelain'):
            raise HostedBlocked('live-data checkout must start clean')
        self.parent = self.git('rev-parse', 'HEAD')
        self.assert_parent()

    def command(self, arguments, *, allow_no_change=False):
        try:
            result = subprocess.run(arguments, cwd=self.root, capture_output=True, text=True,
                                    check=False, timeout=120)
        except subprocess.TimeoutExpired:
            raise HostedBlocked('private Git operation timed out; no POST retry is permitted') from None
        if result.returncode and not (allow_no_change and result.returncode == 1):
            raise HostedBlocked('private Git operation failed; output and credentials omitted')
        return result.stdout.strip()

    def git(self, *arguments):
        return self.command(['git', *arguments])

    def assert_parent(self):
        if self.git('rev-parse', 'HEAD') != self.parent:
            raise HostedBlocked('local data parent changed during this job')
        remote = self.git('ls-remote', 'origin', 'refs/heads/live-data').split()
        if not remote or remote[0] != self.parent:
            raise HostedBlocked('remote data changed; abort rather than force-push or retry a POST')

    def acquire(self):
        lease_path = self.root / 'runtime/lease.json'
        now = self.clock()
        if lease_path.exists():
            lease = json.loads(bounded_bytes(lease_path, MAX_INDEX_BYTES))
            if (lease.get('active') and lease.get('owner') != self.owner
                    and datetime.fromisoformat(lease['expires_at']) > now):
                raise HostedBlocked('another private runtime lease is active')
        write_json(lease_path, {'owner': self.owner, 'active': True, 'acquired_at': now.isoformat(),
                                'expires_at': (now + timedelta(minutes=45)).isoformat()})
        return self.publish('Acquire serialized runtime lease')

    def assert_lease(self):
        self.assert_parent()
        lease = json.loads(bounded_bytes(self.root / 'runtime/lease.json', MAX_INDEX_BYTES))
        expires = datetime.fromisoformat(lease['expires_at'])
        if (not lease.get('active') or lease.get('owner') != self.owner
                or expires.utcoffset() is None or self.clock() >= expires):
            raise HostedBlocked('active owned runtime lease is required before POST')

    def publish(self, reason):
        self.assert_parent()
        lease_path = self.root / 'runtime/lease.json'
        if lease_path.exists():
            lease = json.loads(bounded_bytes(lease_path, MAX_INDEX_BYTES))
            if lease.get('active') and lease.get('owner') != self.owner:
                raise HostedBlocked('state publication requires ownership of the active lease')
        roots = [p for p in ('objects', 'manifests', 'catalog', 'features', 'labels', 'runtime') if (self.root / p).exists()]
        if roots:
            self.git('add', '--', *roots)
        if not self.git('diff', '--cached', '--name-only'):
            return self.parent
        self.git('-c', 'user.name=finpred-automation', '-c', 'user.email=finpred-automation@users.noreply.github.com',
                 'commit', '-m', reason)
        # Fast-forward only. No force option, no changing the expected parent after rejection.
        self.git('push', 'origin', 'HEAD:refs/heads/live-data')
        self.parent = self.git('rev-parse', 'HEAD')
        return self.parent

    def release(self):
        self.assert_parent()
        write_json(self.root / 'runtime/lease.json', {'owner': self.owner, 'active': False,
                                                    'released_at': self.clock().isoformat()})
        return self.publish('Save pipeline state and release runtime lease')
