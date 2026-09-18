from pathlib import Path

from lmts.tools.report_profiles import ReportProfile, ReportProfiles, load_report_profiles, save_report_profiles
from lmts.view.actions.benchmark import BenchmarkActions
from lmts.view.controller import LMTSViewController
from lmts.view.lmts_host import LMTSInteractiveHost
from lmts.view.report_export_runtime import (
    ReportExportBenchmarkActions,
    ReportExportController,
    ReportExportHost,
    ReportExportTUIApplication,
)
from lmts.view.tui_app import TUIApplication


def test_report_export_tui_uses_explicit_application_dependencies() -> None:
    assert issubclass(ReportExportTUIApplication, TUIApplication)
    assert ReportExportTUIApplication.controller_class is ReportExportController
    assert ReportExportTUIApplication.host_class is ReportExportHost
    assert ReportExportTUIApplication.benchmark_actions_class is ReportExportBenchmarkActions


def test_report_export_components_extend_current_tui_architecture() -> None:
    assert issubclass(ReportExportController, LMTSViewController)
    assert issubclass(ReportExportHost, LMTSInteractiveHost)
    assert issubclass(ReportExportBenchmarkActions, BenchmarkActions)


def test_base_benchmark_actions_exposes_pre_run_hook() -> None:
    assert hasattr(BenchmarkActions, 'before_run_choice')


def test_report_profile_store_migrates_v1(tmp_path: Path) -> None:
    path = tmp_path / 'report-profiles.json'
    path.write_text(
        '{"schema_version":1,"profiles":[{"name":"server","endpoint":"http://127.0.0.1/api/report.php","publish_key":"k"}]}',
        encoding='utf-8',
    )
    profiles = load_report_profiles(path)
    assert profiles.schema_version == 3
    assert profiles.auto_publish_profile is None
    assert profiles.by_name('server') is not None
    assert profiles.by_name('server').kind == 'php_api'


def test_report_profile_store_persists_auto_publish(tmp_path: Path) -> None:
    path = tmp_path / 'report-profiles.json'
    profile = ReportProfile(
        name='server',
        endpoint='http://127.0.0.1/api/report.php',
        publish_key='k',
    )
    save_report_profiles(ReportProfiles(profiles=(profile,), auto_publish_profile='server'), path)
    loaded = load_report_profiles(path)
    assert loaded.auto_publish_profile == 'server'
    assert loaded.auto_publish() == profile


def test_report_profile_store_persists_mysql_target(tmp_path: Path) -> None:
    path = tmp_path / 'report-profiles.json'
    profile = ReportProfile(name='direct-db', kind='mysql', endpoint='', publish_key='')
    save_report_profiles(ReportProfiles(profiles=(profile,), auto_publish_profile='direct-db'), path)
    loaded = load_report_profiles(path)
    assert loaded.auto_publish_profile == 'direct-db'
    assert loaded.auto_publish() == profile
    assert loaded.auto_publish().kind == 'mysql'
