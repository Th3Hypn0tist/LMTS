from lmts.core.models import ModelDescriptor
from lmts.view.aigmos import AIGMosViewAdapter
from lmts.view.projector import LMTSViewProjector, LMTSViewState


class DummyController:
    def __init__(self) -> None:
        self.state = LMTSViewState(
            models=[ModelDescriptor(id="fake:m", provider_ref="fake", model_ref="m", location="local")]
        )
        self.refreshed = False

    def refresh(self):
        self.refreshed = True


def test_view_projection_is_host_neutral() -> None:
    state = LMTSViewState(models=[ModelDescriptor(id="fake:m", provider_ref="fake", model_ref="m", location="local")])
    frame = LMTSViewProjector(state).project()
    assert frame.title == "LMTS"
    assert "fake:m" in frame.text()


def test_aigmos_adapter_exposes_view_target_without_render_ownership() -> None:
    controller = DummyController()
    adapter = AIGMosViewAdapter(controller)  # type: ignore[arg-type]
    assert adapter.VIEW_TARGET == "|lmts:view"
    assert adapter.metadata()["lmts_owns_render_logic"] is False
    assert "fake:m" in adapter.value()
    assert adapter.action("refresh") is True
    assert controller.refreshed is True
