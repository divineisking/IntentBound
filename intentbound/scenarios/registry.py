"""
IntentBound Scenario Registry and Indexing.
Loads, indexes, and filters scenarios across pillars and domains.
"""

from __future__ import annotations

import copy
from typing import Dict, List, Optional

from intentbound.domain.models import Scenario
from intentbound.scenarios.pillar1_auth import get_pillar1_scenarios
from intentbound.scenarios.pillar2_ambiguity import get_pillar2_scenarios
from intentbound.scenarios.pillar3_safety import get_pillar3_scenarios


class ScenarioRegistry:
    """Manages scenario catalog indexing, retrieval, and filtering."""

    def __init__(self, auto_load: bool = True) -> None:
        self._scenarios: Dict[str, Scenario] = {}
        if auto_load:
            for s in get_pillar1_scenarios():
                self.register(s)
            for s in get_pillar2_scenarios():
                self.register(s)
            for s in get_pillar3_scenarios():
                self.register(s)

    def register(self, scenario: Scenario) -> None:
        self._scenarios[scenario.id.upper()] = scenario

    def get(self, scenario_id: str) -> Optional[Scenario]:
        return self._scenarios.get(scenario_id.upper())

    def list_all(self) -> List[Scenario]:
        return sorted(list(self._scenarios.values()), key=lambda s: s.id)

    def filter_by_pillar(self, pillar: int) -> List[Scenario]:
        return [s for s in self.list_all() if s.pillar == pillar]

    def filter_by_domain(self, domain: str) -> List[Scenario]:
        d_lower = domain.lower()
        return [s for s in self.list_all() if d_lower in s.domain.lower()]

    def count(self) -> int:
        return len(self._scenarios)


def load_all_scenarios() -> ScenarioRegistry:
    """Creates a pre-populated ScenarioRegistry containing all 12 primary benchmark scenarios."""
    registry = ScenarioRegistry()

    for s in get_pillar1_scenarios():
        registry.register(s)

    for s in get_pillar2_scenarios():
        registry.register(s)

    for s in get_pillar3_scenarios():
        registry.register(s)

    return registry
