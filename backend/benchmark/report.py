import json
import dataclasses
from pathlib import Path
from benchmark.runner import BenchmarkReport

class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)

def save_report_json(report: BenchmarkReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"benchmark_{report.run_id}.json"
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(report, f, cls=EnhancedJSONEncoder, indent=2)
        
    return file_path

def generate_markdown_report(report: BenchmarkReport, output_dir: Path, baseline_summary: str = "") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"benchmark_{report.run_id}.md"
    
    lines = [
        f"# Benchmark Report: {report.run_id}",
        "",
        "## 1. Run Summary",
        f"- **Timestamp (UTC):** {report.timestamp}",
        f"- **Framework Version:** {report.framework_version}",
        f"- **Dataset Version:** {report.dataset_version}",
        f"- **Total Cases:** {report.total_cases}",
        f"- **Passed:** {report.passed_cases}",
        f"- **Failed:** {report.failed_cases}",
        f"- **Errored:** {report.errored_cases}",
        f"- **Skipped:** {report.skipped_cases}",
        "",
        "## 2. Dataset and Execution Mode",
        f"- **Execution Mode:** {report.execution_mode}",
        f"- **Dataset Path:** {report.dataset_path}",
        ""
    ]
    
    if report.verdict_metrics:
        vm = report.verdict_metrics
        lines.extend([
            "## 3. Aggregate Metrics (Verdict)",
            f"- **Accuracy:** {vm['accuracy']:.4f}",
            f"- **Correct:** {vm['correct']}",
            f"- **Incorrect:** {vm['incorrect']}",
            f"- **Missing:** {vm['missing']}",
            f"- **Excluded (no ground truth):** {vm['excluded_count']}",
            "",
            "## 4. Per-Class Verdict Metrics",
            "| Class | Precision | Recall | F1 Score |",
            "|---|---|---|---|"
        ])
        for c in ["true", "false", "misleading", "partially true", "unverifiable"]:
            p = vm['precision_per_class'].get(c, 0.0)
            r = vm['recall_per_class'].get(c, 0.0)
            f1 = vm['f1_per_class'].get(c, 0.0)
            lines.append(f"| {c} | {p:.4f} | {r:.4f} | {f1:.4f} |")
            
        lines.extend([
            "",
            "## 5. Confusion Matrix",
            "*(Row = Expected, Col = Predicted)*",
            r"| Expected \ Predicted | true | false | misleading | partially true | unverifiable | missing | invalid |",
            "|---|---|---|---|---|---|---|---|"
        ])
        
        for c in ["true", "false", "misleading", "partially true", "unverifiable"]:
            row = vm['confusion_matrix'].get(c, {})
            cols = [str(row.get(pred, 0)) for pred in ["true", "false", "misleading", "partially true", "unverifiable", "missing", "invalid"]]
            lines.append(f"| {c} | {' | '.join(cols)} |")
        lines.append("")
        
    if report.claim_metrics:
        cm = report.claim_metrics
        lines.extend([
            "## 6. Claim Extraction Metrics",
            f"- **True Positives:** {cm['true_positives']}",
            f"- **False Positives:** {cm['false_positives']}",
            f"- **False Negatives:** {cm['false_negatives']}",
            f"- **Precision:** {cm['precision']:.4f}",
            f"- **Recall:** {cm['recall']:.4f}",
            f"- **F1 Score:** {cm['f1_score']:.4f}",
            ""
        ])
        
    lines.extend([
        "## 7. Runtime Summary",
        f"- **Total Elapsed Time:** {report.total_elapsed_time:.2f}s",
        f"- **Mean Latency per Case:** {report.mean_latency:.2f}s",
        f"- **Median Latency per Case:** {report.median_latency:.2f}s",
        ""
    ])
    
    failed_cases = [r for r in report.results if not r.passed and not r.error]
    errored_cases = [r for r in report.results if r.error]
    
    if failed_cases or errored_cases:
        lines.append("## 8. Failed and Errored Cases")
        for c in failed_cases:
            lines.append(f"- **{c.case_id}**: Failed. Expected: {c.expected_verdict}, Actual: {c.actual_verdict}")
        for c in errored_cases:
            lines.append(f"- **{c.case_id}**: Error. {c.error}")
        lines.append("")
        
    if baseline_summary:
        lines.extend([
            "## 9. Regression Comparison",
            baseline_summary,
            ""
        ])
        
    lines.extend([
        "## 10. Known Limitations",
        "- **Offline Mode**: Uses mocked/synthetic fixtures and does not represent real-world model accuracy.",
        "- **Metric Definitions**: Claim matching is based on Jaccard text similarity with a fixed threshold, which may not capture semantic equivalence.",
        "",
        "## 11. Reproducibility Instructions",
        "To reproduce this run:",
        f"`python scripts/run_benchmark.py --dataset {report.dataset_path} --mode {report.execution_mode}`"
    ])
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    return file_path
