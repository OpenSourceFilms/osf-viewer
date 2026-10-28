# Generated Office fixture component provenance review

**Review date:** 28 October 2026. **Status: functional candidates accepted;
copyright and redistribution clearance remains conditional.**

This document distinguishes **newly authored visible sample content** from
**formatting and template infrastructure inherited from authoring tools**.
It does not change the 12 existing binary files in `tests/fixtures/`, their
rights-pending manifest or the existing Viewer service.

## Evidence and limits

The original semantic regression suite passed **26/26** assertions against
the generated candidate set on GitHub Actions
[PR #20](https://github.com/OpenSourceFilms/osf-viewer/pull/20),
[PR run 40604202408](https://github.com/OpenSourceFilms/osf-viewer/actions/runs/40604202408)
and [merged-main run 40604374351](https://github.com/OpenSourceFilms/osf-viewer/actions/runs/40604374351).
That is functional evidence, **not** a licence to distribute a binary.

An isolated local recreation with the same pinned authoring versions found
the following structure. The CI component audit
[`scripts/audit_generated_office_components.py`](../scripts/audit_generated_office_components.py)
now inventories the actual generated packages and rejects unexpected binary
media, embedded assets, unsafe ZIP members, external OOXML relationships and
selected private metadata. The audit deliberately **lists**, rather than
silently treats as OSF-owned, source-template styling parts.

| Candidate package | ZIP parts in local sample | Included inherited formatting | Excluded components in local sample |
|---|---:|---|---|
| DOCX | 13 | Word styles, theme, numbering, font table and settings | No raster images, attachments, custom XML or printer settings |
| XLSX | 10 | Workbook theme and styles | No raster images or embedded binary payloads |
| PPTX | 49 | PowerPoint themes, slide master/layouts, notes master | No raster images, attachments, custom XML or printer settings |
| ODT | 5 | ODF styles and package metadata | No separate image/font/binary parts |
| ODS | 5 | ODF styles and package metadata | No separate image/font/binary parts |
| ODP | 5 | ODF styles and package metadata | No separate image/font/binary parts |

The counts are an environmental snapshot, **not a frozen byte-for-byte
reproducibility guarantee**. A CI job must inspect its own generated files.
The legacy DOC/XLS/PPT/RTF candidates are **not ZIP packages** and therefore
are **not cleared by this ZIP component inventory**. Their existing semantic
regressions passed, but raw OLE/RTF metadata and embedded-component
provenance need separate inspection before redistribution.

## Generator dependency and template rights

| Authoring dependency | Reviewed version | Upstream rights and observed inherited components |
|---|---|---|
| [python-docx](https://github.com/python-openxml/python-docx) | 1.2.0 | Its distributed licence is MIT, © 2013 Steve Canny. `Document()` starts from its bundled `templates/default.docx`. The new DOCX retains styles, theme and document properties, although the generator removes thumbnail and custom XML parts. Preserve upstream notices if distributing copied substantial template material. |
| [python-pptx](https://github.com/scanny/python-pptx) | 1.0.2 | Its distributed licence is MIT, © 2013 Steve Canny. `Presentation()` starts from `templates/default.pptx`; the resulting PPTX retains slide layouts, masters and themes. A lack of images is **not** proof that every XML part was independently authored by OSF. |
| [openpyxl](https://foss.heptapod.net/openpyxl/openpyxl) | 3.1.5 | Its distributed licence is MIT, © 2010 openpyxl. The XLSX writer adds standard theme and style definitions. Record their origin and preserve appropriate notices for copied content. |
| [odfpy](https://github.com/eea/odfpy) | 1.4.1 | The upstream README offers its project code under Apache-2.0 **or** GPL-2.0-or-later, excluding OASIS OpenDocument RelaxNG schemas with separate copyright. Generated ODT/ODS/ODP packages contain ODF styles/metadata; the local packages did not contain schema files. Confirm exact distributed metadata/components against applicable notices before any rights-cleared publication. |
| [LibreOffice](https://www.libreoffice.org/) | External host installation | Generates legacy DOC/XLS/PPT/RTF from the modern examples. Successful conversion does not establish the origin or copyright status of all OLE/RTF binary structures. Do not conflate the generator's Python source licence with the converter's separate licences. |

References are pointers to upstream licence/source documentation.
This is a provenance inventory, not legal advice or a determination that
every generated file is cleared. A generation tool's licence does not
automatically confer a blanket copyright assignment over its output.

## Legacy OLE2/RTF candidate component audit

The [generated legacy component scanner](../scripts/audit_generated_legacy_components.py)
inspects only disposable `sample.doc`, `sample.xls`, `sample.ppt`
and `sample.rtf` candidates. It rejects missing/symlinked files,
unexpected OLE2 signatures, illegible OLE2 directories, named macro/
embedded-object storages, RTF embedded image/object controls, external
field instructions and selected private-path/email patterns. It limits
input sizes and emits SHA-256 hashes, OLE2 directory counts and metadata
**field names** without printing raw creator/company/property values.

OLE2 stream enumeration and property inspection use the separately installed
audit-only [olefile 0.47](https://pypi.org/project/olefile/0.47/) package
(BSD-style licence and inherited PIL notice). It is **not** added to the
Viewer application's 21-pin runtime dependencies. The CI dependency is
pinned to `olefile==0.47`; its licences are not being granted by OSF.

A successful structural report **does not** exclude pictures embedded
inside opaque Word/Excel/PowerPoint document streams, prove absence of
all hidden OLE records, or identify ownership of a converter's output.
OLE2 `Pictures`-like streams now receive a bounded stream-size check.
An **empty** stream is reported as such; a nonempty stream is reported with
length and SHA-256 hash only, never raw contents, and remains explicitly flagged
for image/content review. This is a limited payload probe, **not** a complete
parser for all binary image or embedded-object formats. The RTF scanner checks
known control words rather than performing a full RTF parse. A report may also identify inherited
creator/template metadata and historical timestamps: these are recorded
as **attribution and review prompts**, not scrubbed or declared private
simply because the date is old.

The [original extraction compatibility runner](../scripts/verify_generated_office_compatibility.py)
now requires both the ZIP-based and legacy-container reports to pass before
running the unchanged 26-function Office regression suite. Existing
published fixture blobs and inventory remain untouched.

**Do not interpret `pass_structural_checks` as copyright clearance.**
Complete chain-of-title and upstream notices for concrete replacement files
are still pending.

## Exact-file evidence and upstream notices

The [prospective upstream notices](GENERATED_OFFICE_NOTICES.md) contain full
MIT licence notices for the relevant document authoring packages, the
odfpy Apache-2.0 reference licence text, and the separate audit-only
olefile/PIL terms. These notices are **pre-release material**, not a
rights assignment or clearance of old binary fixtures.

The [per-run provenance recorder](../scripts/record_generated_office_evidence.py)
is executed after the existing 26 semantic regressions and the ZIP and
OLE2/RTF structural checks succeed. It rejects missing/extra/symlinked
candidate files, records the exact SHA-256 and byte size for all 12
disposable outputs, the installed versions of the authoring/conversion
tools, the GitHub checkout SHA when available, and the bounded package
audit reports. It never archives the generated Office binaries. The
GitHub Actions job uploads a **JSON-only** evidence artifact retained
for 14 days. A different run may produce different file hashes.

The artifact explicitly declares `copyright_and_redistribution_cleared:
false`. Preserving exact-file provenance enables separate review; it
does not itself authorize publishing replacement binaries. Source
templates, legacy opaque streams and upstream licence notices still
require release-specific acceptance.

## Remaining release gate

1. Preserve upstream notices in a rights file accompanying **any** new
   distribution that includes meaningful reused template/style/master content.
2. Review legacy OLE2/RTF audit results, including opaque document
   streams, known source-template attribution and converter metadata; this
   machine audit alone does not establish embedded-content ownership.
3. For every replacement, retain the source generator, exact authoring and
   conversion versions, file hashes and passing original regression output.
4. Review generated files and notices before changing the twelve tracked
   binary fixtures and their rights-pending inventory.
5. Do not infer clearance for production footage or other documents the
   deployed Viewer can read.

**At present, the existing fixture binaries remain excluded from OSF's
scoped MIT grant and have not been replaced.**
