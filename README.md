# WACE Technical Reports

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22868613.svg)](https://doi.org/10.5281/zenodo.22868613)

Technical reports published by WACE Inc. (주식회사 웨이스), Hwaseong, Republic of Korea — maker of VEXPLOR, a manufacturing AI operating system.

| Report | Title | Files | Status |
| --- | --- | --- | --- |
| **TR-2026-01** | Behavioral Equivalence Cannot See Dormant Logic: A Pre-Registered Negative Result from a Five-Arm Comparison of PLC Command Gates on a Simulated PLC | [PDF](TR-2026-01.pdf) · [Markdown](TR-2026-01.md) · [Errata](ERRATA.md) · [concept DOI 10.5281/zenodo.22868613](https://doi.org/10.5281/zenodo.22868613) | **v1.3 — revised 2026-09-25** (the author's name is now given in its passport spelling, Dong Gul Bang; no other change; see [ERRATA.md](ERRATA.md) E6); its version DOI is recorded here once Zenodo mints it. v1.2 (corrects an overstatement, present since v1.0, about what is public; E5) remains archived under [10.5281/zenodo.22884852](https://doi.org/10.5281/zenodo.22884852). v1.1 (corrects two factual errors of v1.0) remains archived under [10.5281/zenodo.22884024](https://doi.org/10.5281/zenodo.22884024). v1.0 (2026-09-21) remains archived under [10.5281/zenodo.22868614](https://doi.org/10.5281/zenodo.22868614); the concept DOI resolves to the latest version |

## TR-2026-01 in one paragraph

A command gate that pre-executes supervisory writes on a replica of the PLC program is a known approach. We asked whether adding a behavioral-equivalence check (confirming from observed transitions that the replica still matches the plant) reduces hazardous false passes. In a pre-registered five-arm comparison on a simulated PLC (three self-authored ladders, 869 labelled commands, thirteen official attempts, every one listed in the run ledger with its outcome), the arm with the check and the arm without it let through exactly the same hazardous commands issued while the replica was stale — 23 of 280 before a design revision and 19 of 278 after it, identical on every verdict count (p95 latency differs narrowly). The four person-exposure false passes that remain are writes made while a timer preset had been changed in the plant program only: a dormant program difference that produces no behaviour until the timer runs, so no observation-based check sees it. A static program-signature check has to come before any behavioral check; on protocols without a program signature (Modbus) the gate cannot see this class of change. Results are from a simulated PLC on one machine; no physical PLC comparison is included.

> **Correction (v1.3, 2026-09-25).** The author's name is now given in its passport spelling, Dong Gul Bang (v1.0–v1.2: Dongkeol Bang). Same person; no other change. See [ERRATA.md](ERRATA.md) E6.
>
> **Correction (v1.2, 2026-09-22).** v1.0 and v1.1 overstated what is public: the result files, row labels and pre-registration are held by the company and are not public; the run ledger lists every attempt. No number changes. See [ERRATA.md](ERRATA.md) E5.
>
> **Correction (v1.1, 2026-09-22).** v1.0 said four person-exposure false passes were motor-start commands issued after an interlock had been removed. They were commands issued while the PLC was halted; a scan-counter heartbeat now refuses all such commands. v1.0 also predicted that the other four would close by rewriting two rules; they did not. Full list: [ERRATA.md](ERRATA.md).

## What this report is and is not

- It is a **defensive publication** of an experiment and its evaluation discipline. It is not peer-reviewed.
- It does **not** claim field validation, exclusivity, or that the gate makes a plant safe. Known limitations are listed in [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) and in Section 8 of the report.
- The gate's source code and raw result files are **not** part of this repository. Release of the code is a separate decision; the numbers in the report are computed from the result files named in it (v1.1: run 13, commit `8327000`, results committed at `b56177d`; v1.0: run 6, commit `3e7351b`, adopted at `65528cc`). Those result files, the row labels and the pre-registration are not public, so readers cannot yet recompute the numbers; releasing them is a separate decision.

## How these reports are published

- **Pre-registration.** The question, the metrics and the acceptance lines are fixed in writing before the official runs. The result is published whichever way it comes out.
- **Every run counts.** Each official attempt gets a number. Invalid and aborted attempts are listed in the report's run ledger with their cause.
- **Corrections.** A correction is published as a new version with its own DOI. [ERRATA.md](ERRATA.md) lists, for each error, what the earlier version said and what is correct. Earlier versions stay archived; the concept DOI always resolves to the latest.
- **What the numbers come from.** Each report names the result files and commits its numbers were computed from, and states whether those files are public.
- **What is not published.** Customer data, customer names or identifiers, and customer drawings. Results that belong to a funding agency under a grant agreement are not published here without that agency's consent.
- **AI tools.** Reports state how generative AI was used in the work. The named author is responsible for the content.

## Citation

See [CITATION.cff](CITATION.cff).

> Bang, D. G. (2026). *Behavioral Equivalence Cannot See Dormant Logic: A Pre-Registered Negative Result from a Five-Arm Comparison of PLC Command Gates on a Simulated PLC* (Version 1.3). WACE Technical Report TR-2026-01. Zenodo. https://doi.org/10.5281/zenodo.22868613 (all versions; resolves to the latest)

## License

Report text and figures: Creative Commons Attribution 4.0 International (CC BY 4.0) — see [LICENSE](LICENSE). (Licence fixed by the CEO on 2026-09-21.)

## Contact

Dong Gul Bang, CEO, WACE Inc. — bangdk@wace.me · https://wace.me
