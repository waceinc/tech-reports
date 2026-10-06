#!/usr/bin/env python3
"""TR-2026-07 public version (pre-registration sections 10 and 12).

Writes to a new folder only what a reader needs and nothing the round folder must keep private:
- results.jsonl, run.json, tables.json with absolute paths removed and vehicle identifiers replaced by labels;
- runs/a??_<rule>_run?.json: per run, the values the independent recompute needs, read from the raw files
  (exit.json, result.json, diag.json) of the counting attempt;
- layout_public.json: the fixed layout with simulator model identifiers replaced by V1, V2, V3.
Not copied: authored projects, vehicle shape files, diagnostics, logs. The private map's sha256 is printed.
usage: TR-07_public.py <round dir> <public dir> --map <private map.json> --layout <layout.json>
The map is {"labels": {"<model id>": "V1", ...}, "salt": "<64 random hex>"}; the salt makes the map's hash unguessable.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
from pathlib import Path

UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
RULES = ('return', 'predictive', 'lookahead', 'charge')


def compact_run(folder):
    attempts = sorted(glob.glob(os.path.join(folder, 'attempt*')))
    last = attempts[-1]
    exit_code = json.loads(Path(last, 'exit.json').read_text(encoding='utf-8'))['exit']
    measured = all(os.path.exists(os.path.join(last, f)) for f in ('result.json', 'diag.json', 'run.log'))
    out = {'exit': exit_code, 'measured': measured, 'attempts': len(attempts)}
    if measured:
        result = json.loads(Path(last, 'result.json').read_text(encoding='utf-8'))
        samples = json.loads(Path(last, 'diag.json').read_text(encoding='utf-8')).get('samples', [])
        project = json.loads(Path(folder).parent.joinpath('project', 'factory.vexplor').read_text(encoding='utf-8'))
        low = next((a['sceneId'] for a in project['amrs'] if (a['profile'].get('battery') or {}).get('initialSoc') == 0.2), None)
        fleet = result.get('fleet') or {}
        out.update({'state': result.get('state'), 'error': result.get('error'), 'completedTransfers': result.get('completedTransfers'),
                    'emptyTravelMeters': fleet.get('emptyTravelMeters', 0), 'completionTimes': fleet.get('completionTimes', []),
                    'amrPeerContactCount': result.get('amrPeerContactCount'),
                    'lowBatteryDockedSamples': sum(1 for s in samples for v in s.get('runtime', {}).get('vehicles', [])
                                                   if v.get('chargeDocked') and v.get('amrId') == low),
                    'doubleChargerReservations': sum(1 for s in samples if len([v['charger'] for v in s.get('runtime', {}).get('vehicles', []) if v.get('charger')])
                                                     != len({v['charger'] for v in s.get('runtime', {}).get('vehicles', []) if v.get('charger')}))})
    return out


def vehicle_labels(round_dir, labels):
    """Vehicle identifier -> 'V1-1' style label (model label + start order), per authoring."""
    names = {}
    for project_path in sorted(glob.glob(os.path.join(round_dir, 'a??', 'author', 'fleet-control-lab', 'factory.vexplor'))):
        project = json.loads(Path(project_path).read_text(encoding='utf-8'))
        count = {}
        for amr in project['amrs']:
            label = labels[amr['modelId']]
            count[label] = count.get(label, 0) + 1
            names[amr['sceneId']] = f'{label}-{count[label]}'
    return names


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('round', type=Path)
    parser.add_argument('public', type=Path)
    parser.add_argument('--map', required=True, type=Path)
    parser.add_argument('--layout', required=True, type=Path)
    args = parser.parse_args()
    labels = json.loads(args.map.read_text(encoding='utf-8'))['labels']
    args.public.mkdir(parents=True)
    names = vehicle_labels(args.round, labels)
    rename = lambda text: UUID.sub(lambda m: names.get(m.group(0), m.group(0)), text)
    root = str(args.round.resolve())
    for name in ('results.jsonl', 'run.json', 'tables.json'):
        text = (args.round / name).read_text(encoding='utf-8').replace(root + '/', '').replace(root, '.')
        (args.public / name).write_text(rename(text), encoding='utf-8')
    (args.public / 'runs').mkdir()
    for folder in sorted(glob.glob(os.path.join(args.round, 'a??', '*', 'run?'))):
        parts = Path(folder).parts
        k, rule, run = parts[-3], parts[-2], parts[-1]
        if rule in RULES:
            text = json.dumps(compact_run(folder), ensure_ascii=False, sort_keys=True)
            (args.public / 'runs' / f'{k}_{rule}_{run}.json').write_text(rename(text) + '\n', encoding='utf-8')
    layout = json.loads(args.layout.read_text(encoding='utf-8'))
    for vehicle in layout['fleet']:
        vehicle['model'] = labels[vehicle['model']]
    (args.public / 'layout_public.json').write_text(json.dumps(layout, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    text = '\n'.join(Path(p).read_text(encoding='utf-8') for p in glob.glob(os.path.join(args.public, '**', '*.json*'), recursive=True))
    leaked = [model for model in labels if model in text] + ([root] if root in text else []) + \
             sorted({m.group(0) for m in UUID.finditer(text) if m.group(0) in names})
    print(f"TR07_PUBLIC out={args.public} mapSha256={hashlib.sha256(args.map.read_bytes()).hexdigest()} leaked={leaked}")
    return 0 if not leaked else 1


if __name__ == '__main__':
    sys.exit(main())
