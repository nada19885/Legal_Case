from datetime import datetime, timezone
import mimetypes
from pathlib import Path

import dataiku

from .ids import random_id
from .storage import append_rows
from .audit import audit
from .config import (
    CASE_DOCUMENT_FOLDER_ID,
    CASE_DOCUMENTS_DATASET,
)


def _safe_name(
    filename: str,
) -> str:
    name = Path(filename).name

    return "".join(
        character
        if (
            character.isalnum()
            or character in "._-"
        )
        else "_"
        for character in name
    )


def save_upload(
    case_id,
    uploaded_file,
    uploaded_by="",
    document_type="evidence",
):
    document_id = random_id(
        "CDOC"
    )

    safe_name = _safe_name(
        uploaded_file.name
    )

    folder_path = (
        "/cases/{}/{}_{}"
    ).format(
        case_id,
        document_id,
        safe_name,
    )

    payload = uploaded_file.getvalue()

    folder = dataiku.Folder(
        CASE_DOCUMENT_FOLDER_ID
    )

    folder.upload_data(
        folder_path,
        payload,
    )

    row = {
        "case_document_id": document_id,
        "case_id": case_id,
        "folder_path": folder_path,
        "original_filename": (
            uploaded_file.name
        ),
        "mime_type": (
            uploaded_file.type
            or mimetypes.guess_type(
                uploaded_file.name
            )[0]
            or ""
        ),
        "file_size_bytes": len(
            payload
        ),
        "document_type": document_type,
        "document_date": "",
        "document_language": "",
        "extraction_status": "uploaded",
        "page_count": "",
        "uploaded_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "uploaded_by": uploaded_by,
    }

    append_rows(
        CASE_DOCUMENTS_DATASET,
        [row],
    )

    audit(
        case_id,
        "document",
        document_id,
        "uploaded",
        uploaded_by,
        new_value=row,
    )

    return row, payload
