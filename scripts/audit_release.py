"""Portable audit; no credentials, source runtime manifests or network required."""

import json

from export_release import audit, selected_files

if __name__ == "__main__":
    files = selected_files()
    findings = audit(files)
    print(
        json.dumps(
            {
                "files_checked": len(files),
                "credential_findings": findings,
                "credential_files_read": False,
                "runtime_included": False,
            }
        )
    )
    raise SystemExit(bool(findings))
