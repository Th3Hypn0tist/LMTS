from __future__ import annotations

from dataclasses import dataclass


def _short_test_label(ref: str, width: int) -> str:
    value = ref.split("#", 1)[-1] if "#" in ref else ref.rsplit(".", 1)[-1]
    for prefix in ("bot-", "reasoning-", "context-", "robustness-", "workspace-", "research-"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    return value[:width]


@dataclass(frozen=True, slots=True)
class LiveResultsMatrixView:
    target_ids: tuple[str, ...]
    target_kinds: dict[str, str]
    test_refs: tuple[str, ...]
    cells: dict[tuple[str, str], str]
    current_test_ref: str = ""
    max_columns: int = 10
    label_width: int = 12

    def _visible_tests(self) -> tuple[tuple[str, ...], int, int]:
        if not self.test_refs:
            return (), 0, 0
        count = min(max(1, self.max_columns), len(self.test_refs))
        if self.current_test_ref in self.test_refs:
            current = self.test_refs.index(self.current_test_ref)
        else:
            current = len(self.test_refs) - 1
        start = max(0, current - count // 2)
        start = min(start, len(self.test_refs) - count)
        end = start + count
        return self.test_refs[start:end], start, end

    def lines(self) -> tuple[str, ...]:
        visible_tests, start, end = self._visible_tests()
        if not self.target_ids or not visible_tests:
            return ()

        target_labels = [
            f"{self.target_kinds.get(target, '?').upper()} {target}"
            for target in self.target_ids
        ]
        target_width = max(12, min(34, max(len(label) for label in target_labels)))
        col_width = max(8, self.label_width)

        lines = ["Results matrix"]
        if len(visible_tests) < len(self.test_refs):
            lines.append(f"Tests {start + 1}-{end} / {len(self.test_refs)}")

        header = f"{'TARGET':<{target_width}}"
        for test_ref in visible_tests:
            header += f"  {_short_test_label(test_ref, col_width):^{col_width}}"
        lines.append(header)
        lines.append("-" * len(header))

        for target, target_label in zip(self.target_ids, target_labels):
            row = f"{target_label[:target_width]:<{target_width}}"
            for test_ref in visible_tests:
                verdict = self.cells.get((target, test_ref), "-")
                row += f"  {verdict:^{col_width}}"
            lines.append(row)

        return tuple(lines)
