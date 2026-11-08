# TimeGuard — Repair Prompt v1

Your previous proposal **failed validation**.  Here are the checks that failed:

{failures}

Please fix these specific issues and output a **corrected** JSON Proposal.
Keep the same exception_id.  Make sure:

- Evidence IDs and policy clause IDs actually exist in the data you retrieved.
- Timestamps include a UTC offset (e.g. +05:30).
- The action matches the changes (e.g. ADD_PUNCH needs add_punch changes).
- Your changes actually clear the exception without creating new ones.
- If you cannot fix it, set the action to ESCALATE_TO_HR with an empty changes array.

Output exactly one JSON object matching the Proposal schema.  No extra text.
