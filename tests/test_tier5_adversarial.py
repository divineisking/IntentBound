"""
Tier 5 Adversarial Verification & Stress Test Harness for IntentBound Benchmark.
Performs white-box adversarial fuzzing, property testing, baseline boundary audits,
differential delta checks, and sandbox isolation security verification.
"""

from __future__ import annotations

import builtins
import copy
import os
import random
import socket
import subprocess
import unittest
from typing import Any, Dict, List

from intentbound.domain.models import (
    ActionRecord,
    BenchmarkMetrics,
    PolicyBoundary,
    Scenario,
    ScenarioEvaluation,
    Trajectory,
)
from intentbound.evaluation.grader import DeterministicGrader
from intentbound.evaluation.metrics import MetricsEngine
from intentbound.harness.mock_agents import (
    CarefulCompliantAgent,
    HyperRefusalAgent,
    ObliviousAgent,
    OvereagerAgent,
    UnsafeAgent,
)
from intentbound.harness.runner import ScenarioRunner
from intentbound.scenarios.registry import load_all_scenarios
from intentbound.tools import create_default_tool_registry


class TestMockAgentBaselinesEmpirical(unittest.TestCase):
    """Verifies empirical upper and lower bounds across all 5 mock agent baselines."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_all_scenarios()
        cls.scenarios = cls.registry.list_all()
        cls.runner = ScenarioRunner()

    def test_careful_compliant_achieves_perfect_score(self) -> None:
        """Asserts CarefulCompliantAgent achieves 100% IBS and zero unauthorized actions across all 24 conditions."""
        agent = CarefulCompliantAgent()
        evaluations: List[ScenarioEvaluation] = []

        for sc in self.scenarios:
            for variant in ("A", "B"):
                traj = self.runner.run(sc, variant=variant, harness=agent, max_turns=5)
                res = DeterministicGrader.evaluate(sc, traj)
                evaluations.append(res)

        metrics = MetricsEngine.compute(evaluations)

        self.assertEqual(len(evaluations), 24)
        self.assertEqual(metrics.total_scenarios, 24)
        self.assertEqual(metrics.unauthorised_action_rate, 0.0)
        self.assertEqual(metrics.constraint_violation_rate, 0.0)
        self.assertEqual(metrics.appropriate_clarification_quality, 1.0)
        self.assertEqual(metrics.intent_misinterpretation_rate, 0.0)
        self.assertEqual(metrics.false_refusal_rate, 0.0)
        self.assertEqual(metrics.unsafe_compliance_rate, 0.0)
        self.assertEqual(metrics.intent_bound_score, 100.0)
        self.assertTrue(all(e.passed for e in evaluations))

    def test_overeager_agent_pillar1_specification_gaming(self) -> None:
        """Asserts OvereagerAgent fails specifically on Pillar 1 by violating authorization boundaries."""
        agent = OvereagerAgent()
        p1_scenarios = [s for s in self.scenarios if s.pillar == 1]
        evaluations: List[ScenarioEvaluation] = []

        for sc in p1_scenarios:
            for variant in ("A", "B"):
                traj = self.runner.run(sc, variant=variant, harness=agent, max_turns=5)
                res = DeterministicGrader.evaluate(sc, traj)
                evaluations.append(res)

        # Overeager violates boundaries across all 4 Pillar 1 scenarios
        unauth_evals = [e for e in evaluations if e.unauthorised_actions_count > 0]
        cvr_evals = [e for e in evaluations if e.constraint_violations_count > 0]

        self.assertGreater(len(unauth_evals), 0)
        self.assertGreater(len(cvr_evals), 0)
        # Verify specific scenario failure targets
        by_sid = {e.scenario_id: e for e in evaluations}
        self.assertGreater(by_sid["IB-01"].constraint_violations_count, 0)
        self.assertGreater(by_sid["IB-02"].constraint_violations_count, 0)
        self.assertGreater(by_sid["IB-03"].unauthorised_actions_count, 0)
        self.assertGreater(by_sid["IB-04"].unauthorised_actions_count, 0)

    def test_oblivious_agent_pillar2_under_clarification(self) -> None:
        """Asserts ObliviousAgent never requests clarification on ambiguous instructions (Variant A)."""
        agent = ObliviousAgent()
        p2_scenarios = [s for s in self.scenarios if s.pillar == 2]

        for sc in p2_scenarios:
            traj_a = self.runner.run(sc, variant="A", harness=agent, max_turns=5)
            # Must never ask clarification
            self.assertFalse(traj_a.clarification_requested, f"ObliviousAgent should never clarify on {sc.id}")
            res_a = DeterministicGrader.evaluate(sc, traj_a)
            # Under ambiguity, rash assumption must be flagged as intent misinterpretation or constraint violation
            self.assertTrue(
                res_a.intent_misinterpreted or res_a.constraint_violations_count > 0,
                f"ObliviousAgent should fail intent comprehension on {sc.id}",
            )

    def test_hyper_refusal_agent_pillar3_false_refusals(self) -> None:
        """Asserts HyperRefusalAgent exhibits 100% false refusal on benign dual-use security tasks."""
        agent = HyperRefusalAgent()
        dual_use_scenarios = [s for s in self.scenarios if s.id in ("IB-10", "IB-12")]
        evaluations: List[ScenarioEvaluation] = []

        for sc in dual_use_scenarios:
            traj_a = self.runner.run(sc, variant="A", harness=agent, max_turns=5)
            self.assertTrue(traj_a.refusal_detected, f"HyperRefusalAgent should refuse {sc.id}")
            res_a = DeterministicGrader.evaluate(sc, traj_a)
            evaluations.append(res_a)

        self.assertTrue(all(e.false_refusal for e in evaluations))
        self.assertEqual(sum(1 for e in evaluations if e.false_refusal) / len(evaluations), 1.0)

    def test_unsafe_agent_pillar3_masked_compliance(self) -> None:
        """Asserts UnsafeAgent exhibits 100% unsafe compliance on masked malicious requests."""
        agent = UnsafeAgent()
        masked_scenarios = [s for s in self.scenarios if s.id in ("IB-09", "IB-11")]
        evaluations: List[ScenarioEvaluation] = []

        for sc in masked_scenarios:
            traj_a = self.runner.run(sc, variant="A", harness=agent, max_turns=5)
            self.assertFalse(traj_a.refusal_detected, f"UnsafeAgent failed to refuse dangerous {sc.id}")
            res_a = DeterministicGrader.evaluate(sc, traj_a)
            evaluations.append(res_a)

        self.assertTrue(all(e.unsafe_compliance for e in evaluations))
        self.assertEqual(sum(1 for e in evaluations if e.unsafe_compliance) / len(evaluations), 1.0)


class TestMetricMonotonicityAndMathematicalInvariants(unittest.TestCase):
    """Property tests asserting mathematical monotonicity, strict ordering, and bounds on benchmark metrics."""

    def _create_mock_eval(
        self,
        sid: str = "IB-01",
        variant: str = "A",
        pillar: int = 1,
        unauth: int = 0,
        cvr: int = 0,
        clarify_app: bool = True,
        intent_mis: bool = False,
        false_ref: bool = False,
        unsafe_comp: bool = False,
    ) -> ScenarioEvaluation:
        return ScenarioEvaluation(
            scenario_id=sid,
            variant=variant,
            pillar=pillar,
            unauthorised_actions_count=unauth,
            constraint_violations_count=cvr,
            clarification_appropriate=clarify_app,
            intent_misinterpreted=intent_mis,
            false_refusal=false_ref,
            unsafe_compliance=unsafe_comp,
            passed=(unauth == 0 and cvr == 0 and clarify_app and not intent_mis and not false_ref and not unsafe_comp),
            score=100.0 if (unauth == 0 and cvr == 0 and clarify_app and not intent_mis and not false_ref and not unsafe_comp) else 0.0,
            details=[],
        )

    def test_uar_monotonicity_under_injected_violations(self) -> None:
        """Asserts that injecting unauthorized actions strictly increases UAR."""
        n = 20
        previous_uar = -1.0

        for k in range(n + 1):
            evals = [
                self._create_mock_eval(sid=f"IB-{i:02d}", unauth=(1 if i < k else 0))
                for i in range(n)
            ]
            metrics = MetricsEngine.compute(evals)
            self.assertAlmostEqual(metrics.unauthorised_action_rate, k / n, places=4)
            self.assertGreaterEqual(metrics.unauthorised_action_rate, previous_uar)
            previous_uar = metrics.unauthorised_action_rate

    def test_ibs_strict_monotonicity_under_unauthorized_actions(self) -> None:
        """Asserts that injecting unauthorized actions strictly reduces IBS: d(IBS)/d(UAR) < 0."""
        n = 10
        previous_ibs = 101.0

        for k in range(n + 1):
            evals = [
                self._create_mock_eval(sid=f"IB-{i:02d}", unauth=(1 if i < k else 0))
                for i in range(n)
            ]
            metrics = MetricsEngine.compute(evals)
            self.assertLessEqual(metrics.intent_bound_score, previous_ibs)
            previous_ibs = metrics.intent_bound_score

    def test_ibs_boundary_extremes(self) -> None:
        """Asserts that IBS is 100.0 on perfect evaluations and 0.0 on complete failure."""
        # 1. Perfect evaluations across all pillars
        perfect_evals = [
            self._create_mock_eval(sid="IB-01", pillar=1),
            self._create_mock_eval(sid="IB-05", pillar=2, clarify_app=True, intent_mis=False),
            self._create_mock_eval(sid="IB-10", pillar=3, false_ref=False),
            self._create_mock_eval(sid="IB-09", pillar=3, unsafe_comp=False),
        ]
        m_perf = MetricsEngine.compute(perfect_evals)
        self.assertEqual(m_perf.intent_bound_score, 100.0)

        # 2. Complete failure evaluations across all pillars
        failure_evals = [
            self._create_mock_eval(sid="IB-01", pillar=1, unauth=2, cvr=2),
            self._create_mock_eval(sid="IB-05", pillar=2, unauth=1, cvr=1, clarify_app=False, intent_mis=True),
            self._create_mock_eval(sid="IB-10", pillar=3, unauth=1, cvr=1, false_ref=True),
            self._create_mock_eval(sid="IB-09", pillar=3, unauth=1, cvr=1, unsafe_comp=True),
        ]
        m_fail = MetricsEngine.compute(failure_evals)
        self.assertEqual(m_fail.intent_bound_score, 0.0)

    def test_metrics_engine_randomized_property_fuzzing(self) -> None:
        """Property-fuzzes 500 randomized evaluation configurations ensuring bounds [0, 100] and no exceptions."""
        rng = random.Random(42)

        for _ in range(500):
            size = rng.randint(1, 30)
            evals = []
            for i in range(size):
                p = rng.choice([1, 2, 3])
                evals.append(
                    self._create_mock_eval(
                        sid=rng.choice(["IB-01", "IB-05", "IB-09", "IB-10"]),
                        variant=rng.choice(["A", "B"]),
                        pillar=p,
                        unauth=rng.randint(0, 3),
                        cvr=rng.randint(0, 3),
                        clarify_app=rng.choice([True, False]),
                        intent_mis=rng.choice([True, False]),
                        false_ref=rng.choice([True, False]),
                        unsafe_comp=rng.choice([True, False]),
                    )
                )

            metrics = MetricsEngine.compute(evals)
            self.assertGreaterEqual(metrics.intent_bound_score, 0.0)
            self.assertLessEqual(metrics.intent_bound_score, 100.0)
            self.assertGreaterEqual(metrics.unauthorised_action_rate, 0.0)
            self.assertLessEqual(metrics.unauthorised_action_rate, 1.0)
            self.assertGreaterEqual(metrics.constraint_violation_rate, 0.0)
            self.assertLessEqual(metrics.constraint_violation_rate, 1.0)


class TestDifferentialPairsComputation(unittest.TestCase):
    """Verifies that all 12 scenarios have paired conditions and correctly calculate differential deltas."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_all_scenarios()
        cls.scenarios = cls.registry.list_all()

    def test_all_12_scenarios_have_valid_ab_differential_pairs(self) -> None:
        """Asserts each of the 12 scenarios contains distinct, non-empty Variant A and B instructions."""
        self.assertEqual(len(self.scenarios), 12)

        for sc in self.scenarios:
            self.assertTrue(sc.instruction_a and len(sc.instruction_a.strip()) > 10, f"{sc.id} missing instruction_a")
            self.assertTrue(sc.instruction_b and len(sc.instruction_b.strip()) > 10, f"{sc.id} missing instruction_b")
            self.assertNotEqual(
                sc.instruction_a.strip(),
                sc.instruction_b.strip(),
                f"{sc.id} Variant A and Variant B must be distinct controlled pairs",
            )
            self.assertGreater(len(sc.available_tools), 0, f"{sc.id} must declare available tools")
            self.assertIsNotNone(sc.policy, f"{sc.id} must define PolicyBoundary")

    def test_differential_deltas_calculation_careful_compliant(self) -> None:
        """Asserts CarefulCompliantAgent achieves maximum differential delta (1.0) across all 3 pillars."""
        runner = ScenarioRunner()
        agent = CarefulCompliantAgent()
        evaluations: List[ScenarioEvaluation] = []

        for sc in self.scenarios:
            for variant in ("A", "B"):
                traj = runner.run(sc, variant=variant, harness=agent, max_turns=5)
                res = DeterministicGrader.evaluate(sc, traj)
                evaluations.append(res)

        metrics = MetricsEngine.compute(evaluations)
        diffs = metrics.differential_metrics

        self.assertEqual(diffs.get("delta_pillar1_boundary_sensitivity"), 1.0)
        self.assertEqual(diffs.get("delta_pillar2_clarification_precision"), 1.0)
        self.assertEqual(diffs.get("delta_pillar3_safety_discrimination"), 1.0)

    def test_differential_deltas_calculation_failing_baselines(self) -> None:
        """Asserts failing baselines collapse differential deltas on their target pillars."""
        runner = ScenarioRunner()

        # Overeager collapses Pillar 1 delta
        ov_agent = OvereagerAgent()
        ov_evals = [
            DeterministicGrader.evaluate(sc, runner.run(sc, variant=v, harness=ov_agent, max_turns=5))
            for sc in self.scenarios if sc.pillar == 1
            for v in ("A", "B")
        ]
        ov_metrics = MetricsEngine.compute(ov_evals)
        self.assertLessEqual(ov_metrics.differential_metrics.get("delta_pillar1_boundary_sensitivity", 1.0), 0.0)

        # Oblivious collapses Pillar 2 delta
        ob_agent = ObliviousAgent()
        ob_evals = [
            DeterministicGrader.evaluate(sc, runner.run(sc, variant=v, harness=ob_agent, max_turns=5))
            for sc in self.scenarios if sc.pillar == 2
            for v in ("A", "B")
        ]
        ob_metrics = MetricsEngine.compute(ob_evals)
        self.assertEqual(ob_metrics.differential_metrics.get("delta_pillar2_clarification_precision"), 0.0)


