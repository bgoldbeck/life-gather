"""Bounded text and OOXML readers. No rendering, formulas or external requests."""

import csv
import posixpath
import re
from io import BytesIO, StringIO
from typing import Any, Literal
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from pydantic import BaseModel, ConfigDict, Field

MIMES = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "md": "text/markdown",
    "csv": "text/csv",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
PARSER_VERSION = "lifegather-documents/1"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


class PreviewOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    encoding: Literal["utf-8-sig", "utf-16", "cp1252"] = "utf-8-sig"
    delimiter: Literal["", ",", ";", "\t", "|"] = ""
    header: bool = True
    sheet: str = Field(default="", max_length=100)
    cell_range: str = Field(
        default="",
        max_length=25,
        pattern=r"^(?:[A-Z]{1,3}[1-9][0-9]{0,6}:[A-Z]{1,3}[1-9][0-9]{0,6})?$",
    )


class ExtractedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    pages: int = Field(default=1, ge=1, le=10)
    text: str = Field(max_length=4000)
    truncated: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


def _result(
    lines: list[str], metadata: dict[str, Any], *, truncated: bool = False
) -> ExtractedDocument:
    text = "\n".join(lines)
    return ExtractedDocument(
        text=text[:4000],
        truncated=truncated or len(text) > 4000,
        metadata={"parser_version": PARSER_VERSION, **metadata},
    )


def _xml(archive: ZipFile, name: str) -> ET.Element:
    with archive.open(name) as part:
        raw = part.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024 or re.search(
        rb"<!\s*(?:DOCTYPE|ENTITY)", raw.replace(b"\x00", b""), re.I
    ):
        raise ValueError("Unsafe or oversized XML")
    root = ET.fromstring(raw)
    if sum(1 for _ in root.iter()) > 20000:
        raise ValueError("Too many document elements")
    return root


def _office(raw: bytes) -> ZipFile:
    archive = ZipFile(BytesIO(raw))
    entries = archive.infolist()
    names = [entry.filename for entry in entries]
    if not entries or len(entries) > 500 or len(set(names)) != len(names):
        archive.close()
        raise ValueError("Unsupported archive")
    total = 0
    for entry in entries:
        total += entry.file_size
        name = entry.filename
        if (
            entry.flag_bits & 1
            or entry.compress_type not in (ZIP_STORED, ZIP_DEFLATED)
            or entry.file_size > 2 * 1024 * 1024
            or total > 16 * 1024 * 1024
            or name.startswith("/")
            or "\\" in name
            or ":" in name
            or ".." in name.split("/")
            or "vba" in name.lower()
            or "macros" in name.lower()
        ):
            archive.close()
            raise ValueError("Unsafe or oversized Office archive")
    try:
        types = _xml(archive, "[Content_Types].xml")
        if any("macroenabled" in str(node.attrib).lower() for node in types.iter()):
            raise ValueError("Macro-enabled documents are unsupported")
    except Exception:
        archive.close()
        raise
    return archive


def _word(raw: bytes) -> ExtractedDocument:
    lines: list[str] = []
    with _office(raw) as archive:
        root = _xml(archive, "word/document.xml")
        if root.tag != W + "document":
            raise ValueError("Invalid Word document")
        body = root.find(W + "body")
        if body is None:
            raise ValueError("Missing document body")
        paragraph = table = 0
        for node in body:
            if node.tag == W + "p":
                paragraph += 1
                # Only literal run text: field instructions are not executed.
                text = "".join(item.text or "" for item in node.iter(W + "t"))
                lines.append(f"[Paragraph {paragraph}] {text}")
            elif node.tag == W + "tbl":
                table += 1
                for r, row in enumerate(node.findall(W + "tr"), 1):
                    cells = [
                        "".join(t.text or "" for t in cell.iter(W + "t"))
                        for cell in row.findall(W + "tc")
                    ]
                    lines.append(f"[Table {table} row {r}] " + " | ".join(cells))
            if sum(map(len, lines)) > 4000:
                return _result(
                    lines,
                    {
                        "warnings": [
                            "Main body only; headers, footnotes, drawings "
                            "and layout may be omitted."
                        ]
                    },
                    truncated=True,
                )
    return _result(
        lines,
        {
            "warnings": [
                "Main body only; headers, footnotes, drawings "
                "and layout may be omitted."
            ]
        },
    )


