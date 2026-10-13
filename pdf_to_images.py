from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib

import dataiku

from .config import CASE_DOCUMENT_FOLDER_ID, PDF_RENDER_DPI
from .ids import stable_id


@dataclass
class RenderedPage:
    page_id: str
    page_number: int
    image_path: str
    mime_type: str
    width: int
    height: int
    image_bytes: bytes
    image_base64: str
    image_sha256: str
    base64_character_count: int


def render_pdf_to_images(
    case_id: str,
    case_document_id: str,
    pdf_bytes: bytes,
    dpi: int = PDF_RENDER_DPI,
    store_images: bool = True,
) -> list[RenderedPage]:
    """
    Render every PDF page once as a fixed-DPI PNG and explicitly Base64-encode
    it once for the VLM helper.

    PyMuPDF is used only for rendering. No page.get_text() call is made, no
    native PDF text is sent to a model, and no native-text fallback is used.
    """
    if not pdf_bytes:
        raise ValueError("The uploaded PDF is empty.")

    try:
        import fitz
    except ImportError as error:
        raise RuntimeError(
            "Install pymupdf in the Streamlit code environment."
        ) from error

    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    folder = dataiku.Folder(CASE_DOCUMENT_FOLDER_ID) if store_images else None
    try:
        rendered_pages = [
            _render_one(document, case_id, case_document_id, index + 1, dpi, folder)
            for index in range(document.page_count)
        ]
    finally:
        document.close()

    return rendered_pages


def render_pdf_page(
    case_id: str,
    case_document_id: str,
    pdf_bytes: bytes,
    page_number: int,
    dpi: int = PDF_RENDER_DPI,
    store_image: bool = True,
) -> RenderedPage:
    """One page rendered and stored, as render_pdf_to_images does for every
    page. Opens the PDF itself, so pages can be rendered from several
    threads at once."""
    import fitz

    folder = dataiku.Folder(CASE_DOCUMENT_FOLDER_ID) if store_image else None
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        return _render_one(document, case_id, case_document_id, page_number, dpi, folder)


def _render_one(document, case_id: str, case_document_id: str, page_number: int, dpi: int, folder) -> RenderedPage:
    page = document.load_page(page_number - 1)
    pixmap = page.get_pixmap(dpi=int(dpi), alpha=False)
    png_bytes = pixmap.tobytes("png")
    if not png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError(f"Page {page_number} was not rendered as a valid PNG.")

    image_base64 = base64.b64encode(png_bytes).decode("utf-8")
    image_path = f"/cases/{case_id}/documents/{case_document_id}/pages/page_{page_number:04d}.png"
    if folder is not None:
        folder.upload_data(image_path, png_bytes)
    return RenderedPage(
        page_id=stable_id("PAGE", case_document_id, page_number),
        page_number=page_number,
        image_path=image_path,
        mime_type="image/png",
        width=pixmap.width,
        height=pixmap.height,
        image_bytes=png_bytes,
        image_base64=image_base64,
        image_sha256=hashlib.sha256(png_bytes).hexdigest(),
        base64_character_count=len(image_base64),
    )
