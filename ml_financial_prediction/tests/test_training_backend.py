"""Readiness diagnostics must not expose secrets or invoke account write RPCs."""

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

import requests

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('training_backend_probe', PROJECT / 'scripts/check_training_backend.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

SECRET = 'private-kaggle-token-do-not-print-12345678'
USER = 'private-account-do-not-print'


class Response:
    def __init__(self, status=200, payload=b'{"kernels":[]}'):
        self.status_code, self.payload, self.closed = status, payload, False

    def iter_content(self, chunk_size):
        yield self.payload

    def close(self):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError('secret body ' + SECRET, response=self)


def fake_sdk(*, response=None, url=None, method='POST', repeated=False, failure=None):
    response = response or Response()
    sent, constructed, session_instances, requests_seen = [], [], [], []

    class Session:
        def __init__(self):
            self.headers, self.auth, self.closed = {}, None, False
            session_instances.append(self)

        def send(self, request, **kwargs):
            sent.append((request, kwargs))
            if failure:
                raise failure
            return response

        def close(self):
            self.closed = True

    class Client:
        def __init__(self, **kwargs):
            constructed.append(kwargs)
            self.http = SimpleNamespace(_session=None)
            self.kernels = SimpleNamespace(kernels_api_client=SimpleNamespace(list_kernels=self.list_kernels))

        def http_client(self):
            return self.http

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.http._session.close()

        def list_kernels(self, request):
            requests_seen.append(request)
            request = SimpleNamespace(method=method, url=url or probe.RPC_URL)
            answer = self.http._session.send(request, verify=False, allow_redirects=True)
            if repeated:
                self.http._session.send(request)
            answer.raise_for_status()
            return SimpleNamespace(kernels=[SECRET, USER])

    return (Client, SimpleNamespace, 'profile', 'production', Session), sent, constructed, session_instances, requests_seen


class TrainingBackendTests(unittest.TestCase):
    def test_missing_and_incomplete_credentials_never_invoke_sdk_or_child(self):
        for environment in ({}, {'KAGGLE_USERNAME': USER}, {'KAGGLE_KEY': SECRET},
                            {'KAGGLE_API_TOKEN': '  '}):
            with self.subTest(fields=sorted(environment)):
                runner, loader = Mock(), Mock()
                result = probe.check_backend(environment, runner=runner)
                self.assertEqual(result['status'], 'credentials_missing')
                self.assertFalse(result['credentials_ready'])
                self.assertFalse(result['remote_check_performed'])
                runner.assert_not_called()
                self.assertEqual(probe.probe_rpc(environment, sdk_loader=loader)['status'], 'credentials_missing')
                loader.assert_not_called()

    def test_presence_supports_token_or_legacy_pair_without_account_values(self):
        for environment, expected in (({'KAGGLE_API_TOKEN': SECRET}, 'access_token'),
                                      ({'KAGGLE_USERNAME': USER, 'KAGGLE_KEY': SECRET}, 'legacy_api_key')):
            with self.subTest(method=expected):
                runner = Mock(side_effect=AssertionError('presence must not start a worker'))
                result = probe.check_backend(environment, presence_only=True, runner=runner)
                self.assertEqual(result['credential_method'], expected)
                self.assertTrue(result['credentials_ready'])
                text = json.dumps(result)
                self.assertNotIn(SECRET, text)
                self.assertNotIn(USER, text)

    def test_official_read_only_rpc_is_single_bounded_tls_request(self):
        components, sent, constructors, sessions, read_requests = fake_sdk()
        result = probe.probe_rpc({'KAGGLE_API_TOKEN': SECRET}, sdk_loader=lambda: components)
        self.assertEqual(result, {'status': 'authenticated', 'category': 'none', 'remote_check_performed': True})
        self.assertEqual(len(sent), 1)
        request, options = sent[0]
        self.assertEqual((request.method, request.url), ('POST', probe.RPC_URL))
        self.assertTrue(options['verify'])
        self.assertFalse(options['allow_redirects'])
        self.assertEqual(options['timeout'], (5, 12))
        self.assertTrue(options['stream'])
        self.assertEqual(constructors, [{'env': 'production', 'verbose': False}])
        self.assertEqual((read_requests[0].group, read_requests[0].page, read_requests[0].page_size), ('profile', 1, 1))
        self.assertEqual(sessions[0].headers['Authorization'], 'Bearer ' + SECRET)
        self.assertTrue(sessions[0].closed)
        self.assertNotIn(SECRET, json.dumps(result))

    def test_legacy_pair_uses_explicit_basic_auth_without_token_file_fallback(self):
        components, _, _, sessions, _ = fake_sdk()
        result = probe.probe_rpc({'KAGGLE_USERNAME': USER, 'KAGGLE_KEY': SECRET}, sdk_loader=lambda: components)
        self.assertEqual(result['status'], 'authenticated')
        self.assertEqual(sessions[0].auth, (USER, SECRET))
        self.assertNotIn('Authorization', sessions[0].headers)

    def test_write_rpc_redirect_oversize_and_second_call_are_rejected(self):
        cases = ({'url': 'https://api.kaggle.com/v1/kernels.KernelsApiService/SaveKernel'},
                 {'method': 'GET'}, {'repeated': True}, {'response': Response(302)},
                 {'response': Response(payload=b'x' * (probe.MAX_RESPONSE_BYTES + 1))})
        for case in cases:
            with self.subTest(case=list(case)):
                components, sent, _, _, _ = fake_sdk(**case)
                result = probe.probe_rpc({'KAGGLE_API_TOKEN': SECRET}, sdk_loader=lambda: components)
                self.assertNotEqual(result['status'], 'authenticated')
                self.assertEqual(result['category'], 'guard_violation')
                self.assertLessEqual(len(sent), 1)

    def test_http_auth_tls_timeout_and_import_errors_have_safe_categories(self):
        cases = (({'response': Response(401)}, 'authentication_rejected'),
                 ({'response': Response(403)}, 'authentication_rejected'),
                 ({'failure': requests.exceptions.SSLError(SECRET)}, 'tls_failure'),
                 ({'failure': requests.exceptions.ReadTimeout(SECRET)}, 'request_timeout'))
        for options, expected in cases:
            with self.subTest(category=expected):
                components, _, _, _, _ = fake_sdk(**options)
                result = probe.probe_rpc({'KAGGLE_API_TOKEN': SECRET}, sdk_loader=lambda: components)
                self.assertEqual(result['category'], expected)
                self.assertNotIn(SECRET, json.dumps(result))
        result = probe.probe_rpc({'KAGGLE_API_TOKEN': SECRET}, sdk_loader=Mock(side_effect=ImportError(SECRET)))
        self.assertEqual(result['category'], 'dependency_unavailable')
        self.assertFalse(result['remote_check_performed'])

    def test_parent_discards_unexpected_child_fields_and_all_stderr(self):
        raw = json.dumps({'status': 'authenticated', 'category': 'none', 'remote_check_performed': True,
                          'token': SECRET, 'username': USER})
        runner = Mock(return_value=SimpleNamespace(returncode=0, stdout=raw, stderr=SECRET))
        result = probe.check_backend({'KAGGLE_API_TOKEN': SECRET}, runner=runner)
        self.assertEqual(result['status'], 'authenticated')
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertNotIn(USER, json.dumps(result))
        arguments, options = runner.call_args
        self.assertEqual(arguments[0][-1], '--worker')
        self.assertNotIn(SECRET, ' '.join(arguments[0]))
        self.assertEqual(options['timeout'], 30)
        self.assertTrue(options['capture_output'])

    def test_subprocess_deadline_failure_and_invalid_diagnostics_never_echo_output(self):
        failures = (subprocess.TimeoutExpired(['probe'], 5, output=SECRET, stderr=SECRET),
                    OSError(SECRET),
                    SimpleNamespace(returncode=1, stdout=SECRET, stderr=SECRET),
                    SimpleNamespace(returncode=0, stdout=SECRET, stderr=SECRET),
                    SimpleNamespace(returncode=0, stdout=json.dumps({'status': SECRET}), stderr=SECRET))
        for value in failures:
            with self.subTest(kind=type(value).__name__):
                runner = Mock(side_effect=value) if isinstance(value, Exception) else Mock(return_value=value)
                result = probe.check_backend({'KAGGLE_API_TOKEN': SECRET}, runner=runner)
                self.assertNotEqual(result['status'], 'authenticated')
                self.assertNotIn(SECRET, json.dumps(result))
                self.assertIsNone(result['remote_check_performed'])

    def test_cli_presence_writes_only_boolean_github_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'github-output'
            environment = {**os.environ, 'KAGGLE_API_TOKEN': SECRET, 'GITHUB_OUTPUT': str(output)}
            with patch.object(sys, 'argv', ['probe', '--presence-only']), patch.dict(os.environ, environment, clear=True):
                capture = io.StringIO()
                with redirect_stdout(capture):
                    status = probe.main()
            self.assertEqual(status, 0)
            self.assertNotIn(SECRET, capture.getvalue())
            self.assertEqual(output.read_text(), 'credentials_ready=true\n')


if __name__ == '__main__':
    unittest.main()
