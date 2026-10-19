import pytest

from smart_growth_agent.demo_scenarios import exercise_scenarios
from smart_growth_agent.demo_seed import seed_demo


@pytest.mark.asyncio
async def test_complex_fictional_demo_preserves_governance(session_factory, tmp_path):
    state = await seed_demo(
        "fictional-offline-password-only",
        session_factory=session_factory,
        state_path=tmp_path / "state.json",
    )
    result = await exercise_scenarios(session_factory, state, media_path=tmp_path / "media")
    assert result["pass"], result
    assert result["real_model_calls"] == 0
