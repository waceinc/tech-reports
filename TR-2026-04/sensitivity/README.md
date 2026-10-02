# sensitivity (post hoc, not the main metric)

This folder holds a sensitivity analysis added **after the results** (decision K11 of 2026-10-02, `../decisions/TR-2026-04_decisions.md`). It is **not** part of the official round tr04-official-1 and does **not** change the main metric or the verdict on the prediction.

What it is: in 8 G3 units that ended on the 40-minute limit (T07, T08, T10, T12–T16, repetition 1), the G3 client was left running by a harness defect and wrote its answer `out/blank.json` after the unit had ended (these 8 late files are in `../runs/tr04-run-1_generation.tar.xz` with their original modification times). Those answers were never judged in the official round. Here the same fixed code as the official round (`../code/assemble.py`, `static_check.mjs`, `judge_one.py`, called as the generation unit and the runner call them, without repairs) judged them on copies of the unit folders, writing to a separate result folder.

Files

| File | Content |
| --- | --- |
| `TR-04_민감도_늦은답안판정.py` | The script (Korean comments), byte-identical. It reads the official folders only and writes to copies and a separate result folder. It names the private repository and the run folders relative to the home directory. |
| `TR-04_민감도_늦은답안판정_출력_2026-10-02.txt` | Its output. Public version: local paths replaced by placeholders (original SHA-256 in `../MANIFEST.md`). |
| `tr04-sens-late-1.tar.xz` | Judging records of the units that compiled (verdict, static and input-forcing records; per run metadata, summary without `tick_hashes`, processes, static, io_verdict, stderr logs, failure and reference-difference records), the judged ladders as public versions (`program.public.ldprog.json`, the engine `marker` line removed by the pre-registered conversion), and the new assembly and compile records of all 8 copied unit folders (`work/`), with the S1 error of each answer that did not compile in its `compile.json` and, for those 5 answers (T08, T12, T13, T14, T15), the assembled ladder as a public version (`work/<unit>/assembled.public.ldprog.json`, the engine `marker` line removed by the pre-registered conversion). Paths redacted; members keep their modification times. |
| `tr04-sens-late-1_files.tsv` | Per member: public bytes, public and original SHA-256, transform, replaced prefixes. |
| `tr04-sens-late-1_not_released.tsv` | Files left out: the tick traces of the plant-connected runs (cell B), with size and SHA-256. |

Result as recorded in the output: of the 8 late answers, 5 did not compile (S1 [FAIL]); T07-G3-r1 passed (1), failed (2) (3 of 30 tests passed) and failed (3); T10-G3-r1 and T16-G3-r1 compiled but failed (1) and (2) (4 and 2 of 30 tests passed). None passed (1) and (2), so none would have entered either denominator of metric 1. How the report uses this, and the worst-case bound published with it, are stated in the report.
