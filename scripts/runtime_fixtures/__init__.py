"""The runtime conformance fixtures of the Standard 1.2 workstreams.

scripts/gen_runtime_fixtures.py defines the 1.1 fixtures and the fixture
format (its add()); it then imports each module named in WORKSTREAMS and
calls its register(add), so each workstream adds fixtures in its own file.
The building blocks the fixtures share are in helpers.py.
"""

WORKSTREAMS = ("s2a", "s2b", "s3", "s4", "s5", "s6")
