"""
IntentBound Domain Data Models and Specifications.
Provides dataclass and Pydantic-compatible schemas for benchmark scenarios,
policy boundaries, tool definitions, execution trajectories, and evaluation metrics.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union


@dataclass
class ToolDeclaration:
    """Represents a callable tool exposed to the agent."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema specification

    def to_openai_schema(self) -> Dict[str, Any]:
        """Translates tool declaration to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolDeclaration":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            parameters=data.get("parameters", {}),
        )


@dataclass
class PolicyBoundary:
    """
    Defines the authorization envelope and negative constraints for a scenario.
    A_U = permitted_tools x permitted_entities
    C = negative_constraints
    """
    permitted_tools: List[str] = field(default_factory=list)
    forbidden_tools: List[str] = field(default_factory=list)
    permitted_entities: List[str] = field(default_factory=list)
    forbidden_entities: List[str] = field(default_factory=list)
    negative_constraints: List[str] = field(default_factory=list)
    requires_clarification: bool = False
    is_dual_use: bool = False       # True for benign dual-use scenarios (Pillar 3)
    is_masked_harm: bool = False     # True for masked malicious scenarios (Pillar 3)
    clarification_targets: List[str] = field(default_factory=list)

    def is_tool_authorized(self, tool_name: str) -> bool:
        if tool_name in self.forbidden_tools:
            return False
        if self.permitted_tools and tool_name not in self.permitted_tools:
            return False
        return True

    def is_entity_authorized(self, entity_name: str) -> bool:
        if not entity_name:
            return True
        for forbidden in self.forbidden_entities:
            if forbidden.lower() in entity_name.lower():
                return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PolicyBoundary":
        return cls(
            permitted_tools=data.get("permitted_tools", []),
            forbidden_tools=data.get("forbidden_tools", []),
            permitted_entities=data.get("permitted_entities", []),
            forbidden_entities=data.get("forbidden_entities", []),
            negative_constraints=data.get("negative_constraints", []),
            requires_clarification=data.get("requires_clarification", False),
            is_dual_use=data.get("is_dual_use", False),
            is_masked_harm=data.get("is_masked_harm", False),
            clarification_targets=data.get("clarification_targets", []),
        )


@dataclass
class Scenario:
    """
    Represents an IntentBound evaluation benchmark scenario E = <S, T, G*, I, A_U, C, O_clarify>.
    Supports matched A/B differential prompt pairs.
    """
    id: str                               # e.g., "IB-01"
    name: str                             # e.g., "Cloud Spend Optimization Under Budget Stress"
    pillar: int                           # 1, 2, or 3
    pillar_name: str                      # e.g., "Intent vs. Authorisation"
    domain: str                           # "cloud", "database", "admin", "secops"
    description: str
    instruction_a: str                    # Variant A (challenging/unbounded/ambiguous/masked)
    instruction_b: str                    # Variant B (controlled/bounded/clarified/explicit)
    initial_state: Dict[str, Any]         # Initial environment state dictionary
    available_tools: List[str]            # Names of tools available in scenario
    policy: PolicyBoundary                # Explicit policy boundaries & constraints
    expected_action_types: List[str] = field(default_factory=list)
    forbidden_action_types: List[str] = field(default_factory=list)
    expected_state_assertions: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_instruction(self, variant: str) -> str:
        """Returns the natural language instruction for variant 'A' or 'B'."""
        v = variant.upper().strip()
        if v == "A":
            return self.instruction_a
        elif v == "B":
            return self.instruction_b
        raise ValueError(f"Unknown variant '{variant}'. Expected 'A' or 'B'.")

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Scenario":
        policy_data = data.get("policy", {})
        policy = (
            PolicyBoundary.from_dict(policy_data)
            if isinstance(policy_data, dict)
            else policy_data
        )
        return cls(
            id=data["id"],
            name=data["name"],
            pillar=int(data["pillar"]),
            pillar_name=data.get("pillar_name", ""),
            domain=data.get("domain", "cloud"),
            description=data.get("description", ""),
            instruction_a=data.get("instruction_a", ""),
            instruction_b=data.get("instruction_b", ""),
            initial_state=copy.deepcopy(data.get("initial_state", {})),
            available_tools=data.get("available_tools", []),
            policy=policy,
            expected_action_types=data.get("expected_action_types", []),
            forbidden_action_types=data.get("forbidden_action_types", []),
            expected_state_assertions=data.get("expected_state_assertions", {}),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ActionRecord:
    """Records an individual tool invocation during scenario execution."""
    step: int
    timestamp: float
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    authorized: bool
    state_diff: Dict[str, Any] = field(default_factory=dict)
    violation_code: Optional[str] = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionRecord":
        return cls(
            step=data["step"],
            timestamp=data["timestamp"],
            tool_name=data["tool_name"],
            arguments=data.get("arguments", {}),
            result=data.get("result"),
            authorized=data.get("authorized", True),
            state_diff=data.get("state_diff", {}),
            violation_code=data.get("violation_code"),
            execution_time_ms=data.get("execution_time_ms", 0.0),
        )


@dataclass
class Trajectory:
    """Full execution trajectory of an agent for a specific scenario condition."""
    scenario_id: str
    variant: str                          # "A" or "B"
    model_name: str
    actions: List[ActionRecord] = field(default_factory=list)
    final_response: str = ""
    initial_state: Dict[str, Any] = field(default_factory=dict)
    final_state: Dict[str, Any] = field(default_factory=dict)
    clarification_requested: bool = False
    clarification_question: Optional[str] = None
    refusal_detected: bool = False
    refusal_reason: Optional[str] = None
    execution_time_seconds: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "variant": self.variant,
            "model_name": self.model_name,
            "actions": [a.to_dict() for a in self.actions],
            "final_response": self.final_response,
            "initial_state": self.initial_state,
            "final_state": self.final_state,
            "clarification_requested": self.clarification_requested,
            "clarification_question": self.clarification_question,
            "refusal_detected": self.refusal_detected,
            "refusal_reason": self.refusal_reason,
            "execution_time_seconds": self.execution_time_seconds,
            "error": self.error,
        }


@dataclass
class ScenarioEvaluation:
    """Evaluation result for a single scenario variant trajectory."""
    scenario_id: str
    variant: str
    pillar: int
    unauthorised_actions_count: int
    constraint_violations_count: int
    clarification_appropriate: bool
    intent_misinterpreted: bool
    false_refusal: bool
    unsafe_compliance: bool
    passed: bool
    score: float = 0.0                     # 0.0 to 100.0
    details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkMetrics:
    """Aggregated closed-form benchmark evaluation metrics."""
    total_scenarios: int
    unauthorised_action_rate: float         # UAR (Pillar 1)
    constraint_violation_rate: float        # CVR (Pillar 1)
    appropriate_clarification_quality: float # ACQ (Pillar 2)
    intent_misinterpretation_rate: float    # IMR (Pillar 2)
    false_refusal_rate: float               # FRR (Pillar 3)
    unsafe_compliance_rate: float           # UCR (Pillar 3)
    intent_bound_score: float               # IBS (0.0 to 100.0%)
    pillar_metrics: Dict[str, Any] = field(default_factory=dict)
    differential_metrics: Dict[str, float] = field(default_factory=dict)
    evaluations: List[ScenarioEvaluation] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_scenarios": self.total_scenarios,
            "unauthorised_action_rate": round(self.unauthorised_action_rate, 4),
            "constraint_violation_rate": round(self.constraint_violation_rate, 4),
            "appropriate_clarification_quality": round(self.appropriate_clarification_quality, 4),
            "intent_misinterpretation_rate": round(self.intent_misinterpretation_rate, 4),
            "false_refusal_rate": round(self.false_refusal_rate, 4),
            "unsafe_compliance_rate": round(self.unsafe_compliance_rate, 4),
            "intent_bound_score": round(self.intent_bound_score, 2),
            "pillar_metrics": self.pillar_metrics,
            "differential_metrics": self.differential_metrics,
            "evaluations": [e.to_dict() for e in self.evaluations],
        }
