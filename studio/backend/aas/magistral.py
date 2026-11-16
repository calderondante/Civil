"""Codex-authored dialogue with explicit, non-oracular editorial evidence.

No language-model API. This module prepares private source queues and validates
manual/Codex authoring records. It never equates links or hashes with entailment.
"""

import argparse
import copy
import json
import re
from pathlib import Path

from .core import digest, revision_hash
from .documents import extract
from .free_cloud import (
    FreeCloudError,
    actions_privacy_guard,
    load,
    private_path,
    private_root,
    save,
    write_bytes,
)
from .normalization import canonicalize
from .open_models import file_hash

FACETS = ("rule", "conditions", "exceptions", "quantities", "consequences", "relations")


def article_keys(text):
    """Keep bis/ter distinct; only bounded explicit article ranges expand."""
    tokens = canonicalize(text)["tokens"]
    keys = set()
    for i, token in enumerate(tokens):
        if token not in ("articulo", "articulos"):
            continue
        j = i + 1
        if j < len(tokens) and tokens[j] == "numero":
            j += 1
        previous = None
        connector = None
        while j < len(tokens) and re.fullmatch(r"\d+", tokens[j]):
            number = tokens[j]
            j += 1
            suffix = ""
            if j < len(tokens) and tokens[j] in (
                "bis",
                "ter",
                "quater",
                "quinquies",
                "sexies",
            ):
                suffix = tokens[j]
                j += 1
            key = number + suffix
            keys.add(key)
            if (
                previous is not None
                and connector in ("a", "hasta")
                and not suffix
                and 0 < int(number) - previous <= 100
            ):
                keys.update(str(n) for n in range(previous, int(number) + 1))
            previous = int(number) if not suffix else None
            if (
                j + 1 < len(tokens)
                and tokens[j] in ("a", "hasta", "y")
                and re.fullmatch(r"\d+", tokens[j + 1])
            ):
                connector = tokens[j]
                j += 1
            else:
                break
    return keys


def unit_index(document, subject):
    records = document["records"]
    units = {}
    current = None
    appendix = False
    out = []
    for record in records:
        text = record["text"].strip()
        match = re.match(r"^unidad\s+(\d+)\b", text, re.I)
        # TOC entries are not unit boundaries. Administrative running unit labels
        # are body paragraphs; repeated labels continue rather than restart a unit.
        eligible = bool(match) and (
            record["kind"] == "heading"
            if subject == "contratos"
            else text.upper() == text and int(match[1]) in (6, 7, 8, 9)
        )
        if eligible:
            current = int(match[1])
            units.setdefault(str(current), [])
            appendix = False
        if (
            subject == "administrativo"
            and current == 9
            and record["kind"] == "heading"
            and re.match(
                r"^(?:anexo\b|apéndice\b|plazos administrativos\b)", text, re.IGNORECASE
            )
        ):
            appendix = True
        if (
            subject == "contratos"
            and record["locator"]["context"].get("region") != "body"
        ):
            out.append(record["id"])
            continue
        if (
            current is None
            or appendix
            or record["locator"]["context"].get("region") != "body"
        ):
            out.append(record["id"])
            continue
        units[str(current)].append(record["id"])
    return units, out


