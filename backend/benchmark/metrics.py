import re
from typing import TypedDict
from collections import defaultdict

class ClaimMetrics(TypedDict):
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float

class VerdictMetrics(TypedDict):
    correct: int
    incorrect: int
    missing: int
    accuracy: float
    precision_per_class: dict[str, float]
    recall_per_class: dict[str, float]
    f1_per_class: dict[str, float]
    confusion_matrix: dict[str, dict[str, int]]
    excluded_count: int

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return ' '.join(text.split())

def calculate_claim_metrics(expected: list[str], predicted: list[str], threshold: float = 0.7) -> ClaimMetrics:
    if not expected and not predicted:
        return ClaimMetrics(
            true_positives=0, false_positives=0, false_negatives=0,
            precision=1.0, recall=1.0, f1_score=1.0
        )
    
    matched_predicted = set()
    true_positives = 0
    
    for exp in expected:
        norm_exp = normalize_text(exp)
        exp_words = set(norm_exp.split())
        if not exp_words:
            continue
            
        best_match_idx = -1
        best_score = 0.0
        
        for i, pred in enumerate(predicted):
            if i in matched_predicted:
                continue
            norm_pred = normalize_text(pred)
            pred_words = set(norm_pred.split())
            if not pred_words:
                continue
                
            intersection = len(exp_words & pred_words)
            union = len(exp_words | pred_words)
            jaccard = intersection / union if union > 0 else 0
            
            if jaccard > best_score and jaccard >= threshold:
                best_score = jaccard
                best_match_idx = i
                
        if best_match_idx != -1:
            true_positives += 1
            matched_predicted.add(best_match_idx)
            
    false_positives = len(predicted) - len(matched_predicted)
    false_negatives = len(expected) - true_positives
    
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return ClaimMetrics(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1_score=f1_score
    )

def calculate_verdict_metrics(cases: list[dict]) -> VerdictMetrics:
    # cases is a list of {"expected": str | None, "predicted": str | None}
    classes = ["true", "false", "misleading", "partially true", "unverifiable"]
    
    correct = 0
    incorrect = 0
    missing = 0
    excluded_count = 0
    
    confusion_matrix = {c: {c_pred: 0 for c_pred in classes + ["missing", "invalid"]} for c in classes}
    
    # Track per-class metrics
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)
    
    for case in cases:
        expected = case.get("expected")
        predicted = case.get("predicted")
        
        if not expected:
            excluded_count += 1
            continue
            
        if expected not in classes:
            excluded_count += 1
            continue
            
        if not predicted:
            missing += 1
            fn[expected] += 1
            confusion_matrix[expected]["missing"] += 1
        elif predicted not in classes:
            incorrect += 1
            fn[expected] += 1
            confusion_matrix[expected]["invalid"] += 1
        else:
            confusion_matrix[expected][predicted] += 1
            if expected == predicted:
                correct += 1
                tp[expected] += 1
            else:
                incorrect += 1
                fp[predicted] += 1
                fn[expected] += 1
                
    total_evaluated = correct + incorrect + missing
    accuracy = correct / total_evaluated if total_evaluated > 0 else 0.0
    
    precision_per_class = {}
    recall_per_class = {}
    f1_per_class = {}
    
    for c in classes:
        p = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) > 0 else 0.0
        r = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) > 0 else 0.0
        f1 = 2 * (p * r) / (p + r) if (p + r) > 0 else 0.0
        
        precision_per_class[c] = p
        recall_per_class[c] = r
        f1_per_class[c] = f1
        
    return VerdictMetrics(
        correct=correct,
        incorrect=incorrect,
        missing=missing,
        accuracy=accuracy,
        precision_per_class=precision_per_class,
        recall_per_class=recall_per_class,
        f1_per_class=f1_per_class,
        confusion_matrix=confusion_matrix,
        excluded_count=excluded_count
    )
