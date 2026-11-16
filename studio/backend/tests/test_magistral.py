"""Synthetic authoring records only: never commit uploaded academic material."""

import json
import zipfile

import pytest
from aas import free_cloud as free
from aas import magistral as mag
from aas.core import audit, revision_hash
from aas.documents import extract


@pytest.fixture(autouse=True)
def isolated_runner(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY_VISIBILITY", raising=False)


@pytest.fixture
def authored(tmp_path):
    from docx import Document

    source = tmp_path / "synthetic.docx"
    d = Document()
    d.add_heading("Unidad 7 · Reglamento ficticio", 1)
    d.add_heading("Plazo didáctico", 2)
    d.add_paragraph(
        "Reglamento ficticio para pruebas, artículo 7: el pedido requiere firma y se presenta dentro de tres días, salvo suspensión expresa. Vencido el plazo sin suspensión, se cierra este ejercicio."
    )
    d.save(source)
    corpus = tmp_path / "corpus"
    mag.intake(
        corpus,
        {
            "v4": {
                "path": str(source),
                "subject": "contratos",
                "role": "doctrinal_depth_synthetic",
            }
        },
    )
    doc = free.load(corpus, "documents/v4.json")
    r = doc["records"][2]
    claim = {
        "id": "C1",
        "essential": True,
        "source_refs": [{"source_id": "v4:" + r["id"], "quote": r["text"]}],
        "rule": "El reglamento ficticio limita el pedido firmado a tres días.",
        "conditions": ["Firma"],
        "exceptions": ["Suspensión expresa"],
        "quantities": ["Tres días"],
        "consequences": ["Cierra el ejercicio sin suspensión"],
        "relations": [],
    }
    text = "En este reglamento ficticio, el artículo 7 exige firma y concede tres días para pedir. La suspensión expresa es la excepción. Si el plazo vence sin suspensión, se cierra el ejercicio."
    turns = [
        {
            "id": "s1",
            "speaker": "profesora",
            "rate_wpm": 130,
            "statements": [
                {"type": "source_explanation", "text": text, "claim_ids": ["C1"]}
            ],
        },
        {
            "id": "s2",
            "speaker": "profesor",
            "rate_wpm": 145,
            "statements": [
                {
                    "type": "question",
                    "text": "¿La suspensión expresa cambia entonces la consecuencia del vencimiento en este ejercicio ficticio?",
                    "claim_ids": ["C1"],
                }
            ],
        },
    ]
    reviews = {
        "C1": {
            "method": "codex_source_to_script_editorial_review",
            "reviewer": "Synthetic fixture, not a real legal review",
            "facets": {
                f: {
                    "status": "reviewed",
                    "reason": "Fixture editorial: mantiene firma, tres días, suspensión expresa y cierre condicionado al vencimiento sin suspensión.",
                    "supports": [{"turn_id": "s1", "quote": text}],
                }
                for f in mag.FACETS
                if claim[f]
            },
        }
    }
    draft = {
        "title": "Synthetic dialogue",
        "scope": {"unit": 7, "institute": "Reglamento ficticio", "sample": True},
        "claims": [claim],
        "turns": turns,
        "reviews": reviews,
        "source_selection": {"v4": [r["id"]]},
        "chapters": [
            {"id": "c001", "title": "Uno", "segment_ids": ["s1"]},
            {"id": "c002", "title": "Dos", "segment_ids": ["s2"]},
        ],
        "cross_source_decisions": [],
    }
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(draft))
    root = tmp_path / "episode"
    assert mag.assemble(corpus, path, root)["audit_passed"]
    return root, corpus, path, draft


def test_original_dialogue_and_editorial_evidence_do_not_claim_semantic_certification(
    authored,
):
    root, *_ = authored
    ep = free.load(root, "review.json")
    report = audit(ep)
    assert (
        report["passed"] and report["reviewed_facets"] == report["required_facets"] == 5
    )
    assert report["semantic_certified"] is False
    assert ep["segments"][0]["text"] != ep["blocks"][0]["text"]
    assert ep["segments"][0]["rate_wpm"] == 130
    assert ep["segments"][1]["rate_wpm"] == 145


