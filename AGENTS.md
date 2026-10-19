# Paper Orbit development boundaries

This is an independent portfolio adaptation. Preserve inherited application complexity; never modify source repositories or historical records. Do not publish, push or invoke model providers without explicit authorization. This release launcher is offline-only and must not read provider credentials. MIT applies as declared in LICENSE; attribution and capability boundaries are in NOTICE.md.

Use uv sync --locked --extra dev, uv run --locked --extra dev pytest -q, uv run --locked --extra dev ruff check smart_growth_agent tests scripts/local_runtime.py scripts/export_release.py scripts/audit_release.py scripts/offline_demo.py scripts/offline_e2e.py scripts/browser_acceptance.py, npm ci --prefix frontend --ignore-scripts, npm test --prefix frontend, npm run lint --prefix frontend, npm run build --prefix frontend. Each instance uses its own database volume, durable private configuration and project runtime directory; do not treat these as cache or delete them.

Export only with scripts/export_release.py into a fresh directory and audit using scripts/audit_release.py. All validation output paths must be new. Default tests use fake/MockTransport and reject external HTTP. Synthetic results and scripted review are not model-quality or human-approval evidence.

In the managed parent workspace acquire its task lock first; a standalone checkout instead records owner/session/scope locally in ignored .agent/HANDOFF.md. Never import an absent private provenance manifest or the author's runtime to validate a public checkout.
