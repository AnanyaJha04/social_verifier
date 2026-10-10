import argparse
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
import uuid

# Add parent dir to path if run directly
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from benchmark.schema import BenchmarkDataset
from benchmark.runner import BenchmarkRunner, BenchmarkReport
from benchmark.report import save_report_json, generate_markdown_report
from benchmark.baseline import compare_runs

def main():
    parser = argparse.ArgumentParser(description="Run the Automated Evaluation / Benchmark Framework")
    parser.add_argument("--dataset", required=True, help="Path to the JSON dataset file")
    parser.add_argument("--mode", choices=["offline", "pipeline"], default="offline", help="Execution mode")
    parser.add_argument("--outdir", default="benchmark_reports", help="Output directory for reports")
    parser.add_argument("--cases", nargs="+", help="Specific case IDs to run")
    parser.add_argument("--baseline", help="Path to a baseline JSON report to compare against")
    parser.add_argument("--regression-threshold", type=float, default=0.0, help="Accuracy degradation threshold to trigger failure")
    
    args = parser.parse_args()
    
    # Load Dataset
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"Error: Dataset {args.dataset} not found.")
        sys.exit(1)
        
    try:
        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        dataset = BenchmarkDataset(**data)
    except Exception as e:
        print(f"Error loading dataset: {e}")
        sys.exit(1)
        
    # Filter cases
    if args.cases:
        dataset.cases = [c for c in dataset.cases if c.case_id in args.cases]
        
    # Execute Run
    run_id = datetime.now(timezone.utc).strftime("%Y%md%H%M%S") + "-" + uuid.uuid4().hex[:6]
    runner = BenchmarkRunner(mode=args.mode)
    print(f"Starting run {run_id} in {args.mode} mode...")
    
    report = runner.run(dataset, run_id=run_id, dataset_path=str(dataset_path))
    
    out_dir = Path(args.outdir)
    json_path = save_report_json(report, out_dir)
    
    baseline_summary = ""
    has_regression = False
    
    if args.baseline:
        baseline_path = Path(args.baseline)
        if baseline_path.exists():
            with open(baseline_path, "r", encoding="utf-8") as f:
                b_data = json.load(f)
            # reconstruct baseline report
            b_report = BenchmarkReport(**b_data)
            comparison = compare_runs(b_report, report, accuracy_threshold=args.regression_threshold)
            baseline_summary = comparison.summary
            has_regression = comparison.has_regression
            print(comparison.summary)
        else:
            print(f"Warning: Baseline {args.baseline} not found. Skipping comparison.")
            
    md_path = generate_markdown_report(report, out_dir, baseline_summary)
    
    print(f"\nRun completed! Processed {report.total_cases} cases.")
    print(f"Passed: {report.passed_cases}, Failed: {report.failed_cases}, Errored: {report.errored_cases}")
    print(f"JSON Report: {json_path}")
    print(f"Markdown Report: {md_path}")
    
    if has_regression:
        print("\nExiting with status 1 due to detected regression.")
        sys.exit(1)
    
    if report.errored_cases > 0:
        sys.exit(1)
        
if __name__ == "__main__":
    main()
