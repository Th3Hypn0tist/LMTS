from __future__ import annotations

from .controller import LMTSViewController


class UserPage:
    """User dashboard projection.

    Account, tier, invite and contribution services are intentionally separate
    from the local canonical result summary. Until the account service is wired,
    this page reports local benchmark activity without inventing user state.
    """

    def __init__(self, controller: LMTSViewController) -> None:
        self.controller = controller

    def lines(self) -> tuple[str, ...]:
        summary = self.controller.result_service.activity_summary()
        completed = summary['pass'] + summary['fail']
        return (
            'User',
            '',
            'Identity',
            '  Account : not connected',
            '  Tier    : -',
            '',
            'Activity',
            f"  Test runs    : {summary['runs']}",
            f"  Matrices     : {summary['matrices']}",
            f"  Unique tests : {summary['tests']}",
            f"  Targets      : {summary['targets']}",
            f"    Models      : {summary['models']}",
            f"    Bots        : {summary['bots']}",
            f"    Compositions: {summary['compositions']}",
            '',
            'Results',
            f"  Completed : {completed}",
            f"  PASS      : {summary['pass']}",
            f"  FAIL      : {summary['fail']}",
            f"  ERROR     : {summary['error']}",
            f"  CANCELLED : {summary['cancelled']}",
            f"  UNKNOWN   : {summary['unknown']}",
            '',
            'User registration, tiers, invites, Systems, Compute Profiles and',
            'contribution state will bind here through the LMTS user service.',
        )
