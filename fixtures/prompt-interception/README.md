# Prompt-interception workloads

`natural-tasks.json` is the original synthetic natural-language workload.

`external-github-issues-positive-v1.json` is a five-task, positive-only
retrieval workload grounded in public GitHub issues. It is **not a full coding
benchmark**: it does not ask a model to reproduce a bug, edit a repository, or
resolve the linked issue. Each request is a manually bounded operation that one
released primitive in the current eleven-primitive catalog can execute.

Every external task records:

- the GitHub repository, issue number, exact issue URL and title;
- the date on which the source was inspected;
- a locally retained, relevant issue-body excerpt;
- a SHA-256 digest over normalized repository, number, title, and excerpt;
- the exact scope removed when the issue was reduced to a primitive-retrieval
  request;
- two independently authored hidden execution cases that are never included in
  a teacher-model prompt.

Source text normalization uses Unicode NFC, converts CRLF/CR to LF, removes
trailing horizontal whitespace from each line, and removes outer whitespace.
The normalized fields are encoded as canonical JSON before SHA-256 hashing.
`taedri_codegraph.issue_workloads.load_issue_grounded_workload` validates those
bindings and returns plain `NaturalPrimitiveTask` values for campaign use. The
plain task values contain neither source metadata nor the expected primitive.

The version-one task/verifier contract requires executable hidden cases. It
does not represent a `must_abstain` oracle, so unsupported hard negatives are
intentionally absent rather than incorrectly scored. A future versioned schema
must add an explicit expected disposition before negative abstention results can
be claimed.
