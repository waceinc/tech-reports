# TR-2026-08 release bundle - MANIFEST

WACE Technical Report TR-2026-08. Experiment E5: AI decision support on top of a PLC (T1 lockout cause, T2 recovery step, T3 maintenance level, T4 alarm priority), official set, verdict split test_seen + test_unseen, threshold split val; 20,013 items (10,387 in the verdict split). Simulation only, 0 physical comparisons.

The pre-registration SHA-256 was recorded before the run in a private repository only (commit `7650685`, 2026-10-06 13:53:45 KST); the decision to publish was made on 2026-10-08, after the results were known (report Section 7).

## Public scope

Released: the frozen pre-registration v0.3 (byte-identical), its fixed inputs (`fixed/`, byte-identical), the public per-item results (items, rule predictions, M1 probabilities per permutation), the official scorer output, the independent check and the report-table script with their outputs, the evidence records of the official data set (independent re-run, full ladder replay, generation determinism, pre-registration hash record, rule-table record), and the earlier pre-registration versions v0.1 and v0.2 (`fixed/history/`, byte-identical, design history only).

Repository copy and Zenodo record: `results/m1_perms.jsonl.gz` is over 5 MB and is in the Zenodo record only. Without it `scripts/check.py` runs in repository mode (rule side only, M1 parts marked NOT_RUN, output `results/check_output_repo.json`); with it, in full mode (`results/check_output.json`). See README.md for what each mode recomputes.

Not released: the model input texts (PLC record texts; each item carries the SHA-256 of its text), the simulated data set and its generator, the PLC programs, the item builder, the rule-baseline code and the M1 runner (private repository), the model weights (public upstream; only commit and GGUF SHA-256 are given), run logs. The pre-registration names the company's private repository, commits and internal paths; they are not accessible.

## Search for sensitive strings

All files and the decompressed content of every `.gz` were searched for local absolute paths, cloud-sync folder names, an internal host name, a private account name, e-mail addresses other than bangdk@wace.me and token-like strings. No match. The raw compressed bytes of the three `.gz` files contain random e-mail-like and `~/`-like byte sequences (not text). Home-relative paths (`~/`) appear in the byte-identical `fixed/e5/m1/model.json` and `fixed/tools/e5_score.py` (model and llama.cpp locations) and in the pre-registration v0.3 and its earlier versions v0.1 and v0.2 (`fixed/history/`), which also name private repository and working-folder names; these files are kept byte-identical. A positive control was caught by the same search.

## Reproduce

Run from this folder (Python 3.10+ with numpy):

```
python3 scripts/check.py --out /tmp/check_output.json && cmp /tmp/check_output.json results/check_output.json
python3 scripts/tables.py --out /tmp/tables.json && cmp /tmp/tables.json results/tables.json
# repository copy (without results/m1_perms.jsonl.gz):
python3 scripts/check.py --out /tmp/check_output_repo.json && cmp /tmp/check_output_repo.json results/check_output_repo.json
```

## Files

