import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from smart_growth_agent import live_p0


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    directory = tmp_path / ".runtime/live-p0-20261016"
    directory.mkdir(parents=True)
    monkeypatch.setattr(live_p0, "ROOT", tmp_path)
    monkeypatch.setattr(live_p0, "CAMPAIGN", directory)
    monkeypatch.setattr(live_p0, "REPORT", tmp_path / "result.json")
    original = {"calls": [{"number": number, "status": "reserved"} for number in range(37)]}
    (directory / "budget-before.json").write_text(json.dumps(original))
    (directory / "authorization.json").write_text(json.dumps({"cumulative_cap": 61}))
    ledger = tmp_path / ".runtime/live-budget.json"
    ledger.write_text(json.dumps(original))
    return directory, ledger


def test_campaign_never_resets_or_overwrites_original_budget(campaign):
    _, path = campaign
    value = json.loads(path.read_text())
    value["calls"][0]["status"] = "changed"
    path.write_text(json.dumps(value))
    with pytest.raises(AssertionError, match="history"):
        live_p0.ledger()


def test_new_requests_stop_at_authorized_cumulative_limit(campaign):
    _, path = campaign
    value = json.loads(path.read_text())
    value["calls"].extend({"number": n, "status": "reserved"} for n in range(37, 61))
    path.write_text(json.dumps(value))
    live_p0.require_budget(0)
    with pytest.raises(AssertionError, match="Only 0"):
        live_p0.require_budget(1)
    value["calls"].append({"number": 61})
    path.write_text(json.dumps(value))
    with pytest.raises(AssertionError, match="violation"):
        live_p0.ledger()


def test_report_redacts_secret_and_keeps_unknown_slots(campaign, monkeypatch):
    _, path = campaign
    value = json.loads(path.read_text())
    value["calls"].append({"number": 37, "status": "reserved"})
    path.write_text(json.dumps(value))
    monkeypatch.setenv("SMART_GROWTH_OPENAI_API_KEY", "fixture-secret-never-real")
    result = live_p0.report()
    result["failure_message"] = "fixture-secret-never-real"
    live_p0.save(result)
    text = live_p0.REPORT.read_text()
    assert "fixture-secret-never-real" not in text
    parsed = json.loads(text)
    assert parsed["unknown_or_pending"] == 1
    assert parsed["new_requests"] == 1


@pytest.mark.asyncio
async def test_failed_stage_retains_report_without_spending(campaign, monkeypatch):
    directory, _ = campaign

    async def fail(_):
        raise RuntimeError("fictional-import-failure")

    monkeypatch.setattr(live_p0, "imports", fail)
    monkeypatch.setattr(live_p0, "engine", SimpleNamespace(dispose=AsyncMock()))
    with pytest.raises(SystemExit):
        await live_p0.execute_stage("imports")
    result = json.loads(live_p0.REPORT.read_text())
    assert result["stages"]["imports"]["status"] == "failed"
    assert result["new_requests"] == 0
    assert len(list(directory.glob("failure-imports-*.json"))) == 1


@pytest.mark.asyncio
async def test_closed_campaign_cannot_spend_unused_request(campaign, monkeypatch):
    directory, _ = campaign
    path = directory / "authorization.json"
    value = json.loads(path.read_text())
    value["closed"] = True
    path.write_text(json.dumps(value))
    call = AsyncMock()
    monkeypatch.setattr(live_p0, "imports", call)
    with pytest.raises(SystemExit, match="closed"):
        await live_p0.execute_stage("imports")
    call.assert_not_awaited()
