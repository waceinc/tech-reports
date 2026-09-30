# Pre-registrations

Each entry below is the SHA-256 of a pre-registration document, committed here **before** the official runs of that report. The commit time on this repository is the third-party record that the document existed in this exact form before any official result was produced.

The documents themselves are published together with the report and its result files. A reader can then hash the published document and compare it with the value here. If a pre-registration is later revised, the revision gets a new entry; an existing entry is never edited.

| Report | Working title | Pre-registration file | SHA-256 | Committed |
| --- | --- | --- | --- | --- |
| TR-2026-02 | Scan and plant-tick mismatch: how often sampling plant inputs only at tick boundaries changes the PLC verdict, compared with restoring in-tick history (simulated cell A) | `TR-2026-02_사전등록_v0.3.md` | `5e610e77633369fe5dd001af80451e58a09fe24699a3585065c13712eab217c4` | 2026-09-30 |
| TR-2026-03 | Interlock-removal what-if: which removed interlock conditions show up in a scenario set and which do not (simulated cells, correct ladders with one condition shorted at a time) | `TR-2026-03_사전등록_v0.3.md` | `603635d205233477e6d3d987b639ac363a16edb34805aec150c974aac91d1c1c` | 2026-09-30 |
| TR-2026-04 | Verification methods compared: how often LLM-written PLC ladders that pass static checks and input-forcing tests still fail when connected to a simulated plant (simulated cells, tasks written from requirement specs) | `TR-2026-04_사전등록_v0.4.md` | `668b0a2bf36f89e41be0a7d740a36b73f37d22f12fbffcb65c97e657ad254b01` | 2026-09-30 |
| TR-2026-04 (amendment 1) | Same study. Amendment 1, fixed before any generation: the generator sandbox now also blocks the sibling task folders, one of which held another task's correct rung block; two code files changed | `TR-2026-04_사전등록_개정1_2026-10-01.md` | `5d94d4ef5bbbf3f84e38d8cca998081badbdf7d3a23c8d91dff555e7ba70d85c` | 2026-10-01 |

Notes

- The documents are written in Korean; the hash is over the exact bytes of the UTF-8 file.
- All experiments run on a simulated PLC connected to a simulated plant. No physical PLC comparison is included.
