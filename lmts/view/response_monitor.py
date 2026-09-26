from __future__ import annotations

import threading
from collections import deque

from lmts.core.models import ResponseStreamChunk


class ResponseMonitor:
    """Read-only projection buffer for the currently active response stream."""

    def __init__(self, *, max_lines: int = 400) -> None:
        self._lock = threading.Lock()
        self._max_lines = max_lines
        self._source_id = ""
        self._channel = ""
        self._lines: deque[str] = deque(maxlen=max_lines)
        self._partial: dict[str, str] = {"input": "", "thinking": "", "text": "", "tool": "", "meta": ""}

    def reset(self, source_id: str = "") -> None:
        with self._lock:
            self._source_id = source_id
            self._channel = ""
            self._lines.clear()
            for key in self._partial:
                self._partial[key] = ""

    def _flush_partial(self, channel: str) -> None:
        partial = self._partial.get(channel, "")
        if partial:
            self._lines.append(partial)
            self._partial[channel] = ""

    def accept(self, chunk: ResponseStreamChunk) -> None:
        with self._lock:
            if chunk.source_id and chunk.source_id != self._source_id:
                self._flush_partial(self._channel)
                self._source_id = chunk.source_id
                self._channel = ""
                self._lines.clear()
                for key in self._partial:
                    self._partial[key] = ""

            channel = chunk.channel
            if channel != self._channel:
                self._flush_partial(self._channel)
                if self._lines and self._lines[-1] != "":
                    self._lines.append("")
                self._lines.append(channel.upper())
                self._channel = channel

            if chunk.text:
                text = self._partial.get(channel, "") + chunk.text
                pieces = text.split("\n")
                self._partial[channel] = pieces.pop() if pieces else ""
                for piece in pieces:
                    self._lines.append(piece)

            if channel == "meta" and chunk.data:
                summary = "  ".join(f"{key}={value}" for key, value in chunk.data.items())
                if summary:
                    self._lines.append(summary)

    def append_lines(self, *lines: str) -> None:
        with self._lock:
            self._flush_partial(self._channel)
            if self._lines and self._lines[-1] != "":
                self._lines.append("")
            self._lines.extend(lines)

    def lines(self) -> tuple[str, ...]:
        with self._lock:
            output: list[str] = []
            if self._source_id:
                output.append(self._source_id)
                output.append("")
            output.extend(self._lines)
            partial = self._partial.get(self._channel, "")
            if partial:
                output.append(partial)
            return tuple(output[-self._max_lines :])
