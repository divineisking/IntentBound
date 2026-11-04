#!/usr/bin/env python3
"""
IntentBound: An Empirical Evaluation Benchmark for Goal vs. Authorization Boundaries
in Autonomous AI Agents (micro1 Eval Hackathon).

Top-level CLI executable runner for zero-cost reproducible local testing as well as
live frontier LLM API evaluations.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from typing import Any, Dict, List, Optional

from intentbound.domain.models import BenchmarkMetrics, Scenario, ScenarioEvaluation, Trajectory
from intentbound.evaluation.grader import DeterministicGrader
from intentbound.evaluation.metrics import MetricsEngine
from intentbound.evaluation.reporter import EvaluationReporter
from intentbound.harness.frontier import create_model_harness
from intentbound.harness.mock_agents import (
    CarefulCompliantAgent,
    HyperRefusalAgent,
    ObliviousAgent,
    OvereagerAgent,
    UnsafeAgent,
)
from intentbound.harness.runner import ScenarioRunner
from intentbound.scenarios.registry import load_all_scenarios


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="IntentBound: AI Agent Intent vs. Authorization Benchmark Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--scenario",
        "-s",
        type=str,
        default="all",
        help="Target scenario ID(s) (e.g. 'IB-01' or 'IB-01,IB-02') or 'all'.",
    )
    parser.add_argument(
        "--pillar",
        "-p",
        type=str,
        default="all",
        choices=["all", "pillar1", "pillar2", "pillar3", "1", "2", "3"],
        help="Filter scenarios by evaluation pillar.",
    )
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default=None,
        help="Model harness identifier (e.g. 'mock:careful_compliant', 'openai:gpt-4o', 'anthropic:claude-3-5-sonnet-20241022', 'litellm:ollama/llama3').",
    )
    parser.add_argument(
        "--mock-agent",
        type=str,
        default=None,
        choices=["careful_compliant", "overeager", "oblivious", "hyper_refusal", "unsafe"],
        help="Shorthand selection for one of the 5 reference mock agent baselines.",
    )
    parser.add_argument(
        "--all-mocks",
        action="store_true",
        help="Runs zero-cost benchmark across all 5 mock agent baselines and outputs comparative matrix.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="results",
        help="Output directory where results.json and report.md will be saved.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=10,
        help="Maximum conversation turns per scenario episode.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature for frontier LLM calls.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print verbose step-by-step tool calls, arguments, and state diffs.",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress intermediate progress; print only final summary tables.",
    )

    return parser.parse_args()


def filter_scenarios(
    all_scenarios: List[Scenario], scenario_arg: str, pillar_arg: str
) -> List[Scenario]:
    scenarios = all_scenarios

    # Filter by pillar
    p_clean = pillar_arg.lower().replace("pillar", "").strip()
    if p_clean in ("1", "2", "3"):
        target_pillar = int(p_clean)
        scenarios = [s for s in scenarios if s.pillar == target_pillar]

    # Filter by scenario ID
    s_arg = scenario_arg.strip()
    if s_arg != "all":
        ids = {i.strip().upper() for i in s_arg.split(",")}
        scenarios = [s for s in scenarios if s.id.upper() in ids]

    return scenarios


def evaluate_model_on_scenarios(
    harness: Any,
    scenarios: List[Scenario],
    runner: ScenarioRunner,
    variants: List[str] = ("A", "B"),
    max_turns: int = 10,
    verbose: bool = False,
) -> tuple[BenchmarkMetrics, List[Trajectory]]:
    trajectories: List[Trajectory] = []
    evaluations: List[ScenarioEvaluation] = []

    for sc in scenarios:
        for v in variants:
            traj = runner.run(
                scenario=sc,
                variant=v,
                harness=harness,
                max_turns=max_turns,
                verbose=verbose,
            )
            eval_res = DeterministicGrader.evaluate(sc, traj)
            trajectories.append(traj)
            evaluations.append(eval_res)

    metrics = MetricsEngine.compute(evaluations)
    return metrics, trajectories


def print_comparative_table(results_by_agent: Dict[str, BenchmarkMetrics]) -> None:
    sep = "=" * 90
    print(f"\n{sep}")
    print("           INTENTBOUND BENCHMARK: 5 MOCK AGENT COMPARATIVE MATRIX")
    print(sep)
    print(f"{'Mock Agent Baseline':<22} {'IBS':<8} {'UAR':<8} {'CVR':<8} {'ACQ':<8} {'IMR':<8} {'FRR':<8} {'UCR':<8}")
    print("-" * 90)
    for name, m in results_by_agent.items():
        print(
            f"{name:<22} {f'{m.intent_bound_score:.1f}%':<8} {f'{m.unauthorised_action_rate*100:.0f}%':<8} "
            f"{f'{m.constraint_violation_rate*100:.0f}%':<8} {f'{m.appropriate_clarification_quality*100:.0f}%':<8} "
            f"{f'{m.intent_misinterpretation_rate*100:.0f}%':<8} {f'{m.false_refusal_rate*100:.0f}%':<8} "
            f"{f'{m.unsafe_compliance_rate*100:.0f}%':<8}"
        )
    print(sep)
    print("Interpretation:")
    print("  - CarefulCompliant: Gold standard reference (IBS = 100.0%, zero violations, 100% clarification).")
    print("  - Overeager:        Pillar 1 failure (High UAR/CVR; violates boundaries to maximize metric).")
    print("  - Oblivious:        Pillar 2 failure (ACQ = 0%, High IMR; never asks clarification on ambiguity).")
    print("  - HyperRefusal:     Pillar 3 false refusal failure (High FRR; rejects benign dual-use security tasks).")
    print("  - Unsafe:           Pillar 3 unsafe compliance failure (High UCR; executes masked malicious payloads).")
    print(f"{sep}\n")


def main() -> int:
    args = parse_args()
    registry = load_all_scenarios()
    scenarios = filter_scenarios(registry.list_all(), args.scenario, args.pillar)

    if not scenarios:
        print(f"Error: No scenarios matched filter (scenario='{args.scenario}', pillar='{args.pillar}').")
        return 1

    os.makedirs(args.output, exist_ok=True)
    runner = ScenarioRunner()

    # Mode 1: Run all 5 Mock Agents
    if args.all_mocks or (args.model is None and args.mock_agent is None):
        if not args.quiet:
            print(f"Executing IntentBound Benchmark across all 5 reference Mock Agents ({len(scenarios)} scenarios, 24 conditions)...")

        mock_agents = [
            CarefulCompliantAgent(),
            OvereagerAgent(),
            ObliviousAgent(),
            HyperRefusalAgent(),
            UnsafeAgent(),
        ]

        comparative_results: Dict[str, BenchmarkMetrics] = {}
        all_export_data: Dict[str, Any] = {
            "benchmark": "IntentBound",
            "version": "1.0.0",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_scenarios": len(scenarios),
            "agents": {},
        }

        for agent in mock_agents:
            if args.verbose:
                print(f"\n--- Running evaluation for {agent.name} ---")
            metrics, trajectories = evaluate_model_on_scenarios(
                harness=agent,
                scenarios=scenarios,
                runner=runner,
                max_turns=args.max_turns,
                verbose=args.verbose,
            )
            comparative_results[agent.name.replace("mock:", "")] = metrics
            all_export_data["agents"][agent.name] = metrics.to_dict()

        # Print comparative table
        print_comparative_table(comparative_results)

        # Save comparative JSON
        results_path = os.path.join(args.output, "results.json")
        import json
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(all_export_data, f, indent=2)

        # Save comparative Markdown
        report_path = os.path.join(args.output, "report.md")
        # Save detailed report for careful_compliant as baseline
        EvaluationReporter.save_markdown(
            comparative_results["careful_compliant"], report_path, model_name="All Mock Baselines"
        )

        print(f"Artifacts successfully written:")
        print(f"  - Machine-readable JSON: {os.path.abspath(results_path)}")
        print(f"  - Human-readable Markdown: {os.path.abspath(report_path)}")
        return 0

    # Mode 2: Run a single selected model or mock agent
    model_id = args.model or f"mock:{args.mock_agent}"
    try:
        harness = create_model_harness(model_id, temperature=args.temperature)
    except Exception as e:
        print(f"Error initializing model harness '{model_id}': {e}")
        return 1

    if not args.quiet:
        print(f"Evaluating {harness.name} on {len(scenarios)} scenario(s)...")

    metrics, trajectories = evaluate_model_on_scenarios(
        harness=harness,
        scenarios=scenarios,
        runner=runner,
        max_turns=args.max_turns,
        verbose=args.verbose,
    )

    # Print summary table
    EvaluationReporter.print_summary(metrics, model_name=harness.name)

    # Save artifacts
    results_path = os.path.join(args.output, "results.json")
    report_path = os.path.join(args.output, "report.md")
    EvaluationReporter.save_json(metrics, results_path, model_name=harness.name)
    EvaluationReporter.save_markdown(metrics, report_path, model_name=harness.name)

    if not args.quiet:
        print(f"Evaluation complete. Artifacts written to {os.path.abspath(args.output)}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
