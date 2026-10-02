"""TR-2026-04 G3 client: local open-weight model through a llama-server on localhost (runs inside isolate.py --net local).

Sends TASK.md, the specification files, the appendix, io.json, base.ldprog.json (fill-in tasks) and, on a repair round,
the previous output with the error text, then writes the first complete JSON object of the reply to --out.
Sampling is fixed here (Qwen3-Coder recommended values except temperature and seed, which are arguments).
"""
import argparse, json, urllib.request
from pathlib import Path

SAMPLING = {'top_p': 0.8, 'top_k': 20, 'repeat_penalty': 1.05, 'max_tokens': 131072}
SYSTEM = 'You are a PLC programmer. Reply with the content of the requested JSON file only, no explanation, no code fences.'


def files_text(out_rel):
    parts = []
    for rel in ['TASK.md'] + sorted(str(p) for p in Path('spec').glob('*.md')) + ['appendix.md', 'io.json', 'base.ldprog.json']:
        p = Path(rel)
        if p.exists():
            parts.append(f'=== {rel} ===\n{p.read_text(encoding="utf-8")}')
    prev = Path(out_rel)
    if prev.exists():
        parts.append(f'=== {out_rel} (your previous output) ===\n{prev.read_text(encoding="utf-8")}')
    return '\n\n'.join(parts)


def first_json(text):
    start = text.find('{')
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)) if start >= 0 else []:
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', required=True)
    ap.add_argument('--prompt-file', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--temperature', type=float, required=True)
    ap.add_argument('--seed', type=int, required=True)
    a = ap.parse_args()
    instruction = Path(a.prompt_file).read_text(encoding='utf-8')
    body = {'messages': [{'role': 'system', 'content': SYSTEM},
                         {'role': 'user', 'content': instruction + '\n\n' + files_text(a.out) + f'\n\n=== 만들 파일 ===\n{a.out}'}],
            'temperature': a.temperature, 'seed': a.seed, **SAMPLING}
    req = urllib.request.Request(a.url.rstrip('/') + '/v1/chat/completions', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    reply = json.loads(urllib.request.urlopen(req, timeout=7200).read())
    text = reply['choices'][0]['message']['content']
    Path(a.out).parent.mkdir(exist_ok=True)
    Path(a.out).write_text(first_json(text), encoding='utf-8')
    Path('g3_reply_meta.json').write_text(json.dumps({'model': reply.get('model'), 'usage': reply.get('usage'),
                                                      'finish_reason': reply['choices'][0].get('finish_reason'),
                                                      'sampling': {**SAMPLING, 'temperature': a.temperature, 'seed': a.seed}}, indent=1))


if __name__ == '__main__':
    main()
