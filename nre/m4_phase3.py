"""Phase 3 of Milestone 4: the baselines on the C0-clock primary targets, on the development folds, in both versions.

    python -m nre.m4_phase3 audit [--output PATH]     the structure of the real development folds for these targets (cell sizes, events without history, whether the
                                                       opening gap is defined): reads which labels are defined, never an outcome, and evaluates nothing
    python -m nre.m4_phase3 run --date YYYY-MM-DD      the evaluation itself: needs ALLOW_REAL_EVALUATION for these targets, a clean committed tree, no earlier Phase 3
                                                       output, and the experiment log exactly as Phase 2 left it

The C0 clock is the regular open of the reaction session, when the opening print (day1_open_return) is known and the day's high, low and close are not. The
targets are extension_after_open_ge_5pct (the day's high at least 5% above the open) and loses_half_of_gap (among gaps of at least 0.5%, the day-1 close keeps less
than half of the gap). The predictors are Phase 2's, except that M2 also takes the opening gap. It is Phase 2's runner (nre/m4_phase2.py) with Phase 3's targets.
"""
import sys

from . import m4_phase2 as p2

TARGETS = ("extension_after_open_ge_5pct", "loses_half_of_gap")
PHASE_3 = p2.Phase(
    3, TARGETS, 1 + 2 * (18 + 18 + 15), p2.TARGETS,  # the genesis record and Phase 2's 102 experiments
    ("The structure of the real development folds for the two C0-clock targets, taken before any Phase 3 predictor is evaluated: how many training events fall in each cell the C2 and C3 "
     "baselines will use, which cells have too few and so fall back to the pooled value, how many test events have no earlier event of their own issuer to learn from, and whether every "
     "training row and test event has the opening gap that M2 takes as a feature. It counts which labels are defined and reads no outcome value: no rate, no positive count, no return, and not "
     "the value of the opening gap."),
    ("The Milestone 4 baselines beyond the pooled rate, fitted on each development fold's training blocks and scored on its test block, for the two C0-clock primary targets (decided at the "
     "regular open, when the opening gap is known) in both versions (all_event and clean_window). M2 also takes the opening gap. The holdout is sealed. loses_half_of_gap is "
     "INSUFFICIENT_DATA in the clean-window version by the protocol's thresholds, so its all-event results are exploratory. Every contrast is model minus comparator, lower is better. "
     "A status is never a claim of a tradable or production-ready edge."))


def main(argv=None):
    return p2.main(argv, phase=PHASE_3)


if __name__ == "__main__":
    sys.exit(main())
