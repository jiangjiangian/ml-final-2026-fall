import json
from pathlib import Path
import tempfile
import unittest

from finpred.ingestion.market_history import (
    download_market_history, parse_chart_history, parse_twse_sector_snapshot,
)


def payload(symbol="^SOX", prices=None, timestamps=None):
    return json.dumps({"chart": {"error": None, "result": [{
        "meta": {"symbol": symbol, "exchangeTimezoneName": "America/New_York"},
        "timestamp": timestamps or [1577975400, 1578061800],
        "indicators": {"quote": [{"close": [100, None] if prices is None else prices}]}}]}}).encode()


class Response:
    status_code = 200

    def __init__(self, raw):
        self.raw = raw

    def iter_content(self, size):
        yield self.raw

    def close(self):
        pass


class Session:
    def __init__(self, raw):
        self.raw, self.kwargs = raw, None

    def get(self, url, **kwargs):
        self.kwargs = kwargs
        return Response(self.raw)


class MarketHistoryTests(unittest.TestCase):
    def test_official_sector_snapshot_has_exact_three_named_series(self):
        raw = [{"日期": "1151029", "指數": name, "收盤指數": "1,234.56"}
               for name in ["電子工業類指數", "半導體類指數", "金融保險類指數"]]
        rows = parse_twse_sector_snapshot(json.dumps(raw).encode())
        self.assertEqual({r["series_id"] for r in rows}, {"tw_electronics", "tw_semiconductor", "tw_financials"})
        self.assertTrue(all(r["provider_observation_date"] == "2026-10-29" for r in rows))
        with self.assertRaises(ValueError):
            parse_twse_sector_snapshot(json.dumps(raw[:-1]).encode())
        with self.assertRaises(ValueError):
            parse_twse_sector_snapshot(json.dumps(raw + raw[:1]).encode())

    def test_provider_local_date_and_missing_closes_retained(self):
        rows = parse_chart_history(payload(), "sox")
        self.assertEqual([r["provider_observation_date"] for r in rows], ["2020-01-02", "2020-01-03"])
        self.assertIsNone(rows[1]["value"])
        self.assertNotIn("available_at", rows[0])

    def test_wrong_symbol_nonfinite_duplicate_date_and_html_rejected(self):
        for raw in [payload(symbol="^GSPC"), payload(prices=[100, float("nan")]),
                    payload(timestamps=[1577975400, 1577975401]), b"<html>login</html>"]:
            with self.subTest(raw=raw[:20]):
                with self.assertRaises(ValueError):
                    parse_chart_history(raw, "sox")

    def test_tls_and_private_immutable_snapshot_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            client = Session(payload())
            result = download_market_history("sox", "2020-01-01", "2020-01-10", root, session=client)
            self.assertTrue(client.kwargs["verify"])
            self.assertFalse(client.kwargs["allow_redirects"])
            self.assertTrue(Path(result["payload_path"]).is_file())
            self.assertEqual(result["metadata"]["readiness"], "raw_research_only")
            self.assertFalse(result["metadata"]["historical_vintage_verified"])


if __name__ == "__main__":
    unittest.main()
