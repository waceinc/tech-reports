# TR-2026-07 release bundle - MANIFEST

WACE Technical Report TR-2026-07 (v1.0, 2026-10-07). This folder is `TR-2026-07/` of the repository github.com/waceinc/tech-reports and is also the content of the Zenodo record's release bundle. Round tr07-official-1: 20 authorings of one simulated lab x 4 dispatch rules, 150 s each, plus the determinism repeats of authoring 1 (84 runs).

## Public scope

Released: the frozen pre-registration v1.0 (byte-identical), the five hash-fixed files of its section 9 (`fixed/`, byte-identical), the public version of the round (`results/`, written by `fixed/TR-07_public.py`), Figure 1 and its script.

Not released: the application and its physics and dispatch source; the authored projects and the vehicle shape files (redistribution rights not confirmed); the raw run diagnostics and logs, which contain simulator model identifiers and local paths (kept by the company with a SHA-256 list of all 499 raw files); the private model map `TR-07_기종대응표_비공개.json` (SHA-256 `d2e9d84a03dca1c98092c561d4c8a8a5fb6889ac329f35b501c4574456f2a869`, in the pre-registration). The pre-registration names the company's private repository, branches and internal paths; they are not accessible.

Hand redaction after conversion: in `results/layout_public.json`, field `note`, the two vehicle display names were replaced by `V2 / V3`. Nothing else was changed by hand. The developer notes `jobsNote` and `standbyNote` describe an earlier layout (x = ±5 and waiting positions at x = 5); they were kept as in the fixed layout file, and the coordinates in the data (sites at x = ±3.5, waiting positions at x = 6) are authoritative.

## Search for sensitive strings

