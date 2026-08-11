# Recovery Gate Rules

These gates must be checked before any file is considered eligible for restoration.

## Gate 1: Completeness
Every active source record listed in source-manifest.json must be present in the
backup batch. A missing active source record blocks restoration.

## Gate 2: Hash integrity
Every backed-up file must pass a content-hash check against its source-manifest
hash. A hash mismatch blocks the affected file from restoration.

## Gate 3: Target divergence
If the target device holds a different active version of a record, restoration
must stop and request a human decision. Automatic overwrite, version selection,
or merge is forbidden.

## Gate 4: Post-restore verification
After restoration, a post-restore checksum must match the backup checksum. If
verification fails, the restore must be rolled back and marked as failed.

## Gate 5: Derived artifacts
Derived indexes are not authoritative sources. They must be rebuilt from verified
source records after restore and must not be copied across devices.

## Human approval
Even when all gates pass, restoration requires explicit human approval. No
automatic restore, overwrite, merge, or delete is permitted.
