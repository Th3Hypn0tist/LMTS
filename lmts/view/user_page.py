from __future__ import annotations

from .controller import LMTSViewController


class UserPage:
    """Projection of authenticated canonical user state and attributed test activity."""

    def __init__(self, controller: LMTSViewController) -> None:
        self.controller = controller

    @staticmethod
    def _yes_no(value: bool | None) -> str:
        if value is None:
            return '-'
        return 'yes' if value else 'no'

    def lines(self) -> tuple[str, ...]:
        snapshot = self.controller.user_service.dashboard_snapshot()
        activity = snapshot.activity
        lines = [
            'Identity',
            f"  Username   : {snapshot.username or 'anonymous'}",
            f"  User ID    : {snapshot.user_id or '-'}",
            f"  Tier       : {snapshot.tier} {snapshot.tier_label}",
            f"  Status     : {snapshot.status}",
            f"  Verified   : {self._yes_no(snapshot.verified)}",
            f"  Can invite : {self._yes_no(snapshot.can_invite)}",
        ]
        if snapshot.identity_error:
            lines.extend(['', f'IAM identity error: {snapshot.identity_error}'])
        if snapshot.activity_error:
            lines.extend(['', f'Local activity unavailable: {snapshot.activity_error}'])
        if activity is not None:
            lines.extend([
                '',
                'My test activity',
                f"  Reports            : {activity['reports']}",
                f"  Submissions        : {activity['submissions']}",
                f"  Result records     : {activity['result_records']}",
                f"  Test definitions   : {activity['test_definitions']}",
                f"  Test versions      : {activity['test_versions']}",
                f"  Telemetry values   : {activity['telemetry_values']}",
                '',
                'My results',
                f"  PASS               : {activity['pass']}",
                f"  FAIL               : {activity['fail']}",
                f"  ERROR              : {activity['error']}",
                f"  CANCELLED          : {activity['cancelled']}",
                f"  UNKNOWN            : {activity['unknown']}",
                '',
                'My tested coverage',
                f"  Models             : {activity['models']}",
                f"  Compositions       : {activity['compositions']}",
                f"  Systems            : {activity['systems']}",
                f"  Compute profiles   : {activity['compute_profiles']}",
                f"  Hardware nodes     : {activity['hardware_nodes']}",
            ])
        return tuple(lines)
