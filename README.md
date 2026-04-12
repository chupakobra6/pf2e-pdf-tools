# pf2e-pdf-tools

Toolkit for editing Pathfinder 2e fillable character sheet PDFs without breaking form rendering.

The project exists because these PDFs keep state in two places at once:
- page widgets,
- `AcroForm /Fields`.

If you update only one layer, different viewers start disagreeing. Text may look fine in one app and disappear in another, or saving in Preview may flatten or destroy the form state.

This repo keeps those layers in sync and provides a safer editing workflow.

## At a glance

- safe editing for Pathfinder 2e fillable sheets
- one core engine for field updates, autosize, and form synchronization
- local web UI for page-based editing
- canonical public templates in `templates/`
- private local files isolated in `templates/local/`

## Screenshots

### Visual editor

<img src="docs/images/web-editor.png" alt="Visual editor screenshot" width="1000">

### Rendered output

<img src="docs/images/demo-sheet-page1.png" alt="Rendered PDF output" width="760">

## Highlights

- Keeps page widgets and `AcroForm /Fields` synchronized.
- Autosizes text without rewriting field values or checkboxes.
- Provides a local visual editor for direct page-based form editing.
- Works from a canonical Pathfinder 2e fillable template.

## Repository layout

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

- `templates/`
  Public PDF templates and reference sheets tracked in the repository.

- `templates/RM_CharacterSheet_Fillable.pdf`
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
- `playwright` with a local Chromium install if you want automated UI screenshots

Install Python dependencies:

```bash
python3 -m pip install --user pymupdf playwright
python3 -m playwright install chromium
```

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

1. Start from `templates/RM_CharacterSheet_Fillable.pdf` if you need a clean rebuild.
2. Edit fields through `pdf_form_editor.py` or `pdf_form_web_editor.py`.
3. Run `pdf_form_tool.py` once after content edits.
4. Verify visually in Chrome or an Acrobat-compatible viewer.

## Public vs local files

- Keep public templates and reference PDFs in `templates/`.
- Keep private variants and filled sheets in `templates/local/`.
- `templates/local/` is git-ignored by design.

## Do not use

- macOS Preview for saving the working sheet
- IDE PDF viewers as the source of truth for edits

## Validation

- Open the output in Chrome or an Acrobat-compatible viewer.
- Confirm key text fields are visible, not only present in form metadata.
- Confirm required checkboxes render as checked.
- If content changed materially, rerun autosize.

## Troubleshooting

- If Chrome shows the text but Preview destroys it on save, the file is usually fine and Preview is the problem.
- If an IDE viewer shows edits but the file on disk never changes, the viewer did not persist the form.
- If text is present in metadata but not visible, run the file through `PdfFormEditor` and then autosize again.

## Project status

This repo is intentionally small and pragmatic. It is focused on one job:
editing Pathfinder 2e fillable PDFs in a way that remains structurally correct across viewers.
