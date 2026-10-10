from enum import Enum
from pydantic import BaseModel, Field

class VerdictLabel(str, Enum):
    TRUE = "true"
    FALSE = "false"
    MISLEADING = "misleading"
    PARTIALLY_TRUE = "partially true"
    UNVERIFIABLE = "unverifiable"

class ExpectedClaim(BaseModel):
    claim: str
    quote: str | None = None
    timestamp: str | None = None

class BenchmarkCase(BaseModel):
    case_id: str
    description: str
    input_manuscript: str | None = None
    expected_claims: list[ExpectedClaim] | None = None
    expected_verdict: VerdictLabel | None = None
    expected_outcome: str | None = None
    tags: list[str] = Field(default_factory=list)
    evaluation_notes: str | None = None
    enabled: bool = True

class BenchmarkDataset(BaseModel):
    dataset_version: str = "1.0"
    cases: list[BenchmarkCase]
