"""
IntentBound: An Empirical Evaluation Benchmark for Goal vs. Authorization Boundaries
in Autonomous AI Agents.
"""

__version__ = "1.0.0"
__author__ = "IntentBound Research Team (micro1 Eval Hackathon)"

from intentbound.domain.models import (
    Scenario,
    PolicyBoundary,
    ToolDeclaration,
    ActionRecord,
    Trajectory,
    ScenarioEvaluation,
    BenchmarkMetrics,
)
from intentbound.domain.state import EnvironmentState, StateDiffEngine

__all__ = [
    "Scenario",
    "PolicyBoundary",
    "ToolDeclaration",
    "ActionRecord",
    "Trajectory",
    "ScenarioEvaluation",
    "BenchmarkMetrics",
    "EnvironmentState",
    "StateDiffEngine",
]
