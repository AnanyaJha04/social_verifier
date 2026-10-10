from typing import Optional
from dataclasses import dataclass
from benchmark.runner import BenchmarkReport

@dataclass
class BaselineComparison:
    is_compatible: bool
    incompatibility_reason: str
    has_regression: bool
    new_failures: list[str]
    resolved_failures: list[str]
    changed_verdicts: list[str]
    missing_in_current: list[str]
    missing_in_baseline: list[str]
    summary: str

def compare_runs(baseline: BenchmarkReport, current: BenchmarkReport, accuracy_threshold: float = 0.0) -> BaselineComparison:
    if baseline.dataset_version != current.dataset_version:
        return BaselineComparison(
            is_compatible=False,
            incompatibility_reason="Dataset versions differ",
            has_regression=False,
            new_failures=[],
            resolved_failures=[],
            changed_verdicts=[],
            missing_in_current=[],
            missing_in_baseline=[],
            summary="Runs are incompatible because dataset schemas/versions differ."
        )
        
    baseline_cases = {r.case_id: r for r in baseline.results}
    current_cases = {r.case_id: r for r in current.results}
    
    new_failures = []
    resolved_failures = []
    changed_verdicts = []
    
    for cid, cur_res in current_cases.items():
        if cid in baseline_cases:
            base_res = baseline_cases[cid]
            if cur_res.passed and not base_res.passed:
                resolved_failures.append(cid)
            elif not cur_res.passed and base_res.passed:
                new_failures.append(cid)
                
            if cur_res.actual_verdict != base_res.actual_verdict:
                changed_verdicts.append(f"{cid}: {base_res.actual_verdict} -> {cur_res.actual_verdict}")
                
    missing_in_current = list(set(baseline_cases.keys()) - set(current_cases.keys()))
    missing_in_baseline = list(set(current_cases.keys()) - set(baseline_cases.keys()))
    
    has_regression = len(new_failures) > 0
    
    # Check aggregate metric regression
    if baseline.verdict_metrics and current.verdict_metrics:
        b_acc = baseline.verdict_metrics["accuracy"]
        c_acc = current.verdict_metrics["accuracy"]
        if (b_acc - c_acc) > accuracy_threshold:
            has_regression = True
            
    summary_lines = []
    if has_regression:
        summary_lines.append("**REGRESSION DETECTED**")
    else:
        summary_lines.append("**NO REGRESSION DETECTED**")
        
    summary_lines.append(f"- **New Failures:** {len(new_failures)} ({', '.join(new_failures)})")
    summary_lines.append(f"- **Resolved Failures:** {len(resolved_failures)} ({', '.join(resolved_failures)})")
    summary_lines.append(f"- **Changed Verdicts:** {len(changed_verdicts)}")
    
    if missing_in_current:
        summary_lines.append(f"- **Cases missing in current run:** {len(missing_in_current)}")
    if missing_in_baseline:
        summary_lines.append(f"- **Cases missing in baseline run:** {len(missing_in_baseline)}")
        
    return BaselineComparison(
        is_compatible=True,
        incompatibility_reason="",
        has_regression=has_regression,
        new_failures=new_failures,
        resolved_failures=resolved_failures,
        changed_verdicts=changed_verdicts,
        missing_in_current=missing_in_current,
        missing_in_baseline=missing_in_baseline,
        summary="\n".join(summary_lines)
    )
