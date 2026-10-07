# TR-2026-08 release bundle — E5: AI decision support on top of a PLC

WACE Technical Report TR-2026-08. This bundle holds the per-item results of experiment E5, the fixed inputs and the
frozen pre-registration it was judged against, and an independent check that recomputes every verdict, numerator and
denominator from the public files alone.

**Pre-registration and publication.** The pre-registration's SHA-256 was recorded before the run in a private repository
only (commit `7650685`, 2026-10-06 13:53:45 KST), not in a public one, and the decision to publish was made on 2026-10-08,
after the results were known (report Section 7). A reader can compare the released pre-registration with its hash but
cannot verify from a third-party record that it was fixed before the results.

**Simulation only — 0 physical comparisons.** The plant model, the injected faults, the wear and the operator are all
simulated and the physical values are assumptions. Nothing here was compared with a real plant.

## What E5 asked

A PLC keeps all control and safety decisions. On top of it, a read-only decision model looks at the event and I/O record
before a lockout and recommends: T1 the cause category of the lockout, T2 the next recovery step, T3 the maintenance level
(normal / observe / maintenance needed) from a 300 s wear window, T4 which simultaneous alarm to handle first. The
question is which tasks a rule baseline (R0) already answers to the pre-registered line, and whether a small general
language model (M1: Qwen 3.5 4B, first-letter probabilities, no training) adds anything. The verdict lines, sample-size
conditions and definitions are in the pre-registration v0.3 sections 6–8 (`fixed/E5_사전등록_v0.3_2026-10-06.md`, in
Korean, byte-identical; SHA-256 `35b4e315a3e0f6f2279df408fd58905884722d002899a32236c0b5b446d2fe91`).

Verdict split: test_seen + test_unseen (test_unseen is also reported separately). Threshold split: val.

| Task | Verdict (score.json and the independent check agree) |
| --- | --- |
| T1 lockout cause, cell B items R0-full left unresolved | both below the line (`둘 다 미달`) — R0-full 90/165, composite C 40/165, C − R0 = −50/165 |
| T2 recovery step (consistency check) | [PASS] — R0 7,323/7,323, 0 dangerous wrong answers |
| T4 alarm priority (consistency check) | [PASS] — R0 1,374/1,383, 0 dangerous wrong answers |
| T3 maintenance needed (per run) | rule enough (`규칙으로 충분`) — R0-T3 recall 51/53, false alarms 0/108 |

## Layout

