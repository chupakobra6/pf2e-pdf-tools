#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import subprocess
import time
import traceback
import urllib.parse
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default as email_policy_default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import fitz

from pdf_form_editor import FieldInfo, PdfFormEditor


DEFAULT_SCALE = 1.35


@dataclass
class PageSpec:
    page_number: int
    width: float
    height: float


@dataclass
class AppState:
    pdf_path: Path
    autosize_mode: str
    scale: float
    last_message: str = ""


@dataclass
class ParsedForm:
    values: dict[str, list[str]]
    files: dict[str, bytes]

    def getfirst(self, key: str, default: str = "") -> str:
        return self.values.get(key, [default])[0]

    def has(self, key: str) -> bool:
        return key in self.values or key in self.files


def parse_form_data(handler: BaseHTTPRequestHandler) -> ParsedForm:
    content_type = handler.headers.get("Content-Type", "")
    content_length = int(handler.headers.get("Content-Length", "0"))
    payload = handler.rfile.read(content_length)

    if "multipart/form-data" not in content_type:
        parsed = urllib.parse.parse_qs(payload.decode("utf-8"), keep_blank_values=True)
        return ParsedForm(values=parsed, files={})

    message = BytesParser(policy=email_policy_default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + payload
    )
    values: dict[str, list[str]] = {}
    files: dict[str, bytes] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        body = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename:
            files[name] = body
            continue
        charset = part.get_content_charset() or "utf-8"
        values.setdefault(name, []).append(body.decode(charset, errors="replace"))
    return ParsedForm(values=values, files=files)


