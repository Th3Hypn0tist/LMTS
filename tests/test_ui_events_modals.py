from __future__ import annotations

import pytest

from lmts.lib.view import ModalManager, UIEventBus


def test_event_bus_delivers_canonical_event_in_subscription_order() -> None:
    bus = UIEventBus()
    seen: list[tuple[str, object, str]] = []

    bus.subscribe('ui.test', lambda event: seen.append((event.topic, event.payload, event.source)))
    bus.subscribe('ui.test', lambda event: seen.append(('second', event.payload, event.source)))

    event = bus.publish('ui.test', {'value': 7}, source='test')

    assert event.topic == 'ui.test'
    assert seen == [
        ('ui.test', {'value': 7}, 'test'),
        ('second', {'value': 7}, 'test'),
    ]


def test_event_bus_does_not_swallow_subscriber_failure() -> None:
    bus = UIEventBus()

    def broken(_event) -> None:
        raise RuntimeError('subscriber failed')

    bus.subscribe('ui.test', broken)
    with pytest.raises(RuntimeError, match='subscriber failed'):
        bus.publish('ui.test')


def test_modal_manager_allows_nested_flow_for_same_owner() -> None:
    bus = UIEventBus()
    events: list[tuple[str, object]] = []
    bus.subscribe('ui.modal.opened', lambda event: events.append((event.topic, event.payload)))
    bus.subscribe('ui.modal.closed', lambda event: events.append((event.topic, event.payload)))
    modals = ModalManager(bus)

    result = modals.run(
        'lmts.host',
        'directory',
        lambda: modals.run('lmts.host', 'choose', lambda: 'ok'),
    )

    assert result == 'ok'
    assert modals.active is None
    assert [topic for topic, _ in events] == [
        'ui.modal.opened',
        'ui.modal.opened',
        'ui.modal.closed',
        'ui.modal.closed',
    ]


def test_modal_manager_rejects_competing_owner_and_recovers() -> None:
    modals = ModalManager()

    def competing() -> None:
        with pytest.raises(RuntimeError, match='already owned by lmts.host'):
            modals.run('other.host', 'choose', lambda: None)

    modals.run('lmts.host', 'outer', competing)
    assert modals.active is None
    assert modals.run('other.host', 'after', lambda: 42) == 42


def test_modal_manager_releases_ownership_when_callback_fails() -> None:
    modals = ModalManager()

    def broken() -> None:
        raise ValueError('modal failed')

    with pytest.raises(ValueError, match='modal failed'):
        modals.run('lmts.host', 'broken', broken)

    assert modals.active is None
