import json
import unittest
from unittest.mock import patch
from nre.alpaca_probe import collect, main
from nre.core import DataError


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
