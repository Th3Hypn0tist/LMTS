from __future__ import annotations

from lmts.core.ui_state_store import load_ui_scope, save_ui_scope


def test_ui_state_is_scoped_and_round_trips_without_secrets(tmp_path) -> None:
    path = tmp_path / 'ui-state.json'
    state = {
        'active_tab': 'benchmark',
        'suite_level': 'custom',
        'suite_repeats': 10,
        'selected_target_ids': ['model-a'],
        'selected_test_refs': ['core.text_generation@1.0.0#text-generation'],
        'configured_tests': [{
            'type_ref': 'core.text_generation@1.0.0',
            'instance_id': 'text-generation',
            'params': {},
        }],
    }

    save_ui_scope('local', state, path)
    save_ui_scope('user:0', {**state, 'selected_target_ids': ['model-b']}, path)

    assert load_ui_scope('local', path) == state
    assert load_ui_scope('user:0', path)['selected_target_ids'] == ['model-b']
    assert path.stat().st_mode & 0o777 == 0o600


def test_ui_state_rejects_session_and_publish_secrets(tmp_path) -> None:
    path = tmp_path / 'ui-state.json'
    for field in ('token', 'password', 'publish_key', 'session_secret'):
        try:
            save_ui_scope('local', {field: 'nope'}, path)
        except ValueError as exc:
            assert 'must not contain secret field' in str(exc)
        else:
            raise AssertionError(f'secret UI state field accepted: {field}')