def intake(root, documents):
    actions_privacy_guard()
    root = private_root(root)
    meta = {}
    all_units = {}
    for name, info in documents.items():
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", name):
            raise FreeCloudError("invalid_document_key")
        src = Path(info["path"])
        target = write_bytes(root, "originals/" + name + ".docx", src.read_bytes())
        doc = extract(target)
        units, appendix = unit_index(doc, info["subject"])
        save(root, "documents/" + name + ".json", doc)
        meta[name] = {
            "subject": info["subject"],
            "role": info["role"],
            "filename": src.name,
            "sha256": file_hash(target),
            "path": "originals/" + name + ".docx",
            "units": units,
            "appendix_or_frontmatter_ids": appendix,
            "proof": doc["proof"],
        }
        for unit, ids in units.items():
            allowed = (
                info["subject"] == "administrativo"
                and int(unit) in range(6, 10)
                or info["subject"] == "contratos"
                and int(unit) in range(7, 15)
            )
            if not allowed:
                continue
            key = info["subject"] + "-" + unit
            bucket = all_units.setdefault(
                key,
                {
                    "subject": info["subject"],
                    "unit": int(unit),
                    "sources": {},
                    "status": "awaiting_substantive_inventory",
                    "chapters": [],
                },
            )
            bucket["sources"][name] = ids
    # Link appendices, notes and case cards for later explicit selection, never
    # silently attach every appendix to the last unit or invent omitted fichas.
    plan = {
        "units": all_units,
        "reserved_contract_units": [1, 2, 3, 4, 5, 6],
        "documents": meta,
        "external_verification": False,
        "note": "Unit/source discovery only. Candidate inventory is not semantic coverage.",
    }
    save(root, "corpus.json", plan)
    for key, unit in all_units.items():
        candidates = []
        exact = {}
        institutes = []
        for name, ids in unit["sources"].items():
            doc = load(root, "documents/" + name + ".json")
            current = None
            for record in doc["records"]:
                if record["id"] not in ids:
                    continue
                if current is None or record["kind"] == "heading":
                    current = {
                        "document": name,
                        "title": record["text"]
                        if record["kind"] == "heading"
                        else "Inicio de unidad",
                        "heading_id": record["id"]
                        if record["kind"] == "heading"
                        else None,
                        "record_ids": [],
                        "status": "awaiting_claim_inventory_and_source_to_script_review",
                    }
                    institutes.append(current)
                current["record_ids"].append(record["id"])
            for record in doc["records"]:
                if record["id"] not in ids or record["kind"] == "heading":
                    continue
                if re.match(r"^unidad\s+\d+", record["text"], re.I):
                    continue
                fingerprint = digest(" ".join(record["text"].casefold().split()))
                ref = {
                    "document": name,
                    "record_id": record["id"],
                    "locator": record["locator"],
                }
                if fingerprint in exact:
                    exact[fingerprint]["source_refs"].append(ref)
                    continue
                item = {
                    "id": f"{key}-candidate-{len(candidates) + 1:04}",
                    "verbatim": record["text"],
                    "source_refs": [ref],
                    "status": "candidate_only_not_editorially_reviewed",
                    "flags": {
                        "remission_only": bool(
                            re.search(
                                r"consultar ficha|ficha independiente",
                                record["text"],
                                re.I,
                            )
                        ),
                        "conditions_or_exceptions": bool(
                            re.search(
                                r"\bsi\b|salvo|excepto|siempre que|requiere",
                                record["text"],
                                re.I,
                            )
                        ),
                    },
                }
                candidates.append(item)
                exact[fingerprint] = item
        unit["institute_blocks"] = institutes
        batches = []
        for institute in institutes:
            doc = load(root, "documents/" + institute["document"] + ".json")
            lookup = {r["id"]: r for r in doc["records"]}
            current = []
            words = 0
            for rid in institute["record_ids"]:
                count = len(lookup[rid]["text"].split())
                if current and words + count > 1000:
                    batches.append(
                        {
                            "document": institute["document"],
                            "institute": institute["title"],
                            "record_ids": current,
                            "source_words": words,
                            "status": "inventory_then_integrate_then_author_then_review",
                        }
                    )
                    current = []
                    words = 0
                current.append(rid)
                words += count
            if current:
                batches.append(
                    {
                        "document": institute["document"],
                        "institute": institute["title"],
                        "record_ids": current,
                        "source_words": words,
                        "status": "inventory_then_integrate_then_author_then_review",
                    }
                )
        unit["source_work_batches"] = batches
        # Workload limits bound source review only. They neither cap the final
        # duration nor permit dropping an exception to fit an audio chapter.
        unit["chapter_policy"] = (
            "Author by institute after cross-source integration; these are source-review batches, not already approved audio chapters."
        )
        unit["integration_policy"] = (
            "Develop V4 depth, integrate V5 priorities by institute; exact duplicates share refs; near matches are review candidates, never automatic legal corrections."
        )
        # A shortlist for editorial comparison, not semantic deduplication or a
        # verdict that differing numbers are necessarily a legal contradiction.
        from difflib import SequenceMatcher

        primary = [
            c
            for c in candidates
            if any(
                meta[r["document"]]["role"].startswith("doctrinal_depth")
                for r in c["source_refs"]
            )
        ]
        priorities = [
            c
            for c in candidates
            if any(
                meta[r["document"]]["role"].startswith("exam_priorities")
                for r in c["source_refs"]
            )
        ]
        comparisons = []
        for candidate in priorities:
            ranked = sorted(
                (
                    (
                        SequenceMatcher(
                            None,
                            candidate["verbatim"].casefold().split(),
                            p["verbatim"].casefold().split(),
                            autojunk=False,
                        ).ratio(),
                        p["id"],
                    )
                    for p in primary
                ),
                reverse=True,
            )[:2]
            comparisons.append(
                {
                    "priority_candidate": candidate["id"],
                    "possible_overlaps": [
                        {"candidate": cid, "lexical_similarity": round(score, 3)}
                        for score, cid in ranked
                        if score >= 0.35
                    ],
                    "status": "unreviewed_not_a_conflict_verdict",
                    "missing_case_card": candidate["flags"]["remission_only"],
                }
            )
        save(root, "units/" + key + "/cross-version-review.json", comparisons)
        save(root, "units/" + key + "/candidates.json", candidates)
        save(root, "units/" + key + "/plan.json", unit)
    save(root, "corpus.json", plan)
    return {
        "documents": len(meta),
        "units": len(all_units),
        "private_originals": True,
        "semantic_coverage_certified": False,
    }


