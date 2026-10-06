# Pre-registrations

Each entry below is the SHA-256 of a pre-registration document, committed here **before** the official runs of that report. The commit time on this repository is the third-party record that the document existed in this exact form before any official result was produced.

The documents themselves are published together with the report and its result files. A reader can then hash the published document and compare it with the value here. If a pre-registration is later revised, the revision gets a new entry; an existing entry is never edited.

| Report | Working title | Pre-registration file | SHA-256 | Committed |
| --- | --- | --- | --- | --- |
| TR-2026-02 | Scan and plant-tick mismatch: how often sampling plant inputs only at tick boundaries changes the PLC verdict, compared with restoring in-tick history (simulated cell A) | `TR-2026-02_사전등록_v0.3.md` | `5e610e77633369fe5dd001af80451e58a09fe24699a3585065c13712eab217c4` | 2026-09-30 |
| TR-2026-03 | Interlock-removal what-if: which removed interlock conditions show up in a scenario set and which do not (simulated cells, correct ladders with one condition shorted at a time) | `TR-2026-03_사전등록_v0.3.md` | `603635d205233477e6d3d987b639ac363a16edb34805aec150c974aac91d1c1c` | 2026-09-30 |
| TR-2026-04 | Verification methods compared: how often LLM-written PLC ladders that pass static checks and input-forcing tests still fail when connected to a simulated plant (simulated cells, tasks written from requirement specs) | `TR-2026-04_사전등록_v0.4.md` | `668b0a2bf36f89e41be0a7d740a36b73f37d22f12fbffcb65c97e657ad254b01` | 2026-09-30 |
| TR-2026-04 (amendment 1) | Same study. Amendment 1, fixed before any generation: the generator sandbox now also blocks the sibling task folders, one of which held another task's correct rung block; two code files changed | `TR-2026-04_사전등록_개정1_2026-10-01.md` | `5d94d4ef5bbbf3f84e38d8cca998081badbdf7d3a23c8d91dff555e7ba70d85c` | 2026-10-01 |
| TR-2026-06 | End-joint mismatch in numerically planned linear robot moves: how often the planned end joint values differ from the taught ones, how often a tool-tip-only check lets them play back, and whether changing the inverse-kinematics initial guess removes them (simulated robot arms, 12 models x 60 linear moves) | `TR-2026-06_사전등록_v1.0.md` | `09622072fe062a00f2d1b07d2fbc5ada6aeb868d03848419671c5a5064c33b90` | 2026-10-06 |
| TR-2026-07 | Dispatch rules in a simulated heterogeneous AMR lab: how much dispatching a finished vehicle from where it unloaded, instead of returning it to its start position, changes empty travel per completed transfer, whether it costs completed transfers, and how much this varies when the same lab is re-authored (simulated lab, 5 vehicles of 3 types, 20 authorings x 4 rules) | `TR-2026-07_사전등록_v1.0.md` | `7755f5eb15ca2816d971fb8f97132f5d2a926eb54b1a2b74f25c24d5d8888815` | 2026-10-06 |

Notes

- The documents are written in Korean; the hash is over the exact bytes of the UTF-8 file.
- TR-2026-02 to TR-2026-04 run on a simulated PLC connected to a simulated plant; no physical PLC comparison is included. TR-2026-06 runs on simulated robot-arm models; no physical robot or controller comparison is included. TR-2026-07 runs in a simulated vehicle lab; no physical vehicle or dispatch-system comparison is included.
