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
        ('1', 'benchmark'),
        ('2', 'stats'),
        ('3', 'downloader'),
        ('9', 'profile'),
        ('0', 'settings'),
    ]
    assert [item.id for item in TAB_REGISTRY.path('cw_bench')] == [
        'root', 'benchmark', 'deep', 'cw_bench'
    ]
    assert [item.id for item in TAB_REGISTRY.path('profile')] == [
        'root', 'profile'
    ]
    assert [item.id for item in TAB_REGISTRY.path('user')] == [
        'root', 'settings', 'user'
    ]


def test_shortcut_registry_matches_sequences() -> None:
    back = SHORTCUT_REGISTRY.match((), 'esc', ('benchmark',))
    assert back.kind == 'exact'
    assert back.shortcut.action == 'nav.back'

    first = SHORTCUT_REGISTRY.match((), 'q', ('benchmark',))
    second = SHORTCUT_REGISTRY.match(first.buffer, 'q', ('benchmark',))
    third = SHORTCUT_REGISTRY.match(second.buffer, 'q', ('benchmark',))
    assert third.kind == 'exact'
    assert third.shortcut.action == 'app.quit'

    help_match = SHORTCUT_REGISTRY.match((), 'f1', ('settings',))
    assert help_match.kind == 'exact'
    assert help_match.shortcut.action == 'app.help'


def test_shortcuts_are_scoped_by_topic_area() -> None:
    benchmark_actions = {item.action for item in SHORTCUT_REGISTRY.definitions(('benchmark',))}
    profile_actions = {item.action for item in SHORTCUT_REGISTRY.definitions(('profile',))}
    deep_actions = {item.action for item in SHORTCUT_REGISTRY.definitions(('deep',))}
    stats_actions = {item.action for item in SHORTCUT_REGISTRY.definitions(('stats',))}
    downloader_actions = {item.action for item in SHORTCUT_REGISTRY.definitions(('downloader',))}
    settings_actions = {item.action for item in SHORTCUT_REGISTRY.definitions(('settings',))}

    assert {
        'benchmark.tests',
        'benchmark.targets',
        'benchmark.run',
        'benchmark.output',
        'benchmark.refresh',
    } <= benchmark_actions
    assert 'benchmark.tests' not in profile_actions
    assert 'profile.scan' in profile_actions
    assert 'profile.cpu' not in profile_actions
    assert {'deep.cw_bench', 'deep.run', 'deep.results'} <= deep_actions
    assert 'stats.refresh' in stats_actions
    assert {
        'downloader.module',
        'downloader.download',
        'downloader.delete',
        'downloader.progress',
        'downloader.refresh',
        'downloader.cancel',
    } <= downloader_actions
    assert 'settings.user' in settings_actions
    assert 'settings.user' not in benchmark_actions


def test_duplicate_shortcut_sequence_is_rejected_within_scope() -> None:
    registry = ShortcutRegistry([ShortcutDefinition('one', ('x',), 'One', 'Test', scope='a')])
    try:
        registry.register(ShortcutDefinition('two', ('x',), 'Two', 'Test', scope='a'))
    except ValueError:
        pass
    else:
        raise AssertionError('duplicate shortcut sequence was accepted')


def test_global_shortcut_cannot_collide_with_scoped_shortcut() -> None:
    registry = ShortcutRegistry([ShortcutDefinition('global', ('x',), 'Global', 'Test')])
    try:
        registry.register(ShortcutDefinition('local', ('x',), 'Local', 'Test', scope='a'))
    except ValueError:
        pass
    else:
        raise AssertionError('global/scoped shortcut collision was accepted')


def test_overlapping_prefix_shortcuts_are_rejected() -> None:
    registry = ShortcutRegistry([ShortcutDefinition('quit', ('q', 'q', 'q'), 'Quit', 'System')])
    try:
        registry.register(ShortcutDefinition('quick', ('q',), 'Quick', 'Test', scope='a'))
    except ValueError:
        pass
    else:
        raise AssertionError('prefix shortcut collision was accepted')
