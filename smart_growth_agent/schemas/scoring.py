from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DimensionName = Literal[
    "Hook", "Emotion", "Authenticity", "Visual", "SaveValue", "Conversion"
]
EXPECTED_DIMENSIONS = {"Hook", "Emotion", "Authenticity", "Visual", "SaveValue", "Conversion"}


class ScoringDimensionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: DimensionName
    score: int = Field(ge=0, le=100)
    rationale: str = Field(min_length=1)


class ScoringOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    dimensions: list[ScoringDimensionOutput] = Field(min_length=6, max_length=6)
    revision_suggestions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dimensions(self) -> ScoringOutput:
        names = [item.name for item in self.dimensions]
        if set(names) != EXPECTED_DIMENSIONS or len(set(names)) != 6:
            raise ValueError("scoring dimensions must contain each required dimension once")
        return self


class ScoreDimensionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    score: Decimal
    rationale: str


class ScoreReportRead(BaseModel):
    id: uuid.UUID
    content_version_id: uuid.UUID
    rubric_revision_id: uuid.UUID
    prompt_revision_id: uuid.UUID
    total_score: Decimal
    pass_threshold: int
    passed: bool
    summary: str
    revision_suggestions: list[str]
    dimensions: list[ScoreDimensionRead]