@pytest.mark.parametrize("field", ["exceptions", "quantities", "conditions"])
def test_changed_inventory_invalidates_editorial_review(authored, field):
    root, *_ = authored
    ep = free.load(root, "review.json")
    ep["claim_inventory"][0][field] = ["Otro requisito sin revisión"]
    assert "stale_editorial_review" in {f["code"] for f in audit(ep)["findings"]}


def test_deleting_exception_or_changing_number_invalidates_review(authored):
    root, *_ = authored
    ep = free.load(root, "review.json")
    old = revision_hash(ep)
    ep["segments"][0]["text"] = ep["segments"][0]["text"].replace("tres", "dos")
    ep["segments"][0]["statements"][0]["text"] = ep["segments"][0]["text"]
    assert revision_hash(ep) != old
    assert not audit(ep)["passed"]


@pytest.mark.parametrize(
    "change",
    [
        "title_only",
        "example_only",
        "unresolved",
        "chapter_tail",
        "no_source",
        "empty_inventory",
        "untraced",
        "wrong_article",
    ],
)
def test_structural_or_didactic_shortcuts_never_pass_for_substantive_review(
    authored, change
):
    root, *_ = authored
    ep = free.load(root, "review.json")
    if change in ("title_only", "example_only", "wrong_article"):
        s = ep["segments"][0]
        if change == "title_only":
            s["statements"][0]["text"] = s["text"] = "Plazo del reglamento ficticio"
        if change == "example_only":
            s["statements"][0].update(
                type="example",
                hypothetical=True,
                text="Supuesto hipotético: una persona se presenta sin firma durante este ejercicio ficticio.",
            )
            s["text"] = s["statements"][0]["text"]
        if change == "wrong_article":
            s["statements"][0]["text"] = s["text"] = s["text"].replace(
                "artículo 7", "artículo 99"
            )
        ep["editorial_reviews"]["C1"]["binding"] = mag.binding(
            ep["claim_inventory"][0], ep
        )
        for f in ep["editorial_reviews"]["C1"]["facets"].values():
            f["supports"] = [{"turn_id": "s1", "quote": s["text"]}]
    if change == "unresolved":
        ep["cross_source_decisions"] = [{"status": "unresolved"}]
    if change == "chapter_tail":
        ep["chapter_plan"][1]["segment_ids"] = []
    if change == "no_source":
        ep["claim_inventory"][0]["source_refs"] = []
    if change == "empty_inventory":
        ep["claim_inventory"] = []
    if change == "untraced":
        ep["segments"][0]["statements"][0]["claim_ids"] = []
    assert not audit(ep)["passed"]


def test_original_file_tampering_and_unreviewed_edits_block_synthesis(authored):
    root, *_ = authored
    free.approve(root, reviewed=True)
    review = free.load(root, "review.json")
    review["scope"]["sample"] = False
    free.save(root, "review.json", review)
    with pytest.raises(free.FreeCloudError, match="unapproved_edits"):
        free.render(root, "unused")
    free.save(
        root,
        "review.json",
        free.load(
            root,
            "revisions/" + free.load(root, "state.json")["prepared_revision"] + ".json",
        ),
    )
    (root / "inputs/v4.docx").write_bytes(b"changed original")
    with pytest.raises(free.FreeCloudError, match="original_dialogue_source_modified"):
        free.render(root, "unused")


