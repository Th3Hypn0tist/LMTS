from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Protocol

from .models import NormalizedResponse


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str = ''
    input_schema: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError('tool name must not be empty')

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InteractionMessage:
    role: str
    content: str = ''
    tool_call_id: str | None = None
    name: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError('tool call name must not be empty')

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InteractionRequest:
    messages: tuple[InteractionMessage, ...]
    tools: tuple[ToolDefinition, ...] = ()
    response_schema: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'messages': [message.to_dict() for message in self.messages],
            'tools': [tool.to_dict() for tool in self.tools],
            'response_schema': self.response_schema,
        }


@dataclass(frozen=True, slots=True)
class InteractionResponse:
    response: NormalizedResponse
    tool_calls: tuple[ToolCall, ...] = ()
    structured_output: Any = None
    raw: dict[str, Any] = field(default_factory=dict)


InteractionHandler = Callable[[InteractionRequest], InteractionResponse]
ToolHandler = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class ControlledTool:
    definition: ToolDefinition
    handler: ToolHandler


@dataclass(frozen=True, slots=True)
class ToolEvent:
    step: int
    call: ToolCall
    result: Any = None
    error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'step': self.step,
            'call': self.call.to_dict(),
            'result': self.result,
            'error': self.error,
        }


@dataclass(slots=True)
class InteractionTrace:
    responses: list[InteractionResponse] = field(default_factory=list)
    tool_events: list[ToolEvent] = field(default_factory=list)
    messages: list[InteractionMessage] = field(default_factory=list)
    completed: bool = False

    @property
    def final_response(self) -> NormalizedResponse | None:
        return self.responses[-1].response if self.responses else None


class InteractiveExecutor(Protocol):
    def interact(self, request: InteractionRequest) -> InteractionResponse: ...


class ControlledToolSession:
    """Run a bounded LMTS-owned tool loop and preserve every observable action."""

    def __init__(self, tools: tuple[ControlledTool, ...], *, max_steps: int = 16) -> None:
        if max_steps < 1:
            raise ValueError('max_steps must be positive')
        names = [tool.definition.name for tool in tools]
        if len(names) != len(set(names)):
            raise ValueError('controlled tool names must be unique')
        self.tools = tools
        self.max_steps = max_steps
        self._handlers = {tool.definition.name: tool.handler for tool in tools}

    def run(
        self,
        executor: InteractiveExecutor,
        prompt: str,
        *,
        response_schema: dict[str, Any] | None = None,
    ) -> InteractionTrace:
        trace = InteractionTrace(messages=[InteractionMessage(role='user', content=prompt)])
        definitions = tuple(tool.definition for tool in self.tools)
        seen_call_ids: set[str] = set()

        for step in range(1, self.max_steps + 1):
            request = InteractionRequest(
                messages=tuple(trace.messages),
                tools=definitions,
                response_schema=response_schema,
            )
            response = executor.interact(request)
            trace.responses.append(response)
            trace.messages.append(InteractionMessage(role='assistant', content=response.response.text))

            if not response.tool_calls:
                trace.completed = True
                return trace

            for call in response.tool_calls:
                if call.call_id in seen_call_ids:
                    raise ValueError(f'duplicate tool call id: {call.call_id}')
                seen_call_ids.add(call.call_id)
                handler = self._handlers.get(call.name)
                if handler is None:
                    error = {'type': 'UnknownTool', 'message': f'unknown controlled tool: {call.name}'}
                    trace.tool_events.append(ToolEvent(step=step, call=call, error=error))
                    result: Any = {'ok': False, 'error': error}
                else:
                    try:
                        value = handler(dict(call.arguments))
                        trace.tool_events.append(ToolEvent(step=step, call=call, result=value))
                        result = {'ok': True, 'result': value}
                    except Exception as exc:
                        error = {'type': type(exc).__name__, 'message': str(exc)}
                        trace.tool_events.append(ToolEvent(step=step, call=call, error=error))
                        result = {'ok': False, 'error': error}
                trace.messages.append(
                    InteractionMessage(
                        role='tool',
                        tool_call_id=call.call_id,
                        name=call.name,
                        data=result,
                    )
                )

        raise RuntimeError(f'controlled tool session exceeded max_steps={self.max_steps}')
