"""Cross-lingual es-en selection probe with gemma3:4b (fence-tolerant offline parse)."""
import json, re, sys, time, urllib.request
from pathlib import Path
E=Path(__file__).parent; W="<ITER03_WORKTREE>"
sys.path.insert(0,W+"/src")
import extractive_context as ex
from local_summary import LocalSummaryConfig
doc=json.loads((E/"PREREGISTERED_CASES.json").read_text(encoding="utf-8"))
subset=[c for c in doc["cases"] if c["lang"]=="es-en"][:6]
real_complete=ex.complete_summary
captured=[]
def measured(messages,config):
    r=real_complete(messages,config); captured.append(r.content); return r
ex.complete_summary=measured
sel=ex.OllamaSpanSelector(LocalSummaryConfig(model="gemma3:4b",num_ctx=4096,num_predict=128,timeout=90))
rows=[]
for c in subset:
    spans=ex.split_spans(c["source"]); pool=ex.candidate_pool(spans,ex.rank_spans(spans,c["query"]))
    t0=time.perf_counter(); raw=None; ids=[]
    try:
        ids=list(sel(c["query"],tuple(pool))); raw=ids
    except Exception as exc:
        rows.append({"case_id":c["id"],"error":f"{type(exc).__name__}: {exc}","seconds":round(time.perf_counter()-t0,3)}); continue
    t=set(c["expected_target_span_ids"]); hits=[i for i in ids if i in t]
    rows.append({"case_id":c["id"],"lang":"es-en","category":c["category"],"selected_ids":ids,
      "offered_ids":[s.id for s in pool],"seconds":round(time.perf_counter()-t0,3),
      "candidate_recall":bool(t & {s.id for s in pool}) if t else None,
      "selection_recall":bool(hits) if t else None,
      "precision":round(len(hits)/len(ids),3) if ids else None,
      "literal_fidelity":any(c["evidence_expected"] and c["evidence_expected"] in spans[i].text for i in ids if 0<=i<len(spans)) if t else None,
      "false_positives":len([i for i in ids if i not in t])})
# Offline parse of fenced model output, then recompute selection metrics.
for idx,r in enumerate(rows):
    if idx >= len(captured): continue
    r.pop("error", None)
    c=subset[idx]; spans=ex.split_spans(c["source"])
    m=re.search(r"\[[^\]]*\]",captured[idx])
    ids=[v for v in (json.loads(m.group(0)) if m else []) if type(v) is int and v in {s.id for s in ex.candidate_pool(spans,ex.rank_spans(spans,c["query"]))}] if m else []
    t=set(c["expected_target_span_ids"]); hits=[i for i in ids if i in t]
    r.update(selected_ids=ids,selection_recall=bool(hits) if t else None,
             precision=round(len(hits)/len(ids),3) if ids else None,
             candidate_recall=bool(t & {s.id for s in ex.candidate_pool(spans,ex.rank_spans(spans,c["query"]))}) if t else None,
             literal_fidelity=any(c["evidence_expected"] and c["evidence_expected"] in spans[i].text for i in ids if 0<=i<len(spans)) if t else None,
             false_positives=len([i for i in ids if i not in t]),raw_json_valid=False)
selvals=[r["selection_recall"] for r in rows if r.get("selection_recall") is not None]
out={"route":"gemma3_selector_cross_lingual_es_en_offline_rescored","raw_json_valid":"0/6 (fenced markdown)","case_count":len(rows),
 "selection_recall":round(sum(selvals)/len(selvals),3) if selvals else None,
 "precision_mean":round(sum(r["precision"] for r in rows if r.get("precision") is not None)/max(1,sum(1 for r in rows if r.get("precision") is not None)),3),
 "rows":rows}
(E/"CROSS_LINGUAL_PROBE.json").write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
print("cross",out["selection_recall"],out["precision_mean"],"rows",len(rows))
