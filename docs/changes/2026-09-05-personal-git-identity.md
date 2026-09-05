# Personal Git identity correction

Date: 2026-09-05.

The owner requested that all pending work be committed, the after-tax branch
be merged into `main`, and this personal repository's history be attributed
to **hao6yu**, not the inherited work identity.

## What changed

- Committed the 71 pending files and fast-forwarded `main` to
  `after-tax-overlay`; no squash or loss of intermediate commits.
- Set this repository's Git identity to
  `Hao Yu <8432323+hao6yu@users.noreply.github.com>`.
  The GitHub numeric ID and account name were verified through GitHub's API.
  Global Git settings for other repositories were not changed.
- Rewrote author and committer identities on the 65 older commits. The new
  checkpoint already used the personal identity, but its hash also changed
  because its parent changed: 66 commits were mapped in total.
- Preserved every commit's file tree, message, author/committer timestamp, and
  parent topology. Each rewritten commit object was checked against the
  corresponding original object with only identity/parent substitutions.
- The rewritten work checkpoint is `6b11f87425f28e0ed237b8da615fb7a1088dad9a`.
  This note and its map are a subsequent documentation-only commit.

The complete [old-to-new commit map](2026-09-05-git-identity-map.json) resolves
Git IDs quoted in older notes. Those historical notes, external upstream
source commit pins, research snapshots and archived artifacts were not
rewritten to pretend the original evidence was produced under a new Git ID.
Content-based code, data and artifact fingerprints are unchanged by the
identity rewrite. No evaluation, freeze confirmation or holdout reveal was
performed for this maintenance task.

## Verification and recovery

The full suite passed before the metadata-only rewrite: **1,044 tests in
122.11 seconds**. Pytest did not print a separate subtest count for that run.
All commit trees were then verified unchanged through the rewrite.

The pending-file audit found no publication blocker. Credentials, downloaded
market snapshots, experiment outputs and local screenshots remain ignored.
The checked-in research archive contains runtime source code, not market data.

A complete pre-rewrite Git bundle was created and verified in the original
working copy's untracked Git administration directory. It retains the old
history for recovery and is not published. The remote update uses an explicit
force-with-lease against the previously observed remote `main`, so a new
remote commit cannot be overwritten silently.

Existing clones must be reconciled with the rewritten history before pushing;
a fresh clone is the simplest option when there is no local work to preserve.
Do not merge the old history back into the rewritten branch.
