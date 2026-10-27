# Architecture and round API

The user reviews locally, asks an assistant for a plan, approves in their existing
chat, then the assistant revises and creates the next round. The app copies a reading
instruction; it does not observe the chat or authenticate approval.

SQLite stores reviews, immutable saved versions and a separate lineage table. Lineage
adds a stable manuscript ID, round number, parent review and approved source version.
Existing reviews gain metadata without rewriting their archived JSON/Markdown. Explicit
local migration can connect known historical rounds; the tool does not infer project
relationships from similar titles. New roots receive internal project identities.

## Create a round

Use the authenticated local POST `/api/rounds` only after the user approved the plan.
Read the session token from `meta[name="review-token"]` on the local service root page
and send it as `X-Review-Token`, with `Content-Type: application/json`. If an `Origin`
header is sent, it must match the configured loopback service origin. The token changes
when the service restarts. A request body looks like this:

```json
{
  "parentReviewId": "example-review",
  "expectedVersion": 3,
  "approvalNote": "User explicitly approved the proposal in the current chat.",
  "review": {
    "title": "Example introduction",
    "paragraphs": [{"id":"P1","original":"Revised text.","current":"Revised text."}],
    "comments": []
  },
  "responses": [{"commentId":"C1","status":"addressed","action":"Clarified the opening."}]
}
```

The request needs exactly one response per parent comment, with status `addressed` or
`carried`. Carried comments retain their original IDs and anchors. Missing or ambiguous
matches are flagged by the browser. The service checks the source version within a
write transaction; stale approval returns a conflict. Repeating an identical request
returns the same child. The parent becomes read-only and cannot receive stale saves.
The note records the caller's assertion of approval; the assistant remains responsible
for obtaining it from the user. No API call by itself activates writing preferences.

The response includes the child review and `lineage` metadata. Existing `/api/save`
keeps expected-version protection. `/api/reviews` exposes lineage for navigation; the
browser follows a new child only if it has no unsent changes or open draft. Stale
browser copies remain downloadable instead of being silently discarded.

## Persistence and UI

Clicking Save immediately persists the database, versioned JSON/Markdown, then CURRENT.
The pointer hashes stored bytes, including actual newline conventions. ROUND is a
separate metadata file. The UI claims complete saving only after file export succeeds.
File export retries do not depend on models. Browser drafts and recovery supplement
the local files. Ordinary prose edits debounce; comment saves are immediate.

CSS Custom Highlights leave editable nodes unchanged. Exact quotes, snapshots, offsets
and context resolve anchors; ambiguous locations require relinking. The sidebar sorts
a copy by creation time descending, retaining original storage order and source IDs.

Background inference is off by default. Optional opt-in inference writes a private
proposal with source version and suggestions. It does not apply active preferences.
After explicit user approval, the assistant maintains scoped canonical Obsidian notes,
preserving manual text and conflicts. No model training or scientific fact checking occurs.

Known legacy guide templates are upgraded only by matching their normalized content
hash, with the original archived. Custom instructions are never overwritten; a
separate current approval-policy file is supplied. The copied request includes it
when present. Creating a round also refreshes the parent's exported ROUND metadata.
