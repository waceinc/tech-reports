"""TR-03_분석.py 의 읽기 부품 — 실행 기록(trace.jsonl[.gz])을 한 줄씩 읽어 비교에 필요한 값만 뽑고, 원본 래더를 다시 스캔한다.

계산 규칙은 사전 등록 v0.3 §5 를 따른다. 해석이 필요한 곳은 TR-03_분석_고정기록.md 「결과 전 해석」 번호(I-n)로 표시했다.
파일을 쓰지 않는다. 브리지 reconstruct 는 plc-twin-lab bridge/run.py 에서 불러온다(고치지 않는다).
"""
import gzip, hashlib, json, subprocess, sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
RESCAN_MJS = HERE / 'TR03_분석_재스캔.mjs'
# I-3: 생산 사건 — 브리지 verdict() 가 위험 사건에서 빼는 이름 그대로(run.py 63~64행)
PRODUCTION = ('PART_PACKED', 'REJECT_COLLECTED', 'PACK_PLACED', 'CONTAINER_EXCHANGED', 'PART_COLLECTED')
# 브리지 reconstruct() 가 내는 입력 복원 감사 예외 문구(run.py 16~29행) — 이 문구로 끝난 실행은 §7 무효(입력 복원 감사 실패)
AUDIT_ERRORS = ('factory tick must be 10/50 ms', 'I schema', 'edge time', 'edge tag/value', 'edge not a change',
                'edges do not reconstruct final I')


def canon(v):
    """브리지 transport.canon 과 같은 직렬화."""
    return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def trace_path(run_dir):
    for name in ('trace.jsonl.gz', 'trace.jsonl'):
        if (run_dir / name).is_file():
            return run_dir / name
    return None


def iter_trace(path):
    """(원본 바이트 sha256 누적기, 줄 객체) 를 차례로 낸다. gzip 이면 풀어서 원본 바이트로 해시한다."""
    h = hashlib.sha256()
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rb') as f:
        for raw in f:
            h.update(raw)
            if raw.strip():
                yield h, json.loads(raw)
    yield h, None


def final_state(state):
    """I-2: 「최종 상태」 = 마지막 틱 공장 상태의 부품 결과(부품별 분류·경로)와 포장 부품 결과(단계·사유). 연속량(위치·속도)은 넣지 않는다."""
    parts = sorted(({k: p[k] for k in ('id', 'class', 'route') if k in p} for p in state.get('parts', [])), key=canon)
    pack = state.get('pack') or {}
    packed = sorted(({k: p[k] for k in ('id', 'stage', 'reason') if k in p} for p in pack.get('parts', [])), key=canon)
    return hashlib.sha256(canon(dict(parts=parts, pack=packed))).hexdigest()


def extract(run_dir, on_row=None):
    """실행 1 건을 한 번 읽어 비교 값만 남긴다. on_row(row) 가 있으면 틱 행마다 부른다(재스캔용)."""
    path = trace_path(run_dir)
    if path is None:
        return dict(error='trace 없음')
    q, ev, first, judg, meta, summary, last = [], Counter(), {}, Counter(), None, None, None
    for h, obj in iter_trace(path):
        if obj is None:
            break
        if obj.get('type') == 'metadata':
            meta = obj
        elif obj.get('type') == 'tick':
            q.append(hashlib.sha256(canon(obj['Q'])).digest())
            for e in obj['events']:
                ev[e['name']] += 1
                first.setdefault(e['name'], obj['tick'])
            for j in obj['judgments']:
                judg[j['name']] += 1
            last = obj
            if on_row:
                on_row(obj)
        elif obj.get('type') == 'summary':
            summary = obj
    if last is None or summary is None:
        return dict(error='trace 에 틱 행 또는 summary 없음', trace_sha256=h.hexdigest())
    sub = {k: summary[k]['status'] for k in ('recovery', 'safety', 'hmi') if isinstance(summary.get(k), dict)}
    return dict(trace_sha256=h.hexdigest(), trace_file=path.name, ticks=len(q), q=q,
                events=dict(ev), hazard={k: v for k, v in ev.items() if k not in PRODUCTION},
                production={k: v for k, v in ev.items() if k in PRODUCTION}, first_tick=first, judgments=dict(judg),
                status=summary['status'], sub_status=sub, completed=summary.get('completed'),
                summary_trace_hash=summary.get('trace_hash'), final_state=final_state(last['state']),
                last_state_hash=last['state_hash'], meta_scenario=(meta or {}).get('scenario'))


