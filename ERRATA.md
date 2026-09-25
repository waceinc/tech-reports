# Errata — WACE TR-2026-01

## v1.2 → v1.3 (revised 2026-09-25)

| # | Kind | Where in v1.2 | v1.2 said | Correct |
| --- | --- | --- | --- | --- |
| E6 | Author's name (romanisation) | Title block · README · CITATION.cff · Zenodo metadata (v1.0–v1.2) | "Dongkeol Bang" (citation "Bang, D.") | "Dong Gul Bang", the spelling in the author's passport (citation "Bang, D. G."). Same person. No other text, table or number changes. |

## v1.1 → v1.2 (revised 2026-09-22)

| # | Kind | Where in v1.1 | v1.1 said | Correct |
| --- | --- | --- | --- | --- |
| E5 | Overstatement (present since v1.0) | Abstract · README (v1.0 and v1.1) · Section 6 (v1.1) | "thirteen official attempts with all commits and records published"; the v1.0 errors were detectable "because the row labels and the pre-registered predictions were public"; the numbers "are reproducible from the result files named in it" | The run ledger (Table 2) lists every attempt with its commit and outcome. The result files, the row labels and the pre-registration are held by the company and were not public when v1.0, v1.1 or v1.2 was released, so readers cannot yet recompute the numbers. Releasing them is a separate decision. The v1.0 errors were found by the company's own re-check against those records. No number changes. |

## v1.0 (released 2026-09-21) → v1.1 (revised 2026-09-22)

v1.0 remains available under its own version DOI; the concept DOI [10.5281/zenodo.22868613](https://doi.org/10.5281/zenodo.22868613) resolves to the latest version. The corrections below are also printed at the end of the report.

| # | Kind | Where in v1.0 | v1.0 said | Correct |
| --- | --- | --- | --- | --- |
| E1 | Factual error | Abstract · §4 · §5 · KNOWN_LIMITATIONS item 1 · Zenodo description | Four of the eight person-exposure false passes were "motor-start commands issued after an interlock had been removed", a class an observation-based check cannot see | They were motor-start commands issued **while the PLC was halted** (outputs read as 0). Only one of the four plant programs had the interlock removed; all four passed for the same reason. Hazardous commands to a *running* PLC whose interlock was removed (12 rows, 8 person-exposure) were all blocked in run 6 — by the replica's rules or on structural grounds, not by seeing the removal. A scan-counter heartbeat added in v1.1's design revision refuses all 24 commands issued to a halted PLC. |
| E2 | Wrong prediction | §4 | The other four person-exposure rows would close when the rules were rewritten as timer levels ("to be confirmed at zero in run 7") | Measured in runs 10 and 13: they remain (4). The difference is a timer preset changed in the plant program only; the replica judges on its own preset; only a program-signature check can see it, and Modbus exposes none. |
| E3 | Factual error | Abstract · §5 | The permissive evaluated is "a replica value synchronised at least one second earlier" | The replica is synchronised at every judgement. One second is the sampling floor of the equivalence observer, not the age of the judged snapshot. |
| E4 | Superseded | §5, second paragraph | Classes A/B/C of edge-carrying clauses; "an event the PLC does not remember cannot be used in an invariant"; "both stop blocks were class B; the four interlock-removal rows were class A" | The false violations came from window operators (`once`, `held`) whose look-back reached before the synchronisation point, not from edges. Two clauses were rewritten as timer levels (twelve differential tests, including negative controls); a load-time refusal covers such windows; zero committed clauses are refused. |

**Unchanged:** the main finding. Adding the behavioral-equivalence check did not change what the gate lets through — 23 of 280 in both arms in run 6 (v1.0), and 19 of 278 in both arms, identical on every verdict count, in run 13 (v1.1) (p95 latency differs narrowly: 55.3 vs 55.0 ms).

**Qualified:** v1.0's statement that the check "adds cost" (undecidable verdicts under mismatch 5.7% → 7.0%). The whole of that rise was four verdicts on four commands issued to a halted PLC; in run 13 the heartbeat refuses those first and the check has no measurable effect.
