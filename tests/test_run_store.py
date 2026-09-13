from lmts.core.run import RunResult
from lmts.core.store import RunStore


def make_run(run_id="abc"):
    return RunResult(
        run_id=run_id,
        test_ref="demo@1.0.0",
        model_id="provider:model/x",
        model_ref="model/x",
        provider_ref="provider",
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:01+00:00",
        status="completed",
        passed=True,
    )


def test_store_is_model_and_test_scoped_and_append_only(tmp_path):
    store = RunStore(tmp_path)
    path = store.append(make_run())
    assert "models" in path.parts
    assert "tests" in path.parts
    assert store.load(path)["passed"] is True

    try:
        store.append(make_run())
    except FileExistsError:
        pass
    else:
        raise AssertionError("append-only store overwrote an existing run")
