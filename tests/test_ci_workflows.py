"""The npm publish workflow and the WebAssembly build in CI.

`.github/` is outside `tests/test_core_yaml.py`'s scope, so this test is the
one that reads the two workflow files (with the core's YAML loader). It
checks that `publish-npm.yml` builds with CI's Rust toolchain, runs only
from `main` or a pushed tag (release.yml's guard), checks out the tag and
refuses one whose commit is not on `main`, and that every job that builds
the WebAssembly module names the toolchain that has the wasm32 target.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from grounded_agency import _core

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def load(name: str) -> dict[str, Any]:
    doc: dict[str, Any] = _core.load_yaml(str(WORKFLOWS / name))
    return doc


CI = load("ci.yml")
PUBLISH = load("publish-npm.yml")
RELEASE = load("release.yml")


def steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = job.get("steps") or []
    return found


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
