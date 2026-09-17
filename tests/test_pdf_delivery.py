from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.pdf_delivery as delivery_module

from scripts.pdf_delivery import (  # noqa: E402
    DELIVERY_DPI,
    DELIVERY_SUFFIX,
    DeliveryError,
    delivery_filename,
    prepare_for_apple,
    send_saved,
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AppleDeliveryTests(unittest.TestCase):
    def test_prepare_preserves_source_and_creates_image_only_pages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Пип - лист.pdf"
            with fitz.open() as document:
                first = document.new_page(width=300, height=420)
                first.insert_text((24, 42), "Character sheet page one")
                widget = fitz.Widget()
                widget.field_name = "character_name"
                widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                widget.field_value = "Pip"
                widget.rect = fitz.Rect(24, 60, 180, 90)
                first.add_widget(widget)
                second = document.new_page(width=420, height=300)
                second.insert_text((24, 42), "Character sheet page two")
                document.save(source)

            original_hash = digest(source)
            result = prepare_for_apple(source)
            output = Path(result["output"])

            self.assertEqual(digest(source), original_hash)
            self.assertEqual(output.name, f"Пип_лист{DELIVERY_SUFFIX}.pdf")
            self.assertEqual(result["forms"], 0)
            self.assertEqual(result["fonts"], 0)
            self.assertEqual(result["dpi"], DELIVERY_DPI)
            with fitz.open(output) as delivery:
                self.assertFalse(delivery.is_form_pdf)
                self.assertEqual(delivery.page_count, 2)
                for page in delivery:
                    self.assertEqual(list(page.widgets() or ()), [])
                    self.assertEqual(list(page.annots() or ()), [])
                    self.assertEqual(page.get_fonts(full=True), [])
                    self.assertEqual(page.get_text(), "")
                    self.assertEqual(len(page.get_images(full=True)), 1)

    def test_export_reads_source_from_read_only_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "readonly"
            source_dir.mkdir()
            source = source_dir / "sheet.pdf"
            with fitz.open() as doc:
                doc.new_page(width=72, height=72)
                doc.save(source)
            source.chmod(0o444)
            source_dir.chmod(0o555)
            try:
                result = prepare_for_apple(source, root / "output")
                self.assertTrue(Path(result["output"]).is_file())
                self.assertEqual(list(source_dir.iterdir()), [source])
            finally:
                source_dir.chmod(0o755)
                source.chmod(0o644)

    def test_export_does_not_reclassify_publication_after_source_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sheet.pdf"
            with fitz.open() as doc:
                doc.new_page(width=72, height=72)
                doc.save(source)
            original_hash = digest(source)
            replace = os.replace
            def remove_after_publication(temporary, target):
                replace(temporary, target)
                source.unlink()
            with patch("scripts.pdf_file_state.os.replace", side_effect=remove_after_publication):
                result = prepare_for_apple(source)
            self.assertEqual(result["source_sha256"], original_hash)
            self.assertEqual(result["output_sha256"], digest(Path(result["output"])))

    def test_failed_preparation_keeps_existing_output_and_source(self) -> None:
        for failure in ("source_changed", "source_removed", "output_changed", "write", "cancel"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "sheet.pdf"
                with fitz.open() as doc:
                    doc.new_page(width=72, height=72).insert_text((5, 20), "First")
                    doc.save(source)
                target = Path(prepare_for_apple(source)["output"])
                old_output, old_source = target.read_bytes(), source.read_bytes()
                validate = delivery_module._validate_image_only_pdf
                def interrupt(path, dimensions, images):
                    validate(path, dimensions, images)
                    if failure == "source_changed":
                        with fitz.open(source) as doc:
                            doc[0].insert_text((5, 40), "External")
                            doc.saveIncr()
                    elif failure == "source_removed":
                        source.unlink()
                    elif failure == "output_changed":
                        target.write_bytes(old_output + b"\n% externally replaced copy")
                    elif failure == "cancel":
                        raise KeyboardInterrupt()
                with patch.object(delivery_module, "_validate_image_only_pdf", side_effect=interrupt):
                    if failure == "write":
                        with patch("scripts.pdf_file_state.os.replace", side_effect=OSError("full disk")):
                            with self.assertRaises(OSError):
                                prepare_for_apple(source)
                    else:
                        with self.assertRaises(KeyboardInterrupt if failure == "cancel" else DeliveryError):
                            prepare_for_apple(source)
                self.assertEqual(target.read_bytes(), old_output + (b"\n% externally replaced copy" if failure == "output_changed" else b""))
                if failure not in ("source_changed", "source_removed"):
                    self.assertEqual(source.read_bytes(), old_source)
                self.assertFalse(list(target.parent.glob("*.tmp.pdf")))

    def test_delivery_filename_is_telegram_safe_and_stable(self) -> None:
        self.assertEqual(
            delivery_filename(Path("Тилли Кнопка - лист персонажа.pdf")),
            "Тилли_Кнопка_лист_персонажа_iPhone_iPad.pdf",
        )


class TelegramDeliveryTests(unittest.TestCase):
    def test_send_saved_uses_main_self_helper_and_verifies_readback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = root / "telegram-harvest"
            helper.touch()
            pdf = root / "Пип_iPhone_iPad.pdf"
            pdf.write_bytes(b"%PDF-test")
            response = {
                "destination": "saved_messages",
                "profile": {"username": "Pheik13"},
                "message": {
                    "message_id": 42,
                    "attachments": [
                        {
                            "file_name": pdf.name,
                            "mime_type": "application/pdf",
                            "size": pdf.stat().st_size,
                        }
                    ],
                },
                "verified": True,
            }
            completed = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(response), stderr=""
            )
            with patch("scripts.pdf_delivery.subprocess.run", return_value=completed) as run:
                payload = send_saved(pdf, "caption", helper)

            self.assertTrue(payload["verified"])
            run.assert_called_once_with(
                [
                    str(helper.resolve()),
                    "--profile",
                    "main",
                    "send-saved",
                    "--file",
                    str(pdf.resolve()),
                    "--caption",
                    "caption",
                    "--json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

    def test_send_saved_rejects_wrong_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = root / "telegram-harvest"
            helper.touch()
            pdf = root / "Тилли_iPhone_iPad.pdf"
            pdf.write_bytes(b"%PDF-test")
            response = {
                "destination": "saved_messages",
                "profile": {"username": "Pheik13"},
                "message": {
                    "attachments": [
                        {
                            "file_name": "wrong.pdf",
                            "mime_type": "application/pdf",
                            "size": pdf.stat().st_size,
                        }
                    ]
                },
                "verified": True,
            }
            completed = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(response), stderr=""
            )
            with patch("scripts.pdf_delivery.subprocess.run", return_value=completed):
                with self.assertRaises(DeliveryError):
                    send_saved(pdf, "caption", helper)


if __name__ == "__main__":
    unittest.main()
