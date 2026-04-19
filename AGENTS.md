# AGENTS.md

## PDF workflow
- Use `pyproject.toml` and `uv.lock` as the dependency source of truth; do not introduce parallel `requirements.txt` instructions.
- Bootstrap and run repo tooling through `uv` (`uv sync`, `uv run ...`) unless there is a repo-specific reason not to.
- If dependencies change, update and commit `pyproject.toml` and `uv.lock` together.
- Do not bulk-rewrite character sheets.
- Preserve user manual edits by default.
- If a PDF value must change, update only the explicitly requested fields.
- Autosize tooling must only change font sizes, never field values or checkboxes.
- Test autosize changes on a temporary copy before suggesting or using them on the working PDF.
- Use `scripts/pdf_form_editor.py` as the canonical way to edit this PDF form; it updates both visible widgets and form metadata together.
- On the localized D&D sheets, prefer `set_skill_values` and `set_skill_proficiencies` over raw widget names; use `raw:` only for debugging or one-off inspection.
- Use `templates/RM_CharacterSheet_Fillable.pdf` as the canonical fillable base when rebuilding or repairing a sheet; do not treat filled copies as the source template.
- Use `scripts/pdf_form_web_editor.py` for manual interactive editing; do not manually edit the PDF file itself in a browser viewer.
- Keep personal filled sheets out of git; use ignore rules for local character files.
- Put private user-only PDF templates in `templates/local/`; that folder must stay ignored by git.
- After content edits, run `scripts/pdf_form_tool.py` to autosize text fields.
- Do not save this Pathfinder sheet through macOS Preview; it can destroy or flatten form data.
- Do not rely on the Cursor PDF viewer to persist form edits; treat it as view-only for this project.
- Use Chrome or an Acrobat-compatible viewer for visual verification of filled sheets.
- If you change D&D template detection, logical skill remapping, image-slot detection, glyph normalization, or web-editor file-switch / stale-save handling, run `uv run python -m unittest discover -s tests`.
- If you change web-editor image uploads or button/image widget handling, verify the real `multipart/form-data` `/save` path and ensure those widgets do not render as page text overlays.

## Player-facing docs
- For player-facing rules references or lore explainers in this repo, write in concise reference style: factual mechanics/lore statements first, minimal interpretation, and no mood-driven phrasing such as "по вайбу", personality framing, or speculative "reads as" language unless the user explicitly asks for that style.