def _coordinate(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", value)
    if match is None:
        raise ValueError("Invalid cell address")
    column = 0
    for character in match[1]:
        column = column * 26 + ord(character) - 64
    row = int(match[2])
    if column > 16384 or row > 1048576:
        raise ValueError("Cell address exceeds Excel bounds")
    return row, column


def _excel(raw: bytes, options: PreviewOptions) -> ExtractedDocument:
    with _office(raw) as archive:
        workbook = _xml(archive, "xl/workbook.xml")
        if workbook.tag != S + "workbook":
            raise ValueError("Invalid workbook")
        sheets = workbook.findall(S + "sheets/" + S + "sheet")
        if not 1 <= len(sheets) <= 10:
            raise ValueError("Choose a workbook with at most 10 sheets")
        names = [sheet.attrib["name"] for sheet in sheets]
        if len(set(names)) != len(names) or any(len(name) > 100 for name in names):
            raise ValueError("Invalid worksheet names")
        chosen = options.sheet or names[0]
        if chosen not in names:
            raise ValueError("Worksheet not found")
        sheet = sheets[names.index(chosen)]
        relationships = _xml(archive, "xl/_rels/workbook.xml.rels")
        targets = {node.attrib.get("Id"): node for node in relationships}
        relation = targets.get(sheet.attrib.get(REL + "id"))
        if relation is None or relation.attrib.get("TargetMode") == "External":
            raise ValueError("Invalid worksheet relationship")
        target = relation.attrib["Target"]
        path = (
            target.lstrip("/")
            if target.startswith("/")
            else posixpath.normpath("xl/" + target)
        )
        if not path.startswith("xl/worksheets/") or not path.endswith(".xml"):
            raise ValueError("Invalid worksheet path")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = _xml(archive, "xl/sharedStrings.xml")
            strings = [
                "".join(node.text or "" for node in item.iter(S + "t"))
                for item in shared.findall(S + "si")
            ]
        lower, upper = (1, 1), (200, 50)
        if options.cell_range:
            lower, upper = map(_coordinate, options.cell_range.split(":"))
            if (
                upper[0] < lower[0]
                or upper[1] < lower[1]
                or upper[0] - lower[0] >= 200
                or upper[1] - lower[1] >= 50
            ):
                raise ValueError("Select at most 200 rows and 50 columns")
        root = _xml(archive, path)
        lines = [f"[Worksheet {chosen}; range {options.cell_range or 'A1:AX200'}]"]
        omitted = False
        for cell in root.iter(S + "c"):
            address = cell.attrib.get("r", "")
            row, column = _coordinate(address)
            if not (lower[0] <= row <= upper[0] and lower[1] <= column <= upper[1]):
                omitted = True
                continue
            value = cell.findtext(S + "v", "")
            kind = cell.attrib.get("t", "n")
            if kind == "s":
                index = int(value)
                if not 0 <= index < len(strings):
                    raise ValueError("Invalid shared string")
                value = strings[index]
            elif kind == "inlineStr":
                value = "".join(node.text or "" for node in cell.iter(S + "t"))
            formula = cell.find(S + "f")
            if formula is not None:
                value = (
                    f"formula (not executed): {formula.text or '[shared formula]'}; "
                    f"cached (may be stale): {value or '[missing]'}"
                )
            lines.append(f"[{chosen}!{address}; {kind}] {value}")
            if sum(map(len, lines)) > 4000:
                omitted = True
                break
        return _result(
            lines,
            {
                "sheets": names,
                "sheet": chosen,
                "cell_range": options.cell_range,
                "warnings": [
                    "Raw stored cell values; number/date formatting is not applied. "
                    "Formulas are never recalculated; cached results may be stale. "
                    "Charts and external data are not read."
                ],
            },
            truncated=omitted,
        )


def parse_document(
    raw: bytes, extension: str, options: PreviewOptions
) -> ExtractedDocument:
    if not raw or len(raw) > 8 * 1024 * 1024:
        raise ValueError("Document size exceeded")
    if extension == "docx":
        return _word(raw)
    if extension == "xlsx":
        return _excel(raw, options)
    if extension not in ("txt", "md", "csv") or raw.startswith(
        (b"PK\x03\x04", b"%PDF-", b"\xd0\xcf\x11\xe0")
    ):
        raise ValueError("Invalid document type")
    # UTF-16 must be explicit or BOM-marked; no heuristic encoding replacement.
    encoding = (
        "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else options.encoding
    )
    text = raw.decode(encoding, errors="strict")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in text):
        raise ValueError("Binary content is not text")
    metadata: dict[str, Any] = {"encoding": encoding, "warnings": []}
    if extension != "csv":
        return _result(
            [
                f"[L{index}] {line}"
                for index, line in enumerate(text.splitlines()[:2000], 1)
            ],
            metadata,
            truncated=len(text.splitlines()) > 2000,
        )
    delimiter: str = options.delimiter
    if not delimiter:
        try:
            delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
            metadata["warnings"] = [
                "Delimiter is uncertain; confirm or choose it before review."
            ]
    metadata.update(delimiter=delimiter, header=options.header)
    lines = [
        f"[CSV delimiter {delimiter!r}; "
        f"first row {'header' if options.header else 'data'}]"
    ]
    reader = csv.reader(StringIO(text, newline=""), delimiter=delimiter, strict=True)
    for r, row in enumerate(reader, 1):
        if r > 200:
            return _result(lines, metadata, truncated=True)
        if len(row) > 50:
            raise ValueError("CSV exceeds 50 columns")
        lines.append(
            " | ".join(f"[R{r}C{c}] {value}" for c, value in enumerate(row, 1))
        )
        if sum(map(len, lines)) > 4000:
            return _result(lines, metadata, truncated=True)
    return _result(lines, metadata)