def test_resume_revision_segment_rates_and_downloaded_private_matrix(
    authored, monkeypatch
):
    from aas.delivery import download_bundle
    from test_free_cloud import CIOnlySpeechEngine

    class RecordedEngine(CIOnlySpeechEngine):
        rates = []

        def synthesize(self, text, voice, wpm):
            self.rates.append(wpm)
            return super().synthesize(text, voice, wpm)

    monkeypatch.setattr(free, "OpenVoices", RecordedEngine)
    root, corpus, path, draft = authored
    free.approve(root, reviewed=True)
    assert not free.render(root, "unused", chapter_ids=["c001"])["complete"]
    assert not (root / "academic-audio.zip").exists()
    assert free.render(root, "unused", chapter_ids=["c002"])["complete"]
    assert RecordedEngine.rates == [130, 145]
    result = download_bundle(root)
    assert result["download_verified"]
    with zipfile.ZipFile(root / "downloads/academic-audio.zip") as z:
        assert {
            "claim-matrix.json",
            "claim-matrix.md",
            "source-map.json",
            "differences.json",
            "transcript.txt",
        } <= set(z.namelist())
        assert not any(
            n.endswith(".docx") or n.startswith(("inputs", "cache", "engine"))
            for n in z.namelist()
        )
    old = free.load(root, "state.json")["approved_revision"]
    draft["turns"][1]["statements"][0]["text"] = (
        "¿Qué diferencia hace que este ejercicio ficticio requiera expresamente la firma del pedido?"
    )
    path.write_text(json.dumps(draft))
    mag.revise(corpus, path, root)
    assert (root / "revisions" / f"{old}.json").exists()
    assert not (root / "academic-audio.zip").exists()
    with pytest.raises(free.FreeCloudError, match="explicit_review"):
        free.render(root, "unused")
    free.approve(root, reviewed=True)
    resumed = free.render(root, "unused")
    assert resumed["new_segments"] == 1 and resumed["reused_segments"] == 1
    selective = free.render(root, "unused", regenerate=["s2"])
    assert selective["new_segments"] == 1 and selective["reused_segments"] == 1


def test_corpus_unit_detection_preserves_tail_and_exact_duplicate_references(tmp_path):
    from docx import Document

    paths = {}
    for name in ("v4", "v5"):
        d = Document()
        d.add_paragraph("Unidad 7 · Entrada de índice, no cuerpo")
        d.add_heading("Unidad 6 · Reservada", 1)
        d.add_paragraph("No producir todavía.")
        d.add_heading("Unidad 7 · Primera", 1)
        d.add_heading("Instituto uno", 2)
        d.add_paragraph("Regla ficticia coincidente con condiciones completas.")
        d.add_heading("Unidad 8 · Segunda", 1)
        d.add_paragraph("Último párrafo que no debe perderse.")
        p = tmp_path / f"{name}.docx"
        d.save(p)
        paths[name] = {
            "path": str(p),
            "subject": "contratos",
            "role": "doctrinal_depth_synthetic"
            if name == "v4"
            else "exam_priorities_synthetic",
        }
    root = tmp_path / "private"
    result = mag.intake(root, paths)
    assert result["units"] == 2
    corpus = free.load(root, "corpus.json")
    assert "contratos-6" not in corpus["units"]
    candidates = free.load(root, "units/contratos-7/candidates.json")
    assert len(candidates) == 1 and len(candidates[0]["source_refs"]) == 2
    assert (
        "Último párrafo"
        in free.load(root, "units/contratos-8/candidates.json")[0]["verbatim"]
    )
    assert corpus["units"]["contratos-7"]["institute_blocks"]
    assert all(
        c["status"] == "unreviewed_not_a_conflict_verdict"
        for c in free.load(root, "units/contratos-7/cross-version-review.json")
    )


