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
