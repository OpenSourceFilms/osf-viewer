# osf_viewer — universal file-viewer

A read-only inspection service that guarantees every file on the `/workspace`
network volume has a predictable, machine-consumable representation — even
when its native MIME type or binary format is unsupported by ordinary HTTP
clients (browsers, curl, ChatGPT's URL fetcher).

**Install root:** `/workspace/services/osf_viewer` (on the shared network
volume, so it survives pod rebuilds).

**Runs on:** this RunPod pod, bound to `127.0.0.1:3930`. The only public
entry point is a Cloudflare Tunnel path rule in front of it — see `DOCS.md`.

## Source availability and reuse status

**Publicly viewable does not currently mean open-source licensed.** This repository
does not yet contain a repository-wide `LICENSE` or `COPYING` file. OSF is
reviewing code authorship, third-party notices, and an appropriate reuse
licence in [issue #1](https://github.com/OpenSourceFilms/osf-viewer/issues/1).
Until an authorised licence is published, **do not assume that the MIT licence
used by other OSF repositories applies here**, or that public visibility grants
permission to redistribute, modify and republish this source outside the
rights supplied by GitHub's terms and applicable law.

This notice does not change the copyright ownership of any contribution, does
not impose a new licence, and does not grant additional rights. The paths,
tunnel rules and startup assumptions below describe an OSF-specific service,
not a public deployment guarantee.

## Third-party Python dependencies

The [21 pinned dependencies](DEPENDENCY_LICENSES.md) have a dated inventory
of publisher-declared licence metadata, checked against
`requirements.lock.txt` by offline CI. Notably, **mutagen is GPL-2.0-or-later**
and five archive/compression packages are **LGPL-2.1-or-later**. The
`odfpy` metadata is ambiguous about alternative/combined licensing.

This does **not** mean the Viewer code itself is GPL, LGPL or MIT. Assess
whether any future redistributable package bundles those dependencies,
preserve applicable licence/notice terms and resolve the separate
[ownership and reuse issue](https://github.com/OpenSourceFilms/osf-viewer/issues/1).
Package metadata alone is not wheel-level or legal clearance.

## Office fixture provenance and package checks

The public `tests/fixtures/` directory contains synthetic Office test
documents, including six ZIP-based OOXML/ODF packages and older binary
DOC/XLS/PPT/RTF files. The ZIP packages contain some Office-generated
components beyond visible test text: the DOCX and PPTX include
`docProps/thumbnail.jpeg` previews, the PPTX has printer-settings
data, and the DOCX has custom XML. These **are not asserted to be
independently cleared third-party assets** merely because the visible
document text is synthetic.

[The fixture package audit](scripts/audit_fixture_packages.py) and
[offline regression tests](tests/test_fixture_package_safety.py) check
for external relationships, embedded executable/attachment locations,
unexpected package paths and selected personal metadata patterns. They
do **not** prove the creator's copyright, inspect everything inside
legacy OLE/RTF fixtures, or determine the rights to embedded thumbnail
artwork. The complete reuse-licence and fixture-provenance decision
remains tracked in [issue #1](https://github.com/OpenSourceFilms/osf-viewer/issues/1).
No fixture binaries have been changed by this audit.

**Binary review checkpoint (27 October 2026):** the new
[fixture inventory](docs/fixture-inventory.json) records the exact Git
blob-object digest, byte count and unresolved-provenance status of **all 12**
checked-in Office and corrupt-document fixtures. The stdlib-only
[verification script](scripts/verify_fixture_manifest.py), tested in CI,
fails when a binary is added, removed, replaced or symlinked without an
explicit manifest update. Every asset is deliberately labelled
`provenance_and_redistribution_rights_unverified`. A matching hash does
**not** establish who created the document, clear embedded artwork or grant
reuse permission. Changes to fixture bytes must be reviewed separately
before public redistribution.

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

## Symlink and denylist safety

Directory listings and direct file requests share the same deny policy.
Symlinks resolving into denied paths or outside the configured viewer root
are not listed or served. Forbidden path components such as `.claude`
remain denied even if they are symlinks to otherwise allowed content.

The standalone standard-library tests in `tests/test_security_symlink_denials.py`
run on GitHub Actions without a live viewer, credentials or model dependencies.
Those checks cover source behavior only. A live deployment still requires
separate reverse-proxy, effective-permission and directory-listing acceptance.
