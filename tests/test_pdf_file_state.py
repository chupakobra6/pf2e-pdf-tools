from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.pdf_form_editor import FileConflict, PdfFormEditor


def make_pdf(path: Path) -> None:
    with fitz.open() as doc:
        page = doc.new_page(width=200, height=200)
        text = fitz.Widget()
        text.field_name = "Name"
        text.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        text.field_value = "Original"
        text.rect = fitz.Rect(20, 30, 180, 60)
        page.add_widget(text)
        checkbox = fitz.Widget()
        checkbox.field_name = "Ready"
        checkbox.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        checkbox.rect = fitz.Rect(20, 80, 40, 100)
        page.add_widget(checkbox)
        doc.save(path)


class SnapshotSaveTests(unittest.TestCase):
    def test_stale_editor_keeps_new_file_and_its_own_unsaved_input(self):
        for change in ("external", "replacement", "removed"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "sheet.pdf"
                make_pdf(path)
                editor = PdfFormEditor(path)
                self.addCleanup(editor.close)
                editor.set_text("Name", "Unsaved input")
                if change == "external":
                    # An uncooperative writer: no tool locks or editor API.
                    with fitz.open(path) as doc:
                        page = doc[0]
                        widget = next(page.widgets())
                        widget.field_value = "External"
                        widget.update()
                        doc.saveIncr()
                elif change == "replacement":
                    replacement = path.with_name("replacement.pdf")
                    replacement.write_bytes(path.read_bytes())
                    replacement.replace(path)
                else:
                    path.unlink()
                expected = path.read_bytes() if path.exists() else None
                with self.assertRaises(FileConflict):
                    editor.save()
                self.assertEqual(path.read_bytes() if path.exists() else None, expected)
                self.assertEqual(editor.field_value("Name"), "Unsaved input")
                self.assertFalse(list(path.parent.glob(".tmp_edit_*")))

    def test_separate_process_cannot_overwrite_earlier_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sheet.pdf"
            make_pdf(path)
            # Both processes read the same file before either is allowed to save.
            script = '''from scripts.pdf_form_editor import PdfFormEditor, FileConflict
import sys
editor = PdfFormEditor(sys.argv[1])
editor.set_text("Name", sys.argv[2])
print("ready", flush=True)
input()
try:
    editor.save()
    print("saved", flush=True)
except FileConflict:
    print("conflict:" + editor.field_value("Name"), flush=True)
finally:
    editor.close()
'''
            children = [subprocess.Popen([sys.executable, "-c", script, str(path), name],
                cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                for name in ("First", "Second")]
            try:
                for child in children:
                    self.assertEqual(child.stdout.readline().strip(), "ready")
                for child in children:
                    child.stdin.write("go\n")
                    child.stdin.flush()
                outputs = [child.communicate(timeout=10) for child in children]
                results = [out.strip() for out, err in outputs]
                self.assertEqual(results.count("saved"), 1, outputs)
                self.assertEqual(sum(r.startswith("conflict:") for r in results), 1, outputs)
                editor = PdfFormEditor(path)
                self.addCleanup(editor.close)
                winner = "First" if results[0] == "saved" else "Second"
                self.assertEqual(editor.field_value("Name"), winner)
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                    child.communicate()

    def test_external_edit_immediately_after_publication_is_not_adopted_as_our_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sheet.pdf"
            make_pdf(path)
            editor = PdfFormEditor(path)
            self.addCleanup(editor.close)
            editor.set_text("Name", "Our edit")
            replace = os.replace
            def external_after_replace(temporary, target):
                replace(temporary, target)
                with fitz.open(target) as doc:
                    page = doc[0]
                    widget = next(page.widgets())
                    widget.field_value = "Later external edit"
                    widget.update()
                    doc.saveIncr()
            with patch("scripts.pdf_file_state.os.replace", side_effect=external_after_replace):
                editor.save()
            external_bytes = path.read_bytes()
            editor.set_text("Name", "Another edit")
            with self.assertRaises(FileConflict):
                editor.save()
            self.assertEqual(path.read_bytes(), external_bytes)

    def test_failure_keeps_previous_file_and_success_preserves_autosize_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sheet.pdf"
            make_pdf(path)
            editor = PdfFormEditor(path)
            self.addCleanup(editor.close)
            editor.set_text("Name", "New name")
            editor.set_checkbox("Ready", True)
            before = path.read_bytes()
            with patch("scripts.pdf_file_state.os.replace", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    editor.save()
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(editor.field_value("Name"), "New name")
            editor.save()
            first = PdfFormEditor(path)
            self.addCleanup(first.close)
            first.autosize_text_fields("all")
            first.save()
            # Repeat save is allowed from the successfully updated snapshot.
            first.save()
            saved = PdfFormEditor(path)
            self.addCleanup(saved.close)
            self.assertEqual(saved.field_value("Name"), "New name")
            self.assertTrue(saved.checkbox_checked("Ready"))
            with fitz.open(stream=before, filetype="pdf") as original:
                self.assertNotEqual(original[0].get_pixmap().samples, saved.doc[0].get_pixmap().samples)
            self.assertGreater(saved.doc[0].get_pixmap().width, 0)
            self.assertFalse(list(path.parent.glob(".tmp_edit_*")))
