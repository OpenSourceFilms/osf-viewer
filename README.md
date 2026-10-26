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

## Safer 7z member reading

7z files use [diskless bounded extraction](archive_memory.py) rather than
creating files from archive-controlled paths. The `py7zr` pin was updated
from 1.1.3 to **1.1.4**, which addresses an upstream symlink-chain
destination-escape security issue. The new
[synthetic archive regression suite](tests/test_7z_memory_extraction.py)
tests actual selected-member decoding plus size, path and output-stream
safeguards. This source update does **not** change the live deployed Viewer
installation. Hostile archive parsers can still consume CPU and memory;
these checks are not a complete exposure or denial-of-service review.

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

## Native PDF streaming

The public `/__view__/.../preview.pdf` HTTP route now **streams native PDF
files directly** from an opened file descriptor using bounded 1 MiB
chunks, instead of loading the entire document into Python memory first.
A native PDF `HEAD` request sends headers without reading the PDF bytes.
This reuses the same implementation as raw-file streaming. Generated
image/video/Office previews and already-bounded archive-member PDFs retain
their existing handling. Five
[offline regression checks](tests/test_native_pdf_streaming.py) cover
native GET/HEAD, archive members, generated previews and the raw stream.

This change improves the native-PDF response path only, not the memory
and CPU limits for arbitrary PDF parsing or generated previews.
It is not deployed to the running Viewer merely by merging the repository.

## Derived-preview cache source identity

Previously, generated PDF previews were cached under **path + byte count +
modification time**. A replaced image/video/Office source or an archive member
could retain all three, causing the Viewer to show a stale PDF from a
previous file. The cache now also keys on the source identity: disk-file
device/inode/change-time metadata, or SHA-256 of extracted in-memory archive
member bytes. Cache writes use unique same-directory temporary files so
simultaneous requests do not collide on one fixed `.tmp` filename.

A repeated request for unchanged input still reuses its cached preview;
content replacement with an unchanged size and preserved mtime does not.
If a disk source changes during conversion, its output is returned only to
that request and **not cached under either source identity**. Six offline,
synthetic regression tests cover file replacement, archive members, Office
preview calls, ordinary cache hits and concurrent publication.

This is cache invalidation, **not a cryptographic integrity guarantee** for
disk content, a full defence against concurrent filesystem mutation, or an
authentication mechanism. The Viewer still requires restrictive filesystem
permissions and the existing denylist. The live Viewer is not changed merely
by merging the public repository.

## Bounded directory listing memory

HTML directory hubs and `/text` directory reports use the same
[bounded scanner](directory_listing.py): `os.scandir()` streams each
entry, a shared deny predicate rejects private or escaping paths, and a
bounded smallest-name selection retains at most **2,000 paths** instead
of sorting the entire directory into memory. `/text` continues to show
the exact visible-entry count and omitted-entry count. Sorting is by
filename, consistent with the previous report.

The complete directory must still be traversed to find the alphabetically
first 2,000 permitted names; this limits Python allocation, **not CPU or
filesystem enumeration time**. Six
[offline regressions](tests/test_bounded_directory_listing.py) cover a
25,000-entry virtual directory, memory growth, iterator closure, real
temporary-directory denial checks and HTML/text consistency.

## Bounded request concurrency

The HTTP listener uses [bounded worker admission](request_limits.py) to
restrict simultaneous handlers to two by default, reject excess requests
with HTTP 503 and a short `Retry-After`, and time out idle sockets.
An [offline loopback regression suite](tests/test_worker_admission.py)
checks rejection and recovery. This does not bound resources used by any
single archive decoder or establish live deployment acceptance.

## Text-report exception redaction

The plain-text report and embedded HTML preview never intentionally expose
raw Python exception values. Generic fallback markers replace error details
from the main parser, per-page PDF extraction, audio metadata, SQLite row
queries, Parquet row groups and directory stat failures. The report still
includes source-file contents where the requested path is legitimately
accessible. Seven standard-library-only
[error-redaction regressions](tests/test_inspector_error_redaction.py)
exercise the actual inspector function bodies and run in public CI.

## Public HTTP error handling

The Viewer returns a generic HTTP 500 message if a request triggers an
unexpected handler exception. Archive-member and archive-listing failures
also avoid returning internal exception representations, which can reveal
deployment paths or request-specific details. Server logs record only the
exception type for this last-resort boundary, not the full traceback.
An isolated, standard-library-only
[HTTP error regression suite](tests/test_http_error_redaction.py) runs
through GitHub Actions without opening a socket.

These are public-source protections, **not proof of the live deployment's
proxy configuration, filesystem privileges, race resistance or Copyparty
raw-route access controls**. The separate Copyparty exposure described in
[DOCS.md](DOCS.md) must be assessed at the actual ingress and raw routes.

## Mandatory access-control configuration

Viewer now **fails closed** when its `denylist.txt` is unavailable,
malformed or missing mandatory private-directory exclusions. It will not
bind the public-facing service without a valid policy; a running service
whose policy reload fails returns HTTP 503, including on its health route.
[Offline policy failure and recovery tests](tests/test_denylist_fail_closed.py)
cover this contract. This is public-source hardening and does not establish
that the current deployed service has been updated or that Copyparty's
separate raw route implements equivalent rules.

## Symlink and denylist safety

Directory listings and direct file requests share the same deny policy.
Symlinks resolving into denied paths or outside the configured viewer root
are not listed or served. Forbidden path components such as `.claude`
remain denied even if they are symlinks to otherwise allowed content.

The standalone standard-library tests in `tests/test_security_symlink_denials.py`
run on GitHub Actions without a live viewer, credentials or model dependencies.
Those checks cover source behavior only. A live deployment still requires
separate reverse-proxy, effective-permission and directory-listing acceptance.
