from source.db import sync


def task(acquire, validate, admit):
    return sync.SyncTask("source", "deployment", "official", acquire, validate, admit)


def test_initial_and_second_sync_are_idempotent_and_update_changes(monkeypatch):
    monkeypatch.setattr(sync, "_record_attempt", lambda *args: None)
    monkeypatch.setattr(sync, "_record_result", lambda *args: None)
    store = {}
    payload = {"records": [{"id": "a", "value": 1}]}
    def admit(data):
        for record in data["records"]:
            store[record["id"]] = dict(record)
        return {"count": len(store)}
    current = task(lambda: payload, lambda data: None, admit)
    assert sync.run_task(current).status == "SUCCESS"
    assert sync.run_task(current).status == "SUCCESS"
    assert len(store) == 1
    payload["records"][0]["value"] = 2
    payload["records"].append({"id": "b", "value": 3})
    sync.run_task(current)
    assert store == {"a": {"id": "a", "value": 2}, "b": {"id": "b", "value": 3}}


def test_invalid_or_malformed_data_is_never_admitted(monkeypatch):
    monkeypatch.setattr(sync, "_record_attempt", lambda *args: None)
    monkeypatch.setattr(sync, "_record_result", lambda *args: None)
    admitted = []
    def validate(data):
        if not isinstance(data.get("records"), list):
            raise ValueError("malformed")
    result = sync.run_task(task(lambda: {"bad": True}, validate, admitted.append))
    assert result.status == "FAILED"
    assert admitted == []


def test_temporary_source_failure_preserves_existing_data(monkeypatch):
    monkeypatch.setattr(sync, "_record_attempt", lambda *args: None)
    monkeypatch.setattr(sync, "_record_result", lambda *args: None)
    store = {"a": {"id": "a", "active": True}}
    def unavailable():
        raise TimeoutError("temporary")
    result = sync.run_task(task(unavailable, lambda data: None, lambda data: store.clear()))
    assert result.status == "FAILED"
    assert store["a"]["active"] is True


def test_connection_failure_is_reported_and_acquisition_does_not_run(monkeypatch):
    calls = []
    monkeypatch.setattr(sync, "_record_attempt", lambda *args: (_ for _ in ()).throw(ConnectionError("neo4j")))
    result = sync.run_task(task(lambda: calls.append("acquire"), lambda data: None, lambda data: None))
    assert result.status == "FAILED"
    assert calls == []


def test_obsolete_records_are_only_deactivated_for_complete_snapshot():
    store = {"a": True, "b": True}
    def reconcile(incoming, complete):
        for key in incoming:
            store[key] = True
        if complete:
            for key in set(store) - set(incoming):
                store[key] = False
    reconcile(["a"], complete=False)
    assert store["b"] is True
    reconcile(["a"], complete=True)
    assert store["b"] is False