def compare(base, var):
    """사전 등록 §5 2~4단계(실행 1 건 수준). 반환 level: '2'(Q 같음) · '3' · '4a' · '4b' + 시각 열."""
    q_same = base['ticks'] == var['ticks'] and base['q'] == var['q']
    q_first = next((i + 1 for i, (a, b) in enumerate(zip(base['q'], var['q'])) if a != b), None)
    if q_first is None and base['ticks'] != var['ticks']:
        q_first = min(base['ticks'], var['ticks']) + 1
    phys_same = base['events'] == var['events'] and base['final_state'] == var['final_state']
    judg_same = (base['judgments'] == var['judgments'] and base['status'] == var['status']
                 and base['sub_status'] == var['sub_status'])
    level = '4a' if not phys_same else '4b' if not judg_same else '3' if not q_same else '2'
    common = set(base['first_tick']) & set(var['first_tick'])
    shift = {n: var['first_tick'][n] - base['first_tick'][n] for n in sorted(common) if var['first_tick'][n] != base['first_tick'][n]}
    return dict(level=level, q_same=q_same, q_first_diff_tick=q_first,
                hazard_diff=base['hazard'] != var['hazard'], production_or_final_diff=(base['production'] != var['production']
                                                                                     or base['final_state'] != var['final_state']),
                judgment_diff=base['judgments'] != var['judgments'], status_diff=base['status'] != var['status'] or base['sub_status'] != var['sub_status'],
                event_first_tick_shift=shift, strict_state_hash_same=base['last_state_hash'] == var['last_state_hash'],
                anomaly_q_same_but_diff=q_same and level != '2')


class Rescan:
    """원본 래더 재스캔(§5 1단계). 틱 행을 받아 브리지 reconstruct 로 스캔 입력을 만들고, 기록된 스캔 digest·Q 와 대조한다."""

    def __init__(self, lab, ladder, tags):
        sys.path.insert(0, str(lab / 'bridge'))
        from run import reconstruct  # noqa: E402  (브리지 원본, 고치지 않음)
        self.reconstruct, self.tags = reconstruct, tags
        self.p = subprocess.Popen(['node', str(RESCAN_MJS), str(lab / 'bridge/engine.mjs'), str(ladder), json.dumps(tags, ensure_ascii=False)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8')
        hello = json.loads(self.p.stdout.readline())
        assert hello['ok'] and hello['tags'] == len(tags)
        self.prev = None
        self.blocked_scans = {t: Counter() for t in tags}  # 태그별 스캔 끝 값 0/1 개수
        self.first_value_tick = {t: {} for t in tags}
        self.checks = Counter()

    def row(self, r):
        if self.prev is not None and r['I_start'] != self.prev:
            self.checks['I_start_chain_breaks'] += 1
        self.prev = r['I']
        try:
            images = self.reconstruct(r['I_start'], dict(dt_s=r['dt_s'], edges=r['edges'], I=r['I']))
        except Exception:
            self.checks['reconstruct_exceptions'] += 1
            return
        self.p.stdin.write(json.dumps(dict(inputs=images), ensure_ascii=False) + '\n')
        self.p.stdin.flush()
        scans = json.loads(self.p.stdout.readline())['scans']
        self.checks['scans'] += len(scans)
        if len(scans) != len(r['scans']):
            self.checks['scan_count_mismatch'] += 1
        for mine, rec in zip(scans, r['scans']):
            self.checks['digest_mismatch'] += mine['digest'] != rec['digest']
            self.checks['q_mismatch'] += mine['Q'] != rec['Q']
            self.checks['image_q_mismatch'] += not mine['img_q_ok']
            for t, v in zip(self.tags, mine['v']):
                self.blocked_scans[t][v] += 1
                self.first_value_tick[t].setdefault(v, r['tick'])

    def close(self):
        self.p.stdin.write('{"cmd":"quit"}\n')
        self.p.stdin.close()
        self.p.wait(timeout=60)
        c = self.checks
        ok = all(c[k] == 0 for k in ('I_start_chain_breaks', 'reconstruct_exceptions', 'scan_count_mismatch', 'digest_mismatch',
                                     'q_mismatch', 'image_q_mismatch')) and c['scans'] > 0 and self.p.returncode == 0
        return dict(ok=ok, checks={k: c[k] for k in sorted(c)}, node_exit=self.p.returncode,
                    values={t: {k: self.blocked_scans[t][k] for k in ('0', '1')} for t in self.tags},
                    first_value_tick=self.first_value_tick)


def blocked(values, mode):
    """스캔 끝에서 조건이 차단인 스캔 수. NO 는 태그 0 일 때, NC 는 태그 1 일 때 차단."""
    return values['0'] if mode == 'NO' else values['1']