def binding(claim, episode):
    relevant = [s for s in episode["segments"] if claim["id"] in s.get("claim_ids", [])]
    return digest(
        {"claim": claim, "turns": relevant, "sources": episode["source_documents"]}
    )


def progress(corpus, directories):
    """Global claim/source index; references do not imply a complete paragraph."""
    actions_privacy_guard()
    root = private_root(corpus)
    catalog = load(root, "corpus.json")
    rows = {
        key: {
            "unit": unit["unit"],
            "subject": unit["subject"],
            "source_record_count": sum(len(ids) for ids in unit["sources"].values()),
            "scoped_claims": [],
            "unit_complete": False,
            "status": "awaiting_complete_substantive_review",
        }
        for key, unit in catalog["units"].items()
    }
    for directory in directories:
        episode_root = private_root(directory)
        ep = load(episode_root, "review.json")
        verify_sources(episode_root, ep)
        report = audit_dialogue(ep)
        revision = revision_hash(ep)
        for claim in ep["claim_inventory"]:
            refs = {r["source_id"] for r in claim["source_refs"]}
            for key, unit in catalog["units"].items():
                linked = sorted(
                    refs
                    & {
                        name + ":" + rid
                        for name, ids in unit["sources"].items()
                        for rid in ids
                    }
                )
                if linked:
                    rows[key]["scoped_claims"].append(
                        {
                            "id": claim["id"],
                            "episode_revision": revision,
                            "scope": ep["scope"],
                            "source_refs": linked,
                            "editorial_records_valid": report["passed"],
                            "whole_source_paragraph_covered": False,
                        }
                    )
                    rows[key]["status"] = "partial_scoped_work_available"
    save(
        root,
        "unit-coverage-map.json",
        {
            "units": rows,
            "semantic_certified": False,
            "note": "A scoped claim can link multiple units. Counts of references never certify the completeness of a source paragraph or an entire unit.",
        },
    )
    return {
        "units": len(rows),
        "units_complete": 0,
        "scoped_claim_links": sum(len(u["scoped_claims"]) for u in rows.values()),
    }


