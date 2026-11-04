"""
Multi-Format Benchmark Evaluation Reporter.
Generates machine-readable results.json, publication-quality Markdown report,
and colorized console summary tables (with graceful ASCII fallback).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

from intentbound.domain.models import BenchmarkMetrics


class EvaluationReporter:
    """Exports and formats benchmark results across JSON, Markdown, and Console."""

    def __init__(self, output_dir: Optional[str] = None) -> None:
        self.output_dir = output_dir or "results"

    def export_json(
        self,
        model_name: str,
        metrics: BenchmarkMetrics,
        evaluations: Optional[List[Any]] = None,
        output_path: Optional[str] = None,
    ) -> str:
        target = output_path or os.path.join(self.output_dir, "results.json")
        self.save_json(metrics, target, model_name=model_name)
        return target

    def export_markdown(
        self,
        model_name: str,
        metrics: BenchmarkMetrics,
        evaluations: Optional[List[Any]] = None,
        output_path: Optional[str] = None,
    ) -> str:
        target = output_path or os.path.join(self.output_dir, "report.md")
        self.save_markdown(metrics, target, model_name=model_name)
        return target

    @classmethod
    def save_json(cls, metrics: BenchmarkMetrics, filepath: str, model_name: str = "") -> None:
        """Saves machine-readable evaluation results to JSON."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        raw_dict = metrics.to_dict()
        data = {
            "benchmark": "IntentBound",
            "version": "1.0.0",
            "model": model_name,
            "summary_metrics": raw_dict,
        }
        data.update(raw_dict)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def save_markdown(cls, metrics: BenchmarkMetrics, filepath: str, model_name: str = "") -> None:
        """Generates a human-readable Markdown evaluation report."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

        lines = [
            f"# IntentBound Evaluation Report: `{model_name}`",
            "",
            f"**Benchmark Version**: `1.0.0` | **Total Conditions Evaluated**: `{metrics.total_scenarios}`",
            "",
            "## Executive Summary",
            "",
            f"- **Overall Intent Bound Score (IBS)**: **`{metrics.intent_bound_score}%`**",
            f"- **Unauthorised Action Rate (UAR)**: `{metrics.unauthorised_action_rate * 100:.1f}%` (Pillar 1)",
            f"- **Constraint Violation Rate (CVR)**: `{metrics.constraint_violation_rate * 100:.1f}%` (Pillar 1)",
            f"- **Appropriate Clarification Quality (ACQ)**: `{metrics.appropriate_clarification_quality * 100:.1f}%` (Pillar 2)",
            f"- **Intent Misinterpretation Rate (IMR)**: `{metrics.intent_misinterpretation_rate * 100:.1f}%` (Pillar 2)",
            f"- **False Refusal Rate (FRR)**: `{metrics.false_refusal_rate * 100:.1f}%` (Pillar 3)",
            f"- **Unsafe Compliance Rate (UCR)**: `{metrics.unsafe_compliance_rate * 100:.1f}%` (Pillar 3)",
            "",
            "## Pillar Performance Breakdown",
            "",
            "| Pillar | Evaluated Conditions | Passed | Pass Rate | Key Metrics |",
            "|---|---|---|---|---|",
        ]

        pm = metrics.pillar_metrics
        p1 = pm.get("pillar1_intent_vs_auth", {})
        lines.append(
            f"| **Pillar 1: Intent vs. Authorisation** | {p1.get('total_conditions', 0)} | {p1.get('passed', 0)} | "
            f"{p1.get('pass_rate', 0.0) * 100:.1f}% | UAR={p1.get('uar', 0.0):.2f}, CVR={p1.get('cvr', 0.0):.2f} |"
        )
        p2 = pm.get("pillar2_ambiguity_clarification", {})
        lines.append(
            f"| **Pillar 2: Ambiguity & Clarification** | {p2.get('total_conditions', 0)} | {p2.get('passed', 0)} | "
            f"{p2.get('pass_rate', 0.0) * 100:.1f}% | ACQ={p2.get('acq', 0.0):.2f}, IMR={p2.get('imr', 0.0):.2f} |"
        )
        p3 = pm.get("pillar3_safety_boundaries", {})
        lines.append(
            f"| **Pillar 3: Masking & Safety** | {p3.get('total_conditions', 0)} | {p3.get('passed', 0)} | "
            f"{p3.get('pass_rate', 0.0) * 100:.1f}% | FRR={p3.get('frr', 0.0):.2f}, UCR={p3.get('ucr', 0.0):.2f} |"
        )

        lines.extend([
            "",
            "## Controlled Differential Pair Analysis",
            "",
            f"- **$\\Delta_{{Pillar 1}}$ (Boundary Sensitivity)**: `{metrics.differential_metrics.get('delta_pillar1_boundary_sensitivity', 0.0):.3f}`",
            f"- **$\\Delta_{{Pillar 2}}$ (Clarification Precision)**: `{metrics.differential_metrics.get('delta_pillar2_clarification_precision', 0.0):.3f}`",
            f"- **$\\Delta_{{Pillar 3}}$ (Safety Discrimination)**: `{metrics.differential_metrics.get('delta_pillar3_safety_discrimination', 0.0):.3f}`",
            "",
            "## Detailed Condition Scorecard",
            "",
            "| Scenario ID | Variant | Pillar | Status | Unauth Actions | Constraint Violations | Score |",
            "|---|---|---|---|---|---|---|",
        ])

        for ev in metrics.evaluations:
            status = "**PASS**" if ev.passed else "FAIL"
            lines.append(
                f"| `{ev.scenario_id}` | `{ev.variant}` | Pillar {ev.pillar} | {status} | "
                f"{ev.unauthorised_actions_count} | {ev.constraint_violations_count} | {ev.score:.0f}% |"
            )

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    @classmethod
    def print_summary(cls, metrics: BenchmarkMetrics, model_name: str = "") -> None:
        """Prints a colorized terminal table, falling back to clean ASCII if rich is absent."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel

            console = Console()
            table = Table(title=f"IntentBound Benchmark Results: {model_name}")
            table.add_column("Scenario", style="cyan")
            table.add_column("Var", justify="center")
            table.add_column("Pillar", style="magenta")
            table.add_column("Status", justify="center")
            table.add_column("Unauth", justify="right")
            table.add_column("Violations", justify="right")
            table.add_column("Score", justify="right")

            for ev in metrics.evaluations:
                status_pill = "[green]PASS[/green]" if ev.passed else "[red]FAIL[/red]"
                table.add_row(
                    ev.scenario_id,
                    ev.variant,
                    f"Pillar {ev.pillar}",
                    status_pill,
                    str(ev.unauthorised_actions_count),
                    str(ev.constraint_violations_count),
                    f"{ev.score:.0f}%",
                )

            console.print(table)
            summary_panel = (
                f"[bold cyan]Intent Bound Score (IBS):[/bold cyan] [bold green]{metrics.intent_bound_score}%[/bold green]\n"
                f"Unauthorised Action Rate (UAR): {metrics.unauthorised_action_rate * 100:.1f}%\n"
                f"Constraint Violation Rate (CVR): {metrics.constraint_violation_rate * 100:.1f}%\n"
                f"Clarification Quality (ACQ): {metrics.appropriate_clarification_quality * 100:.1f}%\n"
                f"Intent Misinterpretation Rate (IMR): {metrics.intent_misinterpretation_rate * 100:.1f}%\n"
                f"False Refusal Rate (FRR): {metrics.false_refusal_rate * 100:.1f}%\n"
                f"Unsafe Compliance Rate (UCR): {metrics.unsafe_compliance_rate * 100:.1f}%"
            )
            console.print(Panel(summary_panel, title="Benchmark Summary Metrics", expand=False))

        except ImportError:
            cls._print_ascii_summary(metrics, model_name)

    @classmethod
    def _print_ascii_summary(cls, metrics: BenchmarkMetrics, model_name: str = "") -> None:
        sep = "=" * 80
        print(f"\n{sep}")
        print(f"               INTENTBOUND BENCHMARK RESULTS: {model_name.upper()}")
        print(sep)
        print(f"{'Scenario':<12} {'Var':<5} {'Pillar':<10} {'Status':<8} {'Unauth':<8} {'Violations':<12} {'Score':<6}")
        print("-" * 80)
        for ev in metrics.evaluations:
            status = "PASS" if ev.passed else "FAIL"
            print(
                f"{ev.scenario_id:<12} {ev.variant:<5} {f'Pillar {ev.pillar}':<10} {status:<8} "
                f"{ev.unauthorised_actions_count:<8} {ev.constraint_violations_count:<12} {f'{ev.score:.0f}%':<6}"
            )
        print("-" * 80)
        print(f"OVERALL INTENT BOUND SCORE (IBS): {metrics.intent_bound_score:.1f}%")
        print(f"  Unauthorised Action Rate (UAR):     {metrics.unauthorised_action_rate * 100:.1f}%")
        print(f"  Constraint Violation Rate (CVR):    {metrics.constraint_violation_rate * 100:.1f}%")
        print(f"  Clarification Quality (ACQ):      {metrics.appropriate_clarification_quality * 100:.1f}%")
        print(f"  Intent Misinterpretation Rate (IMR): {metrics.intent_misinterpretation_rate * 100:.1f}%")
        print(f"  False Refusal Rate (FRR):           {metrics.false_refusal_rate * 100:.1f}%")
        print(f"  Unsafe Compliance Rate (UCR):       {metrics.unsafe_compliance_rate * 100:.1f}%")
        print(f"{sep}\n")
