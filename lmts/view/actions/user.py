from __future__ import annotations

from lmts.services.auth import AuthenticationError

from .base import TUIActions
from ..tui_common import secret_line, single_line


class UserActions(TUIActions):
    def _confirm_replace_session(self) -> bool:
        try:
            identity = self.controller.auth_service.current_identity()
        except AuthenticationError:
            identity = None
        if identity is None:
            return True
        choice = self.host.choose(
            self.stdscr,
            f'Authenticated as {identity.username}',
            ['Keep current session', 'Replace session'],
            0,
        )
        return choice == 1

    def login(self, _stdscr=None) -> None:
        self.set_message('')
        if not self._confirm_replace_session():
            return
        username = single_line(self.host, self.stdscr, 'IAM username')
        if username is None:
            return
        password = secret_line(self.stdscr, 'IAM password')
        if password is None:
            return
        try:
            identity = self.controller.auth_service.login(username, password)
        except (AuthenticationError, RuntimeError, ValueError) as exc:
            status = f' (HTTP {exc.status})' if isinstance(exc, AuthenticationError) and exc.status is not None else ''
            message = f'IAM login failed{status}: {exc}'
            self.set_message(message)
            self.host.text_viewer(self.stdscr, 'Login failed', (message,))
            return
        self.controller.user_service.clear()
        self.set_message(f'authenticated: {identity.username}')

    def register(self, _stdscr=None) -> None:
        if not self._confirm_replace_session():
            return
        invite = single_line(self.host, self.stdscr, 'Invite code')
        if invite is None:
            return
        username = single_line(self.host, self.stdscr, 'Username')
        if username is None:
            return
        email = single_line(self.host, self.stdscr, 'Email (optional)', allow_empty=True)
        if email is None:
            return
        password = secret_line(self.stdscr, 'Password')
        if password is None:
            return
        repeat = secret_line(self.stdscr, 'Repeat password')
        if repeat is None:
            return
        if password != repeat:
            self.set_message('Passwords do not match.')
            return
        try:
            identity = self.controller.auth_service.register(
                invite,
                username,
                password,
                email=email or None,
            )
        except (AuthenticationError, RuntimeError, ValueError) as exc:
            message = str(exc)
            self.set_message(message)
            self.host.text_viewer(self.stdscr, 'Registration failed', (message,))
            return
        self.controller.user_service.clear()
        self.set_message(f'registered and authenticated: {identity.username}')

    def logout(self, _stdscr=None) -> None:
        try:
            self.controller.auth_service.logout()
        except (AuthenticationError, RuntimeError, ValueError) as exc:
            self.set_message(f'IAM logout failed: {exc}')
            return
        self.controller.user_service.clear()
        self.set_message('logged out')

    def local(self, _stdscr=None) -> None:
        self.controller.auth_service.enter_local()
        self.controller.user_service.clear()
        self.set_message('local mode')

    def refresh(self, _stdscr=None) -> None:
        self.controller.user_service.clear()
        self.controller.user_service.dashboard_snapshot(refresh=True)
        self.set_message('user refreshed')
