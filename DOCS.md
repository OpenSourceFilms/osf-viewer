# osf_viewer — universal file-viewer

A read-only inspection service that guarantees every file reachable through
Copyparty also has a predictable, machine-consumable representation — even
when its native MIME type or binary format is unsupported by ordinary HTTP
clients (browsers, curl, ChatGPT's URL fetcher).

Binds `127.0.0.1:3930` only. Public access is exclusively through the
Cloudflare Tunnel path rule below — there is no other way in.

## URL mapping

For any file at `/workspace/path/to/file.ext`:

| Representation | URL |
|---|---|
| Raw (via Copyparty, unchanged) | `https://files.opensourcefilms.org/path/to/file.ext` |
| Viewer hub (HTML, links to all modes) | `https://files.opensourcefilms.org/__view__/path/to/file.ext` |
| Guaranteed text | `.../__view__/path/to/file.ext/text` |
| Visual representation (PDF) | `.../__view__/path/to/file.ext/preview.pdf` |
| Original bytes, streamed | `.../__view__/path/to/file.ext/raw` |
| Directory listing | `.../__view__/path/to/dir/` (and its own `/text`) |
| Health check | `https://files.opensourcefilms.org/__view_health__` |

Locally (before the Cloudflare hop): same paths under `http://127.0.0.1:3930`.

### `/text` contract

Always returns `text/plain; charset=utf-8`, HTTP 200, for any file that
exists and passes the denylist. Never a bare 500 for an existing file — a
handler failure (corrupt DB, truncated media, unknown pickle format) falls
back to the next rung of the degradation ladder rather than raising:

1. Exact decoded text (source files: `.py .sh .md .json .yaml .toml .log` etc.)
2. Parsed/extracted text (PDF via `pypdf`, one page at a time)
3. Structured metadata/sample (image info via Pillow, audio tags via
   `mutagen`, video/ffprobe JSON, SQLite table+row sample, CSV first 50
   rows, Parquet schema + first row group, safetensors tensor list)
4. Archive member listing (zip/tar/7z, name + size, capped at 5000 entries)
5. Media metadata/contact sheet (video: `ffprobe` JSON; `/preview.pdf` for
   video renders 6 sampled frames via `ffmpeg` into a contact-sheet PDF)
6. Strings (first/last 256KB scanned, ≥4 printable chars, capped at 200 lines)
7. Bounded hex dump (first/last 512 bytes) + libmagic mime/description +
   size/mtime/sha256 (or a first+last-1MB fingerprint for files >50MB)

Any handler exception is caught inside `get_text()` and demoted to rung 7,
never propagated. A corrupt or misidentified file (e.g. a DuckDB file with
a `.db` extension, which fails the SQLite parser) still gets a full rung-7
report rather than an error page — this has been verified against a real
file on this volume (`melb_acquire/census.db`).

### `/preview.pdf` contract

Returns `application/pdf`, or HTTP 404 with a JSON body
`{"error": "no visual representation for this file type"}` when none
applies (text files, archives, audio, unsupported binaries). Native PDFs
are streamed as-is; images are converted losslessly; video gets a 6-frame
contact sheet via `ffmpeg`. Image/video conversions are cached under
`OSFV_CACHE_DIR`, keyed by `sha256(relpath:size:mtime)`.

## Archive members

Addressed as `<archive_relpath>!<member_internal_path>`, e.g.:

```
/__view__/some.zip!inner/dir/file.txt/text
/__view__/some.zip!inner/dir/file.txt/raw
```

The hub view for an archive lists every member as a link in this form.
Nested archives (an archive inside an archive) are **not** currently
addressable through a second `!` — only one level of `!` is parsed. A zip
member that is itself a zip degrades to its own hub/text/raw as an opaque
file, not as a browsable nested archive. This is a known limitation, not a
security gap.

Zip-bomb protection: a single member over 200MB uncompressed
(`MAX_MEMBER_EXTRACT`) is refused rather than extracted; archive listings
cap at 5000 enumerated members (`MAX_ARCHIVE_LIST`). Nothing is ever
extracted onto `/workspace` — 7z members (whose library has no in-memory
read API) are extracted into a throwaway `tempfile.TemporaryDirectory()`
under `OSFV_CACHE_DIR` and the directory is removed immediately after the
bytes are read back.

## Directories

`/__view__/some/dir/` lists entries as links to their own viewer URLs
(capped at 2000 entries). `/__view__/some/dir/text` gives the same listing
as a bounded plain-text table (name, kind, size, mtime) for machine
consumption.

## Large files

Never fully read just to build a page:

- Text cap: 20MB direct decode, then truncated with a marker.
- Hashing: full SHA-256 only under 50MB; otherwise a fingerprint over the
  first+last 1MB plus size.
- Video/audio: `ffprobe`/`mutagen` read headers/indexes only.
- safetensors: reads only the 8-byte length prefix + declared JSON header,
  never tensor data (verified: a 3.9GB checkpoint returns in ~0.02s).
- SQLite: `LIMIT 10` sample rows per table, not a full dump.

## Security / path exclusions

Every inbound path goes through `security.safe_resolve()`
(`services/osf_viewer/security.py`) before touching the filesystem:

- Null bytes and `..` segments (raw or percent-encoded) are rejected.
- The resolved real path must stay under `/workspace` (symlink escapes
  are caught by `Path.relative_to`).
- The resolved real path is checked against `denylist.txt`, which **must
  stay in sync with the `-v` deny mounts in `/workspace/start_copyparty.sh`**
  (the live Copyparty launcher — `services/copyparty/start.sh` is a
  downgraded, currently-unused alternate launcher, read-only, kept only for
  reference per its own env.sh comment). `OSFV_CACHE_DIR`
  (`/workspace/.osf_view_cache`) is *always* denied regardless of what
  denylist.txt says, since that's where derived previews and 7z scratch
  extraction live.
- Denied paths and traversal attempts both return 403, not a redirect or a
  silent empty response.
- **Beyond denylist.txt**, `security.DENIED_BASENAMES` denies any directory
  matching a listed name *wherever it appears in the tree*, not just at a
  fixed path. Currently `{".claude"}` — found 2026-09-08 that 18+
  per-subproject `.claude/` directories exist across this volume (only the
  top-level `/workspace/.claude` was in denylist.txt), some of which can
  hold shell-snapshot files with full env-var dumps. **Copyparty's own deny
  mounts have this same gap** (verified: its raw route still serves a
  nested `.claude/` untouched) — that is a separate, still-open decision
  for Daniel on `start_copyparty.sh`; this project's own denylist only
  tightens what osf_viewer additionally refuses, it does not change
  Copyparty's exposure.

Do not add a route that bypasses `safe_resolve()`. If Copyparty's deny
mounts change, update `denylist.txt` in the same session.

**Listing consistency (fixed 2026-09-08):** directory listings — both the
HTML hub (`/__view__/some/dir/`) and its plain-text form
(`/__view__/some/dir/text`) — omit any entry `security.is_denied()` would
403 on direct access, so a denied path's *name* is never visible even when
its content isn't. This reuses the exact same predicate `safe_resolve()`
uses (via `security.is_denied()`), threaded through `app.py`'s hub-rendering
loop and `inspectors._text_directory()` as an `is_denied` callback — not a
second, independently-maintained filter. Regression-tested in
`tests/test_denied_listing.py` (`.venv/bin/python -m unittest
tests.test_denied_listing -v`).

## Service management

```bash
bash /workspace/services/osf_viewer/start.sh     # idempotent; no-op if already running
bash /workspace/services/osf_viewer/stop.sh
bash /workspace/services/osf_viewer/restart.sh
bash /workspace/services/osf_viewer/status.sh     # PID, port, health check
tail -f /workspace/services/osf_viewer/osf_viewer.log
```

Restart is required after any edit to `app.py`, `inspectors.py`,
`security.py`, or `cache.py` — there is no hot reload.

## venv / dependencies

The venv lives at `/workspace/services/osf_viewer/.venv` (must stay under
`/workspace` — never system site-packages). Dependencies are pinned in
`requirements.lock.txt`:

```
backports.zstd, brotli, inflate64, multivolumefile, mutagen, numpy, odfpy,
openpyxl, pillow, psutil, py7zr, pyarrow, pybcj, pycryptodomex, pypdf,
pyppmd, python-docx, python-magic, python-pptx, safetensors, texttable
```

Plus these **system** packages (already present on this pod, not installed
by this project — record them if reproducing on a fresh image):
`ffmpeg`/`ffprobe` (4.2.7), `libmagic1`/`libmagic-mgc` (5.38), `file`.

## System office dependencies (LibreOffice)

Unlike everything above, LibreOffice is installed via `apt`, which writes
to the container's ephemeral overlay (`/`) — it does **not** survive a pod
rebuild, even though the Python side of office support
(`office_extract.py` + the pinned libraries above) lives safely in the
`/workspace` venv. If osf_viewer starts fine but every DOCX/XLSX/PPTX/ODT/
ODS/ODP/legacy-Office/RTF file falls back to the generic binary report and
`/preview.pdf` 404s for those formats specifically, this is almost
certainly what's missing:

```bash
bash /workspace/services/osf_viewer/setup_system_office_deps.sh
```

Installs `libreoffice-writer libreoffice-calc libreoffice-impress`
(`--no-install-recommends`; verified against `1:6.4.7-0ubuntu0.20.04.15` on
Ubuntu 20.04/focal at time of writing) and functionally verifies it by
actually converting a probe file to PDF, not just checking `soffice`
exists on `$PATH`. No Java/JVM/Tika is installed — see the "why no Apache
Tika / JVM" note above.

**Known trap, already hit once**: this venv's `bin/python` is a symlink
chain that ultimately resolves to a base-image interpreter
(`/usr/bin/python3.12` at time of writing). A pod rebuild that changes the
base image's `python3` default can silently break the venv (it did: found
resolving to `python3.8` with a `pyvenv.cfg` still claiming 3.12.3, and
`sys.path` no longer including the venv's own site-packages at all — a
silent, not a loud, failure). **Restore with:**

