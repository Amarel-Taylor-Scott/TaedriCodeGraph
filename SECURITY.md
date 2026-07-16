# Security policy

Taedri analyzes untrusted source. The default Python syntax analyzer parses bytes and
must never import, install, build, or execute the target package. Runtime analysis is
out of scope for the current release and will require an isolated, opt-in worker with
resource bounds and an exact receipt.

Please report suspected vulnerabilities privately to the repository owner rather than
opening a public exploit report. Include the affected commit, a minimal reproducer,
impact, and any suggested containment.
