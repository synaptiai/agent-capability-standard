"""Runtime fixtures of workstream S3 (delegation, catalogs and diagnostics; RFC-0007).

Define each with add(name, description, catalog, script, end, trace, ...),
the function of scripts/gen_runtime_fixtures.py; the building blocks are in
runtime_fixtures.helpers.
"""


def register(add):
    """Add this workstream's fixtures (none yet)."""
