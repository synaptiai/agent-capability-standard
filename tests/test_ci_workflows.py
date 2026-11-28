"""The npm publish workflow, the WebAssembly build in CI, and time limits.

`.github/` is outside `tests/test_core_yaml.py`'s scope, so this is the
Python test that reads the workflow files `ci.yml`, `site.yml`,
`publish-npm.yml` and `release.yml` (with the core's YAML loader). It checks
that every job in them has a `timeout-minutes` of at least 15, that
`publish-npm.yml` builds with CI's Rust toolchain, runs only from `main` or a
pushed tag (release.yml's guard), checks out the tag and refuses one whose
commit is not on `main`, and that every job that builds the WebAssembly
module names the toolchain that has the wasm32 target. It also checks that
each script a CI step runs can import what it needs from what its job has
installed by then, and that only a pull request's superseded runs are
cancelled.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any

from grounded_agency import _core

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def load(name: str) -> dict[str, Any]:
    doc: dict[str, Any] = _core.load_yaml(str(WORKFLOWS / name))
    return doc


CI = load("ci.yml")
SITE = load("site.yml")
PUBLISH = load("publish-npm.yml")
RELEASE = load("release.yml")


def steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = job.get("steps") or []
    return found


def test_every_job_has_a_time_limit() -> None:
    """Without `timeout-minutes` a hung runner is held for GitHub's default
    of 360 minutes."""
    for doc in (CI, SITE, PUBLISH, RELEASE):
        for name, job in doc["jobs"].items():
            limit = job.get("timeout-minutes")
            assert isinstance(limit, int) and limit >= 15, name


def test_only_a_pull_requests_superseded_runs_are_cancelled() -> None:
    """A pull request's runs share a group keyed on its ref, so a newer push
    cancels the older run. Any other run gets a group of its own (keyed on
    its run id): a group holds one pending run and a newer run cancels it even
    when `cancel-in-progress` is false, so pushes to main sharing a group
    would lose the CI result of a commit merged between two others."""
    concurrency = CI["concurrency"]
    assert concurrency["cancel-in-progress"] == (
        "${{ github.event_name == 'pull_request' }}"
    )
    assert concurrency["group"] == (
        "ci-${{ github.event_name == 'pull_request' && github.ref"
        " || github.run_id }}-${{ github.event_name }}"
    )


def test_publish_uses_cis_toolchain() -> None:
    assert PUBLISH["env"]["RUST_TOOLCHAIN"] == CI["env"]["RUST_TOOLCHAIN"]


def test_publish_runs_only_from_main_or_a_pushed_tag() -> None:
    (release_job,) = RELEASE["jobs"].values()
    (publish_job,) = PUBLISH["jobs"].values()
    assert publish_job["if"] == release_job["if"]
    assert "refs/heads/main" in publish_job["if"]
    triggers = PUBLISH.get("on") or PUBLISH.get(True)
    assert triggers["push"]["tags"] == ["acs-core-v*"]


def test_publish_checks_out_the_tag_and_refuses_one_off_main() -> None:
    (job,) = PUBLISH["jobs"].values()
    checkout = next(
        s for s in steps(job) if str(s.get("uses", "")).startswith("actions/checkout")
    )
    assert checkout["with"]["ref"] == "refs/tags/${{ env.TAG }}"
    runs = "\n".join(str(s.get("run", "")) for s in steps(job))
    assert "git merge-base --is-ancestor" in runs
    publish = [s for s in steps(job) if "npm publish" in str(s.get("run", ""))]
    real = next(s for s in publish if "--dry-run" not in s["run"])
    assert real["env"]["NODE_AUTH_TOKEN"] == "${{ secrets.NPM_TOKEN }}"


def test_publish_dry_runs_unless_enabled_and_the_token_is_set() -> None:
    """The real publish needs both the variable and the token; the dry run
    runs in every other case, so exactly one of the two steps runs."""
    (job,) = PUBLISH["jobs"].values()
    assert job["env"]["HAS_NPM_TOKEN"] == "${{ secrets.NPM_TOKEN != '' }}"
    publish = [s for s in steps(job) if "npm publish" in str(s.get("run", ""))]
    conditions = {"--dry-run" in s["run"]: s["if"] for s in publish}
    assert conditions == {
        False: "vars.NPM_PUBLISH_ENABLED == 'true' && env.HAS_NPM_TOKEN == 'true'",
        True: "vars.NPM_PUBLISH_ENABLED != 'true' || env.HAS_NPM_TOKEN != 'true'",
    }

    def runs(condition: str, enabled: str, token: str) -> bool:
        # The two conditions' grammar: `a == 'x' && b == 'y'`, `a != 'x' || b != 'y'`.
        values = {"vars.NPM_PUBLISH_ENABLED": enabled, "env.HAS_NPM_TOKEN": token}
        joiner = " && " if " && " in condition else " || "
        results = []
        for term in condition.split(joiner):
            name, op, literal = term.split(" ", 2)
            same = values[name] == literal.strip("'")
            results.append(same if op == "==" else not same)
        return all(results) if joiner == " && " else any(results)

    for enabled in ("true", "", "false"):
        for token in ("true", "false"):
            ran = [dry for dry, c in conditions.items() if runs(c, enabled, token)]
            assert ran == [not (enabled == "true" and token == "true")], (
                enabled,
                token,
            )


def test_every_wasm_build_names_its_toolchain() -> None:
    seen = 0
    for doc in (CI, PUBLISH):
        for name, job in doc["jobs"].items():
            if not any(
                "npm run build:wasm" in str(s.get("run", "")) for s in steps(job)
            ):
                continue
            seen += 1
            runs = "\n".join(str(s.get("run", "")) for s in steps(job))
            assert "--target wasm32-unknown-unknown" in runs, name
            assert 'RUSTUP_TOOLCHAIN=$RUST_TOOLCHAIN" >> "$GITHUB_ENV"' in runs, name
    assert seen == 2


# What `pip install -e "."` gives a script besides the standard library: the
# package's one dependency (pyproject.toml, pyyaml) and the package itself.
BASE_MODULES = {"yaml", "grounded_agency"}


def module_imports(script: Path) -> set[str]:
    """The top-level modules a script imports when it starts: those of its
    module-level import statements."""
    tree = ast.parse(script.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_scripts_import_only_what_their_job_installed() -> None:
    """A script that a CI step runs before its job installs the dev extra
    imports only the standard library, the package's own dependencies and
    modules beside it: a generator that imports jsonschema (a dev
    dependency) fails with ModuleNotFoundError in a job that installed
    only the package."""
    checked = 0
    for name, job in CI["jobs"].items():
        defaults = (job.get("defaults") or {}).get("run") or {}
        workdir = ROOT / defaults.get("working-directory", ".")
        dev = False
        for step in steps(job):
            run = str(step.get("run", ""))
            if "pip install" in run and ".[dev]" in run:
                dev = True
            if dev:
                continue
            for script in re.findall(r"\bpython3? (\S+\.py)\b", run):
                path = workdir / script
                beside = {
                    p.stem
                    for p in path.parent.iterdir()
                    if p.suffix == ".py" or (p / "__init__.py").is_file()
                }
                missing = (
                    module_imports(path)
                    - set(sys.stdlib_module_names)
                    - BASE_MODULES
                    - beside
                )
                assert not missing, (
                    f"{name}: step {step.get('name')!r} runs {script}, which "
                    f"imports {sorted(missing)} before the job installs the "
                    "dev extra"
                )
                checked += 1
    assert checked > 0
