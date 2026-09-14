from __future__ import annotations

from dataclasses import dataclass

from .controller import LMTSViewController
from .projector import LMTSViewProjector


@dataclass(slots=True)
class AIGMosViewAdapter:
    controller: LMTSViewController
    view_target: str = "|lmts:view"
    module_type: str = "view"

    @property
    def VIEW_TARGET(self) -> str:
        return self.view_target

    def value(self) -> str:
        return LMTSViewProjector(self.controller.state).project().text()

    def metadata(self) -> dict[str, object]:
        return {
            "module_type": self.module_type,
            "view_target": self.VIEW_TARGET,
            "render_owner": "aigmos-layout",
            "lmts_owns_render_logic": False,
            "profile_required": self.controller.state.profile_required,
            "running": self.controller.state.running,
            "suite_level": self.controller.state.suite_level,
            "registry_test_types": len(self.controller.test_types.definitions()),
            "configured_tests": len(self.controller.state.tests),
            "progress_completed": self.controller.state.progress_completed,
            "progress_total": self.controller.state.progress_total,
        }

    def action(self, name: str, value: object | None = None) -> bool:
        if name == "refresh":
            self.controller.refresh()
            return True
        if name == "select_targets" and isinstance(value, (list, tuple, set)):
            self.controller.select_target_ids({str(item) for item in value})
            return True
        if name == "select_all_targets":
            self.controller.select_all_targets()
            return True
        if name == "select_tests" and isinstance(value, (list, tuple, set)):
            self.controller.select_test_refs({str(item) for item in value})
            return True
        if name == "select_all_tests":
            self.controller.select_all_tests()
            return True
        if name == "set_suite_level" and isinstance(value, str) and value in {"quick", "moderate", "deep"}:
            return self.controller.set_suite_level(value)
        if name == "add_test" and isinstance(value, dict):
            type_ref = str(value.get("type_ref") or "")
            instance_id = str(value.get("instance_id") or "")
            params = value.get("params")
            if params is not None and not isinstance(params, dict):
                return False
            return self.controller.add_test(type_ref, instance_id, params) is not None
        if name == "remove_test" and isinstance(value, str):
            return self.controller.remove_test(value)
        if name == "run":
            return self.controller.run_selected()
        if name == "test_all":
            return self.controller.test_all()
        if name == "cancel":
            return self.controller.cancel()
        if name == "export_errors":
            if not isinstance(value, str) or not value.strip():
                return False
            self.controller.export_errors(value)
            return True
        if name == "profile":
            return self.controller.profile() is not None
        return False
