import pytest
import json
from pydantic import ValidationError

from benchmark.schema import BenchmarkDataset, BenchmarkCase
from benchmark.metrics import calculate_claim_metrics, calculate_verdict_metrics
from benchmark.runner import BenchmarkRunner, BenchmarkReport, RunResult
from benchmark.baseline import compare_runs

def test_dataset_validation():
    # Valid dataset loads successfully
    valid_data = {
        "cases": [
            {
                "case_id": "1",
                "description": "test",
                "expected_verdict": "true"
            }
        ]
    }
    dataset = BenchmarkDataset(**valid_data)
    assert len(dataset.cases) == 1
    
    # Missing required fields
    with pytest.raises(ValidationError):
        BenchmarkDataset(**{"cases": [{"description": "missing id"}]})
        
    # Invalid verdict label
    with pytest.raises(ValidationError):
        BenchmarkDataset(**{
            "cases": [{"case_id": "2", "description": "test", "expected_verdict": "fake_verdict"}]
        })

def test_metrics_claim():
    expected = ["Water boils at 100 degrees Celsius", "Sky is blue"]
    predicted = ["Water boils at 100 degrees", "Grass is green"]
    
    metrics = calculate_claim_metrics(expected, predicted, threshold=0.6)
    assert metrics["true_positives"] == 1
    assert metrics["false_positives"] == 1
    assert metrics["false_negatives"] == 1
    
    # Empty inputs
    metrics_empty = calculate_claim_metrics([], [])
    assert metrics_empty["f1_score"] == 1.0
    
def test_metrics_verdict():
    cases = [
        {"expected": "true", "predicted": "true"},
        {"expected": "false", "predicted": "true"},
        {"expected": "true", "predicted": None}, # missing
        {"expected": "unverifiable", "predicted": "invalid_label"}, # invalid predicted
        {"expected": None, "predicted": "true"} # excluded
    ]
    
    metrics = calculate_verdict_metrics(cases)
    assert metrics["correct"] == 1
    assert metrics["incorrect"] == 2
    assert metrics["missing"] == 1
    assert metrics["excluded_count"] == 1
    
    assert metrics["confusion_matrix"]["true"]["true"] == 1
    assert metrics["confusion_matrix"]["false"]["true"] == 1
    assert metrics["confusion_matrix"]["true"]["missing"] == 1
    assert metrics["confusion_matrix"]["unverifiable"]["invalid"] == 1

def test_runner_offline():
    dataset = BenchmarkDataset(
        cases=[
            BenchmarkCase(
                case_id="mock_1",
                description="Mock case 1",
                input_manuscript="Test",
                expected_claims=[{"claim": "Test claim"}],
                expected_verdict="true"
            ),
            BenchmarkCase(
                case_id="mock_2_disabled",
                description="Disabled case",
                enabled=False
            )
        ]
    )
    
    runner = BenchmarkRunner(mode="offline")
    report = runner.run(dataset, "test_run")
    
    assert report.total_cases == 1
    assert report.passed_cases == 1
    assert report.skipped_cases == 1
    
    # Re-running the same deterministic fixture produces equivalent substantive results
    report2 = runner.run(dataset, "test_run_2")
    assert report.passed_cases == report2.passed_cases
    assert report.results[0].expected_verdict == report2.results[0].expected_verdict

def test_baseline_comparison():
    r1 = RunResult("c1", True, None, 0.1, [], [], "true", "true")
    r2 = RunResult("c2", False, None, 0.1, [], [], "true", "false")
    
    baseline = BenchmarkReport("1.0", "1.0", "b1", "time", "offline", "ds", ["c1", "c2"], 2, 1, 1, 0, 0, [r1, r2], None, None, 0.2, 0.1, 0.1)
    
    # Identical
    comp = compare_runs(baseline, baseline)
    assert not comp.has_regression
    assert len(comp.new_failures) == 0
    assert len(comp.resolved_failures) == 0
    
    # Improved
    r2_improved = RunResult("c2", True, None, 0.1, [], [], "true", "true")
    current_improved = BenchmarkReport("1.0", "1.0", "c1", "time", "offline", "ds", ["c1", "c2"], 2, 2, 0, 0, 0, [r1, r2_improved], None, None, 0.2, 0.1, 0.1)
    comp_improved = compare_runs(baseline, current_improved)
    assert not comp_improved.has_regression
    assert len(comp_improved.resolved_failures) == 1
    
    # Degraded
    r1_degraded = RunResult("c1", False, None, 0.1, [], [], "true", "false")
    current_degraded = BenchmarkReport("1.0", "1.0", "c2", "time", "offline", "ds", ["c1", "c2"], 2, 0, 2, 0, 0, [r1_degraded, r2], None, None, 0.2, 0.1, 0.1)
    comp_degraded = compare_runs(baseline, current_degraded)
    assert comp_degraded.has_regression
    assert len(comp_degraded.new_failures) == 1
