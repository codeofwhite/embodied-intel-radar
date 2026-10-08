import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import market_scan


class MarketScanTests(unittest.TestCase):
    def test_parse_series_uses_latest_two_closes(self):
        payload = {"Time Series (Daily)": {
            "2026-09-12": {"4. close": "12.00"},
            "2026-09-11": {"4. close": "10.00"},
        }}
        quote = market_scan.parse_series(market_scan.WATCHLIST[0], payload, "now")
        self.assertEqual(quote["price"], 12.0)
        self.assertEqual(quote["previousClose"], 10.0)
        self.assertEqual(quote["changePercent"], 20.0)
        self.assertEqual(quote["points"], [10.0, 12.0])
        self.assertEqual(quote["seriesInterval"], "1d")
        self.assertEqual(quote["series"], [
            {"date": "2026-09-11", "close": 10.0},
            {"date": "2026-09-12", "close": 12.0},
        ])

    def test_missing_key_writes_explicit_unconfigured_state(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "quotes.json"
            payload, code = market_scan.collect("", output, delay_seconds=0)
            self.assertEqual(code, 1)
            self.assertEqual(payload["meta"]["status"], "unconfigured")
            self.assertEqual(payload["items"], [])
            self.assertEqual(json.loads(output.read_text())["items"], [])

    def test_watchlist_prioritizes_supported_domestic_symbols(self):
        self.assertEqual(len(market_scan.WATCHLIST), 16)
        self.assertFalse(any(item["providerSymbol"].endswith(".HKG") for item in market_scan.WATCHLIST))
        self.assertIn("688836.SH", {item["symbol"] for item in market_scan.WATCHLIST})

    def test_collect_reuses_same_day_symbol_cache_and_only_fetches_missing(self):
        today = market_scan.dt.datetime.now(market_scan.dt.timezone.utc).date().isoformat()
        watchlist = market_scan.WATCHLIST[:2]
        cached_item = {
            **watchlist[0], "price": 10.0, "previousClose": 9.0,
            "changePercent": 11.1, "marketDate": today, "observedAt": "old",
            "points": [9.0, 10.0], "status": "ok",
            "series": [
                {"date": "2026-09-13", "close": 9.0},
                {"date": today, "close": 10.0},
            ],
        }

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"Time Series (Daily)": {
                    today: {"4. close": "12.0"},
                    "2026-09-13": {"4. close": "11.0"},
                }}

        class Session:
            def __init__(self):
                self.headers = {}
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                return Response()

        session = Session()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "quotes.json"
            output.write_text(json.dumps({
                "meta": {"generatedDate": today, "requestsToday": 3},
                "items": [cached_item], "errors": [],
            }))
            with mock.patch.object(market_scan, "WATCHLIST", watchlist), mock.patch.object(
                market_scan.requests, "Session", return_value=session
            ):
                payload, code = market_scan.collect("key", output, delay_seconds=0, force=True)
        self.assertEqual(code, 0)
        self.assertEqual(session.calls, 1)
        self.assertEqual(payload["meta"]["cachedCount"], 1)
        self.assertEqual(payload["meta"]["apiRequestsThisRun"], 1)
        self.assertEqual(payload["meta"]["requestsToday"], 4)


        self.assertEqual(payload["meta"]["historyReadyCount"], 2)

    def test_same_day_legacy_cache_is_not_treated_as_history_ready(self):
        today = market_scan.dt.datetime.now(market_scan.dt.timezone.utc).date().isoformat()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "quotes.json"
            output.write_text(json.dumps({
                "meta": {"generatedDate": today},
                "items": [{**item, "points": [1.0, 2.0]} for item in market_scan.WATCHLIST],
            }))
            self.assertIsNone(market_scan.cached_today(output, today))

    def test_provider_errors_redact_the_api_key(self):
        message = market_scan.safe_error(ValueError("daily limit for SECRET_KEY"), "SECRET_KEY")
        self.assertEqual(message, "ValueError: daily limit for [REDACTED]")

if __name__ == "__main__":
    unittest.main()