def test_intake_rejects_public_actions_before_reading_private_document(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY_VISIBILITY", "public")
    with pytest.raises(free.FreeCloudError, match="private_material_forbidden"):
        mag.intake(
            tmp_path / "private",
            {"x": {"path": "missing", "subject": "contratos", "role": "test"}},
        )


def test_docx_cached_page_field_and_generic_footnote_text_are_retained(tmp_path):
    from docx import Document
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part
    from docx.oxml import parse_xml

    d = Document()
    d.add_paragraph("Texto del cuerpo con nota.")
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    footer = d.sections[0].footer.paragraphs[0]
    footer._p.append(
        parse_xml(
            f'<w:fldSimple {ns} w:instr="PAGE"><w:r><w:t>1</w:t></w:r></w:fldSimple>'
        )
    )
    notes = Part(
        PackURI("/word/footnotes.xml"),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml",
        f'<w:footnotes {ns}><w:footnote w:id="1"><w:p><w:r><w:t>Condición jurídica ficticia de la nota.</w:t></w:r></w:p></w:footnote></w:footnotes>'.encode(),
        d.part.package,
    )
    d.part.relate_to(
        notes,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes",
    )
    path = tmp_path / "fields.docx"
    d.save(path)
    result = extract(path)
    assert (
        result["proof"]["passed"]
        and result["proof"]["expected_nonempty_paragraphs"] == 3
    )
    assert any(
        r["text"] == "1" and r["locator"]["context"]["region"] == "footer"
        for r in result["records"]
    )
    assert any(
        "Condición jurídica" in r["text"]
        and r["locator"]["context"]["region"] == "note"
        for r in result["records"]
    )


def test_global_progress_keeps_scoped_claims_separate_from_unit_completion(authored):
    root, corpus, *_ = authored
    result = mag.progress(corpus, [root])
    assert result["units_complete"] == 0 and result["scoped_claim_links"] == 1
    progress = free.load(corpus, "unit-coverage-map.json")
    row = progress["units"]["contratos-7"]
    assert row["status"] == "partial_scoped_work_available"
    assert row["unit_complete"] is False
    assert row["scoped_claims"][0]["whole_source_paragraph_covered"] is False
    assert progress["semantic_certified"] is False


def test_administrative_running_labels_do_not_restart_unit_and_annex_stays_separate():
    def record(sid, text, kind="paragraph", region="body"):
        return {
            "id": sid,
            "text": text,
            "kind": kind,
            "locator": {"context": {"region": region}},
        }

    doc = {
        "records": [
            record("1", "UNIDAD 6"),
            record("2", "Regla inicial"),
            record("3", "UNIDAD 6"),
            record("4", "Última condición"),
            record("5", "UNIDAD 9"),
            record("6", "Vía judicial"),
            record("7", "Anexo del ejercicio ficticio", "heading"),
            record("8", "Anexo por revisar"),
            record("9", "Nota vinculada", region="note"),
        ]
    }
    units, appendices = mag.unit_index(doc, "administrativo")
    assert units["6"] == ["1", "2", "3", "4"] and units["9"] == ["5", "6"]
    assert appendices == ["7", "8", "9"]


def test_article_suffixes_and_bounded_ranges_keep_distinct_identifiers():
    assert mag.article_keys("Artículo 1 bis y artículo 82 ter") == {"1bis", "82ter"}
    assert mag.article_keys("Artículos 1574-1580") == {
        str(n) for n in range(1574, 1581)
    }
    assert mag.article_keys("Plazo de 30 días y unidad 7") == set()
    assert "1" not in mag.article_keys("Artículo 1 bis")


@pytest.mark.parametrize(
    "a,b",
    [
        ("El fiador conserva la excusión.", "El fiador conserva la exclusión."),
        ("La división subsiste.", "La solidaridad subsiste."),
        ("Artículo 82 bis.", "Artículo 82 ter."),
        ("Derecho precario.", "Derecho regular."),
    ],
)
def test_guarantee_and_stability_distinctions_are_critical_asr_differences(a, b):
    from aas.quality import assess_transcript

    result = assess_transcript(a, b)
    assert not result["passed"] and result["substantial_difference"]
    assert not result["legal_terms_match"]


def test_secondary_review_exports_only_matching_revision_and_audio_hashes(tmp_path):
    from aas.quality import QUALITY_VERSION

    root = free.private_root(tmp_path / "private")
    report = {"revision": "r", "segments": [{"segment_id": "s1", "sha256": "h"}]}
    review = {
        "revision": "r",
        "normalizer": QUALITY_VERSION,
        "note": "Synthetic only.",
        "rows": [{"segment_id": "s1", "audio_sha256": "h", "clip": "private/path.wav"}],
    }
    free.save(root, "audio-review/review.json", review)
    assert free.export_secondary_review(root, report) == ["secondary-asr-review.json"]
    assert (
        "clip"
        not in free.load(root, "deliverables/secondary-asr-review.json")["rows"][0]
    )
    for change in ["revision", "audio", "normalizer"]:
        copy = json.loads(json.dumps(review))
        if change == "audio":
            copy["rows"][0]["audio_sha256"] = "changed"
        else:
            copy[change] = "changed"
        free.save(root, "audio-review/review.json", copy)
        assert free.export_secondary_review(root, report) == []
