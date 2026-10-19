import pytest

from smart_growth_agent.demo_e2e import run_e2e


@pytest.mark.asyncio
async def test_offline_mode_cannot_launch_a_paid_e2e_worker(monkeypatch):
    monkeypatch.setenv("SMART_GROWTH_LLM_MODE", "fake")
    with pytest.raises(RuntimeError, match="explicit_real_mode"):
        await run_e2e()
