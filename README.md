# pf2e-pdf-tools

Toolkit for editing Pathfinder 2e fillable character sheet PDFs without breaking form rendering.

The project exists because these PDFs keep state in two places at once:
- page widgets,
- `AcroForm /Fields`.

If you update only one layer, different viewers start disagreeing. Text may look fine in one app and disappear in another, or saving in Preview may flatten or destroy the form state.

This repo keeps those layers in sync and provides a safer editing workflow.

## What is here

- `scripts/pdf_form_editor.py`
  Generic editor for fillable PDF forms.
  Updates visible widget state and structural form values together.

- `scripts/pdf_form_tool.py`
  Autosize-only CLI.
  Changes font sizing and appearance only.
  Does not rewrite field values or checkboxes.

- `scripts/pdf_form_web_editor.py`
  Local visual web editor for PDF forms.
  Renders page images with editable text fields and checkboxes overlaid on top.
  Supports portrait upload for the built-in portrait field.

- `RM_CharacterSheet_Fillable.pdf`
  Canonical Pathfinder 2e fillable base used for rebuilds and repair work.

- `templates/local/`
  Private local template directory.
  Files placed there are ignored by git and stay off GitHub.

## Why this exists

Standard viewers are unreliable for this sheet:
- macOS Preview can destroy or flatten form data on save.
- IDE PDF viewers often display forms but do not persist edits correctly.
- browser viewers may render fields differently from Acrobat-compatible tools.

This project gives you a controlled path:
1. edit with the provided tools,
2. autosize once,
3. verify in Chrome or an Acrobat-compatible viewer.

## Quick start

Requirements:
- Python 3
- `pymupdf` / `fitz`

Run the visual editor:

```bash
python3 scripts/pdf_form_web_editor.py /path/to/file.pdf --open-browser
```

Autosize after editing:

```bash
python3 scripts/pdf_form_tool.py /path/to/file.pdf
```

Watch one file:

```bash
python3 scripts/pdf_form_tool.py /path/to/file.pdf --watch
```

Watch a directory:

```bash
python3 scripts/pdf_form_tool.py --watch-dir /path/to/folder
```

## Minimal API example

```python
from pathlib import Path
from scripts.pdf_form_editor import PdfFormEditor

pdf = Path("/path/to/file.pdf")
editor = PdfFormEditor(pdf)

editor.set_text("ancestry_name", "Человек")
editor.set_checkbox("skill_athletics_prof_e", True)
editor.autosize_text_fields("filled")
editor.save()
editor.close()
```

## Recommended workflow

1. Start from `RM_CharacterSheet_Fillable.pdf` if you need a clean rebuild.
2. Edit fields through `pdf_form_editor.py` or `pdf_form_web_editor.py`.
3. Run `pdf_form_tool.py` once after content edits.
4. Verify visually in Chrome or an Acrobat-compatible viewer.

## Local files

- Put private templates in `templates/local/`.
- Do not commit personal filled sheets to the public repository.

## Do not use

- macOS Preview for saving the working sheet
- IDE PDF viewers as the source of truth for edits

## Project status

This repo is intentionally small and pragmatic. It is focused on one job:
editing Pathfinder 2e fillable PDFs in a way that remains structurally correct across viewers.
