from lmts.core.workspace import Workspace as CoreWorkspace
from lmts.core.workspace_protocol import (
    WorkspaceProtocolSession as CoreWorkspaceProtocolSession,
)
from lmts.lib.view import ViewFrame
from lmts.lib.workspace import Workspace, WorkspaceProtocolSession
from lmts.view.model import ViewFrame as CompatViewFrame


def test_workspace_has_single_canonical_implementation() -> None:
    assert CoreWorkspace is Workspace
    assert CoreWorkspaceProtocolSession is WorkspaceProtocolSession


def test_view_frame_has_single_canonical_implementation() -> None:
    assert CompatViewFrame is ViewFrame
