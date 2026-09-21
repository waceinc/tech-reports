# WACE Technical Reports

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22868613.svg)](https://doi.org/10.5281/zenodo.22868613)

Technical reports published by WACE Inc. (주식회사 웨이스), Hwaseong, Republic of Korea — maker of VEXPLOR, a manufacturing AI operating system.

| Report | Title | Files | Status |
| --- | --- | --- | --- |
| **TR-2026-01** | Behavioral Equivalence Cannot See Dormant Logic: A Pre-Registered Negative Result from a Five-Arm Comparison of PLC Command Gates on a Simulated PLC | [PDF](TR-2026-01.pdf) · [Markdown](TR-2026-01.md) · [Errata](ERRATA.md) · [concept DOI 10.5281/zenodo.22868613](https://doi.org/10.5281/zenodo.22868613) | **v1.1 — revised 2026-09-22** (corrects two factual errors of v1.0; see [ERRATA.md](ERRATA.md)), version DOI [10.5281/zenodo.22884024](https://doi.org/10.5281/zenodo.22884024). v1.0 (2026-09-21) remains archived under [10.5281/zenodo.22868614](https://doi.org/10.5281/zenodo.22868614); the concept DOI resolves to the latest version |

## TR-2026-01 in one paragraph

A command gate that pre-executes supervisory writes on a replica of the PLC program is a known approach. We asked whether adding a behavioral-equivalence check (confirming from observed transitions that the replica still matches the plant) reduces hazardous false passes. In a pre-registered five-arm comparison on a simulated PLC (three self-authored ladders, 869 labelled commands, thirteen official attempts with every commit and record published), the arm with the check and the arm without it let through exactly the same hazardous commands issued while the replica was stale — 23 of 280 before a design revision and 19 of 278 after it, identical on every verdict count (p95 latency differs narrowly). The four person-exposure false passes that remain are writes made while a timer preset had been changed in the plant program only: a dormant program difference that produces no behaviour until the timer runs, so no observation-based check sees it. A static program-signature check has to come before any behavioral check; on protocols without a program signature (Modbus) the gate cannot see this class of change. Results are from a simulated PLC on one machine; no physical PLC comparison is included.

> **Correction (v1.1, 2026-09-22).** v1.0 said four person-exposure false passes were motor-start commands issued after an interlock had been removed. They were commands issued while the PLC was halted; a scan-counter heartbeat now refuses all such commands. v1.0 also predicted that the other four would close by rewriting two rules; they did not. Full list: [ERRATA.md](ERRATA.md).

## What this report is and is not

- It is a **defensive publication** of an experiment and its evaluation discipline. It is not peer-reviewed.
- It does **not** claim field validation, exclusivity, or that the gate makes a plant safe. Known limitations are listed in [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) and in Section 8 of the report.
- The gate's source code and raw result files are **not** part of this repository. Release of the code is a separate decision; the numbers in the report are reproducible from the result files named in it (v1.1: run 13, commit `8327000`, results committed at `b56177d`; v1.0: run 6, commit `3e7351b`, adopted at `65528cc`).

## Citation

See [CITATION.cff](CITATION.cff).

> Bang, D. (2026). *Behavioral Equivalence Cannot See Dormant Logic: A Pre-Registered Negative Result from a Five-Arm Comparison of PLC Command Gates on a Simulated PLC* (Version 1.1). WACE Technical Report TR-2026-01. Zenodo. https://doi.org/10.5281/zenodo.22884024 (version 1.1; all versions: https://doi.org/10.5281/zenodo.22868613)

## License

Report text and figures: Creative Commons Attribution 4.0 International (CC BY 4.0) — see [LICENSE](LICENSE). (Licence fixed by the CEO on 2026-09-21.)

## Contact

Dongkeol Bang, CEO, WACE Inc. — bangdk@wace.me · https://wace.me
