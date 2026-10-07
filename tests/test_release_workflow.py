"""Execute release workflow logic with a finite fake external HTTP boundary."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from yaml import safe_load

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
WORKFLOW = safe_load((ROOT / ".github/workflows/release.yml").read_text())
BASE = WORKFLOW["env"]["MAAP_OGC_PROCESSES_URL"]
JOBS = WORKFLOW["env"]["MAAP_OGC_DEPLOYMENT_JOBS_URL"]


@pytest.mark.parametrize("fault", [None, "tag", "own-lock-version", "image"])
def test_release_metadata_checks_own_package(tmp_path: Path, fault: str | None) -> None:
    """Dependency versions cannot mask a mismatched project release version."""
    for name in ("pyproject.toml", "uv.lock", "dps-import-cogs.cwl"):
        shutil.copyfile(ROOT / name, tmp_path / name)
    tag = f"v{VERSION}"
    if fault == "tag":
        tag += "-rc.1"
    elif fault == "own-lock-version":
        lock = tmp_path / "uv.lock"
        lock.write_text(
            lock.read_text().replace(
                f'name = "dps-stac-item-generator"\nversion = "{VERSION}"',
                'name = "dps-stac-item-generator"\nversion = "999.0.0"',
            )
            + f'\n[[package]]\nname = "unrelated"\nversion = "{VERSION}"\n'
        )
    elif fault == "image":
        cwl = tmp_path / "dps-import-cogs.cwl"
        cwl.write_text(
            cwl.read_text().replace(
                f"dps-import-cogs:v{VERSION}", "dps-import-cogs:latest"
            )
        )
    step = next(
        s
        for s in WORKFLOW["jobs"]["validate"]["steps"]
        if s.get("name") == "Validate release tag and version metadata"
    )
    script = step["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={**os.environ, **WORKFLOW["env"], "RELEASE_TAG": tag},
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert (result.returncode == 0) == (fault is None), result.stderr
    if fault == "own-lock-version":
        assert "project's uv.lock package version" in result.stderr


@pytest.mark.parametrize(
    ("responses", "success", "message"),
    [
        ([("POST", BASE, 201, {})], True, "registered"),
        (
            [
                ("POST", BASE, 409, {"processID": "a/b ?"}),
                ("PUT", BASE + "/a%2Fb%20%3F", 500, {}),
            ],
            False,
            "HTTP 500",
        ),
        (
            [
                ("POST", BASE, 409, {"additionalProperties": {"processID": "p"}}),
                ("PUT", BASE + "/p", 202, {"jobID": "j"}),
                ("GET", JOBS + "/j", 404, {}),
                ("GET", JOBS + "/j", 200, {"state": "running"}),
                ("GET", JOBS + "/j", 200, {"status": "SUCCEEDED"}),
            ],
            True,
            "deployment succeeded",
        ),
        (
            [
                ("POST", BASE, 202, {"deploymentID": "j"}),
                ("GET", JOBS + "/j", 200, {"status": "failed"}),
            ],
            False,
            "deployment failed",
        ),
        (
            [("POST", BASE, 202, {"deploymentID": "j"})]
            + [("GET", JOBS + "/j", 404, {})] * 12,
            False,
            "remained unavailable",
        ),
        ([("POST", BASE, 202, {})], False, "without a deployment-job"),
        *[
            (
                [("POST", BASE, 202, {"deploymentJobLink": {"href": url}})],
                False,
                "untrusted deployment-job",
            )
            for url in (
                "https://evil.example/api/ogc/deploymentJobs/j",
                "http://api.maap-project.org/api/ogc/deploymentJobs/j",
                JOBS + "/%2e%2e/processes",
                JOBS + "/j#fragment",
            )
        ],
    ],
)
def test_registration_and_polling_without_network(
    tmp_path: Path,
    responses: list[tuple[str, str, int, dict]],
    success: bool,
    message: str,
) -> None:
    """Run actual Bash orchestration without exposing auth or contacting MAAP."""
    plan = tmp_path / "responses.json"
    plan.write_text(json.dumps(responses))
    curl = tmp_path / "curl"
    # Only the external HTTP boundary is fake. jq, URL validation, Bash control
    # flow, git revision lookup, and payload construction are real.
    curl.write_text(
        f"#!{sys.executable}\n"
        + """import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
plan = Path(os.environ["HTTP_PLAN"])
responses = json.loads(plan.read_text())
method, url, status, body = responses.pop(0)
actual_method = args[args.index("--request") + 1] if "--request" in args else "GET"
assert (actual_method, args[-1]) == (method, url)
assert args[0] == "--disable" and "--location" not in args and "-L" not in args
assert "--connect-timeout" in args and "--max-time" in args
assert "proxy-ticket: test-secret" in args
if method != "GET":
    payload = json.loads(args[args.index("--data") + 1])
    assert payload == {"executionUnit": {"href": os.environ["EXPECTED_CWL_URL"]}}
Path(args[args.index("--output") + 1]).write_text(json.dumps(body))
if "--dump-header" in args:
    Path(args[args.index("--dump-header") + 1]).write_text("")
plan.write_text(json.dumps(responses))
sys.stdout.write(str(status))
"""
    )
    curl.chmod(0o755)
    sleep = tmp_path / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    sleep.chmod(0o755)
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    script = next(
        s["run"]
        for s in WORKFLOW["jobs"]["deploy"]["steps"]
        if s.get("name") == "Register or update MAAP process"
    )
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env={
            **os.environ,
            **WORKFLOW["env"],
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "MAAP_TOKEN": "test-secret",
            "GITHUB_REPOSITORY": "MAAP-Project/dps-import-cogs",
            "HTTP_PLAN": str(plan),
            "EXPECTED_CWL_URL": f"https://raw.githubusercontent.com/MAAP-Project/dps-import-cogs/{sha}/dps-import-cogs.cwl",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert (result.returncode == 0) == success, result.stderr
    assert message in result.stdout + result.stderr
    assert "test-secret" not in result.stdout + result.stderr
    assert json.loads(plan.read_text()) == []
