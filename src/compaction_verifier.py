"""Verificador de perdida para COMPACTACION de conversaciones + compuerta strict.

verify_context_loss (pipeline de prompts) exige semantics/NSL/prompt reconstruido
y no aplica a historiales; este modulo emite un informe con las MISMAS claves
usadas por npsc_service.evaluate_strict (score, critical_losses, profile_failures),
de modo que evaluate_strict puede aplicarse sin modificarlo.
"""

from __future__ import annotations

import hashlib
import re

from compression_policy import get_policy
from context_compactor import compact_history, partition_turns, to_view

DEFAULT_GATE_POLICY = {"min_score": 80, "max_critical_losses": 0}
_FENCE = re.compile(r"```.*?```", re.S)
_URL = re.compile(r"https?://[^\s)>\]]+")
_PATH = re.compile(r"(?<![\w/])(?:[A-Za-z]:\\|\./|~/|/)?[\w.\-]+(?:[\\/][\w.\-]+)+")
_NUM = re.compile(r"\b\d+(?:[.,]\d+)+\b|\b\d{3,}\b")
_IDENT = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_MARK = re.compile(r"\b(nunca|jamas|siempre|obligatorio|prohibido|never|always|must|do not|solo|only)\b", re.I)
_POINTER = re.compile(r"'(offloaded-[0-9a-f]{64}\.txt)'")
MAX_FACTS = 500


class CompactionBlocked(Exception):
    def __init__(self, reasons, report):
        super().__init__("compactacion bloqueada por strict: " + ",".join(reasons))
        self.reasons = reasons
        self.report = report


def extract_facts(text, role="user"):
    facts = set()
    prose = _FENCE.sub(" ", text)
    for m in _URL.findall(prose):
        facts.add(("url", m))
    for m in _PATH.findall(_URL.sub(" ", prose)):
        if re.search(r"\.\w{1,5}$", m) or len(re.findall(r"[\\/]", m)) >= 2:
            facts.add(("path", m))
    for m in _NUM.findall(prose):
        facts.add(("number", m))
    for m in _IDENT.findall(prose):
        facts.add(("identifier", m))
    if role == "user":
        for s in re.split(r"[.\n!?]+", prose):
            s = s.strip()
            if 12 <= len(s) <= 200 and _MARK.search(s):
                facts.add(("constraint", s.lower()))
    return facts


def _words(s):
    return {w for w in re.findall(r"\w+", s.lower()) if len(w) > 3}


def _present(kind, value, out):
    v = value.lower()
    if v in out:
        return True
    if kind == "constraint":
        w = _words(v)
        return len(w) >= 2 and len(w & _words(out)) / len(w) >= 0.8
    return False


def _recoverable(messages, storage_dir, original_views):
    if not storage_dir:
        return ""
    import os
    originals = {hashlib.sha256(v.content.encode("utf-8")).hexdigest(): v.content
                 for v in original_views}
    chunks = []
    for m in messages:
        for name in _POINTER.findall(m["content"]):
            digest = name[len("offloaded-"):-len(".txt")]
            if digest not in originals:
                continue
            p = os.path.join(storage_dir, name)
            if os.path.isfile(p) and not os.path.islink(p):
                try:
                    with open(p, "rb") as fh:
                        raw = fh.read()
                    if hashlib.sha256(raw).hexdigest() == digest and raw == originals[digest].encode("utf-8"):
                        chunks.append(originals[digest].lower())
                except OSError:
                    continue
    return "\n".join(chunks)


