import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from finpred.data.snapshots import snapshot_bytes
from finpred.ingestion.course import (
    COURSE_BASE,
    CourseClient,
    CourseDownloadError,
    LiveClient,
    VerifiedSession,
    audit_template,
    download_course_sources,
)


def response(payload=b'ok', status=200, headers=None):
    result = requests.Response()
    result.status_code = status
    result.headers.update(headers or {})
    result.raw = io.BytesIO(payload)
    return result


class CourseIngestionTests(unittest.TestCase):
    def test_tls_timeout_and_redirect_are_explicit(self):
        session = Mock()
        session.request.side_effect = [response(status=303, headers={'Location': '/'}), response()]
        client = VerifiedSession(COURSE_BASE, session)
        self.assertEqual(client.read('POST', '/login', data={'secret': 'fake-test-secret'}), b'ok')
        calls = session.request.call_args_list
        self.assertEqual(calls[1].args[0], 'GET')
        self.assertNotIn('data', calls[1].kwargs)
        for call in calls:
            self.assertTrue(call.kwargs['verify'])
            self.assertFalse(call.kwargs['allow_redirects'])
            self.assertEqual(call.kwargs['timeout'], (10, 90))

    def test_cross_origin_redirect_never_forwards_post_credentials(self):
        session = Mock()
        session.request.return_value = response(status=307, headers={'Location': 'https://elsewhere.invalid/login'})
        client = VerifiedSession(COURSE_BASE, session)
        with self.assertRaisesRegex(CourseDownloadError, 'cross-origin'):
            client.read('POST', '/login', data={'secret': 'fake-test-secret'})
        self.assertEqual(session.request.call_count, 1)

    def test_network_failure_does_not_echo_secret_exception(self):
        session = Mock()
        session.request.side_effect = requests.ConnectionError('fake-test-secret')
        with self.assertRaises(CourseDownloadError) as raised:
            VerifiedSession(COURSE_BASE, session).read('GET', '/')
        self.assertNotIn('fake-test-secret', str(raised.exception))

    def test_size_bound_and_auth_failure(self):
        session = Mock()
        session.request.return_value = response(b'toolong')
        with self.assertRaisesRegex(CourseDownloadError, 'size limit'):
            VerifiedSession(COURSE_BASE, session).read('GET', '/', max_bytes=2)
        session.request.return_value = response(b'fake-test-secret', 401)
        with self.assertRaisesRegex(CourseDownloadError, 'HTTP 401') as raised:
            CourseClient(session).login('fake@example.invalid', 'fake-test-secret')
        self.assertNotIn('fake-test-secret', str(raised.exception))

    def test_live_html_login_page_is_not_download_success(self):
        session = Mock()
        session.request.return_value = response(b'<html><form>login</form></html>')
        with self.assertRaisesRegex(CourseDownloadError, 'verified download link'):
            LiveClient(session).login('fake-test-secret')

    def test_login_and_frontend_public_key_recovery_stay_in_memory(self):
        session = Mock()
        session.request.side_effect = [
            response(b'{"success":true}'),
            response(b'<script src="/assets/app.js"></script>'),
            response(b'const x="https://140.112.31.182:8444/",k="fake-test-key";'),
        ]
        client = CourseClient(session)
        client.login('fake@example.invalid', 'fake-test-password')
        self.assertEqual(client.published_live_key(), 'fake-test-key')

    def test_snapshot_deduplicates_content_but_preserves_each_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            first = snapshot_bytes(b'raw', directory, 'course-live', 'https://example.invalid/a?key=secret', '.zip')
            second = snapshot_bytes(b'raw', directory, 'course-live', 'https://example.invalid/a', '.zip')
            self.assertEqual(first['payload_path'], second['payload_path'])
            self.assertNotEqual(first['manifest_path'], second['manifest_path'])
            self.assertEqual(Path(first['payload_path']).read_bytes(), b'raw')
            self.assertEqual(os.stat(first['payload_path']).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(Path(first['payload_path']).parent).st_mode & 0o777, 0o700)
            self.assertNotIn('secret', Path(first['manifest_path']).read_text())
            Path(first['payload_path']).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'integrity'):
                snapshot_bytes(b'raw', directory, 'course-live', 'https://example.invalid/a', '.zip')

    def test_invalid_payload_preserves_existing_snapshot_and_safe_failure_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = snapshot_bytes(b'prior raw', directory, 'course-live', 'https://example.invalid/a', '.zip')
            with patch('finpred.ingestion.course.CourseClient') as factory, patch('finpred.ingestion.course.LiveClient'):
                factory.return_value.training_zip.return_value = b'<html>fake-test-secret</html>'
                with self.assertRaises(ValueError):
                    download_course_sources(directory, 'training', email='test', password='fake-test-secret')
            self.assertEqual(Path(existing['payload_path']).read_bytes(), b'prior raw')
            failures = list(Path(directory).glob('failure_*.json'))
            self.assertEqual(len(failures), 1)
            self.assertNotIn('fake-test-secret', failures[0].read_text())
            self.assertEqual(json.loads(failures[0].read_text())['status'], 'failed')

    def test_template_requires_exact_ids_and_binary_rectangular_shape(self):
        data = b'\xef\xbb\xbfid,2026-06-01,2026-06-02\n0050,0,1\n2330,1,0\n'
        self.assertEqual(audit_template(data, ['0050', '2330'], expected_target_count=2)['stock_count'], 2)
        for invalid in (data.replace(b'0050,0,1', b'0050,0'), data.replace(b'0050,0,1', b'0050,0,2')):
            with self.assertRaises(CourseDownloadError):
                audit_template(invalid, expected_target_count=2)
        with self.assertRaises(CourseDownloadError):
            audit_template(data, ['2330', '0050'], expected_target_count=2)
        with self.assertRaises(CourseDownloadError):
            audit_template(data, ['0050', '2330'])


if __name__ == '__main__':
    unittest.main()
