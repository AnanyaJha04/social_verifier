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

    @classmethod
    def validate_unique_case_ids(cls, v: list[BenchmarkCase]) -> list[BenchmarkCase]:
        case_ids = set()
        for case in v:
            if case.case_id in case_ids:
                raise ValueError(f"Duplicate case_id found: {case.case_id}")
            case_ids.add(case.case_id)
        return v
        
    # for pydantic v2
    from pydantic import field_validator
    @field_validator('cases', mode='after')
    @classmethod
    def check_unique(cls, v):
        return cls.validate_unique_case_ids(v)
