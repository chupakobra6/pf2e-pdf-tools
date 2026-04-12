# PDF Runbook

## Goal
- Edit Pathfinder fillable PDFs so that:
- text is visible immediately in the rendered PDF,
- form values remain structurally correct,
- autosize works without changing field content,
- the result survives reopening in compatible viewers.

## Canonical path
1. Edit fields through [`scripts/pdf_form_editor.py`](/Users/igor/projects/pf2e_pdf_tools/scripts/pdf_form_editor.py).
2. For manual interactive editing, use [`scripts/pdf_form_web_editor.py`](/Users/igor/projects/pf2e_pdf_tools/scripts/pdf_form_web_editor.py) instead of editing the PDF in-browser.
3. Autosize text through [`scripts/pdf_form_tool.py`](/Users/igor/projects/pf2e_pdf_tools/scripts/pdf_form_tool.py).
3. Verify visually in Chrome or an Acrobat-compatible viewer.

## Do not use
- macOS Preview for saving this sheet.
- Cursor PDF viewer as an editor.

## Why
- This PDF stores state in both page widgets and `AcroForm /Fields`.
- Updating only one layer causes viewer-specific breakage.
- `pdf_form_editor.py` exists to keep both layers in sync from one code path.

## Current tools
- `scripts/pdf_form_editor.py`
  - `PdfFormEditor(path)`
  - `set_text(field_name, value)`
  - `set_checkbox(field_name, checked)`
  - `set_text_values({...})`
  - `set_checkbox_values({...})`
  - `autosize_text_fields(mode='filled')`
  - `save()`

- `scripts/pdf_form_tool.py`
  - autosize-only CLI
  - safe default: changes font sizing/appearance only
  - supports single-file watch and directory watch

- `scripts/pdf_form_web_editor.py`
  - local visual HTML editor for text fields and checkboxes
  - supports portrait image upload into the built-in portrait area
  - saves through `PdfFormEditor`
  - default mode saves values only; run autosize separately when finished

## Common commands
```bash
python3 scripts/pdf_form_tool.py /path/to/file.pdf
```

```bash
python3 scripts/pdf_form_tool.py /path/to/file.pdf --watch
```

```bash
python3 scripts/pdf_form_tool.py --watch-dir /path/to/folder
```

```bash
python3 scripts/pdf_form_web_editor.py /path/to/file.pdf --open-browser
```

## Minimal editing example
```python
from pathlib import Path
from pdf_form_editor import PdfFormEditor

pdf = Path("/path/to/file.pdf")
editor = PdfFormEditor(pdf)
editor.set_text("ancestry_name", "Человек")
editor.set_checkbox("skill_athletics_prof_e", True)
editor.autosize_text_fields("filled")
editor.save()
editor.close()
```

## Validation checklist
- Open the output in Chrome.
- Confirm key text fields are visible, not only present in form metadata.
- Confirm required checkboxes render as checked.
- If content changed materially, rerun autosize.

## Local-only files
- Keep private templates in `templates/local/`.
- Do not commit personal filled character sheets to the public repository.

## Troubleshooting
- If Chrome shows the text but Preview destroys it on save: the file is fine; Preview is the problem.
- If Cursor shows edits but the file on disk never changes: the viewer did not persist the form.
- If text is present in metadata but not visible: rerun through `PdfFormEditor` and then autosize.
