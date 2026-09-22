import json
import unittest
from urllib.error import URLError
from unittest.mock import patch
from nre.alpaca_probe import collect, main
from nre.core import DataError


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self, size=-1):
        return self._data


class _FakeOpener:
    """Stands in for build_opener(...) so main()'s exception handling is testable
    without a network call. If constructed with an exception instance, .open()
    raises it; otherwise .open() returns a fake response with the given bytes."""

    def __init__(self, result):
        self._result = result

    def open(self, req, timeout=None):
        if isinstance(self._result, BaseException):
            raise self._result
        return _FakeResponse(self._result)


CREDENTIALED_ENV = {"APCA_API_KEY_ID": "id", "APCA_API_SECRET_KEY": "secret"}


class ProbeTests(unittest.TestCase):
    def test_short_page_followed_to_terminal(self):
        requests = []
        def fetch(params):
            requests.append(params)
            return json.dumps({"bars": {}, "next_page_token":
                               "next" if len(requests) == 1 else None}).encode()
        result = collect(fetch)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1]["page_token"], "next")
        self.assertEqual(requests[0]["adjustment"], "raw")
        self.assertEqual(requests[0]["feed"], "sip")
        self.assertTrue(result["terminal_page_observed"])
        self.assertFalse(result["access_check_passed"])
        self.assertFalse(result["accepted_for_labels"])

    def test_missing_or_repeated_token_rejected(self):
        for page in ({"bars": {}}, {"bars": {}, "next_page_token": "loop"}):
            with self.assertRaises(DataError):
                collect(lambda params: json.dumps(page).encode())

    def test_unexpected_symbol_rejected(self):
        with self.assertRaises(DataError):
            collect(lambda params: b'{"bars":{"OTHER":[]},"next_page_token":null}')

    def test_no_credentials_no_network(self):
        with patch.dict("os.environ", {}, clear=True), patch("builtins.print") as output:
            self.assertEqual(main(), 2)
            self.assertIn("MISSING_GITHUB_ACTIONS_SECRETS", output.call_args.args[0])

    def test_data_validation_error_surfaced_safely(self):
        opener = _FakeOpener(json.dumps({"bars": {}}).encode())
        with patch.dict("os.environ", CREDENTIALED_ENV, clear=True), \
             patch("nre.alpaca_probe.build_opener", return_value=opener), \
             patch("builtins.print") as output:
            self.assertEqual(main(), 2)
            printed = output.call_args.args[0]
            self.assertIn("DATA_VALIDATION_FAILED: missing pagination metadata", printed)

    def test_invalid_json_response_categorized(self):
        opener = _FakeOpener(b"<html>not json</html>")
        with patch.dict("os.environ", CREDENTIALED_ENV, clear=True), \
             patch("nre.alpaca_probe.build_opener", return_value=opener), \
             patch("builtins.print") as output:
            self.assertEqual(main(), 2)
            self.assertIn("INVALID_JSON_RESPONSE", output.call_args.args[0])

    def test_network_error_categorized(self):
        opener = _FakeOpener(URLError("connection refused"))
        with patch.dict("os.environ", CREDENTIALED_ENV, clear=True), \
             patch("nre.alpaca_probe.build_opener", return_value=opener), \
             patch("builtins.print") as output:
            self.assertEqual(main(), 2)
            self.assertIn("NETWORK_ERROR", output.call_args.args[0])
            self.assertNotIn("connection refused", output.call_args.args[0])