def audit_dialogue(episode):
    findings = []

    def error(code, message, sid=None):
        findings.append(
            {"severity": "error", "code": code, "message": message, "segment_id": sid}
        )

    records = {b["id"]: b for b in episode["blocks"]}
    segments = {s["id"]: s for s in episode["segments"]}
    claims = {c["id"]: c for c in episode["claim_inventory"]}
    if not claims or not segments or not records:
        error("empty_dialogue", "Faltan afirmaciones, fuentes o intervenciones.")
    if {s["speaker"] for s in segments.values()} != {"profesora", "profesor"}:
        error("two_voices", "La conversación magistral requiere dos profesores.")
    if len(segments) != len(episode["segments"]):
        error("duplicate_turn", "Identificadores de intervención repetidos.")
    if len(claims) != len(episode["claim_inventory"]):
        error("duplicate_claim", "Identificadores de afirmación repetidos.")
    for b in records.values():
        if episode["source"][b["start"] : b["end"]] != b["text"]:
            error("source_integrity", "Fuente o localizador alterado.")
    for s in segments.values():
        if s["speaker"] not in ("profesora", "profesor"):
            error("speaker", "Voz desconocida.", s["id"])
        if not 100 <= s.get("rate_wpm", 140) <= 190:
            error("rate", "Ritmo fuera de límites.", s["id"])
        if s["kind"] != "magistral_turn":
            error(
                "turn_kind",
                "El modo magistral requiere intervenciones originales tipadas.",
                s["id"],
            )
        if (
            not s.get("statements")
            or " ".join(x["text"] for x in s["statements"]) != s["text"]
        ):
            error(
                "statement_integrity",
                "Los tipos de afirmación no reconstruyen la intervención.",
                s["id"],
            )
        for item in s.get("statements", []):
            if item["type"] not in (
                "source_explanation",
                "inference",
                "example",
                "question",
                "didactic_recall",
            ):
                error("statement_type", "Tipo no reconocido.", s["id"])
            if set(item.get("claim_ids", [])) - set(claims):
                error("claim_unknown", "Afirmación inexistente.", s["id"])
            if not item.get("claim_ids"):
                error(
                    "untraced_statement",
                    "Cada afirmación debe identificar sus fundamentos, incluso el ejemplo o la inferencia.",
                    s["id"],
                )
            if item["type"] == "example" and not item.get("hypothetical", False):
                error(
                    "example_label",
                    "El ejemplo debe identificarse como hipotético.",
                    s["id"],
                )
            if item["type"] == "example" and not re.search(
                r"hipotétic|ejemplo|supuesto|caso inventado", item["text"], re.I
            ):
                error(
                    "example_audible_label",
                    "La naturaleza inventada debe ser reconocible también al escuchar.",
                    s["id"],
                )
        if set(s.get("claim_ids", [])) != {
            cid for st in s.get("statements", []) for cid in st.get("claim_ids", [])
        }:
            error(
                "turn_claim_mismatch",
                "Los vínculos del turno no coinciden con sus afirmaciones.",
                s["id"],
            )
        expected_sources = {
            r["source_id"]
            for cid in s.get("claim_ids", [])
            if cid in claims
            for r in claims[cid]["source_refs"]
        }
        if set(s["source_ids"]) != expected_sources:
            error(
                "turn_source_mismatch",
                "Las referencias del turno no coinciden con las afirmaciones.",
                s["id"],
            )
        allowed = [records[r]["text"] for r in s["source_ids"] if r in records]
        if len(allowed) != len(s["source_ids"]):
            error("reference_missing", "Referencia no encontrada.", s["id"])
        # Guides also use explicit abbreviated citations, e.g. LNPA 21 or RL
        # 82 bis. Do not treat arbitrary dates, amounts or unit numbers as law.
        citation_text = re.sub(
            r"\b(?:LNPA|RL)\s+(?=\d)", "artículos ", " ".join(allowed)
        )
        actual = article_keys(s["text"])
        known = article_keys(citation_text)
        if actual - known:
            error(
                "unsupported_article",
                "Artículo sin respaldo en las referencias de esa intervención.",
                s["id"],
            )
        if "Pregunta de examen oral:" in s["text"]:
            error("mechanical_question", "Plantilla mecánica no permitida.", s["id"])
    covered = []
    total_facets = reviewed_facets = 0
    for cid, c in claims.items():
        refs = c["source_refs"]
        valid = True
        if not refs:
            error("claim_source", "Una afirmación sin evidencia no puede revisarse.")
            valid = False
        for r in refs:
            b = records.get(r["source_id"])
            if not b or not r["quote"] or r["quote"] not in b["text"]:
                error(
                    "claim_source",
                    "La evidencia de la afirmación no coincide con la fuente.",
                )
                valid = False
        for f in FACETS:
            if f not in c:
                error("claim_facet_missing", f"Falta declarar {f} para {cid}.")
                valid = False
        review = episode["editorial_reviews"].get(cid, {})
        if review.get("binding") != binding(c, episode):
            error("stale_editorial_review", f"Revisión sustantiva vencida: {cid}.")
            valid = False
        if review.get("method") != "codex_source_to_script_editorial_review":
            error("editorial_method", f"No hay revisión editorial declarada de {cid}.")
            valid = False
        for facet in FACETS:
            values = c.get(facet, [])
            values = values if isinstance(values, list) else [values]
            if not values:
                continue
            total_facets += 1
            decision = review.get("facets", {}).get(facet, {})
            supports = decision.get("supports", [])
            if (
                decision.get("status") != "reviewed"
                or len(decision.get("reason", "")) < 35
                or not supports
            ):
                error(
                    "facet_undeveloped",
                    f"{cid}: {facet} no tiene cotejo sustantivo documentado.",
                )
                valid = False
                continue
            ok = True
            for support in supports:
                turn = segments.get(support["turn_id"])
                if (
                    not turn
                    or support["quote"] not in turn["text"]
                    or len(support["quote"].split()) < 6
                    or cid not in turn.get("claim_ids", [])
                ):
                    ok = False
                elif not any(
                    cid in st.get("claim_ids", [])
                    and st["type"] in ("source_explanation", "didactic_recall")
                    and support["quote"] in st["text"]
                    for st in turn["statements"]
                ):
                    ok = False
            if not ok:
                error(
                    "facet_not_demonstrated",
                    f"{cid}: {facet} sólo está mencionado o apoyado por un ejemplo/inferencia.",
                )
                valid = False
            else:
                reviewed_facets += 1
        if valid:
            covered.append(cid)
    unresolved = [
        c
        for c in episode.get("cross_source_decisions", [])
        if c["status"] == "unresolved"
    ]
    if unresolved:
        error("unresolved_conflict", "Hay discrepancias de fuentes sin resolver.")
    chapters = episode.get("chapter_plan", [])
    ordered = [sid for ch in chapters for sid in ch.get("segment_ids", [])]
    if (
        not chapters
        or ordered != list(segments)
        or len({ch["id"] for ch in chapters}) != len(chapters)
        or any(not ch.get("segment_ids") for ch in chapters)
    ):
        error(
            "chapter_partition",
            "Los capítulos deben conservar todos los turnos una sola vez y en orden.",
        )
    # Never present metadata validation as proof that legal meaning is entailed.
    words = sum(len(s["text"].split()) for s in segments.values())
    return {
        "passed": not findings,
        "findings": findings,
        "coverage": [
            {"id": c["id"], "title": c["rule"], "covered": c["id"] in covered}
            for c in claims.values()
        ],
        "coverage_percent": round(100 * len(covered) / max(1, len(claims)), 2),
        "coverage_basis": "scoped claim/facet editorial records, not automatic semantic certification",
        "reviewed_facets": reviewed_facets,
        "required_facets": total_facets,
        "semantic_certified": False,
        "source_scope": episode["scope"],
        "word_count": words,
        "estimated_minutes": round(
            sum(
                len(s["text"].split()) / s.get("rate_wpm", 140)
                for s in segments.values()
            ),
            2,
        ),
        "target_minutes": None,
        "duration_warning": None,
        "method": "Exact source/turn anchors + revision-bound Codex editorial judgments; entailment is an explicit editorial task, not keyword matching or an independent human review.",
    }


