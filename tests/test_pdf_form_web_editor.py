from __future__ import annotations

import http.client
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for candidate in (ROOT, SCRIPTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts.pdf_form_editor import PdfFormEditor  # noqa: E402
from scripts.pdf_form_web_editor import AppState, build_handler  # noqa: E402


class PdfFormWebEditorTests(unittest.TestCase):
    def _make_pdf(self, path: Path) -> None:
        doc = fitz.open()
        doc.new_page()
        doc.save(path)
        doc.close()

    def _start_server(self, state: AppState) -> tuple[ThreadingHTTPServer, threading.Thread]:
        server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(state))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 1)
        return server, thread

    def _request(
        self,
        server: ThreadingHTTPServer,
        method: str,
        path: str,
        body: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            payload = response.read()
            return response.status, dict(response.getheaders()), payload
        finally:
            connection.close()

    def _multipart_body(
        self,
        fields: dict[str, str],
        files: dict[str, tuple[str, bytes, str]],
    ) -> tuple[bytes, str]:
        boundary = "----CodexBoundary7MA4YWxkTrZu0gW"
        chunks: list[bytes] = []
        for name, value in fields.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                    value.encode("utf-8"),
                    b"\r\n",
                ]
            )
        for name, (filename, payload, content_type) in files.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    (
                        f'Content-Disposition: form-data; name="{name}"; '
                        f'filename="{filename}"\r\n'
                    ).encode("utf-8"),
                    f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                    payload,
                    b"\r\n",
                ]
            )
        chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
        return b"".join(chunks), f"multipart/form-data; boundary={boundary}"

    def _render_page_png(self, pdf_path: Path, page_number: int) -> bytes:
        doc = fitz.open(pdf_path)
        try:
            page = doc.load_page(page_number)
            return page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False).tobytes("png")
        finally:
            doc.close()

    def test_switch_pdf_updates_state_and_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_pdf = root / "first.pdf"
            second_pdf = root / "second.pdf"
            self._make_pdf(first_pdf)
            self._make_pdf(second_pdf)

            state = AppState(
                pdf_path=first_pdf.resolve(),
                picker_root=root.resolve(),
                autosize_mode="filled",
                scale=1.0,
            )
            server, _ = self._start_server(state)

            status, headers, _ = self._request(
                server,
                "GET",
                f"/switch-pdf?path={urllib.parse.quote(second_pdf.name)}",
            )

            self.assertEqual(status, 303)
            self.assertEqual(headers.get("Location"), "/")
            self.assertEqual(state.pdf_path, second_pdf.resolve())
            self.assertEqual(state.document_revision, 1)
            self.assertIn("Открыт PDF", state.last_message)

    def test_stale_save_request_is_rejected_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "sheet.pdf"
            self._make_pdf(pdf_path)

            state = AppState(
                pdf_path=pdf_path.resolve(),
                picker_root=root.resolve(),
                autosize_mode="filled",
                scale=1.0,
            )
            server, _ = self._start_server(state)

            body = urllib.parse.urlencode(
                {
                    "expected_pdf_path": str(pdf_path.resolve()),
                    "expected_pdf_revision": "999",
                }
            )
            status, headers, _ = self._request(
                server,
                "POST",
                "/save",
                body=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            self.assertEqual(status, 303)
            self.assertEqual(headers.get("Location"), "/")
            self.assertIn("форма устарела", state.last_message)
            self.assertEqual(state.document_revision, 0)

    def test_index_shows_image_selector_but_not_button_overlays_for_dnd_template(self) -> None:
        state = AppState(
            pdf_path=(ROOT / "templates" / "DnD_5E_CharacterSheet_Form_Fillable_ru.pdf").resolve(),
            picker_root=(ROOT / "templates").resolve(),
            autosize_mode="filled",
            scale=1.0,
        )
        server, _ = self._start_server(state)

        status, _, payload = self._request(server, "GET", "/")
        html = payload.decode("utf-8")

        self.assertEqual(status, 200)
        self.assertIn('name="image_field_name"', html)
        self.assertIn(">CHARACTER IMAGE</option>", html)
        self.assertIn(">Faction Symbol Image</option>", html)
        self.assertNotIn('name="text:CHARACTER IMAGE"', html)
        self.assertNotIn('name="text:Faction Symbol Image"', html)

    def test_multipart_save_updates_text_and_rerendered_page_for_uploaded_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "sheet.pdf"
            shutil.copy2(
                ROOT / "templates" / "DnD_5E_CharacterSheet_Form_Fillable_ru.pdf",
                pdf_path,
            )

            state = AppState(
                pdf_path=pdf_path.resolve(),
                picker_root=root.resolve(),
                autosize_mode="filled",
                scale=1.0,
            )
            server, _ = self._start_server(state)

            editor = PdfFormEditor(pdf_path)
            self.addCleanup(editor.close)
            image_page_number = editor.widgets_by_name["CHARACTER IMAGE"][0].page_number

            before_png = self._render_page_png(pdf_path, image_page_number)
            image_bytes = (ROOT / "docs" / "images" / "demo-sheet-page1.png").read_bytes()
            body, content_type = self._multipart_body(
                fields={
                    "expected_pdf_path": str(pdf_path.resolve()),
                    "expected_pdf_revision": "0",
                    "text:CharacterName": "Web Smoke",
                    "image_field_name": "CHARACTER IMAGE",
                },
                files={
                    "portrait_image": ("portrait.png", image_bytes, "image/png"),
                },
            )

            status, headers, _ = self._request(
                server,
                "POST",
                "/save",
                body=body,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(len(body)),
                },
            )

            self.assertEqual(status, 303)
            self.assertEqual(headers.get("Location"), "/")
            self.assertEqual(state.document_revision, 1)
            self.assertIn("updated successfully", state.last_message)

            saved = PdfFormEditor(pdf_path)
            self.addCleanup(saved.close)
            self.assertEqual(saved.field_value("CharacterName"), "Web Smoke")

            after_png = self._render_page_png(pdf_path, image_page_number)
            self.assertNotEqual(before_png, after_png)


if __name__ == "__main__":
    unittest.main()
