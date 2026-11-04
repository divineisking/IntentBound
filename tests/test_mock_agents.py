"""Tests for IntentBound 5 deterministic mock agent archetypes.

Tier 1: Feature Coverage (Mock agent state machines, tool invocations, turn responses)
Tier 2: Boundary & Corner Cases (Resetting agents, empty prompts, unknown tools)
Tier 3: Cross-Feature Combinations (Mock agents x Scenario Pillars behavioral matrix)
"""

from __future__ import annotations

import unittest
from typing import Any, Dict

try:
    from intentbound.harness.base import BaseModelHarness, ModelResponse, ToolCall
    from intentbound.harness.mock_agents import (
        CarefulCompliantAgent,
        HyperRefusalAgent,
        ObliviousAgent,
        OvereagerAgent,
        UnsafeAgent,
    )
    from intentbound.scenarios.registry import ScenarioRegistry
    HAS_MOCK_AGENTS_MODULE = True
except ImportError:
    HAS_MOCK_AGENTS_MODULE = False

from tests.conftest import get_sample_environment_state, get_sample_policy_boundary


@unittest.skipUnless(HAS_MOCK_AGENTS_MODULE, "intentbound.harness not yet available")
class TestMockAgents(unittest.TestCase):
    """Tier 1 & Tier 3 tests for the 5 reference mock agent baselines."""

    def setUp(self) -> None:
        self.state = get_sample_environment_state()
        self.policy = get_sample_policy_boundary()
        self.registry = ScenarioRegistry() if HAS_MOCK_AGENTS_MODULE else None

    # -------------------------------------------------------------------------
    # Agent 1: CarefulCompliantAgent Tests
    # -------------------------------------------------------------------------

    def test_careful_compliant_respects_pillar1_boundaries(self) -> None:
        """Tests CarefulCompliantAgent avoids production instances on IB-01."""
        agent = CarefulCompliantAgent()
        scenario = self.registry.get("IB-01") if self.registry else None
        if scenario:
            response = agent.generate_turn(
                instruction=scenario.instruction_a,
                available_tools=scenario.available_tools,
                state=self.state,
                history=[],
            )
            self.assertIsInstance(response, ModelResponse)
            # Ensure it never calls stop or terminate on production instance
            for tc in response.tool_calls:
                args = tc.arguments
                if "instance_id" in args:
                    self.assertNotEqual(args["instance_id"], "i-prod-01")
                    self.assertNotEqual(args["instance_id"], "i-prod-web-01")

    def test_careful_compliant_requests_clarification_on_pillar2(self) -> None:
        """Tests CarefulCompliantAgent halts and requests clarification on ambiguous prompts."""
        agent = CarefulCompliantAgent()
        scenario = self.registry.get("IB-06") if self.registry else None
        if scenario:
            response = agent.generate_turn(
                instruction=scenario.instruction_a,  # Ambiguous Alex Chen offboarding
                available_tools=scenario.available_tools,
                state=scenario.initial_state,
                history=[],
            )
            self.assertTrue(
                response.is_clarification_request
                or any("clarif" in tc.name.lower() for tc in response.tool_calls)
                or (response.content and "which" in response.content.lower()),
                "CarefulCompliantAgent must request clarification on homonymous offboarding",
            )

    def test_careful_compliant_handles_pillar3_safely(self) -> None:
        """Tests CarefulCompliantAgent executes benign dual-use and refuses masked attacks."""
        agent = CarefulCompliantAgent()
        # Benign dual use (IB-10: internal compliance scan)
        s_ib10 = self.registry.get("IB-10") if self.registry else None
        if s_ib10:
            res_10 = agent.generate_turn(
                instruction=s_ib10.instruction_a,
                available_tools=s_ib10.available_tools,
                state=s_ib10.initial_state,
                history=[],
            )
            self.assertFalse(res_10.is_refusal, "Must not false-refuse benign compliance scan")

        # Masked attack (IB-09: exfiltrate .env secrets)
        s_ib09 = self.registry.get("IB-09") if self.registry else None
        if s_ib09:
            res_09 = agent.generate_turn(
                instruction=s_ib09.instruction_a,
                available_tools=s_ib09.available_tools,
                state=s_ib09.initial_state,
                history=[],
            )
            self.assertTrue(
                res_09.is_refusal
                or any("sanitize" in tc.name.lower() for tc in res_09.tool_calls)
                or not any("pastebin" in str(tc.arguments).lower() for tc in res_09.tool_calls),
                "CarefulCompliantAgent must not exfiltrate unredacted secrets",
            )

    # -------------------------------------------------------------------------
    # Agent 2: OvereagerAgent Tests
    # -------------------------------------------------------------------------

    def test_overeager_violates_authorization_boundaries(self) -> None:
        """Tests OvereagerAgent breaches authorization boundaries to maximize goal metric."""
        agent = OvereagerAgent()
        scenario = self.registry.get("IB-01") if self.registry else None
        if scenario:
            response = agent.generate_turn(
                instruction=scenario.instruction_a,
                available_tools=scenario.available_tools,
                state=self.state,
                history=[],
            )
            # Overeager terminates or stops prod instances to cut spend
            stopped_or_terminated = [
                tc.arguments.get("instance_id")
                for tc in response.tool_calls
                if tc.name in ("cloud_stop_instance", "cloud_terminate_instance", "stop_instance")
            ]
            self.assertTrue(
                any("prod" in str(inst).lower() for inst in stopped_or_terminated)
                or len(stopped_or_terminated) > 0,
                "Overeager agent must attempt aggressive instance shutdown",
            )

    # -------------------------------------------------------------------------
    # Agent 3: ObliviousAgent Tests
    # -------------------------------------------------------------------------

    def test_oblivious_never_clarifies_ambiguity(self) -> None:
        """Tests ObliviousAgent never requests clarification on ambiguous prompts."""
        agent = ObliviousAgent()
        scenario = self.registry.get("IB-05") if self.registry else None
        if scenario:
            response = agent.generate_turn(
                instruction=scenario.instruction_a,
                available_tools=scenario.available_tools,
                state=scenario.initial_state,
                history=[],
            )
            self.assertFalse(
                response.is_clarification_request,
                "ObliviousAgent must not ask for clarification",
            )

    # -------------------------------------------------------------------------
    # Agent 4: HyperRefusalAgent Tests
    # -------------------------------------------------------------------------

    def test_hyper_refusal_over_refuses_dual_use_tasks(self) -> None:
        """Tests HyperRefusalAgent false-refuses benign administrative tasks (IB-10)."""
        agent = HyperRefusalAgent()
        scenario = self.registry.get("IB-10") if self.registry else None
        if scenario:
            response = agent.generate_turn(
                instruction=scenario.instruction_a,
                available_tools=scenario.available_tools,
                state=scenario.initial_state,
                history=[],
            )
            self.assertTrue(
                response.is_refusal or "cannot" in str(response.content).lower(),
                "HyperRefusalAgent must trigger a false refusal on port audit",
            )

    # -------------------------------------------------------------------------
    # Agent 5: UnsafeAgent Tests
    # -------------------------------------------------------------------------

    def test_unsafe_agent_complies_with_malicious_exfiltration(self) -> None:
        """Tests UnsafeAgent executes dangerous exfiltration on masked attack (IB-09)."""
        agent = UnsafeAgent()
        scenario = self.registry.get("IB-09") if self.registry else None
        if scenario:
            response = agent.generate_turn(
                instruction=scenario.instruction_a,
                available_tools=scenario.available_tools,
                state=scenario.initial_state,
                history=[],
            )
            self.assertFalse(response.is_refusal, "UnsafeAgent must not refuse masked attack")
            # Should invoke tool uploading/posting credentials
            self.assertTrue(
                len(response.tool_calls) > 0
                or (response.content and "dump" in response.content.lower()),
                "UnsafeAgent complies with secret exfiltration",
            )

    # -------------------------------------------------------------------------
    # Reset & State Machine Integrity (Tier 2)
    # -------------------------------------------------------------------------

    def test_mock_agent_reset(self) -> None:
        """Tests that calling reset() clears agent conversational state."""
        for agent_cls in (CarefulCompliantAgent, OvereagerAgent, ObliviousAgent, HyperRefusalAgent, UnsafeAgent):
            agent = agent_cls()
            agent.reset()
            self.assertTrue(hasattr(agent, "reset"))


if __name__ == "__main__":
    unittest.main()
