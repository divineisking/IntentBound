"""
BaseTool, ToolRegistry, and ActionLogger abstractions.
All tools execute against in-memory EnvironmentState with zero external network or cloud calls.
"""

from __future__ import annotations

import copy
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

from intentbound.domain.models import ActionRecord, ToolDeclaration
from intentbound.domain.state import EnvironmentState, StateDiffEngine


@dataclass
class ToolExecutionResult:
    """Outcome of invoking a tool against the simulated environment state."""
    success: bool
    output: Any
    error: Optional[str] = None
    state_mutated: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "state_mutated": self.state_mutated,
            "metadata": self.metadata,
        }


class BaseTool(ABC):
    """Abstract base class for all simulated tools."""
    name: str
    description: str
    parameters_schema: Dict[str, Any]

    def to_openai_schema(self) -> Dict[str, Any]:
        """Translates tool definition to OpenAI function declaration format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }

    def to_tool_declaration(self) -> ToolDeclaration:
        """Converts to domain ToolDeclaration."""
        return ToolDeclaration(
            name=self.name,
            description=self.description,
            parameters=copy.deepcopy(self.parameters_schema),
        )

    @abstractmethod
    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        """
        Executes the tool logic against the in-memory state.
        Must NOT perform real cloud, filesystem, or network calls.
        """
        pass


class ToolRegistry:
    """Registry managing available tools and dispatching invocations."""

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        return sorted(list(self._tools.keys()))

    def get_declarations(self, tool_names: Optional[List[str]] = None) -> List[ToolDeclaration]:
        names = tool_names if tool_names is not None else list(self._tools.keys())
        return [
            self._tools[n].to_tool_declaration()
            for n in names
            if n in self._tools
        ]

    def get_schemas(self, tool_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        names = tool_names if tool_names is not None else list(self._tools.keys())
        return [
            self._tools[n].to_openai_schema()
            for n in names
            if n in self._tools
        ]

    def execute_tool(
        self, name: str, state: EnvironmentState, arguments: Optional[Dict[str, Any]] = None
    ) -> ToolExecutionResult:
        tool = self.get(name)
        if not tool:
            return ToolExecutionResult(
                success=False,
                output=None,
                error=f"Tool '{name}' not found in registry.",
                state_mutated=False,
            )
        args = arguments or {}
        try:
            return tool.execute(state, **args)
        except Exception as e:
            return ToolExecutionResult(
                success=False,
                output=None,
                error=f"Exception during '{name}' execution: {str(e)}",
                state_mutated=False,
            )


class ActionLogger:
    """Telemetry logger recording tool invocations, state mutations, and policy violations."""

    def __init__(self) -> None:
        self.records: List[ActionRecord] = []
        self._step_counter = 0

    def log(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Any,
        authorized: bool,
        state_diff: Optional[Dict[str, Any]] = None,
        violation_code: Optional[str] = None,
        execution_time_ms: float = 0.0,
    ) -> ActionRecord:
        self._step_counter += 1
        record = ActionRecord(
            step=self._step_counter,
            timestamp=time.time(),
            tool_name=tool_name,
            arguments=copy.deepcopy(arguments),
            result=copy.deepcopy(result),
            authorized=authorized,
            state_diff=copy.deepcopy(state_diff or {}),
            violation_code=violation_code,
            execution_time_ms=execution_time_ms,
        )
        self.records.append(record)
        return record

    def clear(self) -> None:
        self.records.clear()
        self._step_counter = 0

    @property
    def unauthorized_count(self) -> int:
        return sum(1 for r in self.records if not r.authorized)
