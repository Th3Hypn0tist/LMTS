from __future__ import annotations

from lmts.tools.profile import benchmark_system_reference

from ..reference_progress import format_reference_progress
from .base import TUIActions


class ProfileActions(TUIActions):
    def profile_system(self, _stdscr) -> None:
        self.state.profile_console.clear()
        self.state.profile_console.append('System profile scan started')
        self.host.draw(self.stdscr)
        self.controller.profile()
        self.state.profile_console.append('System profile scan completed')
        self.set_message(self.controller.state.message)

    def profile_reference(self, domain: str) -> None:
        self.state.profile_console.clear()

        def on_progress(event) -> None:
            self.state.profile_console.append(format_reference_progress(event))
            self.host.draw(self.stdscr)

        try:
            result = benchmark_system_reference(domain, self.controller.profile_path, progress=on_progress)
        except NotImplementedError as exc:
            self.state.profile_console.append(f'{domain.upper()} unavailable: {exc}')
            self.host.draw(self.stdscr)
            self.set_message(str(exc))
            return
        except (OSError, ValueError) as exc:
            self.state.profile_console.append(f'{domain.upper()} failed: {exc}')
            self.host.draw(self.stdscr)
            self.set_message(f'{domain.upper()} reference benchmark failed: {exc}')
            return
        tests = result.get('tests') if isinstance(result.get('tests'), list) else []
        self.state.profile_console.append(f'{domain.upper()} reference suite saved: {len(tests)} test(s)')
        self.host.draw(self.stdscr)
        self.set_message(f'{domain.upper()} reference suite completed: {len(tests)} test(s)')
