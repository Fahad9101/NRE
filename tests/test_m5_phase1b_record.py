"""What Milestone 5 Phase 1b recorded about itself: the owner's go-ahead and two answers, and how they were read (reports/m5-phase1b-authorization-2026-10-09.json); and the plan (docs/M5-PHASE1B-FORWARD-EXTENSION-PLAN.md)
bound to those records, to the pre-registered protocol and to the earlier records and code its figures and claims come from."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTHORIZATION = ROOT / "reports" / "m5-phase1b-authorization-2026-10-09.json"
PHASE1A = ROOT / "reports" / "m5-phase1a-authorization-2026-10-08.json"
PROTOCOL = ROOT / "config" / "m5-phase1b-protocol.json"
PLAN = ROOT / "docs" / "M5-PHASE1B-FORWARD-EXTENSION-PLAN.md"
PROPOSAL = ROOT / "docs" / "M5-ADVANCED-MODELS-SCOPE.md"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def flat(text):
    return " ".join(text.split())


class AuthorizationRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load(AUTHORIZATION)

    def test_it_quotes_the_owners_go_ahead_and_the_message_it_answers(self):
        record = self.record
        self.assertEqual((record["kind"], record["recorded_on"]), ("m5_phase1b_authorization", "2026-10-09"))
        self.assertEqual([(m["text"], m["at"]) for m in record["owner_messages"]], [("authorize phase 1b", "2026-10-09T07:12:36.854Z")])
        self.assertIn("line 37256", record["owner_messages"][0]["source"])
        replied = record["assistant_message_replied_to"]
        self.assertLess(replied["at"], record["owner_messages"][0]["at"])
        self.assertEqual(replied["source"], "session transcript, line 37252")
        self.assertTrue(replied["text"].startswith("Pushed `5a57316..c96b21b`, which publishes `dd9209d` and `c96b21b`."))
        for phrase in ("**Recommended next step:** authorize Phase 1b, the forward extension.", "it needs your answer on the provider-rights-at-scale question first", "That is a recommendation only."):
            self.assertIn(phrase, replied["text"])

    def test_the_two_questions_and_the_owners_answers_are_recorded_as_asked(self):
        record = self.record
        answers = {a["header"]: a for a in record["owner_answers"]}
        self.assertEqual(list(answers), ["Rights", "Seal"])
        self.assertEqual({h: a["owner_selected"] for h, a in answers.items()}, {"Rights": "Yes, provider rights fine", "Seal": "Hash-only seal (Recommended)"})
        for answer in answers.values():
            self.assertIn(answer["owner_selected"], [o["label"] for o in answer["options_offered"]])
            self.assertGreaterEqual(len(answer["options_offered"]), 2)
            self.assertLess(record["owner_messages"][0]["at"], answer["asked_at"])
            self.assertLess(answer["asked_at"], answer["answered_at"])
            self.assertIn("line 37363", answer["source"])
            self.assertIn("line 37369", answer["source"])
        self.assertTrue(answers["Rights"]["question"].startswith("Does the Alpaca provider research authorization extend to Phase 1b's scale?"))
        self.assertIn("It would add about 48 events to the 128 (an estimate; nothing is enumerated yet)", answers["Rights"]["question"])
        self.assertIn("Phase 1c, which adds features for every event, would put the question to you again.", answers["Rights"]["question"])
        self.assertEqual(answers["Seal"]["question"], "How should the fresh holdout's labels be sealed until Phase 4?")
        self.assertEqual([o["label"] for o in answers["Seal"]["options_offered"]], ["Hash-only seal (Recommended)", "No labels until Phase 4"])
        self.assertEqual([o["label"] for o in answers["Rights"]["options_offered"]], ["Yes, provider rights fine", "Not yet"])

    def test_the_phase_it_authorizes_is_worded_as_in_the_proposal(self):
        words = self.record["phase_as_proposed"]["words"]
        self.assertIn(words, flat(PROPOSAL.read_text(encoding="utf-8")))
        self.assertTrue(words.startswith("a forward extension, \"Milestone 2 step 4\": an outcome-blind enumeration and freeze of candidate events since 2026-04-01"))
        self.assertEqual(self.record["phase_as_proposed"]["document"], "docs/M5-ADVANCED-MODELS-SCOPE.md")

    def test_it_reads_the_words_narrowly_and_says_so(self):
        text = " ".join(self.record["how_the_words_were_read"])
        for phrase in ("It authorizes Phase 1b of docs/M5-ADVANCED-MODELS-SCOPE.md as the proposal words it", "The words do not answer the provider-rights-at-scale question", "'Yes, provider rights fine'",
                       "covering Phase 1b's scale only: about 48 more events", "The question is put to the owner again before Phase 1c.", "The owner chose the hash-only seal", "NOT_POSITIVE_GAP_GE_0_5PCT",
                       "pre-registered in config/m5-phase1b-protocol.json before any run", "The assistant attests nothing", "The go-ahead is for the phase, not for each of its steps", "The words do not carry a push",
                       "It does not authorize 0, 1c or any later phase", "Disclosure:", "It has seen no outcome, price or label of any event since 2026-04-01"):
            self.assertIn(phrase, text)

    def test_what_is_authorized_and_what_is_not_is_listed(self):
        record = self.record
        self.assertEqual(len(record["authorized_under_these_words"]), 5)
        authorized = " ".join(record["authorized_under_these_words"])
        for later in ("Phase 0", "Phase 1c", "Phase 2", "Phase 3", "Phase 4", "Milestone 6"):
            self.assertNotIn(later, authorized)                                  # nothing later is among the things authorized
        for phrase in ("Building, testing and committing locally", "once the owner has said \"push\"", "outcome-blind", "in sealed runs only, for events the owner has attested", "Recording sealed commitments"):
            self.assertIn(phrase, authorized)
        not_authorized = " ".join(record["not_authorized_by_these_words"])
        for phrase in ("Phase 0 (pre-registering config/m5-protocol.json), Phase 1c", "Reading, printing or committing any label value, return, price, ratio or price-derived flag", "Attesting any event's first-public timing",
                       "Adding an issuer to the 23", "Fetching data from a provider the project has not reviewed", "Answering the provider-rights-at-scale question for Phase 1c", "Pushing without the owner's word \"push\"",
                       "Any read of a block-5 outcome", "Declaring the forward extension (Milestone 2 step 4) or Milestone 5 accepted", "Any change to the accepted Milestone 1 to 4 work"):
            self.assertIn(phrase, not_authorized)
        self.assertIn("does not change a confirmed default on its own", record["change_rule"])
        self.assertIn("Not a claim that about 48 events exist", " ".join(record["not_a_claim"]))

    def test_the_default_the_assistant_chose_for_the_owners_veto_is_the_protocols_window(self):
        protocol = load(PROTOCOL)
        reading = " ".join(self.record["how_the_words_were_read"])
        self.assertIn("releases dated %s to %s inclusive" % (protocol["event_window_start"], protocol["event_window_end"]), reading)
        self.assertIn("(2026-10-08)", reading)
        self.assertIn("for the owner's veto before the freeze", reading)


class PlanDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PLAN.read_text(encoding="utf-8")
        cls.flat = flat(cls.text)
        cls.record = load(AUTHORIZATION)
        cls.protocol = load(PROTOCOL)
        cls.proposal = flat(PROPOSAL.read_text(encoding="utf-8"))

    def test_it_says_nothing_has_run_and_what_it_does_not_do(self):
        for phrase in ("fixed on 2026-10-09 before any run, and updated the same day after S1", "S1 is done: the candidate pool is frozen (section 4). S2 is done too: the same-day sweep of the 47 candidates and the review of the filings' text, and the owner has decided the three things it left (`reports/m5-phase1b-s2-decisions-2026-10-09.json`), so 45 candidates stand. S3, the sealed mode of the event acquisition, is built. S4 and S5 have run for batch 1: its event specs were built in the dry-run state, the sealed dry run ran, the signoff packet was prepared and the owner has signed it off (`reports/m5-phase1b-batch1-signoff-2026-10-09.json`): eight events are attested, NBIX's second dry run listed its one action and the owner then attested NBIX too (`reports/m5-phase1b-nbix-signoff-2026-10-10.json`), and ASMB stays quarantined. S6 has run for batch 1: the attested sealed run printed the eight commitments (`reports/m5-phase1b-batch1-sealed-run-2026-10-10.json`) and a second run confirmed those pins and printed NBIX's (`reports/m5-phase1b-batch1-pin-verification-2026-10-10.json`), so all nine are pinned in the events file. Batch 2 has begun: the owner permitted reading its ten releases' wire pages (`reports/m5-phase1b-batch2-permission-2026-10-10.json`) and its ten event specs are built in the dry-run state after batch 1's nine (`reports/m5-phase1b-batch2-sources-2026-10-10.json`). Its sealed dry run ran (`reports/m5-phase1b-batch2-dry-run-2026-10-10.json`) and its signoff packet was prepared (`reports/m5-phase1b-batch2-signoff-packet-2026-10-10.json`) and the owner has signed it off (`reports/m5-phase1b-batch2-signoff-2026-10-10.json`): all ten events are attested, REKR with a caveat for its Item 3.01 filing and ACHV with a caveat for its separate release. The attested sealed run of batch 2 has not run. No label, return or event price has been read; one inadvertent exposure to a company's quarterly average repurchase price, through a search-tool summary, is disclosed in `reports/m5-phase1b-batch1-sources-2026-10-09.json`. Nothing later has started.",
                       "It runs and fetches nothing itself and pushes nothing. The work it describes enumerates candidates by filing metadata only, reads no price or label, and attests no event.",
                       "It does not start Phase 0, 1c, 2, 3 or 4, and it does not answer the provider-rights question for Phase 1c."):
            self.assertIn(phrase, self.flat)
        self.assertEqual(re.findall(r"^## (.+)$", self.text, re.M), ["1. What Phase 1b is", "2. What the owner decided", "3. The rules, fixed before the first run", "4. The stages", "5. What is built first", "6. What this plan does not do"])

    def test_every_quotation_is_the_owners_or_the_proposals(self):
        outside_code = re.sub(r"`[^`]*`", "", self.flat)
        self.assertEqual(outside_code.count('"') % 2, 0)                                       # so that quotation marks pair up
        spans = re.findall(r'"([^"]*)"', outside_code)
        self.assertGreaterEqual(len(spans), 6)
        phase1a = flat(json.dumps(load(PHASE1A)))
        known = {"authorize phase 1b": self.record["owner_messages"][0]["text"], "Yes, provider rights fine": self.record["owner_answers"][0]["owner_selected"],
                 "Hash-only seal (Recommended)": self.record["owner_answers"][1]["owner_selected"], "Milestone 2 step 4": "Milestone 2 step 4"}
        for span in spans:
            with self.subTest(span=span):
                if span == "push":                                                              # the owner's standing word for publishing, as recorded in the Phase 1a record
                    self.assertIn('word \\"push\\"', phase1a)
                else:
                    self.assertEqual(known[span], span)
        self.assertIn('"Milestone 2 step 4"', self.proposal)                                  # and the proposal does say it, in quotation marks
        self.assertEqual(self.text.count('"authorize phase 1b"'), 2)

    def test_the_figures_are_the_records_and_the_earlier_files(self):
        flat_text = self.flat
        events = {name: [e for e in load(ROOT / "config" / name)["events"] if e.get("recorded_result")] for name in ("m1-events.json", "m2-step2-events.json", "m2-step3-events.json")}
        sizes = {name: len(found) for name, found in events.items()}
        self.assertEqual(sizes, {"m1-events.json": 23, "m2-step2-events.json": 45, "m2-step3-events.json": 60})
        self.assertEqual(len(load(ROOT / "config" / "m2-step3-combined-events.json")["events"]), sum(sizes.values()))
        self.assertIn("The exposed derived-data footprint is %d events today (%d from Milestone 1, %d from step 2 and %d from step 3)" % (
            sum(sizes.values()), sizes["m1-events.json"], sizes["m2-step2-events.json"], sizes["m2-step3-events.json"]), flat_text)
        self.assertIn("At the dataset's own rate (128 events over 512 days) about 48 events would have occurred since the data ended", flat_text)
        self.assertIn("(128 events over 512 days, 190 days since the last reaction session) about 48 events would have occurred since", self.proposal)
        batches = lambda pattern: len(list((ROOT / "reports").glob(pattern)))                    # noqa: E731
        self.assertEqual((batches("m2-step2-batch*-signoff-2026-09-29.json"), batches("m2-step3-batch*-signoff-2026-10-02.json")), (4, 6))
        self.assertIn("Step 2 took four batches and step 3 six; about 48 events is about five. The frozen pool has 47 candidates, none of which is an event until it has been reviewed.", flat_text)
        frozen = load(ROOT / "config" / "m5-phase1b-frozen-candidate-ledger.json")["candidates"]
        per_issuer = {}
        for candidate in frozen:
            per_issuer[candidate["ticker"]] = per_issuer.get(candidate["ticker"], 0) + 1
        self.assertEqual((len(frozen), sorted(n for n in per_issuer.values()).count(2), per_issuer["REKR"], sum(1 for c in frozen if c["form"] == "8-K/A")), (47, 22, 3, 1))
        self.assertIn("The freeze found 47 candidates: 22 issuers have two, REKR has three, and one candidate is an 8-K/A.", flat_text)
        protocol = self.protocol
        self.assertIn("Every Item 2.02 8-K or 8-K/A filed from %s to %s" % (protocol["event_window_start"], protocol["event_window_end"]), flat_text)
        self.assertIn("It ends on %s, the last release date whose 20-session label window is complete as of the latest session when the window was fixed (2026-10-08)" % protocol["event_window_end"], flat_text)
        pilot = load(ROOT / "config" / "pilot.json")
        self.assertIn("It starts the day after Milestone 1's event window ended (%s)" % pilot["event_window_end"], flat_text)
        self.assertEqual(protocol["event_window_start"], "2026-04-01")
        self.assertIn("(2026-10-09T07:12:36.854Z)", flat_text)
        self.assertEqual(self.record["owner_messages"][0]["at"], "2026-10-09T07:12:36.854Z")
        ledger = load(ROOT / "config" / "m1-frozen-candidate-ledger.json")["candidates"]
        ciks = {i["cik"] for i in load(ROOT / "config" / "m5-phase1b-cohort-spec.json")["issuers"]}
        later = [c for c in ledger if c["filing_date"] >= protocol["event_window_start"]]
        self.assertEqual((len(later), len([c for c in later if c["cik"] in ciks])), (3, 0))
        self.assertIn("No candidate of the 23 issuers in Milestone 1's frozen ledger is dated on or after 2026-04-01 (three candidates of other issuers are)", flat_text)

    def test_the_seal_paragraph_is_the_protocols_seal_and_the_leak_it_names_is_real(self):
        seal = self.protocol["seal"]
        self.assertEqual(seal["method"], "hash_only")
        for phrase in ("A sealed run reports only an event's state, its quarantine reasons, its window facts, its missing and zero-volume sessions, its corporate actions, the SHA-256 commitment of its labels, and whether each of "
                       "the four session-return labels exists and, if not, why.", "It never reports a label value, a price, a return or a ratio, or whether any day-1 label or gap label is true or false.",
                       "It also hides the engine's reason `NOT_POSITIVE_GAP_GE_0_5PCT`", "which the engine gives exactly when the opening gap is below +0.5%",
                       "At Phase 4 the labels are recomputed once and checked against the commitments (a mismatch is reported, never overwritten), and that look is the only one.",
                       "The seal is a procedure, not secrecy", "The assistant will not seek those prices.", "**A disclosure:** the assistant has seen the Milestone 4 block-5 results (the proposal says so); it has seen no outcome, price or label of "
                       "any event since 2026-04-01."):
            self.assertIn(phrase, self.flat)
        never = " ".join(seal["a_sealed_run_never_reports"])
        self.assertIn("a label value, a price, a return or a ratio", never)
        self.assertIn("whether any day-1 label, gap threshold or gap label is true or false", never)
        self.assertIn("NOT_POSITIVE_GAP_GE_0_5PCT", never)
        self.assertIn("The seal is a procedure and a commitment, not secrecy", " ".join(seal["limits"]))
        self.assertIn("the assistant will not seek those prices", " ".join(seal["limits"]))
        source = (ROOT / "nre" / "dataset.py").read_text(encoding="utf-8")
        self.assertIn('label(None, window, "NOT_POSITIVE_GAP_GE_0_5PCT")', source)
        self.assertIn('Decimal("1.005")', source)                                               # a gap of 0.5% or more is the only case with a value
        self.assertIn("the assistant writing this proposal has seen the block-5 results", self.proposal)
        self.assertIn("labels_sha256", (ROOT / "nre" / "event_acquire.py").read_text(encoding="utf-8"))

    def test_the_stages_are_s1_to_s7_and_what_is_built_first_exists(self):
        rows = re.findall(r"(?m)^\| (S\d) \|", self.text)
        self.assertEqual(rows, ["S%d" % n for n in range(1, 8)])
        for path in ("config/m5-phase1b-protocol.json", "config/m5-phase1b-cohort-spec.json", ".github/workflows/m5-phase1b-sec-cohort-freeze.yml", "tests/test_m5_phase1b_freeze.py",
                     "tests/test_m5_phase1b_freeze_workflow.py", "config/m5-phase1b-frozen-issuer-cohort.json", "config/m5-phase1b-frozen-candidate-ledger.json", "reports/m5-phase1b-sec-cohort-freeze.json",
                     "reports/m5-phase1b-sec-cohort-freeze-result-2026-10-09.json"):
            self.assertTrue((ROOT / path).is_file(), path)
        self.assertIn("the SEC refused its run, so it is now dispatch-only and kept as the record", self.flat)
        self.assertIn("which stops whenever any frozen file exists on main;", self.flat)
        self.assertIn("Done on 2026-10-09 through the built-in browser, because the SEC refused the one-time workflow", self.flat)
        self.assertIn('| the owner\'s permission to download (given), then "push" |', self.flat)
        self.assertIn("Both are done on 2026-10-09. The sweep (`reports/m5-phase1b-same-day-sweep-2026-10-09.json`) found no candidate with another 8-K or 8-K/A on its filing date. The review of the filings' text "
                      "(`reports/m5-phase1b-eligibility-review-2026-10-09.json`, read with the owner's permission) found 44 results releases with no issue and three decisions for the owner: a pre-announcement, "
                      "a header-only amendment and a pending cash take-private. The owner made them the same day (`reports/m5-phase1b-s2-decisions-2026-10-09.json`): exclude the pre-announcement, keep the amendment "
                      "with a caveat, exclude the pending take-private; 45 candidates stand | nothing further |", self.flat)
        self.assertIn("The sweep of S2 followed, from the archived lists alone (`tests/test_m5_phase1b_sweep.py` repeats it); the review of the filings' text followed, with the owner's permission to read the filings "
                      "in the built-in browser (`tests/test_m5_phase1b_review.py` binds its record).", self.flat)
        self.assertIn("Batch 1 is built on 2026-10-09 (`reports/m5-phase1b-batch1-sources-2026-10-09.json`, `config/m5-phase1b-events.json`): nine sealed events, built in the dry-run state; the tenth candidate, ASMB, was released at the 16:00 ET close, "
                      "which the calendar classes as bell-ambiguous, so it is left quarantined for the owner's word. Batch 2 is built on 2026-10-10 (`reports/m5-phase1b-batch2-permission-2026-10-10.json`, "
                      "`reports/m5-phase1b-batch2-sources-2026-10-10.json`): ten more sealed events, appended to the same file in the dry-run state; none is bell-ambiguous, and ACHV carries a caveat for a separate same-day release "
                      "| \"push\" for each batch |", self.flat)
        self.assertIn("Batch 1's ran on 2026-10-09 (`reports/m5-phase1b-batch1-dry-run-2026-10-09.json`): eight events quarantined as a dry run should, and NBIX errored on a corporate action with no ex-date; the packet "
                      "(`reports/m5-phase1b-batch1-signoff-packet-2026-10-09.json`) asked for the eight attestations and put two decisions to the owner. The owner answered the same day (`reports/m5-phase1b-batch1-signoff-2026-10-09.json`): "
                      "the eight are attested, with the packet's caveats; NBIX gets an additive change to `fetch_actions` (an action with no ex-date is dated by its effective, payable or process date; `tests/test_event_acquire_action_dates.py`) "
                      "and stays unattested until its second dry run has listed its action; ASMB stays quarantined. Batch 2's ran on 2026-10-10 (`reports/m5-phase1b-batch2-dry-run-2026-10-10.json`): ten events quarantined as a dry run should, "
                      "no error and no corporate action; the packet (`reports/m5-phase1b-batch2-signoff-packet-2026-10-10.json`) asks for the ten attestations and puts two calls to the owner, REKR's Item 3.01 filing and ACHV's separate "
                      "same-day release. The owner answered the same day (`reports/m5-phase1b-batch2-signoff-2026-10-10.json`): all ten are attested, REKR and ACHV with their caveats "
                      "| batch 1's attestations and decisions (given; NBIX's on 2026-10-10, after the owner had seen its listed action); batch 2's attestations and two calls (given on 2026-10-10) |", self.flat)
        for phrase in ("The signoff of batch 1 added one change to that module, the owner's answer (A) on NBIX: `fetch_actions` dates an action that has no ex_date by the first of its effective, payable and process dates that is present, "
                       "and says which in a `date_field` entry that the sealed view shows only when the date is not an ex-date.",
                       "An action with none of them still fails closed, and a date that is present but unusable is an error, never a reason to try the next one.",
                       "It changes nothing for an input that worked before, because such an input has a valid ex_date, which still decides.",
                       "`tests/test_event_acquire_action_dates.py` pins it and `tests/test_m5_phase1b_attestations.py` binds the signoff record and the attested events file.",
                       "Pushing it starts the Milestone 1 event acquisition again, whose pinned matches are the same real-data check."):
            self.assertIn(phrase, self.flat)
        self.assertIn("| S6 | A sealed attested run for each batch, and each event's commitment pinned. Batch 1's ran on 2026-10-10 (`reports/m5-phase1b-batch1-sealed-run-2026-10-10.json`): the eight attested events are MAPPED "
                      "with a commitment each (CXT's session_20 label does not exist, because of its dividend), and NBIX, then unattested, lists its one action; the owner attested NBIX on 2026-10-10 "
                      "(`reports/m5-phase1b-nbix-signoff-2026-10-10.json`), the eight commitments were pinned, and a second run (`reports/m5-phase1b-batch1-pin-verification-2026-10-10.json`) matched all eight "
                      "and printed NBIX's commitment (its session_10 and session_20 labels do not exist, because of the merger item's date), which is pinned too | \"push\" for NBIX's pin |", self.flat)
        self.assertIn("S6 followed for batch 1's eight attested events. `tests/test_m5_phase1b_sealed_run.py` binds the sealed-run record to the events file and the calendar and checks that the pins are the record's commitments; "
                      "`tests/test_m5_phase1b_batch1.py` runs the pinned file with injected prices and requires each mapped event to report a mismatch, so a pin does catch a different history. "
                      "The same file binds the second record: the eight pins matched, nothing else about them changed, and NBIX's commitment is the events file's ninth pin. "
                      "The owner's later answer on NBIX is bound by `tests/test_m5_phase1b_attestations.py`, which checks the answer as given, the action the owner saw against the sealed-run record, "
                      "and NBIX's attestations and caveats in the events file. "
                      "S4 of batch 2 followed. `tests/test_m5_phase1b_batch2.py` quotes the owner's permission as given, recomputes the ten candidates from the S2 records, checks the ten events against the frozen ledger, "
                      "the eligibility review, the Milestone 1 events, the calendar and the archived SEC lists, recovers their dry-run state byte for byte, and runs them through a sealed run with injected prices. "
                      "`tests/test_m5_phase1b_batch2_signoff.py` then binds batch 2's dry-run record to the sealed view and recomputes its signoff packet from the events file, the sources record, the archived SEC lists, "
                      "the Milestone 1 events, the review table and the calendar. `tests/test_m5_phase1b_batch2_attestations.py` binds the owner's three answers as given and the ten attested events in the events file.", self.flat)
        review = load(ROOT / "reports" / "m5-phase1b-eligibility-review-2026-10-09.json")
        self.assertEqual(review["counts"]["by_assessment"]["results_release_no_issue_found"], 44)
        self.assertEqual(len(review["decisions_for_the_owner"]), 3)
        self.assertIn("Built on 2026-10-09: the `--sealed` flag of `nre/event_acquire.py`, the workflow `.github/workflows/m5-phase1b-event-acquire.yml` and `tests/test_event_acquire_sealed.py` (section 5) | \"push\" |", self.flat)
        for phrase in ("S3 followed, before the first batch's dry run. `nre/event_acquire.py` takes `--sealed`: the report of each event is rebuilt from an allowlist",
                       "every reason and error is checked against a fixed list and anything else becomes OTHER, an exception prints no message, and an output that holds a decimal number or the gap reason is refused whole",
                       "An event marked `seal: hash_only` in its spec refuses to run without the flag, before anything is fetched.", "uploads nothing and uses no calendar argument",
                       "requires identical sealed reports except the commitment", "Pushing it also starts the Milestone 1 event acquisition, which watches that file; its pinned matches are the real-data check that the unsealed path is unchanged."):
            self.assertIn(phrase, self.flat)
        source, workflow = (ROOT / "nre" / "event_acquire.py").read_text(encoding="utf-8"), (ROOT / ".github" / "workflows" / "m5-phase1b-event-acquire.yml").read_text(encoding="utf-8")
        self.assertIn("--sealed", source)
        self.assertIn('SEAL = "hash_only"', source)
        self.assertIn("python -m nre.event_acquire --sealed", workflow)
        self.assertIn("nre/event_acquire.py", (ROOT / ".github" / "workflows" / "event-acquire.yml").read_text(encoding="utf-8"))               # the Milestone 1 workflow does watch the module
        self.assertIn("`window_relation_to_milestone_1`", self.text)
        self.assertIn("window_relation_to_milestone_1", (ROOT / "nre" / "depth_cohort.py").read_text(encoding="utf-8"))
        self.assertIn("which lets a window start after Milestone 1's instead of ending before it, and changes nothing for the earlier steps", self.flat)

    def test_every_file_it_names_exists(self):
        names = sorted(set(re.findall(r"`((?:reports|docs|nre|tests|config|scripts|archive|\.github)/[A-Za-z0-9_./\-]+\.(?:json|jsonl|md|py|yml))`", self.text)))
        self.assertGreaterEqual(len(names), 5)
        for name in names:
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file())


if __name__ == "__main__":
    unittest.main()
