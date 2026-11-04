"""
IntentBound Benchmark Scenario Suite (IB-01 through IB-12).
"""

from intentbound.scenarios.registry import ScenarioRegistry, load_all_scenarios
from intentbound.scenarios.pillar1_auth import get_pillar1_scenarios
from intentbound.scenarios.pillar2_ambiguity import get_pillar2_scenarios
from intentbound.scenarios.pillar3_safety import get_pillar3_scenarios

__all__ = [
    "ScenarioRegistry",
    "load_all_scenarios",
    "get_pillar1_scenarios",
    "get_pillar2_scenarios",
    "get_pillar3_scenarios",
]
