# Vikunja

## What maps to what

| Vikunja | Checklists |
| --- | --- |
| Project | Checklist |
| **Saved filter** | **Checklist — shown as "Name (filter)" in the picker** |
| Open task's title | Checklist item |
| **Task marked done** | **Ignored — never imported** |
| Descriptions, labels, dates, assignees | Ignored |

A project with 5 open and 100 finished tasks gives a **5-item** checklist. The
filtering is done by Vikunja (`filter=done = false`), so the other 100 are never
transferred. The same is true of a filter: only what its own query matches, and
already-done tasks, are excluded either way.

A saved filter can pull together tasks from several projects into one view —
"everything due this week" or "everything tagged `#dive`" — which is often more
useful as a checklist than a single project. It works identically to a project
underneath: same route, same permissions, same limits. The "(filter)" suffix in
the picker is cosmetic, added so a filter is never mistaken for a project of the
same name; the checklist's name on the watch is the plain title either way.
Every account has a built-in filter called **My Open Tasks** — that is not a
bug, it is what a fresh Vikunja account ships with.

Tasks arrive in creation order (`sort_by=id`). Vikunja's manual ordering lives in
`position`, which is per-view and needs a route an API token cannot reach, so
dragging tasks around does not reorder them on the watch. Create them in the
order you want.

Hidden from the picker: **archived projects** only.

Limits: 100 items per checklist, 64 characters per item, 32 per name.

## Requirements

Vikunja **2.4 or newer**. Two routes are used, and no others:

```text
GET {base}/api/v2/projects
GET {base}/api/v2/projects/{project}/tasks?sort_by=id&order_by=asc&filter=done+%3D+false
Authorization: Bearer tk_...
```

## Creating a token

1. Vikunja → avatar → **Settings** → **API tokens** → **Create a token**.
2. Tick exactly two permissions: **Projects → `read_all`** and
   **Tasks → `read_all`**. `read_one` is *not* needed; nothing is ever written.
3. Copy the `tk_…` value — Vikunja shows it once.

These two scopes, including for saved filters, are exactly what CI's end-to-end
test mints and runs against a real Vikunja instance.

## Connecting

On the bridge's web page, under **Vikunja**:

| Field | Value |
| --- | --- |
| Vikunja URL | `https://vikunja.example.com` (no `/api`) |
| API token | the `tk_…` value |

**Save and test** performs a real `GET /api/v2/projects`; credentials are stored
only if it succeeds. Then tick the projects and filters you want and **Import
selected**.

Unticking one removes it from the watch at the next sync.

## Troubleshooting

| Message | Cause |
| --- | --- |
| `Vikunja rejected the API token` | Expired, or missing `read_all` on projects/tasks |
| `could not reach Vikunja at …` | Wrong URL, DNS, or the bridge cannot reach the instance |
| `HTTP 404 for /projects` | URL already includes `/api`, or the instance predates the v2 API |
| A project is missing | It is archived |
| An unexpected "My Open Tasks (filter)" appears | Normal — every Vikunja account has this built-in filter |
