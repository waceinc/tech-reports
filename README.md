# WACE Technical Reports

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22868613.svg)](https://doi.org/10.5281/zenodo.22868613)

Technical reports published by WACE Inc. (주식회사 웨이스), Hwaseong, Republic of Korea — maker of VEXPLOR, a manufacturing AI operating system.

| Report | Title | Files | Status |
| --- | --- | --- | --- |
| **TR-2026-01** | Behavioral Equivalence Cannot See Dormant Logic: A Pre-Registered Negative Result from a Five-Arm Comparison of PLC Command Gates on a Simulated PLC | [PDF](TR-2026-01.pdf) · [Markdown](TR-2026-01.md) · [DOI 10.5281/zenodo.22868614](https://doi.org/10.5281/zenodo.22868614) | **v1.0 — released 2026-09-21** (archived on Zenodo; concept DOI [10.5281/zenodo.22868613](https://doi.org/10.5281/zenodo.22868613) resolves to the latest version) |

## TR-2026-01 in one paragraph

A command gate that pre-executes supervisory writes on a replica of the PLC program is a known approach. We asked whether adding a behavioral-equivalence check (confirming from observed transitions that the replica still matches the plant) reduces hazardous false passes. In a pre-registered five-arm comparison on a simulated PLC (three self-authored ladders, 869 labelled commands, six official runs with every commit and record published), the arm with the check and the arm without it let through exactly the same 23 of 280 hazardous commands issued while the replica was stale. Four of the eight person-exposure false passes were motor-start commands issued after an interlock had been removed — a dormant logic change moves no tag until the start command arrives, so an observation-based check never enters suspicion. A static program-signature check has to come before any behavioral check; on protocols without a program signature (Modbus) the gate cannot see this class of change. Results are from a simulated PLC on one machine; no physical PLC comparison is included.

## What this report is and is not

- It is a **defensive publication** of an experiment and its evaluation discipline. It is not peer-reviewed.
- It does **not** claim field validation, exclusivity, or that the gate makes a plant safe. Known limitations are listed in [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) and in Section 8 of the report.
- The gate's source code and raw result files are **not** part of this repository. Release of the code is a separate decision; the numbers in the report are reproducible from the result files named in it (commit `3e7351b`, adopted at `65528cc`).

## Citation

See [CITATION.cff](CITATION.cff).

> Bang, D. (2026). *Behavioral Equivalence Cannot See Dormant Logic: A Pre-Registered Negative Result from a Five-Arm Comparison of PLC Command Gates on a Simulated PLC.* WACE Technical Report TR-2026-01. Zenodo. https://doi.org/10.5281/zenodo.22868614

## License

Report text and figures: Creative Commons Attribution 4.0 International (CC BY 4.0) — see [LICENSE](LICENSE). (Licence fixed by the CEO on 2026-09-21.)

## Contact

Dongkeol Bang, CEO, WACE Inc. — bangdk@wace.me · https://wace.me