def verify_compaction(history, messages, report, storage_dir=None, tokenizer=None):
    out = {"score": 100, "critical_losses": [], "profile_failures": [], "warnings": [],
           "facts_total": 0, "facts_in_context": 0, "facts_recoverable_only": 0, "facts_lost": 0,
           "fact_retention": 1.0, "code_blocks_lost": 0}
    if not report.get("triggered"):
        original = [{"role": v.role, "content": v.content} for v in (to_view(t, tokenizer) for t in history)]
        if messages != original:
            out["critical_losses"].append("modified_passthrough")
            out["score"] = 0
        return out
    policy = get_policy(report["level"])
    views = [to_view(t, tokenizer) for t in history]
    pinned, middle, recent = partition_turns(views, policy.keep_recent_turns)
    raw_ctx = "\n".join(m["content"] for m in messages)
    ctx = raw_ctx.lower()
    rec = _recoverable(messages, storage_dir, views)

    if not messages or messages[0].get("role") != "system" or not all(
            v.role == "system" and v.content in messages[0]["content"] for v in pinned):
        out["critical_losses"].append("missing_pinned")
    tail = messages[len(messages) - len(recent):] if recent else []
    if [{"role": v.role, "content": v.content} for v in recent] != tail:
        out["critical_losses"].append("missing_recent")

    facts, code_lost = set(), 0
    for v in middle:
        for block in _FENCE.findall(v.content):
            if block not in raw_ctx:
                code_lost += 1
        facts |= {(k, val, v.role) for k, val in extract_facts(v.content, v.role)}
    seen = {}
    for k, val, _ in facts:
        seen[(k, val)] = True
    keys = sorted(seen)[:MAX_FACTS]
    inctx = sum(1 for k, val in keys if _present(k, val, ctx))
    recov = sum(1 for k, val in keys if not _present(k, val, ctx) and val.lower() in rec)
    total = len(keys)
    out.update(facts_total=total, facts_in_context=inctx, facts_recoverable_only=recov,
               facts_lost=total - inctx - recov, code_blocks_lost=code_lost)
    out["fact_retention"] = round((inctx + 0.5 * recov) / total, 3) if total else 1.0
    if code_lost:
        out["critical_losses"].append("missing_code_block")
    ded = 40 * ("missing_pinned" in out["critical_losses"]) + 40 * ("missing_recent" in out["critical_losses"])
    ded += min(60, 20 * code_lost) + round((1 - out["fact_retention"]) * 60)
    out["score"] = max(0, 100 - ded)
    # Every original user message is protected in strict mode, not just known
    # keywords. Compare the ordered sequence, including duplicates and role.
    original_users = [v.content for v in views if v.role == "user"]
    output_users = [m["content"] for m in messages if m.get("role") == "user"]
    if original_users != output_users:
        out["critical_losses"].append("missing_or_modified_user_turn")
        out["warnings"].append("user_authority_not_preserved")
    out["semantic_equivalence"] = "not_verified"
    return out


def evaluate_gate(vreport, policy=None):
    p = policy or DEFAULT_GATE_POLICY
    reasons = []
    score, crit = int(vreport.get("score", 0)), list(vreport.get("critical_losses", []))
    if score < int(p.get("min_score", 0)):
        reasons.append(f"score_below_min:{score}<{p.get('min_score', 0)}")
    if len(crit) > int(p.get("max_critical_losses", 0)):
        reasons.append(f"critical_losses_exceeded:{len(crit)}>{p.get('max_critical_losses', 0)}")
    # User authority, system/recent turns and code are non-waivable.
    hard = {"missing_or_modified_user_turn", "missing_pinned", "missing_recent",
            "missing_code_block", "modified_passthrough"}
    reasons.extend("hard_loss:" + loss for loss in crit if loss in hard)
    reasons.extend(str(x) for x in vreport.get("profile_failures", []))
    return len(reasons) == 0, sorted(set(reasons))


def compact_with_gate(history, num_ctx, level=None, summarizer=None, storage_dir=None,
                      tokenizer=None, strict=True, policy=None):
    """Compacta, verifica y aplica la compuerta. Con strict: si falla, reintenta con
    truncado determinista (sin resumen); si tambien falla, lanza CompactionBlocked."""
    msgs, rep = compact_history(history, num_ctx, level, summarizer, storage_dir, tokenizer,
                                protect_users=strict)
    ver = verify_compaction(history, msgs, rep, storage_dir, tokenizer)
    ok, reasons = evaluate_gate(ver, policy)
    rep["verification"] = {**ver, "strict_requested": bool(strict), "gate_reasons": reasons,
                           "status": "pass" if ok else ("advisory" if not strict else "blocked")}
    if ok or not strict:
        return msgs, rep
    if summarizer is not None:
        msgs2, rep2 = compact_history(history, num_ctx, level, None, storage_dir, tokenizer,
                                      protect_users=True)
        ver2 = verify_compaction(history, msgs2, rep2, storage_dir, tokenizer)
        ok2, reasons2 = evaluate_gate(ver2, policy)
        rep2["verification"] = {**ver2, "strict_requested": True, "gate_reasons": reasons2,
                                "status": "pass_after_fallback_truncation" if ok2 else "blocked",
                                "first_attempt_reasons": reasons}
        if ok2:
            return msgs2, rep2
        raise CompactionBlocked(reasons2, rep2)
    raise CompactionBlocked(reasons, rep)
