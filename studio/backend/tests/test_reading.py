import pytest
from aas.free_cloud import prepare, approve, load, render, FreeCloudError
from aas.core import audit
from aas.quality import assess_transcript
from aas.documents import extract, DocumentError, ScannedPDFError


@pytest.fixture(autouse=True)
def isolated_actions_context(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY_VISIBILITY", raising=False)


@pytest.mark.parametrize(
    "a,b",
    [
        ("Art. 259", "Artículo doscientos cincuenta y nueve"),
        ("Arts. 1061-1068", "Artículos mil sesenta y uno a mil sesenta y ocho"),
        ("El plazo es de 3 años", "El plazo es de tres años"),
        ("$ 1.500,25", "mil quinientos coma veinticinco pesos"),
        ("35%", "treinta y cinco por ciento"),
        ("2,05", "dos coma cero cinco"),
        ("1.000.000", "un millón"),
        ("Pregunta de examen oral", "Pregunta de examenoral"),
    ],
)
def test_representation_equivalence_is_explicit(a, b):
    result = assess_transcript(a, b)
    assert result["passed"], result
    assert result["normalization"]["expected"] or result["normalization"]["recognized"]


@pytest.mark.parametrize(
    "a,b",
    [
        ("Artículo 259", "Artículo 299"),
        ("Artículos 1061-1068", "Artículos 1061.168"),
        ("Tres años", "Tres días"),
        ("No se permite, salvo excepción", "Se permite, salvo excepción"),
        ("La intención", "La intensión"),
        ("Vicio de dolo", "Vicio de dolor"),
        ("Son actos lícitos", "Son actos ilícitos"),
        ("La prescripción", "La caducidad"),
        ("No se puede vender. Se puede donar.", "Se puede vender. No se puede donar."),
        ("Dos coma cero cinco pesos", "Dos coma cinco pesos"),
        ("5 dólares", "Cinco pesos"),
        ("En el año 2025", "En el ano 2025"),
        ("1067", "mil seiscientos sesenta y siete"),
    ],
)
def test_substantive_changes_never_hidden(a, b):
    assert not assess_transcript(a, b)["passed"]


def test_reading_retains_headings_and_every_block_once(tmp_path):
    s = tmp_path / "unit.md"
    s.write_text(
        "# Unidad\n## Concepto\nEl acto es voluntario.\n## Efectos\nEl efecto se conserva.\n"
    )
    p = tmp_path / "program.md"
    p.write_text("- Concepto\n- Efectos")
    root = tmp_path / "reading"
    prepare(s, p, root, mode="reading", voice_count=1)
    ep = load(root, "review.json")
    assert ep["blocks"][0]["text"] == "Unidad"
    assert all(
        x["kind"] == "source" and x["speaker"] == "profesora" for x in ep["segments"]
    )
    assert [b for x in ep["segments"] for b in x["source_ids"]] == [
        b["id"] for b in ep["blocks"]
    ]
    assert audit(ep)["passed"]
    ep["segments"] = ep["segments"][::-1]
    assert not audit(ep)["passed"]


def test_reading_two_voices_change_only_at_chapter_boundaries(tmp_path):
    s = tmp_path / "unit.md"
    s.write_text("## A\n" + ("Concepto de A. " * 100) + "\n## B\nConcepto de B.")
    p = tmp_path / "p.md"
    p.write_text("- A\n- B")
    root = tmp_path / "private"
    prepare(s, p, root, mode="reading", voice_count=2)
    ep = load(root, "review.json")
    speakers = [x["speaker"] for x in ep["segments"]]
    assert speakers.count("profesora") >= 2
    assert speakers[-1] == "profesor"
    assert all(x["kind"] == "source" for x in ep["segments"])


def test_docx_paragraphs_lists_tables_headers_and_notes_kept_in_order(tmp_path):
    from docx import Document

    d = Document()
    d.add_heading("Unidad", 0)
    d.add_heading("Acto jurídico", 1)
    d.add_paragraph("Antes de la tabla.")
    d.add_paragraph("Artículo 259.", style="List Number")
    t = d.add_table(rows=2, cols=2)
    for cell, text in zip(
        [c for row in t.rows for c in row.cells],
        ["Regla", "Excepción", "Texto A", "Texto B"],
    ):
        cell.text = text
    d.add_paragraph("Después de la tabla.")
    d.sections[0].header.paragraphs[0].text = "Encabezado original"
    path = tmp_path / "real.docx"
    d.save(path)
    result = extract(path)
    texts = [r["text"] for r in result["records"]]
    assert (
        result["proof"]["expected_nonempty_paragraphs"]
        == result["proof"]["extracted_nonempty_paragraphs"]
    )
    assert (
        texts.index("Antes de la tabla.")
        < texts.index("Regla")
        < texts.index("Después de la tabla.")
    )
    assert any(
        "1." in r["number_label"] for r in result["records"] if "number_label" in r
    )
    assert "Encabezado original" in texts
    assert all(
        result["source"][b["start"] : b["end"]] == b["text"] for b in result["blocks"]
    )


def test_docx_unsupported_textbox_blocks_instead_of_losing_text(tmp_path):
    from docx import Document
    from docx.oxml import parse_xml

    d = Document()
    d.add_paragraph("Visible")
    d.element.body.append(
        parse_xml(
            '<w:sdt xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:sdtContent><w:p><w:r><w:t>No puede desaparecer</w:t></w:r></w:p></w:sdtContent></w:sdt>'
        )
    )
    p = tmp_path / "unsupported.docx"
    d.save(p)
    with pytest.raises(DocumentError, match="unaccounted_docx"):
        extract(p)


def test_textual_pdf_table_and_order_and_scan_detection(tmp_path):
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from PIL import Image

    path = tmp_path / "text.pdf"
    c = canvas.Canvas(str(path))
    c.drawString(60, 780, "Antes de la tabla")
    for y in [730, 700, 670]:
        c.line(60, y, 400, y)
    for x in [60, 200, 400]:
        c.line(x, 670, x, 730)
    c.drawString(70, 710, "Regla")
    c.drawString(210, 710, "Excepcion")
    c.drawString(70, 680, "Texto A")
    c.drawString(210, 680, "Texto B")
    c.drawString(60, 640, "Despues de la tabla")
    c.save()
    result = extract(path)
    text = result["source"]
    assert (
        text.index("Antes")
        < text.index("Regla")
        < text.index("Excepcion")
        < text.index("Texto A")
        < text.index("Despues")
    )
    assert any(r["kind"] == "table_cell" for r in result["records"])
    assert (
        result["proof"]["pages"][0]["nonspace_characters"]
        == result["proof"]["pages"][0]["accounted_characters"]
    )
    scan = tmp_path / "scan.pdf"
    c = canvas.Canvas(str(scan))
    c.drawImage(
        ImageReader(Image.new("RGB", (600, 800), "white")), 0, 0, width=595, height=800
    )
    c.save()
    with pytest.raises(ScannedPDFError):
        extract(scan)


@pytest.mark.parametrize(
    "a,b",
    [
        ("$2,05", "dos pesos con cinco centavos"),
        ("USD 2,50", "dos dólares con cincuenta centavos"),
        ("0,005", "cero coma cero cero cinco"),
    ],
)
def test_fractional_amounts(a, b):
    assert assess_transcript(a, b)["passed"]


def test_money_and_exceptions_not_fuzzily_merged():
    assert not assess_transcript("$2,05", "dos pesos con cincuenta centavos")["passed"]
    assert not assess_transcript(
        "Procede a menos que se oponga", "Procede aunque se oponga"
    )["passed"]
    assert not assess_transcript(
        "Procede siempre que se oponga", "Procede si no se oponga"
    )["passed"]


@pytest.mark.parametrize(
    "a,b",
    [
        ("Artículo primero", "Artículo 1"),
        ("Título IV", "Título cuatro"),
        ("Capítulo IX", "Capítulo nueve"),
    ],
)
def test_reference_ordinal_and_roman(a, b):
    assert assess_transcript(a, b)["passed"]


def test_plain_clause_letter_is_not_a_roman_hundred():
    assert not assess_transcript("Inciso c", "Inciso 100")["passed"]
    assert not assess_transcript("Artículo III", "Artículo 4")["passed"]


def test_changed_original_doc_or_mode_cannot_keep_approval(tmp_path):
    s = tmp_path / "s.md"
    s.write_text("## Concepto\nTexto original del concepto.")
    p = tmp_path / "p.md"
    p.write_text("- Concepto")
    root = tmp_path / "private"
    prepare(s, p, root, mode="reading")
    approve(root, reviewed=True)
    (root / "inputs/source.md").write_text("Fuente alterada")
    with pytest.raises(FreeCloudError, match="original_input_file_modified"):
        render(root, "unused")


def test_contiguous_speech_windows_lose_no_audio_samples():
    import numpy as np
    from aas.open_models import speech_windows

    samples = np.ones(16000 * 67, dtype="float32") * 0.05
    samples[16000 * 24 : 16000 * 25] = 0
    windows = speech_windows(samples, 16000)
    assert windows[0][0] == 0 and windows[-1][1] == len(samples)
    assert all(a[1] == b[0] for a, b in zip(windows, windows[1:]))
    assert all(b - a <= 29 * 16000 for a, b in windows)


def test_spoken_policy_fixes_money_and_article_degrees_without_rewriting_source():
    from aas.speech import compile_speech

    source = (
        "ARTÍCULO 4°: PESOS DOSCIENTOS CINCUENTA MIL ($250.000). Artículos 1061-1068."
    )
    result = compile_speech(source, {"__policy__": "es-ar-reading-v1"})
    assert result["original_text"] == source
    assert "grados" not in result["spoken_text"] and "$" not in result["spoken_text"]
    assert "doscientos cincuenta mil pesos" in result["spoken_text"]
    assert "mil sesenta y uno a mil sesenta y ocho" in result["spoken_text"]
    assert result["transformations"]
    with pytest.raises(ValueError, match="ambiguous_currency"):
        compile_speech("Capital $500", {"__policy__": "es-ar-reading-v1"})


def test_raw_asr_cache_survives_rechecking_without_resynthesis(tmp_path, monkeypatch):
    from aas import free_cloud as free
    from test_free_cloud import CIOnlySpeechEngine

    calls = []

    class ASR:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, path):
            calls.append(str(path))
            return "Texto distinto para probar discrepancias."

    monkeypatch.setattr(free, "OpenVoices", CIOnlySpeechEngine)
    monkeypatch.setattr(free, "OpenASR", ASR)
    source = tmp_path / "s.md"
    source.write_text("## Concepto\nEl contenido original se conserva.")
    program = tmp_path / "p.md"
    program.write_text("- Concepto")
    root = tmp_path / "private"
    free.prepare(source, program, root, mode="reading")
    free.approve(root, reviewed=True)
    first = free.render(root, "unused", asr=True)
    assert first["new_segments"] > 0
    count = len(calls)
    second = free.render(root, "unused", asr=True)
    assert count > 0 and len(calls) == count and second["new_segments"] == 0
    recheck = free.recheck(root)
    assert (
        recheck["new_audio_segments"] == 0 and recheck["audio_status"] == "unverified"
    )
    assert (root / "deliverables/differences.json").is_file()
    assert load(root, "deliverables/coverage-audio.json")["document_import"]["source"][
        "proof"
    ]["passed"]


