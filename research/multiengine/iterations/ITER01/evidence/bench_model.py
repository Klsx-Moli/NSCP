import os, sys, json, time, urllib.request

OUT = r"<EVIDENCE_DIR>\2026-11-27_b71fb0c\MODEL_BENCHMARK.json"
MODEL = 'qwen3.5:4b-q4_K_M'


def gen(prompt, ctx, num_predict=32, timeout=280):
    payload = {
        'model': MODEL,
        'prompt': prompt,
        'stream': False,
        'options': {'num_ctx': ctx, 'num_predict': num_predict, 'temperature': 0},
        'keep_alive': '10m',
    }
    req = urllib.request.Request('http://localhost:11434/api/generate',
                                 data=json.dumps(payload).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = json.loads(r.read().decode('utf-8'))
    b['wall_s'] = round(time.time() - t0, 2)
    return b


def metrics(b):
    d = {}
    for k in ('prompt_eval_count', 'eval_count', 'done_reason'):
        d[k] = b.get(k)
    for k in ('load_duration', 'prompt_eval_duration', 'eval_duration', 'total_duration'):
        v = b.get(k)
        d[k + '_s'] = round(v / 1e9, 3) if isinstance(v, (int, float)) else None
    d['wall_s'] = b.get('wall_s')
    ev = b.get('eval_count') or 0
    ed = b.get('eval_duration')
    d['tokens_per_sec'] = round(ev / (ed / 1e9), 2) if ev and ed else None
    d['response_head'] = (b.get('response') or '')[:160]
    d['empty'] = not (b.get('response') or '').strip()
    return d

prompt = ("You are a careful assistant. Important constraint: The operator said 'NEVER push to main' and "
          "'do NOT delete the file <REPO_ROOT>\\keep.txt'. "
          "Reply with exactly the SHA-like token a1b2c3d4 and confirm you will not push.")
results = {'model': MODEL, 'runs': []}
for ctx in (4096, 8192, 16384):
    entry = {'num_ctx': ctx}
    try:
        b = gen(prompt, ctx)
        entry.update(metrics(b))
        entry['status'] = 'ok'
    except Exception as e:
        entry['status'] = 'error'
        entry['error'] = f'{type(e).__name__}: {e}'
    print(json.dumps(entry, ensure_ascii=False), flush=True)
    results['runs'].append(entry)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
print('DONE')
