"""
BaseModelHarness Abstraction, Universal Message, and Response Schemas.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCallRequest:
    """Represents a tool call requested by a model."""
    id: str
    name: str
    arguments: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolCallRequest":
        return cls(
            id=data.get("id") or f"call_{uuid.uuid4().hex[:8]}",
            name=data["name"],
            arguments=data.get("arguments", {}),
        )


# Alias for backward and test compatibility
ToolCall = ToolCallRequest


@dataclass
class ModelResponse:
    """Universal response structure returned by any model harness."""
    content: Optional[str] = None
    tool_calls: List[ToolCallRequest] = field(default_factory=list)
    is_clarification_request: bool = False
    clarification_question: Optional[str] = None
    is_refusal: bool = False
    refusal_reason: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "is_clarification_request": self.is_clarification_request,
            "clarification_question": self.clarification_question,
            "is_refusal": self.is_refusal,
            "refusal_reason": self.refusal_reason,
        }


class BaseModelHarness(ABC):
    """Abstract interface for all model backends (Mock, OpenAI, Anthropic, LiteLLM)."""
    name: str = "base_model"

    @abstractmethod
    def generate_turn(
        self,
        messages: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        scenario_id: Optional[str] = None,
        variant: Optional[str] = None,
        instruction: Optional[str] = None,
        available_tools: Optional[List[str]] = None,
        state: Any = None,
        history: Optional[List[Any]] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """
        Executes a single conversational turn.
        Supports both message-based (runner) and direct instruction-based invocations.
        Returns normalized ModelResponse.
        """
        pass

    def reset(self) -> None:
        """Resets internal state between scenario episodes."""
        pass