| File | Licence | Bytes | sha256 | Notes |
| --- | --- | --- | --- | --- |
| `LICENSES/CC-BY-4.0.txt` | CC BY 4.0 | 18,657 | `9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411` | CC BY 4.0 licence text (everything else). |
| `LICENSES/MIT.txt` | CC BY 4.0 | 1,091 | `63cc5a767e0477f40ff06276be84c82852a7a183d8d53dd7bde845b2dd5cf367` | MIT licence text (code). |
| `README.md` | CC BY 4.0 | 15,231 | `dd6c51b69882aa90f84f7acbead1391cbd197121edd1c8ac2b31fef6ccdaf5ab` | Bundle guide (English). |
| `fixed/E5_사전등록_v0.3_2026-10-06.md` | CC BY 4.0 | 35,761 | `35b4e315a3e0f6f2279df408fd58905884722d002899a32236c0b5b446d2fe91` | Frozen pre-registration v0.3 (Korean), byte-identical. |
| `fixed/e5/catalog/calibration.json` | CC BY 4.0 | 5,785 | `bbf700d10c15bf02d28bbaa1eec31d681449bfbb2ac57b501b89d8c30a1222cb` | Calibration (section 12 hash). |
| `fixed/e5/catalog/cause_classes.json` | CC BY 4.0 | 4,886 | `1e0779642ecc1becb875f91d9c437d15f6e6071cf799a8fbaeefde0d61639650` | Cause classes (section 12 hash). |
| `fixed/e5/catalog/degradation.json` | CC BY 4.0 | 3,808 | `44e002a66a5375596cb90600b3514714c1c9e37da07c6b6d4e270d47a5bbe4b4` | Wear (degradation) catalogue (section 12 hash). |
| `fixed/e5/catalog/faults.json` | CC BY 4.0 | 18,086 | `7a3202d501c52715cdb71aebcbe1437771d70e9741d04b36b3917fe2f1f06a15` | Fault catalogue (section 12 hash). |
| `fixed/e5/catalog/holdout.json` | CC BY 4.0 | 56,358 | `a0717ca126b7e30df65ef56756c881703be36e1978309cc9b140c804779b1c2c` | Held-out combinations = test_unseen (section 12 hash). |
| `fixed/e5/catalog/sets/official.json` | CC BY 4.0 | 1,535 | `5373e8d61201aa267f139205121c635c774117070d09b967c4e668a2a1955c09` | Official set settings (section 12 hash). |
| `fixed/e5/m1/judge.json` | CC BY 4.0 | 911 | `9d092fcbae5ab7996afdfa27e3f65b9baa0f9cfb0fe0e3aeb263c923f6c30d64` | Decision constants of sections 6-8 (section 12 hash). |
| `fixed/e5/m1/model.json` | CC BY 4.0 | 1,860 | `09067c8f9073ba92849e76fc22e11afb3cfaedd260a919b5404f223371ed48e4` | Model record: Qwen/Qwen3.5-4B commit, llama.cpp commit, GGUF SHA-256, request (section 12 hash). |
| `fixed/e5/m1/prompts.json` | CC BY 4.0 | 18,403 | `747feecb36b512e02a2aefc4771ae2cff1d1a004388f31d172114e6a6d0ac559` | Instructions, choices and the five permutations (section 12 hash). |
| `fixed/e5/m1/rules_r1.json` | CC BY 4.0 | 1,942 | `e49982292aee74aa8b217273a2c4b60d01891f4323b6b5ae5aafcbe5eeeab6e0` | R1 table rebuilt from the official train split (section 12-③; hash = rule-table record). |
| `fixed/e5/m1/rules_t1_full.json` | CC BY 4.0 | 3,421 | `785ca015ab0e2d556de01d4fcd97ebe179d83e5e57f3e0180a912f0772446f74` | R0-full table rebuilt from the official train split (section 12-③; hash = rule-table record). |
| `fixed/e5/m1/rules_t1_masked.json` | CC BY 4.0 | 3,657 | `f8d3ce73c45e13ff42e1739592fa47a90d74ad63db8a95877e9c7f1810feb0f7` | R0-masked table rebuilt from the official train split (section 12-③; hash = rule-table record). |
| `fixed/e5/m1/rules_t3.json` | CC BY 4.0 | 1,564 | `2d69df57e15a2d47ed6d7b1374a4772866c2772261352718cb6c56df89208538` | R0-T3 rule parameters (section 12 hash; equals the rule-table record). |
| `fixed/e5/t4/priority_table.json` | CC BY 4.0 | 33,592 | `eb4c5af3bb70e0a2e1cbe400f8a8438e01da310171683171c9dbf1ca5891e6fd` | T4 alarm priority table (section 12 hash). |
| `fixed/history/E5_사전등록_v0.1_2026-10-02.md` | CC BY 4.0 | 26,356 | `258c147fe03db3b86ea2b6dc7dee19c064ca7dff9be395076709a95f262e16d4` | Pre-registration v0.1 (Korean), byte-identical; design history only, not a fixed input. |
| `fixed/history/E5_사전등록_v0.2_2026-10-06.md` | CC BY 4.0 | 25,373 | `d96cfb2c41a4997d13c9eebcdb7b5cd41f71c4d8b9cb2273b4e5c96cc3e06f0a` | Pre-registration v0.2 (Korean), byte-identical; design history only, not a fixed input. |
| `fixed/tools/e5_score.py` | MIT | 40,675 | `f7544721cb990604da32eb018bfe5f718962588de9929a99fa413cdb5e0e1ca2` | Official scorer as run (pre-registration section 12); reference only — the check does not use it. |
| `results/check_output.json` | CC BY 4.0 | 79,029 | `20216bf7bd88ee566120ab0f0f4282cdee6d02ebf0032a5819b2e97d0a21a900` | Output of scripts/check.py on the public files: 0 differences from score.json. |
| `results/check_output_repo.json` | CC BY 4.0 | 41,470 | `1ca42ec9009c7174e8d92db0dee98578e22154026f6c33903fc008d0228cff34` | Output of scripts/check.py in repository mode (without m1_perms.jsonl.gz): rule side recomputed, M1 parts NOT_RUN, 0 differences from score.json. |
| `results/evidence/official_determinism.json` | CC BY 4.0 | 671 | `24ef8e68f40df3dcecd7ca2595fb00f44a661ae81c70a1ab401c35e16b44061e` | Official set generated twice on the same machine (127,453 files). First comparison: 124,428 files differed, only in the git commit inside the tool-version string of each file header. Generation-1 windows rebuilt at the same commit without re-simulation; second comparison byte-identical. Counted as one retry of the same cause (report Section 6). Byte-identical to the original (SHA-256 `24ef8e68f40df3dcecd7ca2595fb00f44a661ae81c70a1ab401c35e16b44061e`). |
| `results/evidence/official_ladder_full.json` | CC BY 4.0 | 549,431 | `6f2a5fce47659e933a17878be6582cea941083e68cd25f8cb67d00c988dcddc7` | Full ladder replay of every official run (cell B 2,131, packing 504): first mismatch 0, positive control detected. Byte-identical to the original (SHA-256 `6f2a5fce47659e933a17878be6582cea941083e68cd25f8cb67d00c988dcddc7`). |
| `results/evidence/official_verify.json` | CC BY 4.0 | 94,574 | `0b1dbab3dfd2cdff6b22afd22b6263548d8041b90218ff383601cd961179a4e8` | Independent re-run of 60 official runs / 361 windows against the labels: 0 mismatches, positive control detected. Byte-identical to the original (SHA-256 `0b1dbab3dfd2cdff6b22afd22b6263548d8041b90218ff383601cd961179a4e8`). |
| `results/evidence/preregistration.json` | CC BY 4.0 | 501 | `929e7915fd7b3cf6f37b3ff1b9f668e159b2bc01a37c3212abe73ea43e3c7679` | Hash record of the frozen pre-registration v0.3 (fixed-input commit). Byte-identical to the original (SHA-256 `929e7915fd7b3cf6f37b3ff1b9f668e159b2bc01a37c3212abe73ea43e3c7679`). |
| `results/evidence/rules_record_official.json` | CC BY 4.0 | 863 | `4c21e9e9a7cd6fcbac5f9cbb7b89c00add9102f37bd5b5aa94e148091a9a1afc` | Rule-table record (official train, before test). Public version: the one absolute path made relative; original SHA-256 `c47a2387ea107b1590064680c45faa82083b8e69324c138f6bed45dd90595c75` (900 bytes). |
| `results/items.jsonl.gz` | CC BY 4.0 | 1,545,054 | `02edbaf6a62f212d863484a9f1127f85fe515bde8d7e898c887672d5827ee185` | Public item file, 20,013 items, all splits; no record text (its SHA-256 per item instead). Uncompressed 21,557,513 bytes, SHA-256 `5f15252f01830aca2ac50311f6dda5f2eb4c84c9dae5fab931a9671735abca39`; gzip -9, mtime 0, no file name. |
| `results/m1_perms.jsonl.gz` | CC BY 4.0 | 9,202,294 | `af1fecd51b0df18ff7fdbbc6caf47df2c28eb5b5f00742fa2c9897c1cb1fdf5f` | M1 per (item, permutation), 94,542 lines; probabilities in the original choice order, validity flags. Uncompressed 36,472,039 bytes, SHA-256 `6206194f355f5e28eb6805a08dc54d5eb6f60388841b1021934bbed66cc17be7`; gzip -9, mtime 0, no file name. **Over 5 MB: in the Zenodo record only, not in the repository.** |
| `results/provenance.json` | CC BY 4.0 | 5,469 | `ee76b48c93a6a01d2897edb9354573873a24c70f500eedbc59c02ee699fad982` | Original result files SHA-256 and size; M1 run header, rule metadata, rule-table record (paths replaced). |
| `results/rules_pred.jsonl.gz` | CC BY 4.0 | 246,466 | `1e31d33585e547570aaf4f7d5662c0f5320a9fa2c685dde8690661887d3c551d` | Rule predictions R0-full / R0-masked / R0-T3 / R0 (T2, T4) / R1 — the official file, byte-identical inside the gzip. Uncompressed 6,161,359 bytes, SHA-256 `58fe9f7871d447841c63c82df31ae31bb40766913fcf9856b02325d6808528d2`; gzip -9, mtime 0, no file name. |
| `results/score.json` | CC BY 4.0 | 2,410,912 | `de6e4e0d3d288604771e67d1b1cb091fc59c9d91d58057e62d4623ee3583c1da` | Official scorer output (byte-identical). |
| `results/score.md` | CC BY 4.0 | 3,436 | `584c3e3d65d7eb87f7dd23ea6ec0a396ef38b855d64fe0bcf62c230e50766932` | Official scorer summary (byte-identical). |
| `results/tables.json` | CC BY 4.0 | 56,903 | `92671e1159baeee0bc784572b51633db03ef1ad1cdc86a8ebf66312ee6cba0b8` | Report table numbers from scripts/tables.py (full mode). |
| `results/truncation.jsonl` | CC BY 4.0 | 109,436 | `489355353aad0a0b2d8cd705e85c43a1f2a37916c64ce0c87a393676de0fa6a3` | T3 truncation record of the official run (byte-identical). |
| `scripts/check.py` | MIT | 34,610 | `73a6eb4712d593a62fe2190b182d0da128b707c37540a5ebba18258066a3535f` | Independent check of every verdict, numerator, denominator and interval (stdlib + numpy). |
| `scripts/tables.py` | MIT | 11,826 | `a4f9e9fee8bb773b8fe20034547dea604722f853bbcc830232da1f4e6d8b0e93` | Report tables (some pre-registered, some exploratory, as marked in the report). |

Total 38 files, 14,711,897 bytes (without this MANIFEST).

Licences: code (`.py`) MIT; everything else CC BY 4.0. Hash-fixed files carry no licence notice inside; this table declares it. No patent licence is granted (see README.md).