| Path | Content |
| --- | --- |
| `results/items.jsonl.gz` | One line per item (20,013; all four splits): `item_id`, `task`, `split`, `cell`, `combo_key`, `run_id`, `window_id`, `family`, `answer`, `answer_index`, `choices`; T2 `current_step`, `next_step`, `path`; T3 `lead_s` (seconds to the next PLC warning or lockout, null = none until the end of the run), `channels`, `maint_channels`, `metric` (per-channel wear level); T4 `order`, `grades`; `input_sha256` (SHA-256 of the record text the model read, after any truncation), `dropped_lines` (oldest body lines removed to fit 120,000 tokens), `truncated` (`dropped_lines` > 0), `body_lines` (T3 only; record body lines **before** truncation, from `truncation.jsonl`). There is no separate field for the lines kept: the model and R0-T3 read `body_lines − dropped_lines` lines. The record text itself is not included (size). |
| `results/rules_pred.jsonl.gz` | Rule predictions, byte-identical to the official file (gzip only): T1 `r0_full` (R0-full, with `determined` = rule-resolved and the candidate categories), `r0_masked` (R0-masked), `r1` (R1 majority); T2/T4 `r0` (with `fallback` = R1 used), `r1`; T3 `r0_t3` (with the rule's `dropped_lines` and `record_sha256`), `r1`. |
| `results/m1_perms.jsonl.gz` | **Zenodo record only (over 5 MB; not in the repository copy).** M1, one line per (item, permutation) (94,542): `perm_index`, `perm`, `probs` (renormalised choice-letter probabilities **in the original choice order**), `missing`, `no_letter`, `error`, `valid`, `letter_mass`, `top_token`, `dropped_lines`, `prompt_tokens`. |
| `results/truncation.jsonl` | Byte-identical: one line per T3 item with `body_lines` (body lines before truncation), `dropped_lines` (oldest lines removed; 0 if none) and `prompt_tokens` after truncation. |
| `results/score.json` · `results/score.md` | Byte-identical output of the official scorer. |
| `results/provenance.json` | SHA-256 and size of every original result file, the M1 run header, the rule-prediction metadata and the rule-table record (local paths replaced by `<home>` / `<repo>`). |
| `results/check_output.json` | Output of `scripts/check.py` in full mode (with `m1_perms.jsonl.gz`). |
| `results/check_output_repo.json` | Output of `scripts/check.py` in repository mode (without `m1_perms.jsonl.gz`). |
| `results/evidence/` | Evidence on the official data set, from the private repository's evidence folder: `official_verify.json` (independent re-run of 60 runs / 361 windows against the labels, 0 mismatches, positive control detected), `official_ladder_full.json` (full ladder replay of every run, cell B 2,131 and packaging cell 504, first mismatch 0, positive control detected), `official_determinism.json` (two generations on the same machine, 127,453 files: the first comparison differed in 124,428 files, only in the git commit inside the tool-version string of each file header; the generation-1 windows were rebuilt at the same commit without re-simulation; the second comparison was byte-identical; counted as one retry of the same cause — report Section 6), `preregistration.json` (hash record of the frozen pre-registration), `rules_record_official.json` (rule-table record; its one absolute path was made relative). Original SHA-256 values are in `MANIFEST.md`. The data set, programs and runs they refer to are not released. |
| `results/tables.json` | Report table numbers from `scripts/tables.py` (some pre-registered, some exploratory, as marked in the report). |
| `scripts/check.py` | Independent check (see below). |
| `scripts/tables.py` | Report tables: verdict table, T1 detail, T2/T4, T3 detail, M1-alone reference, test_unseen separately. |
| `fixed/` | Fixed inputs, byte-identical: `e5/m1/*.json` (judge constants, model record, prompts and permutations, rule tables), `e5/catalog/` (cause classes, faults, degradation, calibration, held-out combinations, official set settings), `e5/t4/priority_table.json`, `tools/e5_score.py` (the official scorer, for reference — the check does not use it), and the pre-registration v0.3. `fixed/history/`: the earlier pre-registration versions v0.1 (2026-10-02) and v0.2 (2026-10-06), byte-identical, for the design history only — they are not fixed inputs of the run and were superseded by v0.3 before any official data existed. |
| `LICENSES/` | MIT and CC BY 4.0 texts. |
| `MANIFEST.md` | SHA-256, size and licence of every file. |

## Recompute

Python 3.10+ and numpy (the published output was made with Python 3.12.3 and numpy 2.5.3). From this folder:

```
# full mode (Zenodo release bundle, with results/m1_perms.jsonl.gz)
python3 scripts/check.py --out /tmp/check_output.json && cmp /tmp/check_output.json results/check_output.json
python3 scripts/tables.py --out /tmp/tables.json && cmp /tmp/tables.json results/tables.json
# repository mode (repository copy, without results/m1_perms.jsonl.gz)
python3 scripts/check.py --out /tmp/check_output_repo.json && cmp /tmp/check_output_repo.json results/check_output_repo.json
```

The mode is chosen by whether `results/m1_perms.jsonl.gz` is present. Both modes exit with code 0.

| What is recomputed | Full mode (Zenodo bundle) | Repository mode (repository copy) |
| --- | --- | --- |
| Fixed inputs and pre-registration hash | yes | yes |
| T1: R0-full, R1, R0-masked accuracy (rule-unresolved and all cell B items), R0-full accuracy on rule-resolved items, R0-full risk-category TP/FN/FP and R0-full confusion tables, item and key counts | yes | yes |
| T1: M1 alone and composite C accuracy, C − R0 and its interval, M1/C risk categories and confusion, **T1 verdict** | yes | `[NOT_RUN(m1_perms 없음)]` (a T1 verdict of "withheld" for too few items would still be given) |
| T2 and T4: R0 accuracy, dangerous wrong answers, R1 fallback, per-cell counts, **[PASS]/[FAIL] verdicts** | yes | yes |
| T2 and T4: M1 alone (reference) accuracy and dangerous wrong answers | yes | `[NOT_RUN(m1_perms 없음)]` |
| T3: windows, run units, R0-T3 recall, false-alarm rate, channel recalls, level accuracy, early alarms (R0-T3), belt-only runs, rule/model truncation cross-check (via the per-item text hash) | yes | yes |
| T3: M1 threshold on val, M1 recall, false-alarm rate and level accuracy, R0 − M1 false-alarm difference; **T3 verdict** | yes | verdict yes when R0-T3 meets its line or the sample is too small (the case here: "rule enough"); otherwise `[NOT_RUN(m1_perms 없음)]`; M1 numbers `[NOT_RUN(m1_perms 없음)]` |
| M1 status (failures, human check, confident wrong answers, quantiles) and the M1 miss list | yes | `[NOT_RUN(m1_perms 없음)]` (only the judged-item and truncated-item counts) |
| test_unseen separately | all of the above | the rule-side part |
| `scripts/tables.py` (report tables) | yes | not run (prints a note, exit 0) |

In both modes every number that is computed is compared with `results/score.json`; fields marked NOT_RUN are counted
and listed, not compared.

`scripts/check.py` reads only `results/` and `fixed/`. It was written separately from the official scorer and does not
import or read it. It

1. checks the pre-registration hash and every file in `fixed/` against the SHA-256 table of pre-registration section 12;
2. recomputes M1 per item (mean over the valid permutations, first-in-original-order argmax, "human check" when the top
   choice changes between permutations, failures and partial failures);
3. recomputes the four verdicts of section 8 with exact fractions: T1 accuracy on the rule-unresolved items
   (R0-full, R1, M1 alone, composite C, R0-masked), C − R0 with its 95 % interval, R0-full accuracy on rule-resolved
   items, the four risk categories (TP/FN/FP for C, R0-full, M1) and the confusion tables; T2 and T4 R0 accuracy and
   dangerous wrong answers (the allowed recovery steps are read from the item labels themselves); T3 per-run recall and
   false-alarm rate as defined in
   section 7-4 (positive unit = run with at least one "maintenance needed" window, negative unit = run with negative
   windows only, early alarms counted apart), the M1 threshold chosen on val, the channel recalls, the belt-only runs the
   PLC never flags, and the rule/model truncation cross-check; the M1 status counts (human check, confident wrong answers at
   p ≥ 0.9); everything again for test_unseen alone;
4. compares every number it computes with `results/score.json` and writes the result under `comparison_with_score_json`.

95 % intervals: cluster bootstrap, 10,000 resamples, percentiles 2.5/97.5, clusters = combination key (T1, T2, T4) or run
(T3); proportions of 0 or 1 use the exact Clopper–Pearson interval. The seed string is the pre-registered
`e5-score-boot-v1`; each interval's stream is `numpy.random.default_rng` seeded with the first 8 bytes (big-endian) of
`sha256("e5-score-boot-v1|<metric name>")`, clusters in first-appearance order. This stream convention is the one the
official run used, so the intervals can be compared digit by digit.

Result on these files. Full mode: 1,384 counts, lists and verdicts compared, 0 differences; 562 interval end points and
rates compared, all identical; the M1 miss list (7,938 entries) identical. Repository mode: 531 counts, lists and verdicts
compared, 0 differences; 216 interval end points and rates, all identical; 92 fields NOT_RUN; verdicts T2 [PASS], T4
[PASS], T3 rule enough, T1 NOT_RUN.

### Rule tables and section 12

Three rule tables in `fixed/e5/m1/` (`rules_r1.json`, `rules_t1_full.json`, `rules_t1_masked.json`) do not have the
SHA-256 printed in pre-registration section 12. This is the procedure of section 12-③: the tables are rebuilt from the
**official** train split with the same code and their hashes recorded before the test splits are opened (record
`built_from: ["train"]`, `recorded_at: 2026-10-06T06:54:39+00:00`, in `results/provenance.json` → `rules_record`);
section 12 printed the hashes of the tables that existed when the document was frozen. The check verifies the three files
against that record; `rules_t3.json` (fixed parameters) equals both.

## What a reader can and cannot check

With the Zenodo release bundle (which includes `results/m1_perms.jsonl.gz`), a reader can recompute every verdict,
numerator, denominator and interval in the report; recount the report tables; see each item's label, rule answers and the
model's probabilities for every permutation; check the fixed inputs against the pre-registration. The repository copy
alone does not contain `m1_perms.jsonl.gz`; with it, `scripts/check.py` recomputes the rule side only (table above).
The files in `results/evidence/` are records of checks on the unreleased data set; a reader can read them but not rerun
them.

A reader cannot: re-run the model or the rules on the record texts, which are not included (each item's text SHA-256 is);
regenerate the simulated data set (the generator, the PLC programs and the 127,453-file official set are in a private
repository); confirm that the files came from the stated code. Three windows with no injected fault were dropped when the
items were built (one each in train, val and test_seen) and are not in the item file.

## Model

The model weights are not included. M1 = `Qwen/Qwen3.5-4B` (Apache-2.0), commit `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`,
converted with llama.cpp commit `7049ff0cbeb1f5ead231de4522af6b75d8d773c0` to a BF16 GGUF with SHA-256
`7d9e8d79a81a004e9f5c6725c4f97038b02a80622718d0df647c9afbc79ccc00` (8,665,620,320 bytes). Request: one token, top-100
probabilities, temperature 0. Details in `fixed/e5/m1/model.json`.

## Licence

| Files | Licence |
| --- | --- |
| Code — `scripts/check.py`, `scripts/tables.py`, `fixed/tools/e5_score.py` | MIT — `LICENSES/MIT.txt`, Copyright (c) 2026 WACE Inc. (주식회사 웨이스) |
| Everything else — results, tables, fixed inputs, judgement criteria, the pre-registration, this README and the MANIFEST | CC BY 4.0 — `LICENSES/CC-BY-4.0.txt` |

Files whose hashes are fixed carry no licence notice inside; this table and `MANIFEST.md` declare their licence.

This release does not grant any licence under patents of WACE Inc., including Korean patents No. 10-2904772 and
No. 10-3003470, or under any pending or future patent application of WACE Inc.

Qwen is a model of the Qwen team (Alibaba Cloud); this bundle is not affiliated with them and contains none of their files.
NVIDIA, CUDA and GB10 (named in the pre-registration as the machine used) are trademarks of NVIDIA Corporation; this bundle
is not affiliated with NVIDIA. Other product names (for example Ubuntu, macOS and llama.cpp, named in the pre-registration)
are trademarks of their owners.

## Contact

Dong Gul Bang, WACE Inc. — bangdk@wace.me