def verify_sources(root, episode):
    for name, info in episode["source_documents"].items():
        path = private_path(root, info["path"])
        if file_hash(path) != info["sha256"]:
            raise FreeCloudError("original_dialogue_source_modified")
        doc = extract(path)
        lookup = {r["id"]: r for r in doc["records"]}
        for block in episode["blocks"]:
            if block["document"] != name:
                continue
            r = lookup.get(block["record_id"])
            if not r or r["text"] != block["text"] or r["locator"] != block["locator"]:
                raise FreeCloudError("dialogue_source_locator_mismatch")
    return None


def assemble(corpus, draft_file, directory):
    actions_privacy_guard()
    corpus = private_root(corpus)
    root = private_root(directory)
    draft = json.loads(Path(draft_file).read_text())
    catalog = load(corpus, "corpus.json")
    if (root / "state.json").exists():
        raise FreeCloudError("dialogue_workspace_already_exists")
    blocks = []
    text = ""
    documents = {}
    for name, ids in draft["source_selection"].items():
        info = catalog["documents"][name]
        doc = load(corpus, "documents/" + name + ".json")
        index = {r["id"]: r for r in doc["records"]}
        path = write_bytes(
            root, "inputs/" + name + ".docx", (corpus / info["path"]).read_bytes()
        )
        documents[name] = {
            "path": str(path.relative_to(root)),
            "sha256": info["sha256"],
            "role": info["role"],
            "filename": info["filename"],
        }
        for rid in ids:
            r = index[rid]
            start = len(text)
            text += r["text"] + "\n\n"
            blocks.append(
                {
                    "id": name + ":" + rid,
                    "text": r["text"],
                    "start": start,
                    "end": start + len(r["text"]),
                    "document": name,
                    "record_id": rid,
                    "locator": r["locator"],
                    "heading": draft["title"],
                    "path": [draft["title"]],
                }
            )
    segments = []
    for turn in draft["turns"]:
        s = copy.deepcopy(turn)
        s["kind"] = "magistral_turn"
        s["text"] = " ".join(i["text"] for i in s["statements"])
        s["claim_ids"] = sorted(
            {cid for st in s["statements"] for cid in st.get("claim_ids", [])}
        )
        s["source_ids"] = sorted(
            {
                r["source_id"]
                for c in draft["claims"]
                if c["id"] in s["claim_ids"]
                for r in c["source_refs"]
            }
        )
        s["topic_ids"] = s["claim_ids"]
        segments.append(s)
    ep = {
        "mode": "magistral_dialogue",
        "voice_count": 2,
        "title": draft["title"],
        "source": text,
        "program": "\n".join(c["id"] + " " + c["rule"] for c in draft["claims"]),
        "blocks": blocks,
        "points": [{"id": c["id"], "title": c["rule"]} for c in draft["claims"]],
        "mapping": {
            c["id"]: [r["source_id"] for r in c["source_refs"]] for c in draft["claims"]
        },
        "segments": segments,
        "claim_inventory": draft["claims"],
        "editorial_reviews": draft["reviews"],
        "cross_source_decisions": draft["cross_source_decisions"],
        "scope": draft["scope"],
        "source_documents": documents,
        "chapter_plan": draft["chapters"],
        "wpm": 145,
        "target_minutes": None,
        "pronunciation": {
            "__policy__": "es-ar-reading-v1",
            "LNPA": "Ley Nacional de Procedimientos Administrativos",
            "CCyC": "Código Civil y Comercial",
            "RL": "reglamento de procedimientos administrativos",
        },
        "approved_hash": None,
    }
    for c in ep["claim_inventory"]:
        ep["editorial_reviews"][c["id"]]["binding"] = binding(c, ep)
    verify_sources(root, ep)
    revision = revision_hash(ep)
    save(root, f"revisions/{revision}.json", ep)
    save(root, "review.json", ep)
    save(
        root,
        "state.json",
        {
            "prepared_revision": revision,
            "approved_revision": None,
            "max_words": 15000,
            "public_demo": False,
        },
    )
    report = audit_dialogue(ep)
    save(root, "coverage-draft.json", report)
    save(root, "plan.json", ep["chapter_plan"])
    return {
        "stage": "dialogue_prepared",
        "claims": len(ep["claim_inventory"]),
        "turns": len(segments),
        "audit_passed": report["passed"],
        "estimated_minutes": report["estimated_minutes"],
        "semantic_certified": False,
    }


