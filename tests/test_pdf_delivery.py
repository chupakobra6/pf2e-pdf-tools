from __future__ import annotations

import hashlib
import json
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
