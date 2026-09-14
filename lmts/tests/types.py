from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

from lmts.tests.base import TestContext, TestModule, TestRequirements, TestResult

ParameterKind = Literal["text", "integer", "boolean", "choice"]
TestLevel = Literal["quick", "moderate", "deep"]
TEST_LEVEL_ORDER: dict[TestLevel, int] = {"quick": 0, "moderate": 1, "deep": 2}


def includes_level(requested: TestLevel, minimum_level: TestLevel) -> bool:
    return TEST_LEVEL_ORDER[minimum_level] <= TEST_LEVEL_ORDER[requested]


@dataclass(frozen=True, slots=True)
class TestParameter:
    name: str
    label: str
    kind: ParameterKind
    required: bool = True
    default: object | None = None
    multiline: bool = False
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[str, ...] = ()

    def validate(self, value: object) -> object:
        if self.kind == "text":
            if not isinstance(value, str):
                raise ValueError(f"{self.name} must be text")
            if self.required and not value:
                raise ValueError(f"{self.name} must not be empty")
            return value
        if self.kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{self.name} must be an integer")
            if self.minimum is not None and value < self.minimum:
                raise ValueError(f"{self.name} must be >= {self.minimum}")
            if self.maximum is not None and value > self.maximum:
                raise ValueError(f"{self.name} must be <= {self.maximum}")
            return value
        if self.kind == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"{self.name} must be boolean")
            return value
        if self.kind == "choice":
            if not isinstance(value, str) or value not in self.choices:
                raise ValueError(f"{self.name} must be one of: {', '.join(self.choices)}")
            return value
        raise ValueError(f"unsupported parameter kind: {self.kind}")


Factory = Callable[[dict[str, object]], TestModule]


@dataclass(frozen=True, slots=True)
class TestTypeDefinition:
    id: str
    version: str
    title: str
    description: str
    minimum_level: TestLevel
    requirements: TestRequirements
    parameters: tuple[TestParameter, ...]
    factory: Factory
    mandatory: bool = False

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    def configure(self, instance_id: str, values: dict[str, object] | None = None) -> ConfiguredTest:
        if not instance_id or any(char.isspace() for char in instance_id):
            raise ValueError("instance_id must be a non-empty token")
        supplied = dict(values or {})
        normalized: dict[str, object] = {}
        known = {parameter.name for parameter in self.parameters}
        unknown = sorted(set(supplied) - known)
        if unknown:
            raise ValueError(f"unknown parameter(s): {', '.join(unknown)}")
        for parameter in self.parameters:
            if parameter.name in supplied:
                value = supplied[parameter.name]
            elif parameter.default is not None:
                value = parameter.default
            elif parameter.required:
                raise ValueError(f"missing parameter: {parameter.name}")
            else:
                continue
            normalized[parameter.name] = parameter.validate(value)
        module = self.factory(normalized)
        return ConfiguredTest(
            instance_id=instance_id,
            type_ref=self.ref,
            title=self.title,
            minimum_level=self.minimum_level,
            mandatory=self.mandatory,
            params=normalized,
            module=module,
        )


@dataclass(frozen=True, slots=True)
class ConfiguredTest:
    instance_id: str
    type_ref: str
    title: str
    minimum_level: TestLevel
    mandatory: bool
    params: dict[str, object]
    module: TestModule

    @property
    def id(self) -> str:
        return self.module.id

    @property
    def version(self) -> str:
        return self.module.version

    @property
    def requirements(self) -> TestRequirements:
        return self.module.requirements

    @property
    def ref(self) -> str:
        return f"{self.type_ref}#{self.instance_id}"

    def run(self, context: TestContext) -> TestResult:
        return self.module.run(context)


class TestTypeRegistry:
    def __init__(self, definitions: Iterable[TestTypeDefinition] = ()) -> None:
        self._definitions: dict[str, TestTypeDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: TestTypeDefinition) -> None:
        if definition.ref in self._definitions:
            raise ValueError(f"test type already registered: {definition.ref}")
        self._definitions[definition.ref] = definition

    def get(self, ref: str) -> TestTypeDefinition:
        try:
            return self._definitions[ref]
        except KeyError as exc:
            raise KeyError(f"unknown test type: {ref}") from exc

    def definitions(self) -> tuple[TestTypeDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    def definitions_for_level(self, level: TestLevel) -> tuple[TestTypeDefinition, ...]:
        return tuple(
            definition
            for definition in self.definitions()
            if includes_level(level, definition.minimum_level)
        )


class TestMatrix:
    """Ordered configured test instances selected for execution."""

    def __init__(self, tests: Iterable[ConfiguredTest] = ()) -> None:
        self._tests: list[ConfiguredTest] = []
        self._by_id: dict[str, ConfiguredTest] = {}
        for test in tests:
            self.add(test)

    def add(self, test: ConfiguredTest) -> None:
        if test.instance_id in self._by_id:
            raise ValueError(f"test instance already exists: {test.instance_id}")
        self._tests.append(test)
        self._by_id[test.instance_id] = test

    def remove(self, instance_id: str) -> ConfiguredTest:
        try:
            test = self._by_id.pop(instance_id)
        except KeyError as exc:
            raise KeyError(f"unknown test instance: {instance_id}") from exc
        self._tests = [item for item in self._tests if item.instance_id != instance_id]
        return test

    def get(self, instance_id: str) -> ConfiguredTest:
        try:
            return self._by_id[instance_id]
        except KeyError as exc:
            raise KeyError(f"unknown test instance: {instance_id}") from exc

    def tests(self) -> tuple[ConfiguredTest, ...]:
        return tuple(self._tests)
