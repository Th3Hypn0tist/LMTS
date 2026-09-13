from lmts.lib.view import ShortcutDefinition, ShortcutRegistry, TabDefinition, TabRegistry
from lmts.view.registries import SHORTCUT_REGISTRY, TAB_REGISTRY


def test_tab_registry_is_recursive() -> None:
    registry = TabRegistry(
        [
            TabDefinition('root', 'Root'),
            TabDefinition('one', 'One', parent='root', shortcut='1'),
            TabDefinition('child', 'Child', parent='one', shortcut='1'),
            TabDefinition('leaf', 'Leaf', parent='child', shortcut='2'),
        ]
    )
    assert [item.id for item in registry.path('leaf')] == ['root', 'one', 'child', 'leaf']
    assert registry.parent('leaf').id == 'child'
    assert registry.resolve_child_shortcut('child', '2').id == 'leaf'
    assert [item.id for item in registry.descendants('one')] == ['child', 'leaf']


def test_lmts_top_level_tab_order() -> None:
    assert [(item.shortcut, item.id) for item in TAB_REGISTRY.children('root')] == [
        ('1', 'profiler'),
        ('2', 'server'),
        ('3', 'benchmark'),
    ]


def test_shortcut_registry_matches_sequences() -> None:
    first = SHORTCUT_REGISTRY.match((), 'esc', ('benchmark',))
    assert first.kind == 'prefix'
    second = SHORTCUT_REGISTRY.match(first.buffer, 'esc', ('benchmark',))
    assert second.kind == 'exact'
    assert second.shortcut.action == 'nav.back'

    first = SHORTCUT_REGISTRY.match((), 'q', ('benchmark',))
    second = SHORTCUT_REGISTRY.match(first.buffer, 'q', ('benchmark',))
    third = SHORTCUT_REGISTRY.match(second.buffer, 'q', ('benchmark',))
    assert third.kind == 'exact'
    assert third.shortcut.action == 'app.quit'


def test_shortcuts_are_scoped_by_topic_area() -> None:
    benchmark_actions = {item.action for item in SHORTCUT_REGISTRY.definitions(('benchmark',))}
    profiler_actions = {item.action for item in SHORTCUT_REGISTRY.definitions(('profiler',))}
    assert 'models' in benchmark_actions
    assert 'models' not in profiler_actions
    assert 'profile.run' in profiler_actions


def test_duplicate_shortcut_sequence_is_rejected_within_scope() -> None:
    registry = ShortcutRegistry([ShortcutDefinition('one', ('x',), 'One', 'Test', scope='a')])
    try:
        registry.register(ShortcutDefinition('two', ('x',), 'Two', 'Test', scope='a'))
    except ValueError:
        pass
    else:
        raise AssertionError('duplicate shortcut sequence was accepted')
