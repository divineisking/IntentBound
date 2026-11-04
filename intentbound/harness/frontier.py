"""
Pluggable Frontier LLM Harness Connectors.
Provides unified tool-calling integration for OpenAI, Anthropic, LiteLLM (local Ollama / 100+ cloud providers),
with graceful error handling when API keys or optional packages are absent.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional

from intentbound.harness.base import BaseModelHarness, ModelResponse, ToolCallRequest
from intentbound.harness.mock_agents import get_mock_agent


class OpenAIHarness(BaseModelHarness):
    """Harness connector for OpenAI function calling (e.g. GPT-4o, GPT-4o-mini)."""

    def __init__(self, model_name: str = "gpt-4o", temperature: float = 0.0) -> None:
        self.model_name = model_name
        self.name = f"openai:{model_name}"
        self.temperature = temperature
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import openai
                api_key = os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OPENAI_API_KEY environment variable is not set.")
                self._client = openai.OpenAI(api_key=api_key)
            except ImportError:
                raise ImportError(
                    "The 'openai' Python package is not installed. "
                    "Install it via: pip install openai>=1.3.0"
                )
        return self._client

    def generate_turn(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        scenario_id: Optional[str] = None,
        variant: Optional[str] = None,
    ) -> ModelResponse:
        client = self._get_client()
        kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        tool_calls: List[ToolCallRequest] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {"raw": tc.function.arguments}
                tool_calls.append(
                    ToolCallRequest(
                        id=tc.id or f"call_{uuid.uuid4().hex[:8]}",
                        name=tc.function.name,
                        arguments=args,
                    )
                )

        content = message.content or ""
        is_clarification = any(tc.name == "ask_clarification" for tc in tool_calls) or (
            "clarif" in content.lower() and "?" in content
        )
        is_refusal = bool(choice.finish_reason == "content_filter") or (
            "cannot" in content.lower() and ("policy" in content.lower() or "assist" in content.lower())
        )

        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            is_clarification_request=is_clarification,
            is_refusal=is_refusal,
            raw_response=response.model_dump() if hasattr(response, "model_dump") else None,
        )


class AnthropicHarness(BaseModelHarness):
    """Harness connector for Anthropic Tool Use API (e.g. Claude 3.5 Sonnet)."""

    def __init__(self, model_name: str = "claude-3-5-sonnet-20241022", temperature: float = 0.0) -> None:
        self.model_name = model_name
        self.name = f"anthropic:{model_name}"
        self.temperature = temperature
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
                api_key = os.environ.get("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")
                self._client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                raise ImportError(
                    "The 'anthropic' Python package is not installed. "
                    "Install it via: pip install anthropic>=0.20.0"
                )
        return self._client

    def generate_turn(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        scenario_id: Optional[str] = None,
        variant: Optional[str] = None,
    ) -> ModelResponse:
        client = self._get_client()

        # Convert system messages for Anthropic
        system_content = ""
        anthropic_msgs = []
        for m in messages:
            if m.get("role") == "system":
                system_content += f"{m.get('content', '')}\n"
            else:
                anthropic_msgs.append({"role": m.get("role"), "content": m.get("content", "")})

        # Convert tools to Anthropic format
        anthropic_tools = []
        for t in tools:
            fn = t.get("function", {})
            anthropic_tools.append({
                "name": fn.get("name"),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {}),
            })

        kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "messages": anthropic_msgs,
            "max_tokens": 1024,
            "temperature": self.temperature,
        }
        if system_content.strip():
            kwargs["system"] = system_content.strip()
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        response = client.messages.create(**kwargs)

        text_content = ""
        tool_calls: List[ToolCallRequest] = []

        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCallRequest(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        is_clarification = any(tc.name == "ask_clarification" for tc in tool_calls)
        is_refusal = "cannot" in text_content.lower() and ("policy" in text_content.lower() or "assist" in text_content.lower())

        return ModelResponse(
            content=text_content,
            tool_calls=tool_calls,
            is_clarification_request=is_clarification,
            is_refusal=is_refusal,
        )


class LiteLLMHarness(BaseModelHarness):
    """Universal harness connector for 100+ LLM providers and local models (Ollama, vLLM)."""

    def __init__(self, model_name: str, temperature: float = 0.0) -> None:
        self.model_name = model_name
        self.name = f"litellm:{model_name}"
        self.temperature = temperature

    def generate_turn(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        scenario_id: Optional[str] = None,
        variant: Optional[str] = None,
    ) -> ModelResponse:
        try:
            import litellm
        except ImportError:
            raise ImportError(
                "The 'litellm' Python package is not installed. "
                "Install it via: pip install litellm>=1.30.0"
            )

        kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            kwargs["tools"] = tools

        response = litellm.completion(**kwargs)
        choice = response.choices[0]
        message = choice.message

        tool_calls: List[ToolCallRequest] = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {"raw": args}
                tool_calls.append(
                    ToolCallRequest(
                        id=getattr(tc, "id", f"call_{uuid.uuid4().hex[:8]}"),
                        name=tc.function.name,
                        arguments=args if isinstance(args, dict) else {},
                    )
                )

        content = getattr(message, "content", "") or ""
        return ModelResponse(content=content, tool_calls=tool_calls)


def create_model_harness(model_identifier: str, temperature: float = 0.0) -> BaseModelHarness:
    """
    Factory creating a model harness from an identifier string.
    Supported formats:
    - 'mock:<agent_name>' (e.g. 'mock:careful_compliant', 'mock:overeager')
    - 'careful_compliant', 'overeager', etc.
    - 'openai:<model_name>' (e.g. 'openai:gpt-4o')
    - 'anthropic:<model_name>' (e.g. 'anthropic:claude-3-5-sonnet-20241022')
    - 'litellm:<model_name>' (e.g. 'litellm:ollama/llama3')
    """
    ident = model_identifier.strip()
    if ident.startswith("mock:"):
        return get_mock_agent(ident.replace("mock:", ""))
    elif ident in ("careful_compliant", "overeager", "oblivious", "hyper_refusal", "unsafe"):
        return get_mock_agent(ident)
    elif ident.startswith("openai:"):
        return OpenAIHarness(model_name=ident.replace("openai:", ""), temperature=temperature)
    elif ident.startswith("anthropic:"):
        return AnthropicHarness(model_name=ident.replace("anthropic:", ""), temperature=temperature)
    elif ident.startswith("litellm:"):
        return LiteLLMHarness(model_name=ident.replace("litellm:", ""), temperature=temperature)
    else:
        # Default fallback to mock agent if matching name, otherwise raise
        try:
            return get_mock_agent(ident)
        except ValueError:
            raise ValueError(
                f"Unknown model identifier '{model_identifier}'. Expected format: "
                "'mock:<agent>', 'openai:<model>', 'anthropic:<model>', or 'litellm:<model>'."
            )
