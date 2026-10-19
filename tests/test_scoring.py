from __future__ import annotations

import pytest
from pydantic import ValidationError

from smart_growth_agent.schemas.scoring import ScoringOutput


def test_scoring_contract_requires_each_dimension_once() -> None:
    dimensions = [
        {"name": name, "score": 80, "rationale": "测试理由"}
        for name in [
            "Hook",
            "Emotion",
            "Authenticity",
            "Visual",
            "SaveValue",
            "Conversion",
        ]
    ]
    output = ScoringOutput(
        summary="测试评分",
        dimensions=dimensions,
        revision_suggestions=[],
    )
    assert len(output.dimensions) == 6

    dimensions[-1] = {"name": "Hook", "score": 80, "rationale": "重复维度"}
    with pytest.raises(ValidationError, match="each required dimension once"):
        ScoringOutput(
            summary="错误评分",
            dimensions=dimensions,
            revision_suggestions=[],
        )
