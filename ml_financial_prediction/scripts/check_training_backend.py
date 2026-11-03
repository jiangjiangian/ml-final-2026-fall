"""Inspect configured Kaggle credentials and perform one bounded read-only RPC.

ListKernels is a read operation carried by the official SDK's HTTP POST RPC.
This probe never creates a dataset, kernel, training session or submission.
Only presence booleans and fixed status/category names may reach stdout.
"""

import argparse
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys

FIELDS = ('KAGGLE_API_TOKEN', 'KAGGLE_USERNAME', 'KAGGLE_KEY')
RPC_URL = 'https://api.kaggle.com/v1/kernels.KernelsApiService/ListKernels'
MAX_RESPONSE_BYTES = 256 * 1024
STATUSES = {'authenticated', 'credentials_missing', 'authentication_rejected',
            'network_or_unavailable', 'backend_unavailable'}
CATEGORIES = {'none', 'credentials_missing', 'authentication_rejected', 'tls_failure',
              'request_timeout', 'network_failure', 'api_unavailable', 'response_invalid',
              'dependency_unavailable', 'unsupported_version', 'probe_timeout', 'worker_failed',
              'guard_violation'}


class ProbeGuardError(ValueError):
    """The SDK attempted something outside the single read-only request contract."""


def credential_presence(environment):
    return {name: isinstance(environment.get(name), str) and bool(environment[name].strip()) for name in FIELDS}


def auth_method(presence):
    if presence['KAGGLE_API_TOKEN']:
        return 'access_token'
    if presence['KAGGLE_USERNAME'] and presence['KAGGLE_KEY']:
        return 'legacy_api_key'
    return 'none'


def _sdk_components():
    # Importing `kaggle` itself authenticates automatically. Use its official SDK
    # directly so this script controls every request and avoids OAuth/file fallback.
    from importlib.metadata import version
    if version('kaggle') != '2.2.5':
        raise ProbeGuardError('unsupported SDK wrapper version')
    import requests
    from kagglesdk import KaggleClient, KaggleEnv
    from kagglesdk.kernels.types.kernels_api_service import ApiListKernelsRequest
    from kagglesdk.kernels.types.kernels_enums import KernelsListViewType
    return KaggleClient, ApiListKernelsRequest, KernelsListViewType.PROFILE, KaggleEnv.PROD, requests.Session


def _category(error):
    # Never stringify exceptions: they can contain URLs, response bodies or keys.
    status = getattr(getattr(error, 'response', None), 'status_code', None)
    if status in (401, 403):
        return 'authentication_rejected', 'authentication_rejected'
    names = {kind.__name__ for kind in type(error).__mro__}
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return 'backend_unavailable', 'dependency_unavailable'
    if isinstance(error, ProbeGuardError):
        return 'backend_unavailable', 'guard_violation'
    if 'SSLError' in names:
        return 'network_or_unavailable', 'tls_failure'
    if names & {'Timeout', 'ConnectTimeout', 'ReadTimeout', 'TimeoutError'}:
        return 'network_or_unavailable', 'request_timeout'
    if names & {'ConnectionError', 'ProxyError'}:
        return 'network_or_unavailable', 'network_failure'
    return 'network_or_unavailable', 'api_unavailable'


