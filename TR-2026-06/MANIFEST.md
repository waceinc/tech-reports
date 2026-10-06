# TR-2026-06 release bundle - MANIFEST

WACE Technical Report TR-2026-06 (v1.0, 2026-10-06). This folder is `TR-2026-06/` of the repository github.com/waceinc/tech-reports and is also the content of the Zenodo record's release bundle. Round tr06-official-1: 12 robot-arm models × 60 linear moves × 7 rows (C0 base twice, C0 at half speed, C1, C2, C3, C2z) = 5,040 rows, plus 2,880 E1 joint moves; simulation only, 0 physical comparisons. Every file is below 5 MB and is in the repository as well as in the Zenodo record.

## Public scope

Released: the frozen pre-registration v1.0 (byte-identical), the six hash-fixed files of its section 9 (`fixed/`, byte-identical, in one folder because the independent check's self-test loads the input generator from its own folder), the public version of every result file of the official round, the separate pre-check run, the independent check's output on the public files, the runner source as run, and the scripts and output of the Section 5 tables and Figure 1.

Not released: the original result files, which name the eleven non-ABB models (their SHA-256 values are in `results/run.json` → `original_sha256`); the private model mapping `TR-06_모델대응표_비공개.json` (SHA-256 `222d8e47a6de09341f4f358d3fb5b51228510b00446741a8a004aeef4d3339f4`, also in the pre-registration); the product planner, IK, checker and robot catalogue (decision of 2026-10-02); robot geometry files; the development-run outputs; the working notes and cross-reviews of the pre-registration. Uncompressed public `results.jsonl`: 5,177,769 bytes, SHA-256 `aba523fa2811b75b1d3c935a0508e8543bd7fa7a94f21020e797f0707062b8ba`.

## Search for sensitive strings

All files, the decompressed `results.jsonl.gz` and the PNG text chunk were searched for the eleven internal model names, local absolute paths, the home-relative prefix, the local machine and account names, cloud-sync folder names, private repository folder names, an internal host name and manufacturer names other than ABB. No match, except two bytes equal to the home-relative prefix inside the compressed pixel data of `figures/figure1.png`. A positive control (an internal model name and a local path in a plain file) was found by the same search.

## Reproduce

Run from this folder:

```
mkdir run && cp results/{labels.json,e1.jsonl,summary.json,precheck.json,run.json} run/ && gzip -dc results/results.jsonl.gz > run/results.jsonl
python3 fixed/TR-06_입력생성.py | cmp - fixed/TR-06_입력목록_v2.json
python3 fixed/TR-06_독립검산.py run --inputs fixed/TR-06_입력목록_v2.json --json check_output.json && cmp check_output.json results/check_output.json
python3 scripts/tables.py run fixed/TR-06_입력목록_v2.json tables.json && cmp tables.json results/tables.json
python3 scripts/figure1.py run/results.jsonl fixed/TR-06_입력목록_v2.json figure1.png        # needs matplotlib; pixel-identical with matplotlib 3.11.2
```

## Files

| File | Licence | Bytes | sha256 | Notes |
| --- | --- | --- | --- | --- |
| `figures/figure1.png` | CC BY 4.0 | 91,541 | `277ed4b9ba8608a0225a0fcd0a14f4b81d80858610b5a1b36f30d7c5ec44857d` | Figure 1. |
| `fixed/TR-06_개발입력_전용.json` | CC BY 4.0 | 2,176 | `619014a7bf65a7fbb3ef81158b0637e645461ae90b431a40e0f5b2d6b51e995c` | Development inputs k = 100…109, used only to test the runner (hash-fixed). |
| `fixed/TR-06_결과형식_v1.md` | CC BY 4.0 | 7,609 | `782426ff9512c54de6d6a4edcf390cd45d5f7f30ea5976fc2b5ab72de9329674` | Result-file format shared by the runner, the independent check and the converter (hash-fixed). |
| `fixed/TR-06_공개본변환.py` | MIT | 12,218 | `476f9fe751b45977a7edd4248472d9555b7868db9cbdd16675fa815a9cbbd141` | Public-version converter: models to A–L, B–L masking (hash-fixed). |
| `fixed/TR-06_독립검산.py` | MIT | 33,309 | `4251c03079fc39e6b0892f7d48faa6b10e5f883d8e8b0524c5567038e0eb2721` | Independent check: recomputes every verdict and Section 4 count from raw fields (hash-fixed). |
| `fixed/TR-06_입력목록_v2.json` | CC BY 4.0 | 11,617 | `43da27bf7d0e63d51fedc9341e5555206550f62f73d723f53c832606e0874f8a` | Confirmation input list, 60 moves (hash-fixed; SHA-256 checked by the runner and the independent check). |
| `fixed/TR-06_입력생성.py` | MIT | 5,160 | `3ce85f3f29c170630906b225a2de1581b1ae6cdcc49eed1373e0e24e4fb99546` | Input generator (pre-registration v1.0 section 9; hash-fixed, byte-identical). |
| `precheck/tr06-precheck-1_precheck.json` | CC BY 4.0 | 1,342 | `de2cf270c19183cc3a183b94ab0954f210d81e2e4ac227f331c34909f1bdc79a` | Separate pre-check run of the official executable before the official round. |
| `preregistration/TR-2026-06_사전등록_v1.0.md` | CC BY 4.0 | 40,256 | `09622072fe062a00f2d1b07d2fbc5ada6aeb868d03848419671c5a5064c33b90` | Frozen pre-registration; SHA-256 equals the value committed in PREREGISTRATIONS.md (commit 48d8eda) before the official run. |
| `results/check_output.json` | CC BY 4.0 | 2,695 | `2be4e73de57bbec20bbe2330582bdfa4c390cb288109f3932ea589b0f8c32098` | Independent check output on the public files (gate [PASS]). |
| `results/e1.jsonl` | CC BY 4.0 | 268,915 | `cf74b503522f765e7e43762ca7be9cf6c7030974524eca7e682a07c7c9c64a94` | E1 joint-speed rounding rows, public version (B–L without distance, duration, acceleration). |
| `results/labels.json` | CC BY 4.0 | 183,480 | `08030ef36ea623442f4ae77dc4c84349a0704fcf7867c6214b69301a52b161aa` | Configuration labels, public version (label values only). |
| `results/precheck.json` | CC BY 4.0 | 1,342 | `de2cf270c19183cc3a183b94ab0954f210d81e2e4ac227f331c34909f1bdc79a` | Pre-check block of the official round (byte-identical to the original). |
| `results/results.jsonl.gz` | CC BY 4.0 | 338,754 | `b8b409728dc674b873b6ceb8192652806dca807d6ffc27d5396f241cc420fdbf` | gzip -n -9 of the public results.jsonl (5,177,769 bytes uncompressed; its SHA-256 is under Public scope). |
| `results/run.json` | CC BY 4.0 | 1,095 | `b58157468830763d77397c3703ee1bbdc8447dad5ae426adb3740aa446c74a95` | Run metadata, public version (adds original_sha256 of every original file). |
| `results/summary.json` | CC BY 4.0 | 1,690 | `b002d3816e133444ac19205a0bc100b110f83983e43dae9bfbf80a21ee94fb23` | Runner summary of Section 4 (byte-identical to the original). |
| `results/tables.json` | CC BY 4.0 | 7,815 | `3c356a058f9d133be2eb1e682820516957a902218ff6b03f35ec3b407bcc896d` | Section 5 tables from scripts/tables.py on the public files. |
| `runner/robot_program_tr06.cpp` | MIT | 30,136 | `99272d21db63c6ba978225e45257b8092c18950383ca71106de7884d106a60c4` | Runner as run (vexplor-vision-2 commit d1c4971); calls the unreleased product planner, IK and checker. |
| `scripts/figure1.py` | MIT | 3,011 | `4d7f7fd27889ab09fcc66f75f7dc5048b8b1c530a85bcc9fae6d507a53810eca` | Figure 1 (needs matplotlib). |
| `scripts/tables.py` | MIT | 6,468 | `e92f61e79a90387423e66f233eae760f2106430ce00ef0d3613bbffa67214ac2` | Section 5 tables (not pre-registered). |

Licences: code (`.py`, `.cpp`) MIT; everything else CC BY 4.0. No patent licence is granted. ABB is a trademark of ABB Ltd; this bundle is not affiliated with ABB.