```bash
bash /workspace/services/osf_viewer/setup_venv.sh
```

This recreates the venv from `/usr/bin/python3.12`, reinstalls the pinned
lockfile, and verifies by function (calls `magic.from_file()`, not just
`import magic`) before declaring success. Run it any time osf_viewer fails
to start after a pod rebuild, before debugging anything else.

## Adding a new handler

`inspectors.py` is the single dispatch point. To add support for a new
format:

1. Add its extension(s) to the relevant set near the top of the file (or
   extend `identify()`'s libmagic-mime fallback if extension-based
   detection isn't reliable for it).
2. Add a branch in `get_text()`'s dispatch and write a `_text_<kind>()`
   function. It may raise — `get_text()`'s `except Exception` wraps every
   branch and demotes to the generic binary report automatically, so you
   do not need your own top-level try/except for the "never fail" contract.
3. If a visual representation makes sense, add a branch to
   `get_preview_pdf()`. Return `None` (not raise) for "no visual
   representation exists" — that's what turns into the contractual 404.
4. If large files need to stay cheap, read headers/seek rather than
   `_read_bytes()`'s full-read path — follow the safetensors or ffprobe
   pattern (metadata/index only, real work bounded and fast regardless of
   file size).
5. Never call `pickle.load` / `torch.load` / any code-executing
   deserializer on user-writable file content — the pickle-family
   extensions are deliberately refused with metadata-only fallback; keep
   any new deserializing format handler to safe, declarative parsers only
   (the same reasoning that keeps `sqlite3` read-only via `?mode=ro`).

## Fallback behaviour summary

| Category | Handling |
|---|---|
| Source/text files | Exact decoded content, verbatim |
| PDF | Per-page extracted text; `/preview.pdf` streams the original |
| Image | Pillow format/mode/size/info; `/preview.pdf` is a lossless PDF wrap |
| Video | `ffprobe` JSON; `/preview.pdf` is a 6-frame contact sheet |
| Audio | `mutagen` tags + length/bitrate/sample rate |
| Archive (zip/tar/7z) | Member listing; each member viewable via `!` syntax |
| SQLite | Table list, columns, row count, first 10 rows per table |
| CSV | Column count + first 50 rows |
| Parquet | Arrow schema + first row group sample |
| safetensors | Tensor name/shape/dtype list, no tensor data read |
| pickle-family (.pt/.ckpt/.pkl/...) | Refused deserialization; metadata-only report |
| Directory | Sorted entry listing (name/kind/size/mtime), capped at 2000 |
| Office (DOCX/XLSX/PPTX/ODT/ODS/ODP/DOC/XLS/PPT/RTF) | Real semantic extraction — see below; `/preview.pdf` via LibreOffice headless, cached |
| Anything else / corrupt file of a known type | libmagic mime+description, size, mtime, sha256 (or fingerprint if >50MB), strings, bounded hex dump — never a bare error |

## Office / document formats (`office_extract.py`)

Added 2026-09-08. Supported: **DOCX, XLSX, PPTX, ODT, ODS, ODP** natively,
plus legacy **DOC, XLS, PPT, RTF** via a LibreOffice-conversion step first
(see below). This is the *only* format family in this service whose
extraction lives in its own module rather than `inspectors.py` directly —
`inspectors.py` just dispatches by extension to `office_extract.get_text()`
/ `get_preview_pdf()`, same pattern as every other kind.

**Why no Apache Tika / JVM:** this pod has no Java runtime at all (checked:
`java -version` → not found). Rather than install a JVM plus a ~70MB Tika
jar, DOCX/XLSX/PPTX/ODT/ODS/ODP are extracted with pure-Python libraries
(`python-docx`, `openpyxl`, `python-pptx`, `odfpy`) that give *better*
structural fidelity than a raw Tika text dump anyway — real paragraph
order, heading levels, intelligible tables, worksheet/slide boundaries,
speaker notes — for a much smaller footprint. LibreOffice headless
(already needed for `/preview.pdf`) covers everything Tika would have
added beyond that. If a real need for Tika-specific extraction (e.g. a
format none of these libraries open) arises later, add it as an additional
fallback rung in `office_extract.py` rather than replacing this.

**`/text` extraction:**

- **DOCX/legacy DOC/RTF:** walks `document.element.body` in document order
  (not `doc.paragraphs`/`doc.tables` separately, which lose interleaving) —
  paragraphs render verbatim, headings render as `# `/`## ` by style level,
  tables render as `name | value | notes`-style rows (capped at 200 rows).
  Document metadata (title/author/created/modified) prefixed when present.
- **XLSX/legacy XLS:** lists every worksheet name up front, then per sheet
  a bounded, trimmed table (trailing empty cells stripped so short rows
  don't pad out to the column cap). Read in `read_only` mode so this stays
  cheap even for huge sheets — `iter_rows(max_row=200, max_col=50)` never
  loads the full sheet, and a separate **global 20,000-cell cap across all
  sheets** stops a many-sheet workbook from producing unbounded output.
- **PPTX/legacy PPT:** slides in order, numbered, with every text-frame and
  table shape's content, plus **speaker notes** where present, capped at
  300 slides. Deck-level title/author metadata included when present.
- **ODT/ODS/ODP:** same shape as DOCX/XLSX/PPTX via `odfpy`, walking
  `doc.text`/`doc.spreadsheet`/`doc.presentation` element children
  directly by qualified name (odfpy's element classes like `odf.text.P`
  are factory *functions*, not real types — `isinstance()` against them
  raises `TypeError`; compare `el.qname` to the real namespace tuple
  instead, e.g. `(TEXTNS, "p")`). Slightly less structurally rich than the
  DOCX/XLSX/PPTX path (closer to "extracted text with tables/headings/
  notes recognized" than a full block-level walk), still far above the
  generic binary fallback.
- **Legacy DOC/XLS/PPT/RTF:** converted via `soffice --convert-to
  docx|xlsx|pptx` first, then run through the *exact same* structural
  extractor as the native format — not a separate, flatter code path — so
  a `.doc` gets the same headings/tables fidelity a `.docx` does. If that
  conversion itself fails, falls back one more rung to `soffice
  --convert-to txt` (plain decoded text), and if *that* fails too, the
  exception propagates up to `inspectors.get_text()`'s blanket handler and
  demotes to the standard generic binary report — same "never a bare
  error" guarantee as everything else in this service.

**`/preview.pdf`:** every format above converts via `soffice --headless
--convert-to pdf`, cached exactly like the existing image/video previews
(`cache.get`/`cache.put` keyed by `sha256(relpath:size:mtime)` — see
`cache.py`). First request for a given file pays the LibreOffice cost
(~5s observed for a 3-slide PPTX fixture); every subsequent request for
the same content is a cache hit (~30ms observed). `/preview.pdf` failure
never affects `/text` for the same file — they're independent code paths.

**Limits and safety:**

- A hard **200MB cap** (`MAX_OFFICE_SRC_BYTES`) before *any* extraction is
  attempted at all, and a tighter **150MB cap** (`MAX_CONVERT_SRC_BYTES`)
  specifically before invoking `soffice` (conversion is the expensive
  rung) — both degrade to the next fallback rather than attempting a slow
  or memory-heavy operation.
- Every `soffice` invocation runs with a **45-second hard timeout**
  (`LO_TIMEOUT_S`), `subprocess.run(..., timeout=...)`, killed on expiry.
- **Macro execution is disabled** via a seed LibreOffice profile
  (`MacroSecurityLevel=3` in `registrymodifications.xcu` — "never run any
  macro, signed or not"), copied fresh into an isolated temp directory
  for *every* conversion (never shared/mutable profile state, and this
  also means concurrent preview requests don't collide on LibreOffice's
  single-instance-per-profile lock).
- Every conversion's input/output/profile lives in its own
  `tempfile.TemporaryDirectory(dir=CACHE_DIR)` — under
  `/workspace/.osf_view_cache` (itself always denylisted, never
  `/workspace` directly or system `/tmp`) — and is deleted immediately
  after, success or failure, same pattern as the existing 7z-extraction
  code in `inspectors.py`.
- Output filenames are derived entirely from our own `input.<ext>` /
  `out/input.<ext>` naming — never from anything inside the document.
- **Known limitation, not attempted:** no network-level sandboxing of the
  `soffice` subprocess itself (no container/namespace isolation beyond the
  isolated profile+tempdir+macro-lockdown above) — a document containing a
  remote reference (linked OLE object, remote image) could still cause an
  outbound request during conversion. Full egress isolation would need
  container-level sandboxing, judged disproportionate for this pass;
  flagged here rather than silently assumed away.

**Dependencies:** see "venv / dependencies" below for the pinned Python
libraries, and "System office dependencies" for LibreOffice itself.