def probe_rpc(environment, *, sdk_loader=_sdk_components):
    """One official ListKernels PROFILE RPC, no output/list contents returned."""
    presence = credential_presence(environment)
    method = auth_method(presence)
    if method == 'none':
        return {'status': 'credentials_missing', 'category': 'credentials_missing', 'remote_check_performed': False}
    sent = [False]
    try:
        Client, Request, profile, production, Session = sdk_loader()
        client = Client(env=production, verbose=False)
        http = client.http_client()
        # Supply the session/auth explicitly. No local config, token files,
        # environment-selected endpoint or automatic OAuth flow is consulted.
        session = Session()
        http._session = session
        session.headers.update({'User-Agent': 'finpred-kaggle-readiness/1', 'Content-Type': 'application/json'})
        if method == 'access_token':
            session.headers['Authorization'] = 'Bearer ' + environment['KAGGLE_API_TOKEN']
        else:
            session.auth = (environment['KAGGLE_USERNAME'], environment['KAGGLE_KEY'])
        original_send = session.send

        def guarded_send(request, **settings):
            if sent[0] or request.method != 'POST' or request.url != RPC_URL:
                raise ProbeGuardError('only one official ListKernels read RPC is allowed')
            sent[0] = True
            settings.update(verify=True, allow_redirects=False, timeout=(5, 12), stream=True)
            response = original_send(request, **settings)
            try:
                if 300 <= response.status_code < 400:
                    raise ProbeGuardError('redirects are not allowed')
                chunks, total = [], 0
                for chunk in response.iter_content(65536):
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise ProbeGuardError('response exceeded bounded diagnostic size')
                    chunks.append(chunk)
                response._content = b''.join(chunks)
                response._content_consumed = True
            finally:
                response.close()
            return response

        session.send = guarded_send
        try:
            request = Request()
            request.group, request.page, request.page_size = profile, 1, 1
            with client:
                response = client.kernels.kernels_api_client.list_kernels(request)
            if not sent[0] or not hasattr(response, 'kernels'):
                raise ProbeGuardError('expected authenticated profile response')
        finally:
            session.close()
        return {'status': 'authenticated', 'category': 'none', 'remote_check_performed': True}
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, GeneratorExit)):
            raise
        status, category = _category(error)
        return {'status': status, 'category': category, 'remote_check_performed': sent[0]}


def check_backend(environment=None, *, presence_only=False, timeout_seconds=30, runner=subprocess.run):
    environment = dict(os.environ if environment is None else environment)
    presence = credential_presence(environment)
    method = auth_method(presence)
    result = {'backend': 'kaggle', 'credential_backend': 'environment', 'credential_presence': presence,
              'credential_method': method, 'credentials_ready': method != 'none',
              'mcp_available_for_current_session': False,
              'mcp_observation_basis': 'not_exposed_in_parent_Codex_tools; CLI_does_not_enumerate_MCP',
              'read_only_rpc': 'ListKernels',
              'training_started': False, 'data_uploaded': False, 'remote_check_performed': False}
    if method == 'none':
        return {**result, 'status': 'credentials_missing', 'category': 'credentials_missing'}
    if presence_only:
        return {**result, 'status': 'configured_not_verified', 'category': 'none'}
    if isinstance(timeout_seconds, bool) or not 5 <= timeout_seconds <= 45:
        raise ValueError('probe timeout must be between 5 and 45 seconds')
    try:
        process = runner([sys.executable, str(Path(__file__).resolve()), '--worker'],
                         env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                         timeout=timeout_seconds, check=False)
        if process.returncode:
            raise ValueError('worker did not return a valid diagnostic')
        report = json.loads(process.stdout)
        if (not isinstance(report, dict) or report.get('status') not in STATUSES
                or report.get('category') not in CATEGORIES
                or not isinstance(report.get('remote_check_performed'), bool)):
            raise ValueError('worker returned an invalid diagnostic')
        # Ignore every other key, even if a dependency accidentally emitted it.
        return {**result, **{name: report[name] for name in ('status', 'category', 'remote_check_performed')}}
    except subprocess.TimeoutExpired:
        return {**result, 'status': 'network_or_unavailable', 'category': 'probe_timeout',
                'remote_check_performed': None}
    except (OSError, ValueError, TypeError):
        return {**result, 'status': 'backend_unavailable', 'category': 'worker_failed',
                'remote_check_performed': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--presence-only', action='store_true')
    parser.add_argument('--timeout-seconds', type=int, default=30)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        # Third-party logging/help output must never enter public Actions logs.
        with open(os.devnull, 'w') as silent, contextlib.redirect_stdout(silent), contextlib.redirect_stderr(silent):
            result = probe_rpc(dict(os.environ))
        print(json.dumps(result))
        return 0
    result = check_backend(presence_only=args.presence_only, timeout_seconds=args.timeout_seconds)
    print(json.dumps(result))
    if args.presence_only and os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('credentials_ready=' + str(result['credentials_ready']).lower() + '\n')
    return 0 if args.presence_only or result['status'] == 'authenticated' else 1


if __name__ == '__main__':
    raise SystemExit(main())
