# Generated Viewer Office fixture candidate notices (pre-release)

**Status: provenance record and prospective attribution, not redistribution clearance.**
These notices apply to the **disposable newly generated candidates** only.
They are not a licence for any of the 12 historical fixtures currently
published under `tests/fixtures/`, which remain explicitly outside the
original OSF-source MIT grant.

## Attribution and origin mapping

| Candidate | Newly authored content and generated-from lineage | Inherited source and notices |
|---|---|---|
| `sample.docx` | Hand-authored sample headings/paragraphs/tables in [generator](../scripts/generate_clean_office_candidates.py) | `python-docx==1.2.0`, bundled default DOCX template, styles and theme. See Steve Canny MIT notice below. |
| `sample.pptx` | Generator's three slides and notes | `python-pptx==1.0.2`, bundled default PPTX template, masters, notes master, themes/layouts. See Steve Canny MIT notice below. |
| `sample.xlsx` | Generator's workbook and sample values | `openpyxl==3.1.5` writer-provided styles and workbook theme. See openpyxl MIT notice below. |
| `sample.odt`, `sample.ods`, `sample.odp` | Generator's synthetic document, spreadsheet and presentation | `odfpy==1.4.1`, upstream dual GPL-2.0-or-later **or** Apache-2.0 licence (Apache route is under review). [Apache-2.0 full text](third_party/APACHE-2.0-odfpy.txt); [upstream README](https://github.com/eea/odfpy/blob/master/README.md). OASIS OpenDocument schema assets carry separate copyright, and have not been observed as extra files in the generated packages. |
| `sample.doc`, `sample.rtf` | Generated from candidate DOCX using local LibreOffice | Inherit candidate DOCX attribution plus separately licensed LibreOffice converter and possible conversion metadata; no new blanket rights assertion. |
| `sample.ppt` | Generated from candidate PPTX using LibreOffice | Inherit candidate PPTX attribution and converter metadata. The generated `Pictures` stream was confirmed **empty** by CI; opaque streams remain unproven. |
| `sample.xls` | Generated from candidate XLSX using LibreOffice | Inherit XLSX attribution and converter metadata; no new blanket rights assertion. |
| `corrupt.docx`, `corrupt.xls` | Explicit intentionally invalid byte literals in generator | No Office source template copied into those deliberately malformed files. |

The audit-only `olefile==0.47` OLE2 reader is **not bundled into the
Viewer's runtime**. If distributing the audit environment or reader, review
its BSD-style and inherited PIL notices from the [upstream licence](https://github.com/decalage2/olefile/blob/v0.47/LICENSE.txt), reproduced below.

`LibreOffice` is used as an external conversion program, not distributed
by this repository. Review the exact installed LibreOffice release's bundled
licences and any relevant output metadata before distributing derivatives.
The CI record retains the concrete version string.

## Exact inherited-template bytes

The [template comparison script](../scripts/audit_generated_template_inheritance.py)
identifies DOCX/PPTX members copied byte-for-byte from the installed default
templates, including Word styles and Office themes. The evidence is linked
to exact template and generated-candidate SHA-256 hashes in each CI
provenance record. Modified same-name members may also derive from those
templates and should not be presumed independently authored.

Preserve the upstream MIT notices below alongside any binary distribution
that contains substantial original template material. These notices
document a prospective redistribution basis, not a new OSF ownership
claim over the copied formatting. The historical 12 fixtures remain
excluded and unverified.

## Original python-docx and python-pptx licence notice

Both pinned source projects include the following MIT licence text with the
same copyright owner, checked against
[python-docx v1.2.0](https://github.com/python-openxml/python-docx/blob/v1.2.0/LICENSE)
and [python-pptx v1.0.2](https://github.com/scanny/python-pptx/blob/v1.0.2/LICENSE).
This notice is retained for potentially substantial inherited template parts.

```text
The MIT License (MIT)
Copyright (c) 2013 Steve Canny, https://github.com/scanny

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

## openpyxl licence notice and its additional upstream qualification

The original openpyxl MIT notice from
[the historic upstream licence file](https://github.com/ericgazoni/openpyxl/blob/master/LICENCE.rst)
is included below. The source licence also mentions a separate Python Software
Foundation licence for historical `odict` code. This is a conservative
notice record, **not** proof that the exact 3.1.5 XLSX generated bytes contain
that historical source component.

```text
This software is under the MIT Licence
======================================

Copyright (c) 2010 openpyxl

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Odict implementation in openpyxl/writer/odict.py uses the following licence:

Copyright (c) 2001-2011 Python Software Foundation
              2011 Raymond Hettinger
License: PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2
         See http://www.opensource.org/licenses/Python-2.0 for full terms
Note: backport changes by Raymond were originally distributed under MIT
      license, but since the original license for Python is more 
      restrictive than MIT, code cannot be released under its terms and
      still adheres to the limitations of Python license.
```

## olefile audit-only notice

The full upstream [olefile v0.47 licence](https://github.com/decalage2/olefile/blob/v0.47/LICENSE.txt)
includes a notice for code inherited from the Python Imaging Library.
It is reproduced for the audit-only toolchain, **not** as a claim that `olefile`
contributes bytes to the generated Office documents.

```text
LICENSE for the olefile package:

olefile (formerly OleFileIO_PL) is copyright (c) 2005-2023 Philippe Lagadec
(https://www.decalage.info)

All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

 * Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
 * Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


----------

olefile is based on source code from the OleFileIO module of the Python
Imaging Library (PIL) published by Fredrik Lundh under the following license:

The Python Imaging Library (PIL) is
- Copyright (c) 1997-2009 by Secret Labs AB
- Copyright (c) 1995-2009 by Fredrik Lundh

By obtaining, using, and/or copying this software and/or its associated
documentation, you agree that you have read, understood, and will comply with
the following terms and conditions:

Permission to use, copy, modify, and distribute this software and its
associated documentation for any purpose and without fee is hereby granted,
provided that the above copyright notice appears in all copies, and that both
that copyright notice and this permission notice appear in supporting
documentation, and that the name of Secret Labs AB or the author not be used
in advertising or publicity pertaining to distribution of the software without
specific, written prior permission.

SECRET LABS AB AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS
SOFTWARE, INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN
NO EVENT SHALL SECRET LABS AB OR THE AUTHOR BE LIABLE FOR ANY SPECIAL,
INDIRECT OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
```

## Remaining requirements before replacing binary fixtures

1. Match the exact generated candidate bytes to a machine-generated
   [per-run provenance manifest](../scripts/record_generated_office_evidence.py)
   with 12 SHA-256 digests, sizes and installed tool versions. **Different
   CI runs may generate different hashes** because formats and timestamps are
   not guaranteed byte-reproducible across environments.
2. Confirm that the notices in this document, the Apache-2.0 licence if
   applicable, and any additional appropriate upstream notices accompany a
   proposed binary redistribution. A lawyer or rights owner may still need
   to resolve unclear inherited template/legacy stream ownership.
3. Treat the OLE2 and RTF audits as bounded structural evidence, not full
   forensic analysis of opaque Office content.
4. Replace historical rights-pending binary fixtures only in a **separate
   reviewed change** that updates the exact-byte inventory and reruns all
   semantic, integrity and security checks.

**No historical fixture or its rights status is modified by this notice file.**