def revise(corpus, draft_file, directory):
    """A new authored revision invalidates approval, preserves audio and caches."""
    import time

    root = private_root(directory)
    old = load(root, "review.json")
    staged = private_path(root, "authoring-history/" + str(time.time_ns()))
    result = assemble(corpus, draft_file, staged)
    proposal = load(staged, "review.json")
    if not result["audit_passed"]:
        raise FreeCloudError("new_dialogue_fails_audit")
    if proposal["source_documents"] != old["source_documents"]:
        raise FreeCloudError("source_documents_changed_use_new_episode")
    verify_sources(root, proposal)
    revision = revision_hash(proposal)
    save(root, f"revisions/{revision}.json", proposal)
    save(root, "review.json", proposal)
    state = load(root, "state.json")
    state.update(prepared_revision=revision, approved_revision=None)
    save(root, "state.json", state)
    save(root, "coverage-draft.json", audit_dialogue(proposal))
    save(root, "plan.json", proposal["chapter_plan"])
    archive = private_path(root, "exports/" + str(time.time_ns()))
    archive.mkdir(parents=True, mode=0o700)
    for name in ("deliverables", "academic-audio.zip", "latest-run.json", "downloads"):
        path = private_path(root, name)
        if path.exists():
            path.rename(archive / name)
    return {
        **result,
        "stage": "dialogue_revised_requires_approval",
        "revision": revision,
    }