def test_nested_word_numbering_keeps_parent_and_child_formats(tmp_path):
    from docx import Document
    from docx.oxml import parse_xml

    d = Document()
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    d.part.numbering_part.element.append(
        parse_xml(
            f'<w:abstractNum {ns} w:abstractNumId="99"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl><w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%1.%2)"/></w:lvl></w:abstractNum>'
        )
    )
    d.part.numbering_part.element.append(
        parse_xml(f'<w:num {ns} w:numId="99"><w:abstractNumId w:val="99"/></w:num>')
    )
    for level, text in [
        (0, "Regla principal"),
        (1, "Primer inciso"),
        (1, "Segundo inciso"),
    ]:
        p = d.add_paragraph(text)
        p._p.get_or_add_pPr().append(
            parse_xml(
                f'<w:numPr {ns}><w:ilvl w:val="{level}"/><w:numId w:val="99"/></w:numPr>'
            )
        )
    path = tmp_path / "numbering.docx"
    d.save(path)
    assert [r["text"] for r in extract(path)["records"]] == [
        "1. Regla principal",
        "1.a) Primer inciso",
        "1.b) Segundo inciso",
    ]


def test_word_title_and_heading_and_tracked_changes(tmp_path):
    from docx import Document
    from docx.oxml import parse_xml

    d = Document()
    d.add_heading("Título de unidad", 0)
    d.add_heading("Concepto", 1)
    d.add_paragraph("Cuerpo íntegro.")
    path = tmp_path / "title.docx"
    d.save(path)
    r = extract(path)
    assert [(x["text"], x["level"]) for x in r["records"][:2]] == [
        ("Título de unidad", 1),
        ("Concepto", 2),
    ]
    d.element.body.append(
        parse_xml(
            '<w:ins xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Cambio no resuelto</w:t></w:r></w:p></w:ins>'
        )
    )
    d.save(path)
    with pytest.raises(DocumentError, match="tracked_changes"):
        extract(path)
