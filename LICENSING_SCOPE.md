# Licence scope and third-party exclusions

The root [MIT licence](LICENSE) applies to source code, project-authored tests,
scripts, configuration examples and documentation **only to the extent Open
Source Films (OSF) or its contributors own or have the necessary rights to
license those particular contributions**. The licence does not override a
third party's copyright or separate terms. Preserve contributor and upstream
notices where applicable.

## Material not granted under OSF's MIT licence

- **All 12 binary Office and corrupted-document fixtures in
  `tests/fixtures/`**. Their hashes and unresolved rights are recorded in
  [docs/fixture-inventory.json](docs/fixture-inventory.json).
  The [file-by-file replacement decision](docs/FIXTURE_REPLACEMENT_DECISION.md)
  and [machine-readable register](docs/fixture-replacement-assessment.json)
  retain an explicit NOT APPROVED state for all twelve and document the
  residual Git-history publication issue. Some ZIP-based
  Office fixtures contain generated thumbnails, printer settings or custom
  XML; legacy binary fixtures are not fully inspected. No OSF MIT grant or
  permission to redistribute these files is asserted.
- Python packages and other external programs described in
  [DEPENDENCY_LICENSES.md](DEPENDENCY_LICENSES.md), including the applicable
  GPL, LGPL and other upstream requirements. They are not relicensed by OSF.
- Any externally owned code, images, models, sample media, data or other
  material, wherever located, for which OSF lacks sublicensing rights.
- Live files exposed by a Viewer installation under `/workspace` or
  Copyparty. Licensing the Viewer service does not license files it reads.

The public history identifies OSF-linked contributors, but commit authorship
alone is not a complete independent chain-of-title audit. Report any
unidentified third-party material through the
[licensing issue](https://github.com/OpenSourceFilms/osf-viewer/issues/1)
before relying on a redistribution grant for that material.

**Operational boundary:** Source licensing is not permission to bypass
the Viewer denylist, expose protected paths or deploy with an unreviewed
proxy configuration. Published code changes do not imply changes to a
running installation.
