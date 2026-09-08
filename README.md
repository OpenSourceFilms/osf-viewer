# osf_viewer — universal file-viewer

A read-only inspection service that guarantees every file on the `/workspace`
network volume has a predictable, machine-consumable representation — even
when its native MIME type or binary format is unsupported by ordinary HTTP
clients (browsers, curl, ChatGPT's URL fetcher).

**Install root:** `/workspace/services/osf_viewer` (on the shared network
volume, so it survives pod rebuilds).

**Runs on:** this RunPod pod, bound to `127.0.0.1:3930`. The only public
entry point is a Cloudflare Tunnel path rule in front of it — see `DOCS.md`.

## Why

Copyparty serves files on this volume as raw bytes. That's fine for a video
or a PDF, but useless for a `.pyc`, a SQLite database, a truncated video, or
anything a browser or an LLM's URL fetcher can't natively render. This
service sits alongside Copyparty and gives every one of those files a
degradation ladder instead of a dead end: exact text where possible, falling
back through extracted text, structured metadata, an archive listing,
strings, and finally a bounded hex dump — so a request for `/text` on any
existing file is guaranteed `200 text/plain`, never a bare error.

## Quick reference

| Representation | URL |
|---|---|
| Raw (via Copyparty, unchanged) | `https://files.opensourcefilms.org/path/to/file.ext` |
| Viewer hub | `https://files.opensourcefilms.org/__view__/path/to/file.ext` |
| Guaranteed text | `.../__view__/path/to/file.ext/text` |
| Visual (PDF) | `.../__view__/path/to/file.ext/preview.pdf` |
| Health check | `https://files.opensourcefilms.org/__view_health__` |

See `DOCS.md` for the full URL mapping, the `/text` and `/preview.pdf`
degradation contracts, and service management (`start.sh` / `stop.sh` /
`restart.sh` / `status.sh`).