def export_evidence(root, episode):
    """Private, human-readable scoped matrix, separate from acoustic status."""
    report = audit_dialogue(episode)
    save(
        root,
        "deliverables/claim-matrix.json",
        {
            "scope": episode["scope"],
            "claims": episode["claim_inventory"],
            "editorial_reviews": episode["editorial_reviews"],
            "cross_source_decisions": episode["cross_source_decisions"],
            "audit": report,
        },
    )
    save(
        root,
        "deliverables/source-map.json",
        {
            "documents": episode["source_documents"],
            "records": episode["blocks"],
            "chapters": episode["chapter_plan"],
        },
    )
    rows = [
        "# Matriz de cobertura editorial de la muestra",
        "",
        "Alcance: " + json.dumps(episode["scope"], ensure_ascii=False),
        "",
        "Cotejo de Codex contra las guías adjuntas. No certifica vigencia normativa, revisión humana ni cobertura integral de la unidad. Los porcentajes cuentan registros revisados; no prueban equivalencia semántica por sí solos.",
        "",
    ]
    for c in episode["claim_inventory"]:
        rows += ["## " + c["id"], ""]
        for facet in FACETS:
            rows += [facet + ": " + json.dumps(c[facet], ensure_ascii=False), ""]
        rows += ["Fuentes: " + ", ".join(r["source_id"] for r in c["source_refs"]), ""]
        for facet, decision in episode["editorial_reviews"][c["id"]]["facets"].items():
            rows += [
                facet
                + " → "
                + ", ".join(s["turn_id"] for s in decision["supports"])
                + ": "
                + decision["reason"],
                "",
            ]
    write_bytes(root, "deliverables/claim-matrix.md", "\n".join(rows).encode())


def main():
    import os
    import sys

    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    i = sub.add_parser("intake")
    i.add_argument("--manifest", required=True)
    i.add_argument("--workdir", required=True)
    a = sub.add_parser("assemble")
    a.add_argument("--corpus", required=True)
    a.add_argument("--draft", required=True)
    a.add_argument("--workdir", required=True)
    a = sub.add_parser("revise")
    a.add_argument("--corpus", required=True)
    a.add_argument("--draft", required=True)
    a.add_argument("--workdir", required=True)
    g = sub.add_parser("progress")
    g.add_argument("--corpus", required=True)
    g.add_argument("--episodes", nargs="+", required=True)
    args = p.parse_args()
    try:
        if args.command == "intake":
            result = intake(args.workdir, json.loads(Path(args.manifest).read_text()))
        elif args.command == "progress":
            result = progress(args.corpus, args.episodes)
        else:
            result = (revise if args.command == "revise" else assemble)(
                args.corpus, args.draft, args.workdir
            )
        print(json.dumps(result))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "stage": "blocked",
                    "code": str(exc)
                    if isinstance(exc, FreeCloudError)
                    else type(exc).__name__,
                }
            ),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