All files were searched for the simulator's vehicle model identifiers and display names, local absolute paths, local machine and account names, cloud-sync folder names and private repository folder names. Remaining hits, all disclosed: the pre-registration (hash-fixed) names the private repository, its branches and internal paths; the scripts and `results/layout_public.json` contain the company's own product and file names (for example `vexplor`, `factory.vexplor`, the lab's Korean name). No vehicle model identifier or display name, local path or account name remains.

## Reproduce

Run from this folder (Python 3; matplotlib only for the figure):

```
python3 fixed/TR-07_tables.py results --json /tmp/tables.json && cmp /tmp/tables.json results/tables.json
python3 fixed/TR-07_recompute.py results results/tables.json                 # MATCH
sha256sum preregistration/TR-2026-07_사전등록_v1.0.md                         # compare with ../PREREGISTRATIONS.md
python3 scripts/figure1.py results/tables.json /tmp/figure1.png              # visually identical, not byte-identical
```

The rule names in the files are `return`, `predictive` (= rebalance), `lookahead` and `charge`.

## Files

| File | Licence | Bytes | sha256 | Notes |
| --- | --- | --- | --- | --- |
| `figures/figure1.png` | CC BY 4.0 | 107,572 | `3e6ef37f4db4d79bf605dbad6d89140397f5c9a5402bd86891fb5951eaa11aae` | Figure 1, drawn by scripts/figure1.py from results/tables.json. |
| `fixed/TR-07_fixed.json` | CC BY 4.0 | 455 | `adaf3dfe048d5fabb475aded119bd3ec5709b850e76d2028055b27fdcd2fb950` | Pre-registered SHA-256 of the layout file and the four scripts; the runner refuses to start on a mismatch (hash-fixed). |
| `fixed/TR-07_public.py` | MIT | 5,553 | `1269bbea9ce8d5f77beadddb4f6b2136c162a2903ccf99589f8ed9d4c45dc3f6` | Public-version converter (hash-fixed). |
| `fixed/TR-07_recompute.py` | MIT | 7,803 | `bb99b3069046dc85d108f194cfeb1f825132a695f4e77abc381ccf3bcd8caf1a` | Independent recompute: rebuilds every verdict from the raw files or from results/runs/ without reading results.jsonl (hash-fixed). |
| `fixed/TR-07_run.py` | MIT | 15,439 | `94e576f0d210109a00ecbf14372e80a2f0ebe6fd7c97fcb9ff3e0a5981e8b0f7` | Official runner as run (hash-fixed); needs the unreleased application. |
| `fixed/TR-07_tables.py` | MIT | 9,090 | `836fd1d72c7c64d3bf3104d2f617dc8279fa2989fafbf1018754f4a556a4e362` | Tables and pre-registered verdicts from results.jsonl and run.json (hash-fixed). |
| `preregistration/TR-2026-07_사전등록_v1.0.md` | CC BY 4.0 | 26,901 | `7755f5eb15ca2816d971fb8f97132f5d2a926eb54b1a2b74f25c24d5d8888815` | Frozen pre-registration (Korean); SHA-256 equals the value committed in PREREGISTRATIONS.md (commit bbd88eb) before the official round. |
| `results/layout_public.json` | CC BY 4.0 | 7,972 | `13451c8394d3a335ee9b2e3bc2c968c592360f7dbefda49d78f664c0cab8629c` | The fixed layout file with vehicle model identifiers replaced by V1 to V3 by the converter; one developer note redacted by hand (see Public scope). |
| `results/recompute_output.txt` | CC BY 4.0 | 66 | `098ea1ec0142991635474e4bfe974ce7b725050f397bb7a736ad40ac1b6cb8c5` | Output of the independent recompute on the public files (MATCH). |
| `results/results.jsonl` | CC BY 4.0 | 98,778 | `9500a3b50993135482d9afc8497d18b28a133492770371134fdfa28a3730e153` | One row per counted run (84), public version: vehicle identifiers as V1-1 style labels, folders relative. |
| `results/run.json` | CC BY 4.0 | 5,957 | `d8cc4584c8ec543de7d78abe604609f3abc3d2e8737294dbb3f07574f8e911e1` | Round ledger: product commit, SHA-256 of the executable and fixed inputs, authoring events with canonical SHA-256. |
| `results/tables.json` | CC BY 4.0 | 22,192 | `d98d7a66f385d431afefd1fc8388202e38e1b4e3a12127204534729e54bbbd7f` | Tables and verdicts from fixed/TR-07_tables.py on the official round. |
| `scripts/figure1.py` | MIT | 1,683 | `9b5c3bc5882692c9075480b5336262a9aea7ff91970e89c52944894756f48fe9` | Figure 1 (needs matplotlib; not pre-registered). |
| `results/runs/*.json` (84 files) | CC BY 4.0 | 46,008 | `c66079417efa0cd039ee317692e224273bbde50352f75ccd67264985581ad7f4` | Per-run values read from the raw files of the counting attempt, for the independent recompute. The sha256 is over the `sha256sum`-style list of the 84 files sorted by path (listed below). |

### results/runs/

| File | Bytes | sha256 |
| --- | --- | --- |
| `results/runs/a01_charge_run1.json` | 511 | `cb58226153d7e019f0228a75dbaa32699160465e7b9b8489807a6d19c99cd9f7` |
| `results/runs/a01_charge_run2.json` | 511 | `cb58226153d7e019f0228a75dbaa32699160465e7b9b8489807a6d19c99cd9f7` |
| `results/runs/a01_lookahead_run1.json` | 516 | `d767bf73e2ca46e1e7398a225fc15531158dd7f5f8df99326567a91fd88b6273` |
| `results/runs/a01_lookahead_run2.json` | 516 | `d767bf73e2ca46e1e7398a225fc15531158dd7f5f8df99326567a91fd88b6273` |
| `results/runs/a01_predictive_run1.json` | 516 | `d767bf73e2ca46e1e7398a225fc15531158dd7f5f8df99326567a91fd88b6273` |
| `results/runs/a01_predictive_run2.json` | 516 | `d767bf73e2ca46e1e7398a225fc15531158dd7f5f8df99326567a91fd88b6273` |
| `results/runs/a01_return_run1.json` | 551 | `6e198eabf955e79c3e9512e1d896cd9a022b7f0ced636c3a1556c90e645578f5` |
| `results/runs/a01_return_run2.json` | 551 | `6e198eabf955e79c3e9512e1d896cd9a022b7f0ced636c3a1556c90e645578f5` |
| `results/runs/a02_charge_run1.json` | 533 | `b467ceabca47ade1ff1ec949f0014aacf9d0eabde1374780b3523fd1ea852159` |
| `results/runs/a02_lookahead_run1.json` | 536 | `a98e18ad99efbfa58bc6b01a68fa6ed2062b0bac54e19c0bad4ec3a7995bc5f2` |
| `results/runs/a02_predictive_run1.json` | 536 | `a98e18ad99efbfa58bc6b01a68fa6ed2062b0bac54e19c0bad4ec3a7995bc5f2` |
| `results/runs/a02_return_run1.json` | 534 | `3c996f13b1b8d16c9d4233eb144587edd3f35709f04aabaa4618c64bada61a30` |
| `results/runs/a03_charge_run1.json` | 554 | `e20396812314e6fec64fe4c3a430cda3601f06b41ea20413ea4a01d9d4b8e0da` |
| `results/runs/a03_lookahead_run1.json` | 572 | `8e7e6c3e12823cb0b7410f3cb4f925e721964a4aac9d6c531193509f01ec442c` |
| `results/runs/a03_predictive_run1.json` | 572 | `8e7e6c3e12823cb0b7410f3cb4f925e721964a4aac9d6c531193509f01ec442c` |
| `results/runs/a03_return_run1.json` | 572 | `2febb301e9a375f4176290030cf849a18f06b0ba1be74942cb4e686bf23f04d4` |
| `results/runs/a04_charge_run1.json` | 555 | `dca28f2cff21b4fb211ed1a5aec6ba29f448eafbe57f5959d50386f5e9f2adfc` |
| `results/runs/a04_lookahead_run1.json` | 587 | `4b86a865f4ed46f420a6144b61b74a8c3ef14c3beb8ea7910c759c72288e620c` |
| `results/runs/a04_predictive_run1.json` | 587 | `4b86a865f4ed46f420a6144b61b74a8c3ef14c3beb8ea7910c759c72288e620c` |
| `results/runs/a04_return_run1.json` | 514 | `46f73313de34780f4cf0367749736682dbfd0a69b4ffb2cb784a48040e8c71a2` |
| `results/runs/a05_charge_run1.json` | 553 | `4fa1d6dd82e1631a65a11f9b336da1c3f39c46d5a0f01b467e2103f9cd48b0b8` |
| `results/runs/a05_lookahead_run1.json` | 553 | `a743e0690359e8ecf19bcc6ec172dba427f5a165d33c56c766097a159df60b40` |
| `results/runs/a05_predictive_run1.json` | 535 | `b0b961aa0f3b3bf412bdddf2111e7936108ac920558a97adbd218734cb8202f9` |
| `results/runs/a05_return_run1.json` | 515 | `f667999ffda2ac924fe8974c600434a95e03512ae72100fdf9185857ff14212e` |
| `results/runs/a06_charge_run1.json` | 555 | `81c477ccdf493dd2c1e509ff1198ade85a0fb8c110ca7a570ef286aae2380b95` |
| `results/runs/a06_lookahead_run1.json` | 574 | `dac6fd1266df8bb361528c9f07d8dfd0b7524f48ccd4f9c8b4d3ea3ed164b6f6` |
| `results/runs/a06_predictive_run1.json` | 573 | `4e8ed934751cc81106f47f728192f7cd1fc9693c1953b02de05fa7b07030b7f7` |
| `results/runs/a06_return_run1.json` | 574 | `7217c0a3fc5b29e5cf975d71475bb1811439bec69e4ad15d6dbc21b21a796cf9` |
| `results/runs/a07_charge_run1.json` | 535 | `6e2b5041e77da47c0befa67dc36f3c8cec66395fbf4042ae59ae9c901c4abe68` |
| `results/runs/a07_lookahead_run1.json` | 573 | `d029bb780657eca22905d41d2ed1f1bd4341522b7c85adeb39d0ae79e3159d43` |
| `results/runs/a07_predictive_run1.json` | 554 | `31a0da3d8308975cb22a46a5392f4905703b97377798a2ebbedbc2a33703d9c3` |
| `results/runs/a07_return_run1.json` | 536 | `747300ebfa929f0a28586c1e662aee827bfc432288de8e56c453fb22bddda8c4` |
| `results/runs/a08_charge_run1.json` | 531 | `19708a114abad1c53fb11ce8934840ce5b379d9f36708f4721709cc280a11f02` |
| `results/runs/a08_lookahead_run1.json` | 531 | `47f3b9f6fffba68c367d93b76e31f17ababbafc90b8374a854e40413e72d01ff` |
| `results/runs/a08_predictive_run1.json` | 531 | `47f3b9f6fffba68c367d93b76e31f17ababbafc90b8374a854e40413e72d01ff` |
| `results/runs/a08_return_run1.json` | 569 | `b62895460850290a3683b6f3f0a0532bde4b267805479eaa26610c0cdba1b5cd` |
| `results/runs/a09_charge_run1.json` | 535 | `d7672e0829f975ce101fa094e193cb88b7986199bbf6fe9f43c54aaed63bd55d` |
| `results/runs/a09_lookahead_run1.json` | 591 | `c3bd7a05e12ac52dbbee25838ea94d367572a88f875acf579c0695c4c82c172b` |
| `results/runs/a09_predictive_run1.json` | 550 | `40193859cf0738c5c97648ed74de803571b2dc4746b4de2dbf0dc05badd29d70` |
| `results/runs/a09_return_run1.json` | 553 | `f16ce531451cc325cac5edc2d706283309f47f2c2e2070865aa533c5aa5b2b26` |
| `results/runs/a10_charge_run1.json` | 512 | `50a2b5c1b0887515e1fe1388bfc7dacc941a92fe8d33d8c2cf9021c84bdcd159` |
| `results/runs/a10_lookahead_run1.json` | 532 | `a122cc7352cbc30890e9f74979ad3010bbb42762f0f5edbb1c5058771ddf225e` |
| `results/runs/a10_predictive_run1.json` | 532 | `a122cc7352cbc30890e9f74979ad3010bbb42762f0f5edbb1c5058771ddf225e` |
| `results/runs/a10_return_run1.json` | 536 | `747300ebfa929f0a28586c1e662aee827bfc432288de8e56c453fb22bddda8c4` |
| `results/runs/a11_charge_run1.json` | 532 | `27ec1b6571fa09c66d41d60e91803f207c08f8673034fbb69b36da5cec600dab` |
| `results/runs/a11_lookahead_run1.json` | 553 | `6e0e9703b618618045a95a6cda533cdf0c18fa53454a1307b4751f61a0cd7a58` |
| `results/runs/a11_predictive_run1.json` | 553 | `6e0e9703b618618045a95a6cda533cdf0c18fa53454a1307b4751f61a0cd7a58` |
| `results/runs/a11_return_run1.json` | 551 | `b64625bc2097a9ad3dbf93983bb7b005dc1cd7ad6f17a9c645fdf49f73823746` |
| `results/runs/a12_charge_run1.json` | 534 | `2380cfd1602a2da974a23d2f450e31a99087c99c8473ceea40ab9048e195c1b7` |
| `results/runs/a12_lookahead_run1.json` | 587 | `4b86a865f4ed46f420a6144b61b74a8c3ef14c3beb8ea7910c759c72288e620c` |
| `results/runs/a12_predictive_run1.json` | 587 | `4b86a865f4ed46f420a6144b61b74a8c3ef14c3beb8ea7910c759c72288e620c` |
| `results/runs/a12_return_run1.json` | 514 | `46f73313de34780f4cf0367749736682dbfd0a69b4ffb2cb784a48040e8c71a2` |
| `results/runs/a13_charge_run1.json` | 574 | `3e9bd48a00748d1764dbba895255716695b09417983d9e39d71c9a7cd905ce95` |
| `results/runs/a13_lookahead_run1.json` | 590 | `7b05ada7ccc176ce12b0a4b3096448769f74b03e1bf73af1e50249d6323637a3` |
| `results/runs/a13_predictive_run1.json` | 553 | `d9d863f2531069ebdf072270adefe374d911178aa2edebe2267a1ae8f5e43a76` |
| `results/runs/a13_return_run1.json` | 553 | `751999acf92f1657c310aa49048f1f0ce61001e6a55043dac6d903d5429ba068` |
| `results/runs/a14_charge_run1.json` | 513 | `84bfebadab2bbe07e43bd66f730c88d5d7b7c006b4d635369d931987cb629e1d` |
| `results/runs/a14_lookahead_run1.json` | 551 | `d1241445208e8c35d17ea86ba511c75edb42062c125dba3327b46c686a22dca0` |
| `results/runs/a14_predictive_run1.json` | 551 | `d1241445208e8c35d17ea86ba511c75edb42062c125dba3327b46c686a22dca0` |
| `results/runs/a14_return_run1.json` | 512 | `99fd7bd676180d5f7d2a8f67d3580140cf0ecf5f0ef345eccb47384ac4daf4cc` |
| `results/runs/a15_charge_run1.json` | 554 | `704d59f6fea8b51ed6feb955c3b8b6e5f7f9a6b1b489e3198ec4443df68d5397` |
| `results/runs/a15_lookahead_run1.json` | 534 | `b2401bbd001b872c648e3e71d1c59dce27014b3a78b394713900bb4116039e0e` |
| `results/runs/a15_predictive_run1.json` | 534 | `b2401bbd001b872c648e3e71d1c59dce27014b3a78b394713900bb4116039e0e` |
| `results/runs/a15_return_run1.json` | 551 | `ef55e49546ea5a345cce1bb1be4ad0853570da19d5c0a01d587000a0cba242fa` |
| `results/runs/a16_charge_run1.json` | 530 | `a1714a571b13abed36c7a81c1d903d7008fc30569dd8e862f5edc7aee4b88b66` |
| `results/runs/a16_lookahead_run1.json` | 531 | `47f3b9f6fffba68c367d93b76e31f17ababbafc90b8374a854e40413e72d01ff` |
| `results/runs/a16_predictive_run1.json` | 531 | `47f3b9f6fffba68c367d93b76e31f17ababbafc90b8374a854e40413e72d01ff` |
| `results/runs/a16_return_run1.json` | 571 | `a6b3a9270a51ab4ad469e2cfbcfa3f2f50985cd605f61a91ce38f1a9c7829dd6` |
| `results/runs/a17_charge_run1.json` | 574 | `3e9bd48a00748d1764dbba895255716695b09417983d9e39d71c9a7cd905ce95` |
| `results/runs/a17_lookahead_run1.json` | 590 | `7b05ada7ccc176ce12b0a4b3096448769f74b03e1bf73af1e50249d6323637a3` |
| `results/runs/a17_predictive_run1.json` | 553 | `d9d863f2531069ebdf072270adefe374d911178aa2edebe2267a1ae8f5e43a76` |
| `results/runs/a17_return_run1.json` | 553 | `751999acf92f1657c310aa49048f1f0ce61001e6a55043dac6d903d5429ba068` |
| `results/runs/a18_charge_run1.json` | 512 | `dc1abf62a3f6b8dcaae50f24453e4a36d0fb9d64236268985a87ab1acfac217e` |
| `results/runs/a18_lookahead_run1.json` | 536 | `a98e18ad99efbfa58bc6b01a68fa6ed2062b0bac54e19c0bad4ec3a7995bc5f2` |
| `results/runs/a18_predictive_run1.json` | 536 | `a98e18ad99efbfa58bc6b01a68fa6ed2062b0bac54e19c0bad4ec3a7995bc5f2` |
| `results/runs/a18_return_run1.json` | 534 | `3c996f13b1b8d16c9d4233eb144587edd3f35709f04aabaa4618c64bada61a30` |
| `results/runs/a19_charge_run1.json` | 573 | `763af17eeaa3476c0957c4fb5390f154f9fccccd51bed46b49f95c01ba1a80e1` |
| `results/runs/a19_lookahead_run1.json` | 590 | `52c6f4f5814cda2ca41f3fa9d882c0ef0de1f0be9305d04b1d06632fbc4c58b3` |
| `results/runs/a19_predictive_run1.json` | 590 | `52c6f4f5814cda2ca41f3fa9d882c0ef0de1f0be9305d04b1d06632fbc4c58b3` |
| `results/runs/a19_return_run1.json` | 534 | `bf2b76f86b36aae92f06df381387ab42a307566f650f0094c436230c88f71982` |
| `results/runs/a20_charge_run1.json` | 555 | `ac8035f0b4d26127eb79bde0955967c3f418591f6f90d3a3386fbdc2b064d6e9` |
| `results/runs/a20_lookahead_run1.json` | 594 | `7d37a8cde8789e857f7c9249c4c3f57b0f57baccece826eed0ded1a5b55e2bac` |
| `results/runs/a20_predictive_run1.json` | 554 | `94345da02fee469d8b71638959e249915d8d8db2a93557f0412d8f8c89bb0d52` |
| `results/runs/a20_return_run1.json` | 513 | `25d870ac23e2bca5dee6cee04161719d68e59bf15f48d08f308b7c35b25b3fbe` |

Licences: code (`.py`) MIT, Copyright (c) 2026 WACE Inc. (주식회사 웨이스); everything else CC BY 4.0. This release does not grant any licence under patents of WACE Inc., including Korean patents No. 10-2904772 and No. 10-3003470, or under any pending or future patent application of WACE Inc. No patent will be filed on the dispatch rules described in Section 3.1 (the return, rebalance and lookahead rules and the charge variant); this report serves as their disclosure. This bundle names no vehicle manufacturer or vehicle product.
