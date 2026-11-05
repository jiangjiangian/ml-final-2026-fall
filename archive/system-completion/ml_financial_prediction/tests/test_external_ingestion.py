"""Public adapters use synthetic payloads; no network or credentials in tests."""

import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests

from finpred.ingestion.external import (
    MAX_PAYLOAD_BYTES,
    ExternalDataError,
    download_external,
    download_fred_ipv4,
    parse_external_payload,
    summarize_external,
)

VIX = b"DATE,OPEN,HIGH,LOW,CLOSE\n01/02/2026,15,17,14,16\n01/05/2026,16,19,15,18\n"
FRED = b"observation_date,DGS10\n2026-01-01,.\n2026-01-02,4.00\n2026-01-05,4.10\n"
TWSE = json.dumps([
    {"Date": "1150102", "OpeningIndex": "20,000", "HighestIndex": "20,500",
     "LowestIndex": "19,900", "ClosingIndex": "20,300.5"},
    {"Date": "1150105", "OpeningIndex": "20,400", "HighestIndex": "20,600",
     "LowestIndex": "20,100", "ClosingIndex": "20,500.5"},
]).encode()


class Response:
    def __init__(self, payload=VIX, status=200, content_type="text/csv"):
        self.payload = payload
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.closed = False

    def iter_content(self, chunk_size):
        for start in range(0, len(self.payload), chunk_size):
            yield self.payload[start:start + chunk_size]

    def close(self):
        self.closed = True


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class ParseTests(unittest.TestCase):
    def test_verified_curl_ipv4_uses_official_url_and_same_parser(self):
        calls = []

        def run(arguments, **kwargs):
            calls.append((arguments, kwargs))
            Path(arguments[arguments.index('--output') + 1]).write_bytes(FRED)
            return SimpleNamespace(returncode=0, stdout='200 0', stderr='omitted')

        with tempfile.TemporaryDirectory() as directory:
            with patch('shutil.which', return_value='/usr/bin/curl'), patch('subprocess.run', side_effect=run):
                manifest = download_fred_ipv4('fred_us10y', directory)
            self.assertEqual(manifest['metadata']['audit']['row_count'], 3)
            self.assertTrue(manifest['metadata']['tls_verification'])
            self.assertFalse(manifest['metadata']['audit']['historical_features_ready'])
            self.assertEqual(manifest['metadata']['transport'], 'curl_ipv4_verified_tls')
        args, kwargs = calls[0]
        self.assertIn('--ipv4', args)
        self.assertNotIn('--insecure', args)
        self.assertNotIn('-k', args)
        self.assertTrue(args[-1].startswith('https://fred.stlouisfed.org/'))
        self.assertEqual(kwargs['timeout'], 50)

    def test_curl_ipv4_rejects_redirect_bad_tls_html_and_other_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            for status in ('301 0', '200 60', '000 0'):
                with patch('shutil.which', return_value='/usr/bin/curl'), patch('subprocess.run',
                     return_value=SimpleNamespace(returncode=0, stdout=status, stderr='secret')):
                    with self.assertRaises(ExternalDataError) as error:
                        download_fred_ipv4('fred_us10y', directory)
                    self.assertNotIn('secret', str(error.exception))

            def html(arguments, **kwargs):
                Path(arguments[arguments.index('--output') + 1]).write_bytes(b'<html>error</html>')
                return SimpleNamespace(returncode=0, stdout='200 0', stderr='')

            with patch('shutil.which', return_value='/usr/bin/curl'), patch('subprocess.run', side_effect=html):
                with self.assertRaises(ExternalDataError):
                    download_fred_ipv4('fred_us10y', directory)
            with self.assertRaises(ExternalDataError):
                download_fred_ipv4('cboe_vix', directory)

    def test_vix_keeps_provider_dates_and_points(self):
        rows = parse_external_payload("cboe_vix", VIX)
        self.assertEqual(rows[1]["provider_observation_date"], "2026-01-05")
        self.assertEqual(rows[1]["value"], 18)
        self.assertEqual(rows[1]["unit"], "index_point")
        self.assertNotIn("available_at", rows[1])

    def test_twse_roc_year_and_thousand_separator(self):
        rows = parse_external_payload("twse_twii", TWSE)
        self.assertEqual(rows[0]["provider_observation_date"], "2026-01-02")
        self.assertEqual(rows[0]["value"], 20300.5)

    def test_fred_missing_observation_is_preserved(self):
        rows = parse_external_payload("fred_us10y", FRED)
        self.assertIsNone(rows[0]["value"])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]["unit"], "percent_per_annum")
        summary = summarize_external("fred_us10y", rows)
        self.assertEqual(summary["missing_values"], 1)
        self.assertFalse(summary["historical_features_ready"])
        self.assertIsNone(summary["published_at"])
        self.assertFalse(summary["complete_native_calendar_verified"])

    def test_fred_legacy_date_header_and_quote_direction(self):
        rows = parse_external_payload("fred_usd_twd", b"DATE,DEXTAUS\n2026-01-02,32.54\n")
        self.assertEqual(rows[0]["unit"], "TWD_per_USD")
        self.assertEqual(rows[0]["value"], 32.54)

    def test_duplicates_unsorted_nonfinite_and_missing_fields_rejected(self):
        payloads = [
            VIX + b"01/05/2026,16,19,15,18\n",
            VIX.replace(b"01/02/2026", b"01/06/2026"),
            VIX.replace(b",18\n", b",NaN\n"),
            VIX.replace(b",18\n", b"\n"),
            VIX.replace(b",18\n", b",0\n"),
        ]
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(ExternalDataError):
                parse_external_payload("cboe_vix", payload)

    def test_fred_missing_is_not_global_negative_one_rule(self):
        rows = parse_external_payload("fred_us10y", b"observation_date,DGS10\n2026-01-02,-1\n")
        self.assertEqual(rows[0]["value"], -1)
        with self.assertRaises(ExternalDataError):
            parse_external_payload("fred_usd_twd", b"observation_date,DEXTAUS\n2026-01-02,-1\n")

    def test_twse_duplicate_keys_invalid_date_and_wrong_shape_rejected(self):
        for payload in [b'{"Date":"1150102"}', b'[{"Date":"1150102","Date":"1150103"}]',
                        TWSE.replace(b"1150102", b"1150230"), b"[]"]:
            with self.subTest(payload=payload), self.assertRaises(ExternalDataError):
                parse_external_payload("twse_twii", payload)

    def test_html_unknown_source_and_bad_header_rejected(self):
        for source, payload in [("cboe_vix", b"<html>login</html>"), ("invalid", VIX),
                                ("fred_us10y", b"date,other\n2026-01-02,1\n")]:
            with self.subTest(source=source), self.assertRaises(ExternalDataError):
                parse_external_payload(source, payload)


