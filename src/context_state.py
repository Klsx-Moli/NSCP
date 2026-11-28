"""Experimental resolution of explicit, externally authenticated events.

This is not an NLP permission extractor or an authorization enforcement layer.
The trusted host must authenticate source events and provide their exact
digests. Text/model output must never supply its own trust anchor.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

ROLES = frozenset({"system", "user", "assistant", "tool"})
KINDS = frozenset({"grant", "revoke"})
MAX_EVENTS = 10000


def _identity(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 512 or "\x00" in value:
        raise ValueError("Invalid state identity")
    return value


def _nonnegative(value):
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise ValueError("Invalid event sequence or time")
    return value


@dataclass(frozen=True)
class AuthorizationEvent:
    session: str
    event_id: str
    sequence: int
    scope: str
    kind: str
    source_role: str
    source_reference: str
    issued_at: int
    expires_at: int | None = None

    def __post_init__(self):
        for value in (self.session, self.event_id, self.scope, self.source_reference):
            _identity(value)
        _nonnegative(self.sequence)
        _nonnegative(self.issued_at)
        if (not isinstance(self.kind, str) or self.kind not in KINDS
                or not isinstance(self.source_role, str) or self.source_role not in ROLES):
            raise ValueError("Invalid event kind or source role")
        if self.expires_at is not None:
            _nonnegative(self.expires_at)
            if self.kind != "grant" or self.expires_at <= self.issued_at:
                raise ValueError("Invalid grant expiration")

    @property
    def digest(self):
        raw = json.dumps({"schema": "nscp/authorization-event/v1", **asdict(self)},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                         allow_nan=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuthorizationState:
    status: str
    candidate_grant: bool
    reason: str
    event_digest: str | None
    history: tuple[str, ...]
    ignored_untrusted: int
    ignored_non_user: int
    future_events: int


def resolve_authorization(events, *, session, scope, as_of, trusted_event_digests,
                          hard_denied=False):
    """Resolve exact scope in one session; deny by default.

    The host supplies a separate hard policy veto and authenticated digests
    of explicitly parsed user events, not raw source hashes. This contract
    does not infer broad scopes, permit inheritance, or parse natural text.
    A later expired grant never resurrects an earlier grant.
    """
    _identity(session)
    _identity(scope)
    _nonnegative(as_of)
    if type(hard_denied) is not bool:
        raise ValueError("Expected explicit hard policy decision")
    if (not isinstance(events, (list, tuple)) or len(events) > MAX_EVENTS
            or any(not isinstance(e, AuthorizationEvent) for e in events)):
        raise ValueError("Invalid or oversized event ledger")
    if (not isinstance(trusted_event_digests, (set, frozenset))
            or len(trusted_event_digests) > MAX_EVENTS
            or any(not isinstance(d, str) or len(d) != 64
                   or any(c not in "0123456789abcdef" for c in d)
                   for d in trusted_event_digests)):
        raise ValueError("Invalid trusted event digest set")
    eligible = {}
    untrusted = nonuser = future = 0
    for e in events:
        if e.session != session:
            continue
        if e.digest not in trusted_event_digests:
            if e.scope == scope:
                untrusted += 1
            continue
        if e.source_role != "user":
            if e.scope == scope:
                nonuser += 1
            continue
        if e.issued_at > as_of:
            if e.scope == scope:
                future += 1
            continue
        eligible[e.digest] = e

    # Check immutable identity and sequence across the authenticated session,
    # not merely within one scope. Exact duplicate replay is idempotent.
    by_id, by_sequence = {}, {}
    conflict = False
    for digest, e in eligible.items():
        if e.event_id in by_id and by_id[e.event_id] != digest:
            conflict = True
        if e.sequence in by_sequence and by_sequence[e.sequence] != digest:
            conflict = True
        by_id[e.event_id] = digest
        by_sequence[e.sequence] = digest
    matching = sorted((e for e in eligible.values() if e.scope == scope),
                      key=lambda e: (e.sequence, e.digest))
    history = tuple(e.digest for e in matching)
    latest = matching[-1] if matching else None

    def result(status, candidate, reason, digest=None):
        return AuthorizationState(status, candidate, reason, digest, history,
                                  untrusted, nonuser, future)

    if hard_denied:
        return result("denied", False, "hard_policy_veto")
    if conflict:
        return result("unknown", False, "authenticated_event_conflict")
    if latest is None:
        return result("unknown", False, "no_authenticated_user_event")
    if latest.kind == "revoke":
        return result("revoked", False, "latest_explicit_revocation", latest.digest)
    if latest.expires_at is not None and as_of >= latest.expires_at:
        return result("expired", False, "latest_grant_expired", latest.digest)
    return result("grant_candidate", True, "latest_authenticated_explicit_grant", latest.digest)
