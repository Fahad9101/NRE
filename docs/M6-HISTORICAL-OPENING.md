# Milestone 6 — Historical opening-only diagnostic

The owner authorized an opening-only historical check after the real-time SIP entitlement probe returned insufficient subscription. This diagnostic uses the 128 pinned development event specifications and the fixed reference statistics and comparator threshold from protocols v1 and v2. It deduplicates economic clusters and excludes recorded opening caveats. The fixed full-history reference and retrospective caveats make this a descriptive feed and disagreement check.

For each eligible event the check uses the preceding regular-session close from a raw SIP daily bar and queries only the first minute of the reaction session from the historical single-symbol SIP trades endpoint. It requires the official-open condition Q on the listing venue and expected tape. Conflicting or revised official opens are excluded. The workflow publishes a signed allocation cross-tabulation, disposition counts, and discordant issuer and session counts. No raw bars, trades, or reaction-session closing outcomes are written. [Alpaca historical trades](https://docs.alpaca.markets/us/reference/stocktradesingle-1) · [Official-open condition](https://www.nyse.com/publicdocs/nyse/data/Daily_TAQ_Client_Spec_v4.1a.pdf)

Historical records show the feed timestamp. They cannot establish the original receipt latency, what corrections were known at the time, or whether prospective capture would meet the pilot's clock and coverage requirements. The historical diagnostic leaves the prospective study gate in place.

After the authorized push, dispatch `m6-historical-opening.yml` on main. Check the result in the job log. The workflow has a request budget and fails closed on unexpected response structure or provider error.
