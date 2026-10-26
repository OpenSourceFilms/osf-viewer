# Viewer third-party dependency licence metadata

**Review date: 27 October 2026. Source: publisher-supplied PyPI metadata for the pinned releases.**

The 21 rows below correspond exactly to the direct pins in requirements.lock.txt.
These metadata descriptions are not source-code licence verification, wheel/SDist
inspection, a full transitive software bill of materials or legal approval.
PyPI does not independently verify whether project metadata matches the
actual distributed licence texts. Names, versions and URLs are evidence
for further review, not rights granted by OSF.

**OSF Viewer itself currently has no root LICENSE/COPYING.** Its source
remains publicly visible without a general reuse grant. An LGPL, GPL,
Apache, BSD or MIT licence on a dependency grants rights to the material
covered by that dependency, not automatically to the Viewer application.
Owner approval is still required: https://github.com/OpenSourceFilms/osf-viewer/issues/1.

## Publisher-declared licences by exact pinned package

| Pinned requirement | Published licence metadata | Evidence | Notes |
|---|---|---|---|
| backports.zstd==1.7.0 | PSF-2.0 | [PyPI 1.7.0](https://pypi.org/project/backports.zstd/1.7.0/) | Pinned-release SPDX metadata |
| brotli==1.2.0 | MIT | [PyPI 1.2.0](https://pypi.org/project/brotli/1.2.0/) | Upstream publisher description / release metadata |
| inflate64==1.0.4 | LGPL-2.1-or-later | [PyPI 1.0.4](https://pypi.org/project/inflate64/1.0.4/) | Pinned-release metadata; bundled zlib C code needs notice review |
| multivolumefile==0.2.3 | LGPL-2.1-or-later | [PyPI 0.2.3](https://pypi.org/project/multivolumefile/0.2.3/) | Pinned-release metadata |
| mutagen==1.48.1 | GPL-2.0-or-later | [PyPI 1.48.1](https://pypi.org/project/mutagen/1.48.1/) | Pinned-release SPDX metadata; redistribution analysis required |
| numpy==2.5.2 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | [PyPI 2.5.2](https://pypi.org/project/numpy/2.5.2/) | Combined published SPDX expression; inspect build notices |
| odfpy==1.4.1 | Apache / GPL / LGPL (terms unresolved) | [PyPI 1.4.1](https://pypi.org/project/odfpy/1.4.1/) | Release metadata names multiple licence families; applicable grants still require source review |
| openpyxl==3.1.5 | MIT | [PyPI 3.1.5](https://pypi.org/project/openpyxl/3.1.5/) | Pinned-release metadata |
| pillow==12.3.0 | MIT-CMU | [PyPI 12.3.0](https://pypi.org/project/pillow/12.3.0/) | Pinned-release SPDX expression; external image codecs require separate review |
| psutil==7.2.2 | BSD-3-Clause | [PyPI 7.2.2](https://pypi.org/project/psutil/7.2.2/) | Pinned-release metadata |
| py7zr==1.1.4 | LGPL-2.1-or-later | [PyPI 1.1.4](https://pypi.org/project/py7zr/1.1.4/) | Pinned-release SPDX expression; 12 Oct 2026 upstream fix for symlink-chain arbitrary writes |
| pyarrow==25.0.1 | Apache-2.0 | [PyPI 25.0.1](https://pypi.org/project/pyarrow/25.0.1/) | Pinned-release SPDX expression; binary C++ libraries/notices not audited |
| pybcj==1.0.8 | LGPL-2.1-or-later | [PyPI 1.0.8](https://pypi.org/project/pybcj/1.0.8/) | Pinned-release SPDX expression; C code adapted from 7-Zip family |
| pycryptodomex==3.23.0 | BSD / Public Domain | [PyPI 3.23.0](https://pypi.org/project/pycryptodomex/3.23.0/) | Pinned-release metadata; inspect bundled components |
| pypdf==6.17.0 | BSD-3-Clause | [PyPI 6.17.0](https://pypi.org/project/pypdf/6.17.0/) | Pinned-release SPDX expression |
| pyppmd==1.3.1 | LGPL-2.1-or-later | [PyPI 1.3.1](https://pypi.org/project/pyppmd/1.3.1/) | Pinned-release metadata |
| python-docx==1.2.0 | MIT | [PyPI 1.2.0](https://pypi.org/project/python-docx/1.2.0/) | Pinned-release metadata |
| python-magic==0.4.27 | MIT | [PyPI 0.4.27](https://pypi.org/project/python-magic/0.4.27/) | Python wrapper only; external libmagic C library separate |
| python-pptx==1.0.2 | MIT | [PyPI 1.0.2](https://pypi.org/project/python-pptx/1.0.2/) | Pinned-release metadata |
| safetensors==0.8.0 | Apache-2.0 | [PyPI 0.8.0](https://pypi.org/project/safetensors/0.8.0/) | Pinned-release metadata |
| texttable==1.7.0 | MIT | [PyPI 1.7.0](https://pypi.org/project/texttable/1.7.0/) | Pinned-release metadata |

## Security update: 27 October 2026

The earlier `py7zr==1.1.3` pin predates upstream's 12 October 2026
`py7zr==1.1.4` security fix for crafted archive symlink chains
([upstream changelog](https://py7zr.readthedocs.io/en/stable/Changelog.html)).
The repository now pins 1.1.4 and uses a bounded in-memory WriterFactory
for Viewer 7z member extraction instead of asking py7zr to create files.
Upgrading the source pin does **not** install the update on any running
Viewer service. Independently validate before deploying.

## Rights-sensitive dependencies

- **mutagen 1.48.1: GPL-2.0-or-later.** Do not describe the dependency
  chain as entirely MIT/permissive. Determine whether and how a particular
  redistributed deliverable includes or combines this library, and what
  source/notice obligations apply. This table does not assert that Viewer
  application code is automatically GPL-licensed.
- **inflate64, multivolumefile, py7zr, pybcj, pyppmd: LGPL-2.1-or-later.**
  Their use and possible redistribution require the relevant licence texts,
  copyright notices and compliance appropriate to the actual packaging.
- **odfpy:** the published package metadata lists Apache, GPL and LGPL
  licence families without a clear per-file/alternative-grant determination.
  Treat that as **unresolved**, not as a proven blanket Apache permission.
- **numpy / Pillow / pyarrow / cryptography and compression extensions:**
  pinned-release licence metadata does not establish every licence present
  in compiled wheels, bundled C/C++ libraries, transitive dependencies or
  optional system packages. In particular, python-magic wraps system
  libmagic, which is not itself covered by the wrapper's MIT metadata.

## Release and maintenance rules

1. If requirements.lock.txt changes, update the corresponding licence
   table in this same change set. Offline CI checks exact pin coverage.
2. For any redistribution, record actual wheel/sdist hashes and licences,
   required NOTICE/COPYING files and whether a dependency was modified.
3. Establish authorship/assignment for OSF's own source and independently
   clear the 12 Office test fixtures, including document thumbnails and
   legacy binary payloads, before deciding the repository-wide licence.
4. Do not silently append a root MIT licence simply because some
   dependencies use MIT. See the open rights-decision issue.

**This document creates no new licence grant and does not change any installed
package, running service, real media, credential or historical Git object.**
