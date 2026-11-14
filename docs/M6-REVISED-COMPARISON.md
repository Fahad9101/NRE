# Milestone 6 — Revised selection comparison

[Protocol v2](../config/m6-protocol-v2.json) tests whether the reaction-gap tail rule selects better events to fade than opening-gap magnitude alone. Both rules use the same opening clock and fade direction. Each allocates one signed unit on flagged events and zero otherwise. The primary score is the difference in their opening-to-close reference returns averaged over the common cohort.

The comparator flags when the absolute opening gap strictly exceeds 15.9625584%. The cutoff was calibrated on 58 development diagnostics to match the tail rule's nine flags. Both rules selected the same five upward and four downward fades. The other 49 events received zero under both rules. This was a development coverage check using daily opening proxies. The threshold used only opening magnitudes and flag membership.

Unlike v1, v2 can select different events. For example, given the v1 reference pool's tail boundaries, a +15% open satisfies the upper-tail rule and falls below the magnitude threshold. The diagnostic nevertheless supplied zero discordant allocations. It provides no estimate of paired-return dispersion on discordant rows and no defensible confirmatory sample size for the proposed cohort.

The proposed 2027 collection remains blocked. A further feasibility study would need a separately authorized, outcome-blind way to estimate discordance in verified opening observations before proposing confirmatory collection. The [freeze record](../reports/m6-revised-comparison-freeze-2026-11-14.json) records the owner's authorization and protocol digest.
