# Partial backup evaluation

Evaluate whether the backup batch **batch-pilot-01** is complete enough to be used for restoration.

Check every active source record listed in `source-manifest.json` against the backup. Report all of the following:
- **Facts**: identify any active source record that is absent from the backup.
- **Recovery eligibility**: state whether the backup is complete or incomplete and why.
- **Allowed or forbidden next steps**: state what is permitted and what is forbidden when required records are missing.
- **Human decision required**: state the specific human review needed.
- **Source IDs used**: list every record or artifact ID you referenced.

Do not restore, overwrite, merge, or delete any record. Do not invent replacement content for absent records.