def html_page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #efe7db;
      --panel: #fffaf2;
      --ink: #21160f;
      --muted: #6c5b4d;
      --line: #d7c5af;
      --accent: #7f3119;
      --accent-2: #564235;
      --field: rgba(255,255,255,0.82);
      --field-border: rgba(120, 80, 50, 0.28);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top right, #eadbc7 0, transparent 28rem),
        linear-gradient(180deg, #f8f3eb 0%, var(--bg) 100%);
      font: 14px/1.4 Georgia, "Times New Roman", serif;
    }}
    .wrap {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 20px;
    }}
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 30;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 16px;
      padding: 14px 18px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255, 250, 242, 0.94);
      backdrop-filter: blur(8px);
    }}
    .title {{
      font-size: 18px;
      font-weight: 700;
    }}
    .meta {{
      color: var(--muted);
      font-size: 12px;
      word-break: break-all;
    }}
    .actions {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .btn, button {{
      border: 0;
      border-radius: 10px;
      padding: 10px 14px;
      color: white;
      background: var(--accent);
      cursor: pointer;
      text-decoration: none;
      font: inherit;
    }}
    .btn.secondary {{
      background: var(--accent-2);
    }}
    .file-input {{
      color: var(--muted);
      font-size: 12px;
      max-width: 220px;
    }}
    .status {{
      margin-bottom: 14px;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fff;
    }}
    .hintbar {{
      margin-bottom: 16px;
      color: var(--muted);
      font-size: 13px;
    }}
    .pages {{
      display: grid;
      gap: 20px;
      justify-content: center;
    }}
    .page-card {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 18px;
      padding: 14px;
      box-shadow: 0 8px 30px rgba(70, 48, 29, 0.08);
    }}
    .page-title {{
      margin: 0 0 10px;
      font-size: 15px;
    }}
    .page-canvas {{
      position: relative;
      overflow: hidden;
      border-radius: 10px;
      background: white;
      box-shadow: 0 4px 18px rgba(80, 60, 40, 0.1);
    }}
    .page-image {{
      display: block;
      width: 100%;
      height: auto;
      user-select: none;
      pointer-events: none;
    }}
    .field {{
      position: absolute;
      margin: 0;
      padding: 0;
      border: 1px solid var(--field-border);
      background: rgba(255,255,255,0.58);
      color: #17120d;
      border-radius: 4px;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.32);
      font-family: Menlo, Monaco, monospace;
      line-height: 1.0;
    }}
    .field:focus {{
      outline: 2px solid rgba(127, 49, 25, 0.45);
      background: rgba(255,255,255,0.95);
      z-index: 5;
    }}
    .field.text {{
      padding: 0 2px;
      line-height: 1.08;
    }}
    .field.multiline {{
      padding: 1px 2px;
      resize: none;
      line-height: 1.14;
    }}
    .field.checkbox {{
      appearance: none;
      background: rgba(255,255,255,0.7);
    }}
    .field.checkbox::after {{
      content: "";
      display: block;
      width: 100%;
      height: 100%;
    }}
    .field.checkbox:checked {{
      background:
        linear-gradient(135deg, transparent 40%, #1b1712 40%, #1b1712 53%, transparent 53%),
        linear-gradient(45deg, transparent 58%, #1b1712 58%, #1b1712 71%, transparent 71%),
        rgba(255,255,255,0.92);
    }}
    .legend {{
      position: fixed;
      right: 16px;
      bottom: 16px;
      max-width: 320px;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(255, 250, 242, 0.95);
      color: var(--muted);
      font-size: 12px;
      backdrop-filter: blur(8px);
    }}
    .fields-hidden .field {{
      opacity: 0;
      pointer-events: none;
    }}
    .saving-overlay {{
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      background: rgba(25, 18, 14, 0.42);
      z-index: 60;
      padding: 20px;
    }}
    .saving-overlay.visible {{
      display: flex;
    }}
    .saving-card {{
      width: min(420px, 100%);
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255, 250, 242, 0.98);
      padding: 18px;
      box-shadow: 0 16px 50px rgba(30, 21, 14, 0.25);
    }}
    .saving-title {{
      margin: 0 0 8px;
      font-size: 16px;
      font-weight: 700;
    }}
    .saving-text {{
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 13px;
    }}
    .progress {{
      position: relative;
      overflow: hidden;
      height: 10px;
      border-radius: 999px;
      background: #eadcc9;
    }}
    .progress::before {{
      content: "";
      position: absolute;
      inset: 0;
      width: 42%;
      border-radius: 999px;
      background: linear-gradient(90deg, #7f3119, #c06422);
      animation: progress-slide 1.2s linear infinite;
    }}
    @keyframes progress-slide {{
      0% {{ transform: translateX(-110%); }}
      100% {{ transform: translateX(260%); }}
    }}
    @media (max-width: 900px) {{
      .wrap {{ padding: 12px; }}
      .topbar {{ position: static; }}
      .legend {{ position: static; margin-top: 16px; }}
    }}
  </style>
</head>
<body>
{body}
<script>
  const formEl = document.getElementById('editor-form');
  const savingOverlay = document.getElementById('saving-overlay');
  const toggleFieldsBtn = document.getElementById('toggle-fields');

  function syncPeersByName(syncName, value, checked, source) {{
    const peers = document.querySelectorAll(`[data-sync-name="${{CSS.escape(syncName)}}"]`);
    for (const peer of peers) {{
      if (peer === source) continue;
      if (peer.type === 'checkbox') {{
        peer.checked = checked;
      }} else {{
        peer.value = value;
      }}
    }}
  }}

  for (const el of document.querySelectorAll('[data-sync-name]')) {{
    const eventName = el.type === 'checkbox' ? 'change' : 'input';
    el.addEventListener(eventName, () => {{
      const name = el.dataset.syncName;
      syncPeersByName(name, el.value, el.checked, el);
    }});
  }}

  if (formEl && savingOverlay) {{
    formEl.addEventListener('submit', () => {{
      savingOverlay.classList.add('visible');
    }});
  }}

  if (toggleFieldsBtn) {{
    const applyState = () => {{
      const hidden = document.body.classList.toggle('fields-hidden');
      toggleFieldsBtn.textContent = hidden ? 'Показать поля' : 'Скрыть поля';
    }};
    toggleFieldsBtn.addEventListener('click', applyState);
  }}
</script>
</body>
</html>""".encode("utf-8")


def get_page_specs(pdf_path: Path) -> list[PageSpec]:
    doc = fitz.open(pdf_path)
    try:
        return [
            PageSpec(page_number=page.number, width=page.rect.width, height=page.rect.height)
            for page in doc
        ]
    finally:
        doc.close()


def overlay_font_size(field: FieldInfo, scale: float, height: float, multiline: bool) -> float:
    pdf_size = max(4.0, field.font_size)
    scaled_pdf_size = pdf_size * scale
    if multiline:
        line_count = max(1, field.value.count("\n") + 1 if field.value.strip() else 1)
        height_budget = height * 0.72 / max(1.0, line_count)
        return max(10.5, min(16.0, max(scaled_pdf_size, height_budget)))
    height_budget = height * 0.74
    return max(11.5, min(18.0, max(scaled_pdf_size, height_budget)))


def control_html(field: FieldInfo, scale: float) -> str:
    if field.field_type == "Button":
        return ""

    left = field.x0 * scale
    top = field.y0 * scale
    width = max(8.0, (field.x1 - field.x0) * scale)
    height = max(8.0, (field.y1 - field.y0) * scale)
    title = html.escape(field.name)
    multiline = "\n" in field.value or height > 24
    font_size = overlay_font_size(field, scale, height, multiline)
    style = (
        f"left:{left:.1f}px;top:{top:.1f}px;width:{width:.1f}px;height:{height:.1f}px;"
        f"font-size:{font_size:.1f}px;"
    )
    if field.field_type == "CheckBox":
        checked = " checked" if field.checked else ""
        return (
            f'<input class="field checkbox" type="checkbox" '
            f'name="check:{title}" data-sync-name="check:{title}" title="{title}" '
            f'style="{style}" value="on"{checked}>'
        )

    value = html.escape(field.value)
    if multiline:
        return (
            f'<textarea class="field text multiline" '
            f'name="text:{title}" data-sync-name="text:{title}" title="{title}" '
            f'style="{style}">{value}</textarea>'
        )
    return (
        f'<input class="field text" type="text" '
        f'name="text:{title}" data-sync-name="text:{title}" title="{title}" '
        f'style="{style}" value="{value}">'
    )


def render_index(
    pdf_path: Path,
    pages: list[PageSpec],
    fields: list[FieldInfo],
    image_field_names: list[str],
    default_image_field_name: str | None,
    message: str,
    scale: float,
) -> bytes:
    fields_by_page: dict[int, list[FieldInfo]] = {}
    for field in fields:
        fields_by_page.setdefault(field.page_number, []).append(field)

    page_blocks: list[str] = []
    for page in pages:
        page_width = page.width * scale
        page_height = page.height * scale
        controls = "".join(control_html(field, scale) for field in fields_by_page.get(page.page_number, []))
        page_blocks.append(
            f"""
            <section class="page-card">
              <h2 class="page-title">Страница {page.page_number + 1}</h2>
              <div class="page-canvas" style="width:{page_width:.1f}px;height:{page_height:.1f}px;">
                <img class="page-image" src="/page/{page.page_number}.png" alt="PDF page {page.page_number + 1}" width="{page_width:.0f}" height="{page_height:.0f}">
                {controls}
              </div>
            </section>
            """
        )

    status_html = f'<div class="status">{html.escape(message)}</div>' if message else ""
    image_controls = ""
    if image_field_names:
        options = "".join(
            (
                f'<option value="{html.escape(name)}"'
                f'{" selected" if name == default_image_field_name else ""}>'
                f"{html.escape(name)}</option>"
            )
            for name in image_field_names
        )
        image_controls = f"""
            <select name="image_field_name" title="Поле изображения">
              {options}
            </select>
            <input class="file-input" type="file" name="portrait_image" accept="image/*" title="Загрузить изображение">
        """

    body = f"""
    <div class="wrap">
      <form id="editor-form" method="post" action="/save" enctype="multipart/form-data">
        <div class="topbar">
          <div>
            <div class="title">PDF Visual Editor</div>
            <div class="meta">{html.escape(str(pdf_path))}</div>
          </div>
          <div class="actions">
            {image_controls}
            <button type="button" class="btn secondary" id="toggle-fields">Скрыть поля</button>
            <a class="btn secondary" href="/open-pdf">Open PDF</a>
            <button type="submit">Save To PDF</button>
          </div>
        </div>
        {status_html}
        <div class="hintbar">
          Редактируй поля прямо поверх страницы. PDF в браузере больше не сохраняй вручную: только эта кнопка пишет значения в файл. Портрет можно загрузить через выбор файла сверху.
        </div>
        <div class="pages">
          {''.join(page_blocks)}
        </div>
      </form>
      <div class="legend">Если одно и то же поле встречается в нескольких местах, ввод в одном месте синхронизируется с его копиями на странице.</div>
    </div>
    <div id="saving-overlay" class="saving-overlay" aria-hidden="true">
      <div class="saving-card">
        <div class="saving-title">Сохранение PDF</div>
        <div class="saving-text">Подождите. Значения полей сейчас пишутся в PDF.</div>
        <div class="progress"></div>
      </div>
    </div>
    """
    return html_page(f"PDF Visual Editor - {pdf_path.name}", body)


def render_page_png(pdf_path: Path, page_number: int, scale: float) -> bytes:
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_number]
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def build_handler(state: AppState):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            print(f"[pdf-web] GET {parsed.path}")
            if parsed.path == "/":
                self._send_index()
                return
            if parsed.path == "/open-pdf":
                subprocess.Popen(["open", str(state.pdf_path)])
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/")
                self.end_headers()
                return
            if parsed.path.startswith("/page/") and parsed.path.endswith(".png"):
                self._send_page_png(parsed.path)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            print(f"[pdf-web] POST {parsed.path}")
            if parsed.path != "/save":
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            form = parse_form_data(self)
            editor = PdfFormEditor(state.pdf_path)
            try:
                started = time.time()
                fields = editor.list_fields()
                text_names = sorted({field.name for field in fields if field.field_type == "Text"})
                checkbox_names = sorted({field.name for field in fields if field.field_type == "CheckBox"})
                image_field_name = form.getfirst("image_field_name") or None
                portrait_bytes = form.files.get("portrait_image", b"")
                print(
                    f"[pdf-web] save start file={state.pdf_path} "
                    f"text_fields={len(text_names)} checkbox_fields={len(checkbox_names)} "
                    f"portrait={'yes' if portrait_bytes else 'no'} "
                    f"image_field={image_field_name or '<auto>'}"
                )
                for name in text_names:
                    editor.set_text(name, form.getfirst(f"text:{name}", ""))
                for name in checkbox_names:
                    editor.set_checkbox(name, form.has(f"check:{name}"))
                if portrait_bytes:
                    editor.set_portrait_image(portrait_bytes, field_name=image_field_name)
                editor.autosize_text_fields(state.autosize_mode)
                editor.save()
                duration = time.time() - started
                print(f"[pdf-web] save ok duration={duration:.2f}s")
                state.last_message = f"PDF updated successfully in {duration:.2f}s."
            except Exception as exc:
                print(f"[pdf-web] save failed: {exc}")
                traceback.print_exc()
                state.last_message = f"Save failed: {exc}"
            finally:
                editor.close()

            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()

        def log_message(self, format: str, *args) -> None:
            return

        def _send_index(self) -> None:
            editor = PdfFormEditor(state.pdf_path)
            try:
                fields = editor.list_fields()
                image_field_names = editor.button_field_names()
                default_image_field_name = editor.default_image_field_name()
            finally:
                editor.close()
            print(f"[pdf-web] render index fields={len(fields)}")
            pages = get_page_specs(state.pdf_path)
            content = render_index(
                state.pdf_path,
                pages,
                fields,
                image_field_names,
                default_image_field_name,
                state.last_message,
                state.scale,
            )
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _send_page_png(self, path: str) -> None:
            try:
                page_number = int(path.removeprefix("/page/").removesuffix(".png"))
            except ValueError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            pages = get_page_specs(state.pdf_path)
            if page_number < 0 or page_number >= len(pages):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            print(f"[pdf-web] render page png page={page_number}")
            content = render_page_png(state.pdf_path, page_number, state.scale)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve a local visual editor for a fillable PDF.")
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument(
        "--autosize",
        choices=("none", "filled", "all"),
        default="none",
        help="Autosize mode applied after each save.",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=DEFAULT_SCALE,
        help="Rendered page scale for the editor UI.",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the local editor in the default browser after startup.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    pdf_path = args.input_pdf
    if not pdf_path.exists():
        parser.error(f"PDF does not exist: {pdf_path}")

    state = AppState(pdf_path=pdf_path, autosize_mode=args.autosize, scale=args.scale)
    server = ThreadingHTTPServer((args.host, args.port), build_handler(state))
    url = f"http://{args.host}:{args.port}/"
    print(f"Serving PDF visual editor for {pdf_path}")
    print(f"Open: {url}")
    if args.open_browser:
        subprocess.Popen(["open", url])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
