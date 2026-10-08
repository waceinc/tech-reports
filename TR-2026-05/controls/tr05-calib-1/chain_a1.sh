#!/bin/bash
cd <tr-public>/고정입력_TR-05
export PYTHONDONTWRITEBYTECODE=1 TR05_APP=<scratch>/e2/native/build-linux/vexplor_studio_native
R=<runs>/calib-1; V=<repos>/tech-reports/TR-2026-03/variants
C=$(ls -d $R/pc2/_invalid/*/main/M0/*2617252722*)
<scratch>/e2_5/sweep.sh; echo SWEEP-DONE
python3 bridge/refcheck.py --selftest --case $C > $R/refcheck_case.log 2>&1; echo "refcheck-case exit $? :: $(tail -1 $R/refcheck_case.log)"
python3 bridge/tr05.py gate --out $R/gate-a1 > $R/gate-a1.log 2>&1; echo "gate exit $? :: $(grep -c '^\[PASS\]' $R/gate-a1.log) pass lines; fails: $(grep '^\[FAIL\]' $R/gate-a1.log | tr '\n' ';')"
python3 bridge/sources.py | tail -1
python3 bridge/round.py fixed --app $TR05_APP --seed-table seed-table.json --e4-variants $V/TR-03_변종목록_v1.json --e4-sha $V/ladders-sha256.json --out fixed.json | tail -1
mkdir -p $R/pc2-a1
python3 bridge/round.py run --dev --stages main --only cell-b:correct:normal --seed-table seed-table.json --fixed fixed.json --app $TR05_APP --out $R/pc2-a1/round > $R/pc2-a1/round.log 2>&1; echo "pc2 exit $? :: $(tail -1 $R/pc2-a1/round.log)"
python3 bridge/tables.py $R/pc2-a1/round --out $R/pc2-a1/tables.json | tail -1
python3 bridge/public.py build $R/pc2-a1/round --out $R/pc2-a1/public --fixed fixed.json --seed-table seed-table.json --names <scratch>/e2_5/private-names.txt | tail -1
python3 bridge/recompute.py $R/pc2-a1/public --tables $R/pc2-a1/tables.json --out $R/pc2-a1/recompute.json | tail -1
python3 bridge/recompute.py $R/pc2-a1/public --tables $R/pc2-a1/public/tables.json | tail -1
python3 bridge/patent_check.py --tool $HOME/e5-work/patent/patent_scan.py --prereg ../TR-2026-05_사전등록_v0.6.md --bundle $R/pc2-a1/public --out $R/patent_check_v06.json > $R/patent.log 2>&1; cat $R/patent.log
python3 bridge/patent_check.py --tool $HOME/e5-work/patent/patent_scan.py --prereg ../TR-2026-05_사전등록_개정1_2026-10-08.md --out $R/patent_check_a1.json | head -1
python3 bridge/round.py fixed --app $TR05_APP --seed-table seed-table.json --e4-variants $V/TR-03_변종목록_v1.json --e4-sha $V/ladders-sha256.json --out $R/fixed-final-check.json | tail -1
sha256sum fixed.json
echo CHAIN-DONE
