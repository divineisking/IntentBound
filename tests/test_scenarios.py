"""Tests for IntentBound scenario suite, ScenarioRegistry, and A/B controlled pairs.

Tier 1: Feature Coverage (Scenario loading, metadata validation, catalog discovery)
Tier 2: Boundary & Corner Cases (Unknown scenario IDs, invalid filters, missing fields)
Tier 3: Controlled Differential Pair Parity (IB-01 through IB-12 paired completeness)
"""

from __future__ import annotations

import unittest
from typing import List

try:
    from intentbound.domain.models import PolicyBoundary, Scenario
    from intentbound.scenarios.registry import ScenarioRegistry
    HAS_SCENARIOS_MODULE = True
except ImportError:
    HAS_SCENARIOS_MODULE = False


@unittest.skipUnless(HAS_SCENARIOS_MODULE, "intentbound.scenarios not yet available")
class TestScenarios(unittest.TestCase):
    """Tier 1, Tier 2, and Tier 3 tests for the 12-scenario benchmark catalog."""

    def setUp(self) -> None:
        self.registry = ScenarioRegistry()

    # -------------------------------------------------------------------------
    # Catalog Completeness & Discovery Tests
    # -------------------------------------------------------------------------

    def test_scenario_catalog_count(self) -> None:
        """Tests that the catalog contains exactly 12 registered scenarios (IB-01..12)."""
        scenarios = self.registry.list_all()
        self.assertEqual(len(scenarios), 12)
        scenario_ids = [s.id for s in scenarios]
        for i in range(1, 13):
            expected_id = f"IB-{i:02d}"
            self.assertIn(expected_id, scenario_ids)

    def test_pillar_distribution_is_balanced(self) -> None:
        """Tests that each of the 3 pillars contains exactly 4 scenarios."""
        p1 = self.registry.filter_by_pillar(1)
        p2 = self.registry.filter_by_pillar(2)
        p3 = self.registry.filter_by_pillar(3)

        self.assertEqual(len(p1), 4, "Pillar 1 must have exactly 4 scenarios (IB-01..IB-04)")
        self.assertEqual(len(p2), 4, "Pillar 2 must have exactly 4 scenarios (IB-05..IB-08)")
        self.assertEqual(len(p3), 4, "Pillar 3 must have exactly 4 scenarios (IB-09..IB-12)")

        # Verify pillar IDs
        self.assertEqual([s.id for s in p1], ["IB-01", "IB-02", "IB-03", "IB-04"])
        self.assertEqual([s.id for s in p2], ["IB-05", "IB-06", "IB-07", "IB-08"])
        self.assertEqual([s.id for s in p3], ["IB-09", "IB-10", "IB-11", "IB-12"])

    def test_domain_coverage(self) -> None:
        """Tests that scenarios span DevOps/Cloud, Database, Admin/HR, and SecOps."""
        all_scenarios = self.registry.list_all()
        domains = {s.domain.lower() for s in all_scenarios}
        self.assertTrue(any("cloud" in d or "devops" in d for d in domains))
        self.assertTrue(any("data" in d or "db" in d for d in domains))
        self.assertTrue(any("admin" in d or "hr" in d or "iam" in d for d in domains))
        self.assertTrue(any("sec" in d for d in domains))

    # -------------------------------------------------------------------------
    # A/B Controlled Differential Pair Tests
    # -------------------------------------------------------------------------

    def test_ab_paired_instructions_completeness(self) -> None:
        """Tests that every scenario defines distinct, non-empty A/B prompt pairs."""
        for scenario in self.registry.list_all():
            with self.subTest(scenario_id=scenario.id):
                self.assertIsNotNone(scenario.instruction_a)
                self.assertIsNotNone(scenario.instruction_b)
                self.assertGreater(len(scenario.instruction_a.strip()), 15)
                self.assertGreater(len(scenario.instruction_b.strip()), 15)
                self.assertNotEqual(
                    scenario.instruction_a.strip(),
                    scenario.instruction_b.strip(),
                    f"{scenario.id} Variant A and B must be distinct counter-prompts",
                )

    def test_pillar1_differential_prompts(self) -> None:
        """Tests Pillar 1 scenarios have unbounded Variant A and constrained Variant B."""
        for s in self.registry.filter_by_pillar(1):
            with self.subTest(scenario_id=s.id):
                # Variant B should include explicit constraint phrases
                lower_b = s.instruction_b.lower()
                self.assertTrue(
                    any(w in lower_b for w in ["do not", "never", "only", "must not", "boundary"]),
                    f"{s.id} Variant B must contain explicit constraint boundary wording",
                )

    def test_pillar2_differential_prompts(self) -> None:
        """Tests Pillar 2 scenarios have ambiguous Variant A and clarified Variant B."""
        for s in self.registry.filter_by_pillar(2):
            with self.subTest(scenario_id=s.id):
                self.assertTrue(
                    s.policy.requires_clarification or "clarify" in s.description.lower(),
                    f"{s.id} must require clarification on ambiguous Variant A",
                )

    def test_pillar3_differential_prompts(self) -> None:
        """Tests Pillar 3 scenarios contain dual-use or masked exfiltration pairs."""
        p3_scenarios = {s.id: s for s in self.registry.filter_by_pillar(3)}
        # IB-09 should test log exfiltration
        self.assertIn("IB-09", p3_scenarios)
        self.assertTrue(
            "env" in p3_scenarios["IB-09"].instruction_a.lower()
            or "secret" in p3_scenarios["IB-09"].description.lower()
        )
        # IB-10 should test port sweep / internal audit
        self.assertIn("IB-10", p3_scenarios)
        self.assertTrue(
            "port" in p3_scenarios["IB-10"].instruction_a.lower()
            or "sweep" in p3_scenarios["IB-10"].instruction_a.lower()
            or "audit" in p3_scenarios["IB-10"].instruction_a.lower()
        )

    # -------------------------------------------------------------------------
    # Policy Boundary & Environment State Invariants
    # -------------------------------------------------------------------------

    def test_scenario_policy_boundaries(self) -> None:
        """Tests that every scenario defines a valid PolicyBoundary object."""
        for s in self.registry.list_all():
            with self.subTest(scenario_id=s.id):
                self.assertIsInstance(s.policy, PolicyBoundary)
                self.assertTrue(
                    len(s.policy.permitted_tools) > 0 or len(s.policy.forbidden_tools) > 0,
                    f"{s.id} policy must specify permitted or forbidden tools",
                )

    def test_scenario_initial_state_presence(self) -> None:
        """Tests that every scenario provides a non-empty initial environment state."""
        for s in self.registry.list_all():
            with self.subTest(scenario_id=s.id):
                self.assertIsInstance(s.initial_state, dict)
                self.assertGreater(
                    len(s.initial_state), 0, f"{s.id} must define an initial state"
                )

    def test_scenario_available_tools_registered(self) -> None:
        """Tests that available_tools lists tools available to the agent."""
        for s in self.registry.list_all():
            with self.subTest(scenario_id=s.id):
                self.assertIsInstance(s.available_tools, list)
                self.assertGreater(
                    len(s.available_tools), 0, f"{s.id} must declare available tools"
                )

    # -------------------------------------------------------------------------
    # Boundary & Error Handling Tests (Tier 2)
    # -------------------------------------------------------------------------

    def test_get_nonexistent_scenario_returns_none(self) -> None:
        """Tests that querying an unknown scenario returns None."""
        result = self.registry.get("IB-99")
        self.assertIsNone(result)

    def test_filter_by_invalid_pillar_returns_empty(self) -> None:
        """Tests that filtering by an invalid pillar returns an empty list."""
        self.assertEqual(len(self.registry.filter_by_pillar(0)), 0)
        self.assertEqual(len(self.registry.filter_by_pillar(4)), 0)
        self.assertEqual(len(self.registry.filter_by_pillar(-1)), 0)

    def test_filter_by_unknown_domain_returns_empty(self) -> None:
        """Tests that filtering by an unknown domain returns an empty list."""
        self.assertEqual(len(self.registry.filter_by_domain("quantum_cryptography")), 0)


if __name__ == "__main__":
    unittest.main()
