import time
import json
from dataclasses import dataclass
from typing import Any
from benchmark.schema import BenchmarkCase, BenchmarkDataset
from benchmark.metrics import calculate_claim_metrics, calculate_verdict_metrics, ClaimMetrics, VerdictMetrics

# Import pipeline functions
from app.verifier.claims import extract_claims, verify_claim, ExtractedClaim, ClaimVerification

@dataclass
class RunResult:
    case_id: str
    passed: bool
    error: str | None
    elapsed_time: float
    expected_claims: list[str]
    actual_claims: list[str]
    expected_verdict: str | None
    actual_verdict: str | None
    
@dataclass
class BenchmarkReport:
    framework_version: str
    dataset_version: str
    run_id: str
    timestamp: str
    execution_mode: str
    dataset_path: str
    selected_case_ids: list[str]
    total_cases: int
    passed_cases: int
    failed_cases: int
    skipped_cases: int
    errored_cases: int
    results: list[RunResult]
    claim_metrics: ClaimMetrics | None
    verdict_metrics: VerdictMetrics | None
    total_elapsed_time: float
    mean_latency: float
    median_latency: float

class BenchmarkRunner:
    def __init__(self, mode: str = "offline"):
        self.mode = mode
        
    def execute_case(self, case: BenchmarkCase) -> RunResult:
        start_time = time.monotonic()
        
        expected_claims = [c.claim for c in (case.expected_claims or [])]
        expected_verdict = case.expected_verdict.value if case.expected_verdict else None
        
        actual_claims = []
        actual_verdict = None
        error_msg = None
        
        try:
            if not case.input_manuscript:
                raise ValueError("No input manuscript provided")
                
            if self.mode == "offline":
                # Mock execution
                if expected_claims:
                    actual_claims = expected_claims.copy() # perfectly predicted
                
                if expected_verdict:
                    actual_verdict = expected_verdict # perfectly predicted
                    
            elif self.mode == "pipeline":
                # Real pipeline evaluation
                # This could make live calls to LLM, but test sets must ensure no credentials leak, etc.
                # However, the user requires opt-in. We just call the real functions.
                extracted = extract_claims(case.input_manuscript)
                actual_claims = [c.claim for c in extracted]
                
                # For verdict, we verify the first expected claim or the first extracted claim
                if extracted:
                    claim_to_verify = extracted[0]
                    # verify_claim falls back if no web_search available
                    verification = verify_claim(claim_to_verify, [], [])
                    actual_verdict = verification.verdict
            else:
                raise ValueError(f"Unknown execution mode: {self.mode}")
                
        except Exception as e:
            error_msg = str(e)
            
        elapsed = time.monotonic() - start_time
        
        passed = False
        if not error_msg:
            # simple pass criteria
            passed = True
            if expected_verdict and actual_verdict != expected_verdict:
                passed = False
                
        return RunResult(
            case_id=case.case_id,
            passed=passed,
            error=error_msg,
            elapsed_time=elapsed,
            expected_claims=expected_claims,
            actual_claims=actual_claims,
            expected_verdict=expected_verdict,
            actual_verdict=actual_verdict
        )

    def run(self, dataset: BenchmarkDataset, run_id: str, dataset_path: str = "unknown") -> BenchmarkReport:
        results = []
        start_total = time.monotonic()
        
        for case in dataset.cases:
            if not case.enabled:
                continue
            res = self.execute_case(case)
            results.append(res)
            
        total_elapsed = time.monotonic() - start_total
        
        # Calculate aggregate metrics
        all_expected_claims = []
        all_actual_claims = []
        verdict_pairs = []
        
        passed_count = sum(1 for r in results if r.passed)
        failed_count = sum(1 for r in results if not r.passed and not r.error)
        errored_count = sum(1 for r in results if r.error)
        skipped_count = len(dataset.cases) - len(results)
        
        for r in results:
            all_expected_claims.extend(r.expected_claims)
            all_actual_claims.extend(r.actual_claims)
            if r.expected_verdict:
                verdict_pairs.append({"expected": r.expected_verdict, "predicted": r.actual_verdict})
                
        claim_metrics = calculate_claim_metrics(all_expected_claims, all_actual_claims) if all_expected_claims else None
        verdict_metrics = calculate_verdict_metrics(verdict_pairs) if verdict_pairs else None
        
        latencies = sorted([r.elapsed_time for r in results])
        mean_latency = sum(latencies) / len(latencies) if latencies else 0.0
        median_latency = latencies[len(latencies)//2] if latencies else 0.0
        
        from datetime import datetime, timezone
        
        return BenchmarkReport(
            framework_version="1.0.0",
            dataset_version=dataset.dataset_version,
            run_id=run_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_mode=self.mode,
            dataset_path=dataset_path,
            selected_case_ids=[r.case_id for r in results],
            total_cases=len(results),
            passed_cases=passed_count,
            failed_cases=failed_count,
            skipped_cases=skipped_count,
            errored_cases=errored_count,
            results=results,
            claim_metrics=claim_metrics,
            verdict_metrics=verdict_metrics,
            total_elapsed_time=total_elapsed,
            mean_latency=mean_latency,
            median_latency=median_latency
        )
