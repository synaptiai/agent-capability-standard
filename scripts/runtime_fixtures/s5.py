"""Runtime fixtures of workstream S5 (checkpoint, rollback, send and memory; RFC-0009).

Define each with add(name, description, catalog, script, end, trace, ...),
the function of scripts/gen_runtime_fixtures.py; the building blocks are in
runtime_fixtures.helpers.
"""


def register(add):
    """Add this workstream's fixtures (none yet)."""