class DownloadTests(unittest.TestCase):
    def test_verified_request_and_immutable_reruns(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Session(Response())
            first = download_external("cboe_vix", tmp, session=session)
            second = download_external("cboe_vix", tmp, session=Session(Response()))
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(first["payload_path"], second["payload_path"])
            self.assertNotEqual(first["manifest_path"], second["manifest_path"])
            self.assertEqual(Path(first["payload_path"]).read_bytes(), VIX)
            self.assertTrue(Path(first["manifest_path"]).is_file())
            _, kwargs = session.calls[0]
            self.assertTrue(kwargs["verify"])
            self.assertFalse(kwargs["allow_redirects"])
            self.assertEqual(kwargs["timeout"], (10, 40))
            self.assertTrue(session.response.closed)

    def test_http_html_malformed_and_oversized_never_saved(self):
        cases = [Response(status=302), Response(status=503),
                 Response(content_type="text/html"), Response(payload=b"not CSV"),
                 Response(payload=b"x" * (MAX_PAYLOAD_BYTES + 1))]
        for response in cases:
            with self.subTest(status=response.status_code), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ExternalDataError):
                    download_external("cboe_vix", tmp, session=Session(response))
                self.assertEqual(list(Path(tmp).iterdir()), [])
                self.assertTrue(response.closed)

    def test_network_error_does_not_expose_raw_exception(self):
        session = Session(requests.ConnectionError("fixture-secret-must-not-leak"))
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ExternalDataError) as result:
            download_external("cboe_vix", tmp, session=session)
        self.assertNotIn("fixture-secret", str(result.exception))
        self.assertEqual(result.exception.network_category, 'connection_failure')

    def test_precise_network_categories_do_not_include_exception_messages(self):
        cases = [
            (requests.exceptions.SSLError('fixture-secret'), 'tls_failure'),
            (requests.exceptions.ProxyError('fixture-secret'), 'proxy_failure'),
            (requests.exceptions.ConnectTimeout('fixture-secret'), 'connect_timeout'),
            (requests.exceptions.ReadTimeout('fixture-secret'), 'read_timeout'),
            (requests.exceptions.Timeout('fixture-secret'), 'request_timeout'),
        ]
        for error, category in cases:
            with self.subTest(category=category), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ExternalDataError) as result:
                    download_external('fred_us10y', tmp, session=Session(error))
                self.assertEqual(category, result.exception.network_category)
                self.assertNotIn('fixture-secret', str(result.exception))
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_retry_wrapped_read_timeout_keeps_safe_underlying_category(self):
        from urllib3.exceptions import ReadTimeoutError

        underlying = ReadTimeoutError(None, '/fixture-secret', 'fixture-secret')
        wrapped = requests.ConnectionError(underlying)
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ExternalDataError) as result:
            download_external('fred_usd_twd', tmp, session=Session(wrapped))
        self.assertEqual('read_timeout', result.exception.network_category)
        self.assertNotIn('fixture-secret', str(result.exception))


if __name__ == "__main__":
    unittest.main()
