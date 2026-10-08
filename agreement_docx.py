"""
The reviewed contract as a Word file: the agreement's extracted text with
every proposed wording change as a Word tracked change (the lawyer accepts
or rejects each one) and its reason as a comment. Written with the
standard library only (a .docx is a zip of XML files).
Location: lib/python/legal_platform/agreement_docx.py

contract_docx(contract, title, language) -> bytes, where `contract` is
agreement_markup.contract_document(...).
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape

AUTHOR = "BSF contract review (AI)"
_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
RED, GREEN, GREY = "C00000", "00804A", "6B6B6B"

TEXT = {
    "ar": {"note": "التعديلات المقترحة ظاهرة كتعديلات متعقّبة: راجع كل تعديل واختر قبول أو رفض. سبب كل تعديل في التعليق المرفق به.",
           "other": "تعديلات مقترحة أخرى", "other_note": "لم يُعثر على هذه العبارات حرفياً في النص المستخرج، لذا لم تُوضع في موضعها.",
           "advice": "توصيات المراجعة (ليست صياغة للعقد)",
           "clause": "البند", "delete": "حذف", "add": "إضافة", "title": "مراجعة العقد"},
    "en": {"note": "Proposed changes are shown as tracked changes: review each one and choose Accept or Reject. "
                   "The reason for each change is in its comment.",
           "other": "Other proposed changes", "other_note": "These words were not found exactly in the extracted text, "
                                                            "so they are not placed in it.",
           "advice": "Advice from the review (not contract wording)",
           "clause": "Clause", "delete": "delete", "add": "add", "title": "Contract review"},
}


def _clean(text) -> str:
    return _INVALID_XML.sub("", str(text or "").replace("\r", "").replace("\n", " "))


def _is_arabic(text: str) -> bool:
    letters = re.findall(r"[^\W\d_]", text or "")
    return bool(letters) and sum(1 for ch in letters if _ARABIC.match(ch)) * 2 >= len(letters)


class _Writer:
    def __init__(self, contract: dict, language: str):
        self.contract = contract
        self.edits = contract.get("edits") or {}
        self.words = TEXT["ar" if language == "ar" else "en"]
        self.language = language
        self.date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.revision = 0
        self.comments = []

    # -- runs -------------------------------------------------------------
    def _rpr(self, text: str, extra: str = "") -> str:
        rtl = "<w:rtl/>" if _ARABIC.search(text) else ""
        return f"<w:rPr>{extra}{rtl}</w:rPr>" if (extra or rtl) else ""

    def run(self, text: str, extra: str = "") -> str:
        text = _clean(text)
        if not text:
            return ""
        return f'<w:r>{self._rpr(text, extra)}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'

    def deleted(self, text: str, extra: str = "") -> str:
        text = _clean(text)
        if not text:
            return ""
        self.revision += 1
        return (f'<w:del w:id="{self.revision}" w:author="{AUTHOR}" w:date="{self.date}"><w:r>{self._rpr(text, extra)}'
                f'<w:delText xml:space="preserve">{escape(text)}</w:delText></w:r></w:del>')

    def inserted(self, text: str, extra: str = "") -> str:
        text = _clean(text)
        if not text:
            return ""
        self.revision += 1
        return (f'<w:ins w:id="{self.revision}" w:author="{AUTHOR}" w:date="{self.date}"><w:r>{self._rpr(text, extra)}'
                f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:ins>')

    def reason(self, edit: dict) -> str:
        first, second = ("reason_ar", "reason_en") if self.language == "ar" else ("reason_en", "reason_ar")
        return str(edit.get(first) or edit.get(second) or "").strip()

    def commented(self, inner: str, edit: dict) -> str:
        text = self.reason(edit)
        if not text:
            return inner
        number = len(self.comments)
        self.comments.append(text)
        return (f'<w:commentRangeStart w:id="{number}"/>{inner}<w:commentRangeEnd w:id="{number}"/>'
                f'<w:r><w:commentReference w:id="{number}"/></w:r>')

    def runs(self, runs: list, extra: str = "") -> str:
        out = []
        for item in runs or []:
            edit = self.edits.get(item.get("edit_id") or "") or {}
            if item.get("kind") == "mark":
                piece = self.deleted(item.get("text", ""), extra)
                if item.get("last"):
                    new = edit.get("replacement") if edit.get("type") != "delete" else ""
                    piece += self.inserted(" " + new if new else "", extra)
                    piece = self.commented(piece, edit)
                out.append(piece)
            elif item.get("kind") == "insert":
                out.append(self.commented(self.inserted(" " + str(edit.get("replacement") or ""), extra), edit))
            else:
                out.append(self.run(item.get("text", ""), extra))
        return "".join(out)

    # -- blocks -----------------------------------------------------------
    def paragraph(self, inner: str, plain: str, style: str = "", extra_ppr: str = "") -> str:
        ppr = (f'<w:pStyle w:val="{style}"/>' if style else "") + ("<w:bidi/>" if _is_arabic(plain) else "") + extra_ppr
        return f"<w:p>{f'<w:pPr>{ppr}</w:pPr>' if ppr else ''}{inner}</w:p>"

    def block(self, block: dict) -> str:
        kind = block.get("type")
        plain = "".join(r.get("text", "") for r in block.get("runs") or [])
        if kind == "document":
            return self.paragraph(self.run(block.get("text", "")), block.get("text", ""), "Heading1")
        if kind == "page":
            return ""
        if kind == "heading":
            style = {1: "Heading1", 2: "Heading2"}.get(int(block.get("level") or 2), "Heading3")
            return self.paragraph(self.runs(block["runs"]), plain, style)
        if kind == "item":
            return self.paragraph(self.run("• ") + self.runs(block["runs"]), plain)
        if kind == "table":
            return self.table(block)
        return self.paragraph(self.runs(block.get("runs")), plain)

    def table(self, block: dict) -> str:
        rows = block.get("rows") or []
        width = max((len(r.get("cells") or []) for r in rows), default=0)
        if not width:
            return ""
        texts = "".join("".join(x.get("text", "") for x in cell) for r in rows for cell in r.get("cells") or [])
        bidi = "<w:bidiVisual/>" if _is_arabic(texts) else ""
        grid = "".join('<w:gridCol w:w="{}"/>'.format(9000 // width) for _ in range(width))
        out = [f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>{bidi}<w:tblW w:w="{9000 // width * width}" w:type="dxa"/></w:tblPr>'
               f"<w:tblGrid>{grid}</w:tblGrid>"]
        for row in rows:
            header = '<w:trPr><w:tblHeader/></w:trPr>' if row.get("header") else ""
            cells = []
            for cell in (row.get("cells") or []) + [[]] * (width - len(row.get("cells") or [])):
                plain = "".join(x.get("text", "") for x in cell)
                inner = self.runs(cell, "<w:b/>" if row.get("header") else "")
                shade = '<w:shd w:val="clear" w:color="auto" w:fill="EDEFF2"/>' if row.get("header") else ""
                cells.append(f'<w:tc><w:tcPr><w:tcW w:w="{9000 // width}" w:type="dxa"/>{shade}</w:tcPr>'
                             f"{self.paragraph(inner, plain)}</w:tc>")
            out.append(f"<w:tr>{header}{''.join(cells)}</w:tr>")
        out.append("</w:tbl>")
        return "".join(out) + "<w:p/>"

    def other_changes(self) -> str:
        listed = [self.edits[e] for e in self.contract.get("unplaced") or [] if e in self.edits]
        unplaced = [e for e in listed if e.get("type") != "advice"]
        advice = [e for e in listed if e.get("type") == "advice"]
        words = self.words
        out = []
        if unplaced:
            out += [self.paragraph(self.run(words["other"]), words["other"], "Heading1"),
                    self.paragraph(self.run(words["other_note"], f'<w:i/><w:color w:val="{GREY}"/>'), words["other_note"])]
        for edit in unplaced:
            label = "{} {}: ".format(words["clause"], edit.get("clause_number") or edit.get("clause_id") or "").strip()
            old = edit.get("original") or ""
            new = edit.get("replacement") or ""
            parts = [self.run(label + " ", "<w:b/>")]
            if edit.get("type") != "add" and old:
                parts.append(self.run(old, f'<w:strike/><w:color w:val="{RED}"/>'))
                parts.append(self.run(" ← " if _is_arabic(old) else " → ", f'<w:color w:val="{RED}"/>'))
            if edit.get("type") == "delete":
                parts.append(self.run(words["delete"], f'<w:i/><w:color w:val="{RED}"/>'))
            else:
                parts.append(self.run(new, f'<w:b/><w:color w:val="{GREEN}"/>'))
            out.append(self.paragraph("".join(parts), label + old + new))
            reason = self.reason(edit)
            if reason:
                out.append(self.paragraph(self.run(reason, f'<w:i/><w:color w:val="{GREY}"/>'), reason))
        if advice:
            out.append(self.paragraph(self.run(words["advice"]), words["advice"], "Heading1"))
        for edit in advice:
            label = "{} {}: ".format(words["clause"], edit.get("clause_number") or edit.get("clause_id") or "").strip()
            text = str(edit.get("replacement") or "")
            out.append(self.paragraph(self.run(label + " ", "<w:b/>") + self.run(text, "<w:i/>"), label + text))
        return "".join(out)

    def document(self, title: str) -> str:
        words = self.words
        body = [self.paragraph(self.run(title or words["title"]), title or words["title"], "Title"),
                self.paragraph(self.run(words["note"], f'<w:i/><w:color w:val="{GREY}"/>'), words["note"])]
        body += [self.block(b) for b in self.contract.get("blocks") or []]
        body.append(self.other_changes())
        bidi = "<w:bidi/>" if self.language == "ar" else ""
        section = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                   '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="567" '
                   f'w:footer="567" w:gutter="0"/>{bidi}</w:sectPr>')
        return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>'
                f'{"".join(body)}{section}</w:body></w:document>')

    def comments_xml(self) -> str:
        items = "".join(
            f'<w:comment w:id="{n}" w:author="{AUTHOR}" w:date="{self.date}" w:initials="AI">'
            f'{self.paragraph(self.run(text), text)}</w:comment>'
            for n, text in enumerate(self.comments))
        return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:comments {W}>{items}</w:comments>'


STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {W}>
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="Arial" w:cs="Arial"/>
<w:sz w:val="22"/><w:szCs w:val="24"/><w:lang w:val="en-US" w:bidi="ar-SA"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:spacing w:after="200"/></w:pPr><w:rPr><w:b/><w:bCs/><w:color w:val="0B4F4A"/><w:sz w:val="40"/><w:szCs w:val="40"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="360" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr>
<w:rPr><w:b/><w:bCs/><w:color w:val="0B4F4A"/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="1"/></w:pPr>
<w:rPr><w:b/><w:bCs/><w:color w:val="0B4F4A"/><w:sz w:val="26"/><w:szCs w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="200" w:after="60"/><w:outlineLvl w:val="2"/></w:pPr>
<w:rPr><w:b/><w:bCs/><w:sz w:val="24"/><w:szCs w:val="26"/></w:rPr></w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders>
<w:top w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/><w:left w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/>
<w:bottom w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/><w:right w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/>
<w:insideH w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/>
</w:tblBorders><w:tblCellMar><w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>
</w:styles>"""

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>
</Relationships>"""

SETTINGS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings {W}><w:defaultTabStop w:val="720"/><w:characterSpacingControl w:val="doNotCompress"/></w:settings>"""


def _core(title: str, date: str) -> str:
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{escape(_clean(title))}</dc:title><dc:creator>{AUTHOR}</dc:creator>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{date}</dcterms:created></cp:coreProperties>')


def contract_docx(contract: dict, title: str = "", language: str = "ar") -> bytes:
    """The Word file of the reviewed contract (see the module note)."""
    writer = _Writer(contract or {}, "ar" if str(language).lower().startswith("ar") else "en")
    document = writer.document(title)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", CONTENT_TYPES)
        package.writestr("_rels/.rels", ROOT_RELS)
        package.writestr("docProps/core.xml", _core(title or writer.words["title"], writer.date))
        package.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)
        package.writestr("word/document.xml", document)
        package.writestr("word/styles.xml", STYLES)
        package.writestr("word/settings.xml", SETTINGS)
        package.writestr("word/comments.xml", writer.comments_xml())
    return buffer.getvalue()
