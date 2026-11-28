from dataclasses import replace

import pytest

from context_state import AuthorizationEvent, resolve_authorization


def event(i=1, kind="grant", **kwargs):
    fields = dict(session="s", event_id=f"e{i}", sequence=i, scope="git:push:feature",
                  kind=kind, source_role="user", source_reference=f"source-{i}", issued_at=10)
    fields.update(kwargs)
    return AuthorizationEvent(**fields)


def resolve(events, trusted=None, **kwargs):
    fields = dict(session="s", scope="git:push:feature", as_of=30,
                  trusted_event_digests=set(e.digest for e in events) if trusted is None else trusted)
    fields.update(kwargs)
    return resolve_authorization(events, **fields)


def test_revocation_and_later_explicit_grant_are_ordered_by_sequence():
    grant, revoke, new = event(), event(2, "revoke"), event(3)
    assert resolve([revoke, grant]).status == "revoked"
    assert resolve([revoke, new, grant, new]).candidate_grant
    assert len(resolve([revoke, new, grant, new]).history) == 3


def test_authentication_binds_payload_not_only_source_reference():
    grant = event()
    changed = replace(grant, scope="git:push:main")
    state = resolve([changed], {grant.digest}, scope="git:push:main")
    assert not state.candidate_grant and state.ignored_untrusted == 1
    assert not resolve([grant], set()).candidate_grant


@pytest.mark.parametrize("role", ["assistant", "tool", "system"])
def test_nonuser_cannot_grant_even_with_authenticated_data(role):
    grant = event(source_role=role)
    result = resolve([grant])
    assert not result.candidate_grant and result.ignored_non_user == 1


def test_untrusted_data_cannot_revoke_or_grant_and_policy_veto():
    grant, revoke = event(), event(2, "revoke")
    assert resolve([grant, revoke], {grant.digest}).candidate_grant
    assert not resolve([grant], hard_denied=True).candidate_grant


def test_scope_session_and_future_events():
    grant = event()
    assert not resolve([grant], scope="git:push:main").candidate_grant
    assert not resolve([grant], session="other").candidate_grant
    future = event(2, "revoke", issued_at=40)
    state = resolve([grant, future])
    assert state.candidate_grant and state.future_events == 1
    assert resolve([grant, future], as_of=40).status == "revoked"


def test_expiration_never_resurrects_old_grant():
    old, new = event(), event(2, expires_at=20)
    assert resolve([old, new], as_of=19).candidate_grant
    state = resolve([old, new], as_of=20)
    assert state.status == "expired" and not state.candidate_grant


def test_authenticated_conflicting_identity_or_sequence_fails_closed():
    a = event()
    b = replace(a, kind="revoke")
    assert resolve([a, b]).reason == "authenticated_event_conflict"
    c = event(2, sequence=1, scope="different")
    assert resolve([a, c]).reason == "authenticated_event_conflict"


@pytest.mark.parametrize("kwargs", [
    {"sequence": True}, {"issued_at": -1}, {"expires_at": 10},
    {"source_role": []}, {"kind": "observe"}, {"scope": ""},
])
def test_invalid_event_contract(kwargs):
    with pytest.raises(ValueError):
        event(**kwargs)
