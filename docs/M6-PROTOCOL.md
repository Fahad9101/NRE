# Milestone 6 Step A — Reaction gap pre-registration

The [frozen protocol](../config/m6-protocol.json) specifies the benchmark, coverage gates, opening and closing price references, and quality checks. The [freeze record](../reports/m6-step-a-freeze-2026-11-14.json) binds the owner authorization and protocol digest.

The proposed prospective window is January 1 through December 31, 2027, in New York time, covering the 23 fixed issuers. Operational readiness and separate collection authorization must precede the start. The price-source plan uses the Alpaca SIP trade stream with an official opening-print condition, listing venue, and simultaneously logged receipt time. Entitlement, condition mappings, clock accuracy and applicable NYSE and listing exchange calendars require verification before collection. [Alpaca stream](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data) · [NYSE calendar](https://www.nyse.com/trade/hours-calendars)

## Why the proposed primary comparison is blocked

The 119 clean development close returns give a mean of -2.43% and empirical 10th and 90th percentiles of -19.12% and +14.28%. On the 58 earlier-mature diagnostic rows, nine daily-opening proxies flagged. All nine agreed with the opening-gap fade rule, with five positive and four negative flags.

This follows from the benchmark geometry. The lower tail lies below both zero and the benchmark mean, so its candidate and fade directions are both positive. The upper tail lies above both, so both are negative. With the frozen pool and tail rule, the paired return difference is therefore zero on every flagged row regardless of the closing outcome. Collecting more events cannot make that contrast informative.

Treat the frozen v1 rules as an engineering specification with a blocked confirmatory comparison. The recommended revision is to test whether the tail rule improves the selection of fade opportunities. Compare the flagged fade rule against a same-clock, coverage-matched fade selector based on opening-gap magnitude, using zero exposure when either selector abstains and scoring on the whole eligible cohort. The allocation, coverage-matching method and claim threshold must be fixed prospectively in a separately approved revision. The 2027 dates and descriptive support floors in v1 are design defaults. The sample-size illustration is a scale check and supplies no feasible confirmatory target for the blocked contrast.
