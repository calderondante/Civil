"""Private, loss-accounted DOCX and textual PDF extraction. No OCR or network.

DOCX uses XML paragraph inventory, including tables/notes, not just doc.paragraphs.
PDF has no native paragraph tree: preserve positioned glyphs and table cell order,
report ambiguity, and never claim semantic paragraph recovery from glyph counts.
"""

import re
from collections import Counter
from pathlib import Path
from .open_models import file_hash


class DocumentError(ValueError):
    pass


class ScannedPDFError(DocumentError):
    pass


def compact(text):
    return "".join(text.split())


def extract(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        records, proof = read_docx(path)
    elif suffix == ".pdf":
        records, proof = read_pdf(path)
    elif suffix in (".md", ".markdown", ".txt"):
        text = path.read_text(encoding="utf-8")
        return {
            "format": suffix.lstrip("."),
            "source": text,
            "records": None,
            "proof": {
                "passed": bool(text.strip()),
                "method": "original UTF-8 text retained",
            },
            "sha256": file_hash(path),
            "review_required": False,
        }
    else:
        raise DocumentError("unsupported_document_format")
    if not records:
        raise DocumentError("empty_document")
    source = ""
    hierarchy = {}
    blocks = []
    for index, record in enumerate(records):
        text = record["text"]
        level = record.get("level") if record["kind"] == "heading" else None
        if level:
            hierarchy = {k: v for k, v in hierarchy.items() if k < level}
            hierarchy[level] = text
        prefix = ("#" * level + " ") if level else ""
        start = len(source) + len(prefix)
        source += prefix + text + "\n\n"
        record.update({"id": f"d{index + 1}", "start": start, "end": start + len(text)})
        a = start
        end = record["end"]
        while a < end:
            stop = min(a + 850, end)
            if stop < end:
                boundary = source.rfind(" ", a + 400, stop)
                if boundary > a:
                    stop = boundary
            blocks.append(
                {
                    "id": f"b{len(blocks) + 1}",
                    "text": source[a:stop],
                    "start": a,
                    "end": stop,
                    "line": source.count("\n", 0, a) + 1,
                    "path": list(hierarchy.values()),
                    "heading": list(hierarchy.values())[-1]
                    if hierarchy
                    else "Documento",
                    "kind": record["kind"],
                    "record_id": record["id"],
                    "locator": record["locator"],
                }
            )
            a = stop
    return {
        "format": suffix.lstrip("."),
        "source": source,
        "records": records,
        "blocks": blocks,
        "proof": proof,
        "sha256": file_hash(path),
        "review_required": bool(proof.get("warnings")),
    }


def read_docx(path):
    import zipfile
    from docx import Document
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph

    with zipfile.ZipFile(path) as z:
        if (
            sum(x.file_size for x in z.infolist()) > 60_000_000
            or len(z.infolist()) > 20000
        ):
            raise DocumentError("docx_size_limit")
    doc = Document(path)
    if (
        next(doc.element.body.iter(qn("w:ins")), None) is not None
        or next(doc.element.body.iter(qn("w:del")), None) is not None
    ):
        raise DocumentError("tracked_changes_require_explicit_revision_selection")
    has_title = any(
        p.style is not None and p.style.style_id in ("Title", "Titulo", "Ttulo")
        for p in doc.paragraphs
    )
    records = []
    seen = set()
    expected = set()
    empty = 0
    numbering = doc.part.numbering_part.element
    counts = {}

    def key(p, part):
        return part + ":" + p.getroottree().getpath(p)

    def number(p):
        pr = p._p.pPr
        np = pr.numPr if pr is not None else None
        style = p.style
        while np is None and style is not None:
            sp = style.element.pPr
            np = sp.numPr if sp is not None else None
            style = style.base_style
        if np is None or np.numId is None or np.numId.val == 0:
            return ""
        num_id = str(np.numId.val)
        level = int(np.ilvl.val) if np.ilvl is not None else 0
        num = next(
            (
                n
                for n in numbering.findall(qn("w:num"))
                if n.get(qn("w:numId")) == num_id
            ),
            None,
        )
        if num is None:
            raise DocumentError("unresolved_word_numbering")
        aid = num.find(qn("w:abstractNumId")).get(qn("w:val"))
        abstract = next(
            a
            for a in numbering.findall(qn("w:abstractNum"))
            if a.get(qn("w:abstractNumId")) == aid
        )
        lvl = next(
            (
                l
                for l in abstract.findall(qn("w:lvl"))
                if l.get(qn("w:ilvl")) == str(level)
            ),
            None,
        )
        if lvl is None:
            raise DocumentError("unresolved_word_list_level")
        fmt = lvl.find(qn("w:numFmt")).get(qn("w:val"))
        template = lvl.find(qn("w:lvlText")).get(qn("w:val"))
        start = lvl.find(qn("w:start"))
        initial = int(start.get(qn("w:val"))) if start is not None else 1
        for override in num.findall(qn("w:lvlOverride")):
            if override.get(qn("w:ilvl")) == str(level):
                if override.find(qn("w:lvl")) is not None:
                    raise DocumentError(
                        "unsupported_word_level_override_requires_review"
                    )
                item = override.find(qn("w:startOverride"))
                if item is not None:
                    initial = int(item.get(qn("w:val")))
        for k in list(counts):
            if k[0] == num_id and k[1] > level:
                del counts[k]
        counts[num_id, level] = counts.get((num_id, level), initial - 1) + 1
        if fmt == "bullet":
            return "• "
        if fmt not in (
            "decimal",
            "lowerLetter",
            "upperLetter",
            "lowerRoman",
            "upperRoman",
        ):
            raise DocumentError("unsupported_word_number_format")

        def display(value, actual_format):
            if actual_format.endswith("Letter"):
                result = ""
                v = value
                while v:
                    v, r = divmod(v - 1, 26)
                    result = chr(97 + r) + result
                return result.upper() if actual_format == "upperLetter" else result
            if actual_format.endswith("Roman"):
                result = ""
                v = value
                for n, r in [
                    (1000, "M"),
                    (900, "CM"),
                    (500, "D"),
                    (400, "CD"),
                    (100, "C"),
                    (90, "XC"),
                    (50, "L"),
                    (40, "XL"),
                    (10, "X"),
                    (9, "IX"),
                    (5, "V"),
                    (4, "IV"),
                    (1, "I"),
                ]:
                    while v >= n:
                        result += r
                        v -= n
                return result.lower() if actual_format == "lowerRoman" else result
            return str(value)

        def placeholder(match):
            index = int(match[1]) - 1
            definition = next(
                (
                    l
                    for l in abstract.findall(qn("w:lvl"))
                    if l.get(qn("w:ilvl")) == str(index)
                ),
                None,
            )
            if definition is None:
                raise DocumentError("unresolved_word_list_placeholder")
            numfmt = definition.find(qn("w:numFmt")).get(qn("w:val"))
            start = definition.find(qn("w:start"))
            initial = int(start.get(qn("w:val"))) if start is not None else 1
            return display(counts.get((num_id, index), initial), numfmt)

        return re.sub(r"%(\d+)", placeholder, template) + " "

    def walk(element, part, context):
        for child in element:
            if child.tag == qn("w:p"):
                ident = key(child, part)
                if ident in seen:
                    continue
                seen.add(ident)
                p = Paragraph(child, doc)
                raw = "".join(t.text or "" for t in child.iter(qn("w:t")))
                if compact(raw) != compact(p.text):
                    raise DocumentError("unsupported_word_text_container")
                if not p.text.strip():
                    continue
                name = p.style.style_id if p.style is not None else ""
                heading = re.search(r"(?:Heading|Titulo|Ttulo)([1-6])", name, re.I)
                level = (
                    min(6, int(heading[1]) + int(has_title))
                    if heading
                    else 1
                    if name in ("Title", "Titulo", "Ttulo")
                    else None
                )
                if level is None:
                    pr = child.find(qn("w:pPr"))
                    outline = pr.find(qn("w:outlineLvl")) if pr is not None else None
                    if outline is not None and int(outline.get(qn("w:val"))) < 6:
                        level = int(outline.get(qn("w:val"))) + 1
                prefix = number(p)
                kind = "heading" if level else "list_item" if prefix else "paragraph"
                records.append(
                    {
                        "text": prefix + p.text,
                        "kind": kind,
                        "level": level,
                        "locator": {
                            "part": part,
                            "xml_path": ident,
                            "context": context,
                            "note_refs": [
                                n.get(qn("w:id"))
                                for tag in ("footnoteReference", "endnoteReference")
                                for n in child.iter(qn("w:" + tag))
                            ],
                        },
                        "original_text": p.text,
                        "number_label": prefix,
                    }
                )
            elif child.tag == qn("w:tbl"):
                for ri, row in enumerate(child.findall(qn("w:tr"))):
                    for ci, cell in enumerate(row.findall(qn("w:tc"))):
                        walk(
                            cell,
                            part,
                            {**context, "table_row": ri + 1, "table_cell": ci + 1},
                        )
            # Unsupported nested content is caught by the independent XML inventory below.

    parts = [
        p
        for p in doc.part.package.parts
        if str(p.partname).startswith("/word/") and hasattr(p, "element")
    ]
    headers = [p for p in parts if "header" in str(p.partname)]
    footers = [p for p in parts if "footer" in str(p.partname)]
    for p in headers:
        walk(p.element, str(p.partname), {"region": "header"})
    walk(doc.element.body, "/word/document.xml", {"region": "body"})
    for p in footers:
        walk(p.element, str(p.partname), {"region": "footer"})
    # Notes may be generic OPC parts rather than parsed python-docx story parts.
    from lxml import etree

    roots = [("/word/document.xml", doc.element.body)] + [
        (str(p.partname), p.element) for p in headers + footers
    ]
    for part in doc.part.package.parts:
        if str(part.partname) in ("/word/footnotes.xml", "/word/endnotes.xml"):
            root = etree.fromstring(
                part.blob,
                parser=etree.XMLParser(resolve_entities=False, no_network=True),
            )
            for note in root:
                if int(note.get(qn("w:id"), "0")) < 0:
                    continue
                walk(
                    note,
                    str(part.partname),
                    {"region": "note", "note_id": note.get(qn("w:id"))},
                )
            roots.append((str(part.partname), root))
    for part, root in roots:
        for p in root.iter(qn("w:p")):
            raw = "".join(t.text or "" for t in p.iter(qn("w:t")))
            if raw.strip():
                expected.add(key(p, part))
            else:
                empty += 1
    missed = expected - seen
    if missed:
        raise DocumentError("unaccounted_docx_paragraphs")
    extracted = {r["locator"]["xml_path"] for r in records}
    if extracted != expected:
        raise DocumentError("docx_inventory_mismatch")
    warnings = []
    if list(doc.element.body.iter(qn("w:drawing"))) or list(
        doc.element.body.iter(qn("w:pict"))
    ):
        warnings.append({"code": "embedded_images_not_transcribed"})
    return records, {
        "passed": True,
        "method": "independent XML nonempty-paragraph inventory and exact visible-text comparison",
        "expected_nonempty_paragraphs": len(expected),
        "extracted_nonempty_paragraphs": len(extracted),
        "empty_paragraphs": empty,
        "warnings": warnings,
        "notes": "Tables kept in body order; cells row-major. Header/footer parts retained once; their repeated page layout is not inferred.",
    }


def _lines(chars):
    lines = []
    for char in sorted(chars, key=lambda c: (round(c["top"] / 3) * 3, c["x0"])):
        if not lines or abs(lines[-1][0]["top"] - char["top"]) > 3:
            lines.append([char])
        else:
            lines[-1].append(char)
    result = []
    for line in lines:
        line.sort(key=lambda c: c["x0"])
        text = ""
        previous = None
        for char in line:
            if (
                previous
                and char["x0"] - previous["x1"]
                > max(1, float(char.get("size", 10)) * 0.22)
                and not text.endswith(" ")
            ):
                text += " "
            text += char["text"]
            previous = char
        if text.strip():
            result.append((text, line))
    return result


def read_pdf(path):
    import pdfplumber
    import statistics

    records = []
    pages = []
    warnings = []
    with pdfplumber.open(path) as pdf:
        for page_index, page in enumerate(pdf.pages, 1):
            chars = [{**c, "_idx": i} for i, c in enumerate(page.chars)]
            count = sum(not ch.isspace() for c in chars for ch in c["text"])
            image_area = sum(
                max(0, i["x1"] - i["x0"]) * max(0, i["bottom"] - i["top"])
                for i in page.images
            )
            if page.images and (
                count == 0
                or count < 200
                and image_area > page.width * page.height * 0.35
            ):
                raise ScannedPDFError(
                    "scanned_or_image_dominated_pdf_page_" + str(page_index)
                )
            if "(cid:" in "".join(c["text"] for c in chars) or any(
                "\ufffd" in c["text"] for c in chars
            ):
                raise DocumentError("unreadable_pdf_glyph_encoding")
            if image_area > page.width * page.height * 0.05:
                warnings.append(
                    {"page": page_index, "code": "embedded_images_not_transcribed"}
                )
            used = set()
            items = []
            sizes = [c["size"] for c in chars if c["text"].strip()]
            body_size = statistics.median(sizes) if sizes else 10
            for table_index, table in enumerate(page.find_tables(), 1):
                cells = []
                for row_index, row in enumerate(table.rows, 1):
                    for cell_index, box in enumerate(row.cells, 1):
                        if box is None:
                            continue
                        x0, top, x1, bottom = box
                        selected = [
                            c
                            for c in chars
                            if c["_idx"] not in used
                            and x0 <= (c["x0"] + c["x1"]) / 2 <= x1
                            and top <= (c["top"] + c["bottom"]) / 2 <= bottom
                        ]
                        used.update(c["_idx"] for c in selected)
                        text = "\n".join(s for s, line in _lines(selected))
                        if text.strip():
                            cells.append(
                                {
                                    "text": text,
                                    "kind": "table_cell",
                                    "locator": {
                                        "page": page_index,
                                        "table": table_index,
                                        "row": row_index,
                                        "cell": cell_index,
                                        "bbox": list(box),
                                    },
                                }
                            )
                if cells:
                    items.append((table.bbox[1], table.bbox[0], cells))
            for text, line in _lines([c for c in chars if c["_idx"] not in used]):
                used.update(c["_idx"] for c in line)
                large = statistics.median(c["size"] for c in line) > body_size * 1.15
                level = (
                    1
                    if re.match(r"^(?:unidad|capitulo|capítulo)\b", text, re.I)
                    else 2
                    if large
                    else None
                )
                rec = {
                    "text": text,
                    "kind": "heading" if level else "paragraph",
                    "level": level,
                    "locator": {
                        "page": page_index,
                        "bbox": [
                            min(c["x0"] for c in line),
                            min(c["top"] for c in line),
                            max(c["x1"] for c in line),
                            max(c["bottom"] for c in line),
                        ],
                    },
                }
                items.append(
                    (min(c["top"] for c in line), min(c["x0"] for c in line), [rec])
                )
                gaps = [line[i + 1]["x0"] - line[i]["x1"] for i in range(len(line) - 1)]
                if gaps and max(gaps) > page.width * 0.18:
                    warnings.append(
                        {
                            "page": page_index,
                            "code": "possible_columns_review_reading_order",
                        }
                    )
            local = [
                r for _, _, rs in sorted(items, key=lambda x: (x[0], x[1])) for r in rs
            ]
            actual = Counter(compact("".join(r["text"] for r in local)))
            if actual != Counter(compact("".join(c["text"] for c in chars))):
                raise DocumentError("unaccounted_pdf_glyphs")
            records.extend(local)
            pages.append(
                {
                    "page": page_index,
                    "nonspace_characters": count,
                    "accounted_characters": sum(actual.values()),
                    "records": len(local),
                }
            )
    return records, {
        "passed": True,
        "method": "every decoded non-whitespace glyph accounted exactly once; geometric text/table order",
        "pages": pages,
        "warnings": warnings,
        "notes": "PDF has no native paragraph semantics. Glyph accounting does not prove intended multi-column order or recover text embedded in images. Scanned/image-only pages are blocked, not invented.",
    }
