"""Tests for IntentBound execution runner, CLI entrypoint (run_eval.py), and multi-format reporters.

Tier 1: Feature Coverage (EvaluationReporter, ScenarioRunner, CLI argument parsing)
Tier 2: Boundary & Corner Cases (Invalid CLI flags, missing output paths, quiet mode)
Tier 4: Real-World Scenarios (End-to-end benchmark evaluation run simulating hackathon submission)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

try:
    from intentbound.evaluation.metrics import MetricsEngine
    from intentbound.evaluation.reporter import EvaluationReporter
    from intentbound.harness.mock_agents import CarefulCompliantAgent
    from intentbound.harness.runner import ScenarioRunner
    from intentbound.scenarios.registry import ScenarioRegistry
    HAS_RUNNER_MODULE = True
except ImportError:
    HAS_RUNNER_MODULE = False

RUN_EVAL_PATH = Path(__file__).resolve().parent.parent / "run_eval.py"


class TestE2ERunner(unittest.TestCase):
    """Tier 1 & Tier 4 tests for the benchmark runner, CLI, and reporting pipeline."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="intentbound_test_")
        self.registry = ScenarioRegistry() if HAS_RUNNER_MODULE else None

    def tearDown(self) -> None:
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # EvaluationReporter Tests
    # -------------------------------------------------------------------------

    @unittest.skipUnless(HAS_RUNNER_MODULE, "intentbound.evaluation.reporter not yet available")
    def test_reporter_exports_results_json(self) -> None:
        """Tests that EvaluationReporter writes schema-compliant results.json."""
        engine = MetricsEngine()
        metrics = engine.compute_metrics([])
        reporter = EvaluationReporter(output_dir=self.tmp_dir)

        json_path = reporter.export_json(
            model_name="mock:careful_compliant",
            metrics=metrics,
            evaluations=[],
        )

        self.assertTrue(os.path.exists(json_path))
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("benchmark", data)
        self.assertIn("summary_metrics", data)
        self.assertIn("model", data)
        self.assertEqual(data["model"], "mock:careful_compliant")

    @unittest.skipUnless(HAS_RUNNER_MODULE, "intentbound.evaluation.reporter not yet available")
    def test_reporter_exports_markdown_report(self) -> None:
        """Tests that EvaluationReporter writes clean Markdown scorecard report.md."""
        engine = MetricsEngine()
        metrics = engine.compute_metrics([])
        reporter = EvaluationReporter(output_dir=self.tmp_dir)

        md_path = reporter.export_markdown(
            model_name="mock:careful_compliant",
            metrics=metrics,
            evaluations=[],
        )

        self.assertTrue(os.path.exists(md_path))
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("# IntentBound Evaluation Report", content)
        self.assertIn("Intent Bound Score (IBS)", content)

    # -------------------------------------------------------------------------
    # ScenarioRunner Integration Tests
    # -------------------------------------------------------------------------

    @unittest.skipUnless(HAS_RUNNER_MODULE, "intentbound.harness.runner not yet available")
    def test_scenario_runner_executes_single_scenario(self) -> None:
        """Tests ScenarioRunner executing a single scenario against CarefulCompliantAgent."""
        scenario = self.registry.get("IB-01") if self.registry else None
        if scenario:
            agent = CarefulCompliantAgent()
            runner = ScenarioRunner()
            trajectory = runner.run_scenario(scenario, agent, variant="A", max_turns=5)

            self.assertIsNotNone(trajectory)
            self.assertEqual(trajectory.scenario_id, "IB-01")
            self.assertEqual(trajectory.variant, "A")
            self.assertGreaterEqual(len(trajectory.actions), 0)

    # -------------------------------------------------------------------------
    # Tier 4: Real-World CLI Subprocess Execution Tests
    # -------------------------------------------------------------------------

    @unittest.skipUnless(RUN_EVAL_PATH.exists(), "run_eval.py not yet created")
    def test_cli_execution_careful_compliant(self) -> None:
        """Tests end-to-end execution of 'python run_eval.py --mock-agent careful_compliant'."""
        cmd = [
            sys.executable,
            str(RUN_EVAL_PATH),
            "--mock-agent",
            "careful_compliant",
            "--scenario",
            "IB-01",
            "--output",
            self.tmp_dir,
            "--quiet",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        self.assertEqual(
            result.returncode,
            0,
            f"CLI failed with stderr:\n{result.stderr}\nstdout:\n{result.stdout}",
        )

        # Verify output files exist
        json_file = Path(self.tmp_dir) / "results.json"
        md_file = Path(self.tmp_dir) / "report.md"
        self.assertTrue(json_file.exists(), "CLI must generate results.json")
        self.assertTrue(md_file.exists(), "CLI must generate report.md")

        # Verify JSON content
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("summary_metrics", data)

    @unittest.skipUnless(RUN_EVAL_PATH.exists(), "run_eval.py not yet created")
    def test_cli_pillar_filter(self) -> None:
        """Tests CLI filter '--pillar pillar1' runs only Pillar 1 scenarios."""
        cmd = [
            sys.executable,
            str(RUN_EVAL_PATH),
            "--mock-agent",
            "careful_compliant",
            "--pillar",
            "pillar1",
            "--output",
            self.tmp_dir,
            "--quiet",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0)

    @unittest.skipUnless(RUN_EVAL_PATH.exists(), "run_eval.py not yet created")
    def test_cli_invalid_arguments_exits_nonzero(self) -> None:
        """Tests that invoking run_eval.py with invalid flags exits with non-zero code."""
        cmd = [
            sys.executable,
            str(RUN_EVAL_PATH),
            "--nonexistent-flag-xyz",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
