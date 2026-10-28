# Viewer Office fixture replacement decision record

**Date:** 28 October 2026  
**Decision:** **NOT APPROVED for binary replacement or relicensing**  
**Scope:** 12 historical public `tests/fixtures/` files and 12 **disposable source-generated candidates**.

This is an actionable technical and rights decision record, not a legal opinion or
permission to redistribute either set of files.

## Current acceptance evidence

- The generator in [`scripts/generate_clean_office_candidates.py`](../scripts/generate_clean_office_candidates.py) produces 12 disposable candidate files; no generated binaries are committed.
- The [exact merged-main candidate run](https://github.com/OpenSourceFilms/osf-viewer/actions/runs/40609015297)
  passed **26/26 unchanged Office extraction tests**, generated ZIP/legacy structure audits, and default DOCX/PPTX template-byte inheritance checks.
- The JSON-only `viewer-office-evidence` artifact records 12 candidate SHA-256 hashes,
  source/derived-from lineage, installed tool versions and inherited template ZIP
  part hashes. **The hashes are per-run evidence**, not a stable release target.
- [`docs/GENERATED_OFFICE_NOTICES.md`](GENERATED_OFFICE_NOTICES.md)
  retains relevant upstream notices and alternative licence routes.
- All historical Git blob IDs are recorded in
  [`docs/fixture-inventory.json`](fixture-inventory.json) and remain excluded
  from the OSF original-source MIT grant. The companion
  [machine-readable review register](fixture-replacement-assessment.json)
  binds each original blob and size to its proposed candidate lineage,
  outstanding rights conditions and explicit **NOT_APPROVED** state.

## File-by-file decision table

The entries below refer to **proposed new candidates**, not to rights in the
historical binary with the same name. Every historical fixture remains pending.

| File | Candidate origin and evidence | Additional required review | Decision |
|---|---|---|---|
| `corrupt.docx` | Explicit malformed byte literal in OSF generator | Verify source authorship and fallback assertion, bind exact candidate SHA-256 | NOT APPROVED |
| `corrupt.xls` | Explicit malformed byte literal in OSF generator | Same as above | NOT APPROVED |
| `sample.docx` | `python-docx` MIT default template, with exact inherited ZIP member hashes | Keep Steve Canny notice, check all same-name modified derivatives and package contents | NOT APPROVED |
| `sample.xlsx` | `openpyxl` MIT writer, new workbook content | Keep openpyxl notice, review theme/style and metadata | NOT APPROVED |
| `sample.pptx` | `python-pptx` MIT default template, with exact inherited ZIP member hashes | Keep Steve Canny notice, check masters/layouts, package contents | NOT APPROVED |
| `sample.odt` | `odfpy` OpenDocument writer | Confirm Apache-2.0 option and any OASIS schema exceptions | NOT APPROVED |
| `sample.ods` | `odfpy` OpenDocument writer | Same as above, including generated spreadsheet data | NOT APPROVED |
| `sample.odp` | `odfpy` OpenDocument writer | Same as above, including slide style data | NOT APPROVED |
| `sample.doc` | LibreOffice conversion of new DOCX candidate | Carry through MIT template notice; inspect OLE record provenance, converter metadata | NOT APPROVED |
| `sample.xls` | LibreOffice conversion of new XLSX candidate | Carry through openpyxl notice; inspect opaque OLE/BIFF records and attribution | NOT APPROVED |
| `sample.ppt` | LibreOffice conversion of new PPTX candidate | Carry through MIT template notice; inspect opaque PowerPoint records and attribution; the generated `Pictures` stream was **0 bytes** | NOT APPROVED |
| `sample.rtf` | LibreOffice conversion of new DOCX candidate | Carry through MIT template notice; inspect RTF formatting, metadata and references | NOT APPROVED |

The notices support a **plausible redistribution route for new candidates**
where the governing terms and file contents are confirmed. They do not cure
unknown rights in old files. The independent release reviewer should record
the specific output-byte evidence and permission basis before a decision changes.

## Historical Git objects remain published

**Replacing `tests/fixtures/*` in a new commit does not remove the old blobs
from previous commits.** The old content may also persist in forks, caches,
downloaded archives and existing clones. This is a separate publication issue:

1. If rights in the *historical* bytes are substantiated, retain source
   evidence, proper notices and the relevant scope boundaries.
2. If rights are missing, decide separately how to mitigate past publication.
   Potential options include a fresh-history repository, rewriting history,
   or rights-holder outreach. Each has external consequences and may break
   links, commit SHAs, existing clones, open PRs and downstream dependencies.
3. **Do not rewrite public Git history, force-push, delete repositories or
   make a legal representation without a separate explicit decision.**
   An existing clone or fork cannot necessarily be recalled after a rewrite.

Leaving the old files excluded from the project's MIT grant is an appropriate
interim rights statement, **not a substitute for resolving an unauthorized
publication if one is identified**.

## Gate for a future proposed replacement PR

The new [assessment verifier](../scripts/verify_fixture_replacement_assessment.py)
deliberately accepts **only NOT_APPROVED records** bound to the current original
blob IDs. Changing approval status or replacing files would require an explicit,
reviewed update to the verifier and the historical inventory.

Before any new fixture bytes can be proposed, require:

1. Capture 12 candidate binaries from one evidence-linked generation run with
   exact hashes, tool versions, provenance and notices.
2. Review all 12 on a **specific** rights basis. Note copied MIT template
   material, OpenDocument licence choice and opaque legacy conversion limits.
3. Record separate authorized approval for those exact replacement hashes,
   including any rights limitations. Functional tests cannot be approval.
4. Make a separate binary replacement PR; update the old-file inventory and
   scope document only as independently justified, and pass all semantic,
   manifest, component and security tests.
5. Review separately whether historical public content requires remediation.

**No replacements, license-scope changes, history rewrites or deployments
have been made as part of this assessment.**
