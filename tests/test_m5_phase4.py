"""Phase 4 locks fitted predictors before the holdout is made available."""
import unittest
from unittest.mock import patch

from nre import m5_harness as harness, m5_phase4 as phase4
from test_m5_phase2 import fixtures, PROTOCOL


class OneLookTests(unittest.TestCase):
    def test_lock_needs_only_holdout_metadata(self):
        events, daily = fixtures()
        target = PROTOCOL["targets"][0]
        metadata = [{key: event[key] for key in ("event_id", "cluster_id", "reaction_session", "clock")}
                    | {"outcome": None} for event in events[80:]]
        training_features = {event["event_id"]: daily[event["event_id"]] for event in events[:80]}
        lock, predict = harness.run_fold(PROTOCOL, target, "final", events[:80], metadata,
                                         training_features, prepare_only=True)
        self.assertEqual(lock["status"], "PREPARED")
        self.assertRegex(lock["fitted_probe_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(lock["predictions"], [])
        event = events[-1]
        self.assertEqual(predict(event, daily), predict(dict(event, outcome=1 - event["outcome"]), daily))

    def test_label_mismatch_stops_before_feature_acquisition(self):
        event = {"recorded_result": {"labels_sha256": "0" * 64}}
        with (patch.object(phase4, "load", return_value={"provider": {}}),
              patch.object(phase4.ea, "event_window"),
              patch.object(phase4.ea, "fetch_event_data", return_value=({}, [], [], [])),
              patch.object(phase4.ea, "build_bundle"),
              patch.object(phase4.ea, "build", return_value=([{"state": "MAPPED", "labels": {}}], {})),
              patch.object(phase4.features, "acquire") as acquire):
            with self.assertRaisesRegex(ValueError, "label commitment mismatch"):
                phase4.verified_holdout(PROTOCOL, [event], None, None, {}, None)
            acquire.assert_not_called()
