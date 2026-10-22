from pathlib import Path

import pytest
from database_support import database

from lifegather.auth.store import AuthStore, InvalidFlow


def test_flow_is_browser_bound_expiring_and_single_use(tmp_path: Path) -> None:
    store = AuthStore(database(tmp_path))
    store.migrate()
    store.begin_flow("browser", "state", "nonce", "verifier", now=100)
    with pytest.raises(InvalidFlow):
        store.consume_flow("other-browser", "state", now=101)
    flow = store.consume_flow("browser", "state", now=101)
    assert flow.nonce == "nonce"
    with pytest.raises(InvalidFlow):
        store.consume_flow("browser", "state", now=101)
    store.begin_flow("browser", "state", "nonce", "verifier", now=100)
    with pytest.raises(InvalidFlow):
        store.consume_flow("browser", "state", now=701)


def test_identity_session_persistence_and_revocation(tmp_path: Path) -> None:
    path = database(tmp_path)
    store = AuthStore(path)
    store.migrate()
    first = store.login("one", "same@example.test", "First", now=100)
    second = store.login("two", "same@example.test", "Second", now=100)
    assert first.user.id != second.user.id
    returning = store.login("one", "new@example.test", "Updated", now=101)
    assert returning.user.id == first.user.id
    assert store.authenticate("invented", now=101) is None
    restarted = AuthStore(path)
    restarted.migrate()
    current = restarted.authenticate(returning.token, now=102)
    assert current is not None
    assert current.user.email == "new@example.test"
    assert restarted.authenticate(first.token, now=100 + 604800) is None
    restarted.logout(returning.token)
    assert restarted.authenticate(returning.token, now=102) is None
    assert restarted.authenticate(second.token, now=102) is not None
