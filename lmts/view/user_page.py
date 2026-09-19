from __future__ import annotations

from .controller import LMTSViewController


class UserPage:
    """User dashboard projection without inventing unavailable account state."""

    def __init__(self, controller: LMTSViewController) -> None:
        self.controller = controller

    def lines(self) -> tuple[str, ...]:
        snapshot = self.controller.user_service.dashboard_snapshot()
        summary = snapshot.activity
        completed = summary['pass'] + summary['fail']
        return (
            'User', '', 'Identity',
            f"  Username : {snapshot.username or 'not connected'}",
            f"  Tier     : {snapshot.tier or '-'}",
            '', 'Activity',
            f"  Test runs    : {summary['runs']}",
            f"  Matrices     : {summary['matrices']}",
            f"  Unique tests : {summary['tests']}",
            f"  Targets      : {summary['targets']}",
            f"    Models      : {summary['models']}",
            f"    Bots        : {summary['bots']}",
            f"    Compositions: {summary['compositions']}",
            '', 'Results',
            f"  Completed : {completed}",
            f"  PASS      : {summary['pass']}",
            f"  FAIL      : {summary['fail']}",
            f"  ERROR     : {summary['error']}",
            f"  CANCELLED : {summary['cancelled']}",
            f"  UNKNOWN   : {summary['unknown']}",
        )