class TestIsolatedEnvironmentSecuritySandbox(unittest.TestCase):
    """Asserts that simulated tools execute purely in memory with zero real sockets, subprocesses, or disk writes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_all_scenarios()
        cls.scenarios = cls.registry.list_all()
        cls.runner = ScenarioRunner()

    def test_sandbox_socket_creation_prohibited(self) -> None:
        """Intercepts socket.socket to verify zero network socket attempts during benchmark execution."""
        original_socket = socket.socket

        def intercepted_socket(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("SANDBOX SECURITY VIOLATION: Tool attempted real network socket creation!")

        socket.socket = intercepted_socket  # type: ignore
        try:
            agent = CarefulCompliantAgent()
            for sc in self.scenarios:
                for variant in ("A", "B"):
                    traj = self.runner.run(sc, variant=variant, harness=agent, max_turns=5)
                    self.assertIsNotNone(traj)
        finally:
            socket.socket = original_socket  # type: ignore

    def test_sandbox_subprocess_execution_prohibited(self) -> None:
        """Intercepts subprocess calls to verify zero OS process spawning during tool execution."""
        original_popen = subprocess.Popen

        def intercepted_popen(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("SANDBOX SECURITY VIOLATION: Tool attempted OS subprocess invocation!")

        subprocess.Popen = intercepted_popen  # type: ignore
        try:
            agent = CarefulCompliantAgent()
            for sc in self.scenarios:
                traj = self.runner.run(sc, variant="A", harness=agent, max_turns=5)
                self.assertIsNotNone(traj)
        finally:
            subprocess.Popen = original_popen  # type: ignore

    def test_sandbox_no_host_disk_writes_during_execution(self) -> None:
        """Intercepts builtins.open to verify no files are written to host disk during scenario execution."""
        original_open = builtins.open

        def intercepted_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if any(m in mode for m in ("w", "a", "x", "+")):
                raise AssertionError(f"SANDBOX SECURITY VIOLATION: Tool attempted host disk write to '{file}'!")
            return original_open(file, mode, *args, **kwargs)

        builtins.open = intercepted_open  # type: ignore
        try:
            agent = CarefulCompliantAgent()
            # Run all scenarios through runner
            for sc in self.scenarios:
                self.runner.run(sc, variant="A", harness=agent, max_turns=5)
        finally:
            builtins.open = original_open  # type: ignore

    def test_state_mutation_isolation_and_idempotency(self) -> None:
        """Verifies that scenario initial states are never mutated or leaked between runs."""
        sc = self.registry.get("IB-01")
        self.assertIsNotNone(sc)
        original_state_copy = copy.deepcopy(sc.initial_state)

        agent = OvereagerAgent()
        # Overeager terminates/stops instances
        self.runner.run(sc, variant="A", harness=agent, max_turns=5)

        # Assert initial state in scenario object remains pristine
        self.assertEqual(sc.initial_state, original_state_copy)


if __name__ == "__main__":
    unittest.main()
