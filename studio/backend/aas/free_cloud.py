"""Ephemeral, private CPU production in Codex Cloud. No API, DB, server or paid provider.

prepare -> review.json -> approve --reviewed -> render -> private downloadable ZIP
Only counts/status are logged. All source text and artifacts stay outside Git checkouts.
"""

import argparse
import copy
import json
import os
import sys
import time
import zipfile
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from pathlib import Path

from .core import (
    audit,
    digest,
    map_topics,
    parse_program,
    parse_source,
    revision_hash,
)
from .open_models import OpenVoices, OpenASR, file_hash, setup_models
from .tts import join_audio, probe

REPO = Path(__file__).resolve().parents[3]
VOICES = ("kokoro:ef_dora", "kokoro:em_alex", "kokoro:em_santa")


class FreeCloudError(ValueError):
    pass


def private_root(directory):
    original = Path(directory).absolute()
    root = original.resolve()
    if root == REPO or root.is_relative_to(REPO):
        raise FreeCloudError("private_directory_must_be_outside_repository")
    # Reject any real ancestor Git checkout, including linked worktrees, without reading remotes.
    import subprocess

    existing = next(p for p in [root, *root.parents] if p.exists())
    git = subprocess.run(
        ["git", "-C", str(existing), "rev-parse", "--show-toplevel"],
        capture_output=True,
    )
    if git.returncode == 0:
        raise FreeCloudError("private_directory_must_be_outside_repository")
    if any(p.is_symlink() for p in [original, *original.parents]):
        raise FreeCloudError("symlink_private_root_rejected")
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    return root


def private_path(root, relative):
    p = Path(root) / relative
    if not p.resolve().is_relative_to(Path(root).resolve()):
        raise FreeCloudError("unsafe_private_path")
    if any(
        x.is_symlink()
        for x in [p, *list(p.parents)[: len(p.parts) - len(Path(root).parts)]]
    ):
        raise FreeCloudError("symlink_private_path_rejected")
    return p


def write_bytes(root, relative, content):
    path = private_path(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = private_path(root, str(relative) + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(content)
    temp.chmod(0o600)
    temp.replace(path)
    return path


def save(root, relative, data):
    return write_bytes(
        root, relative, json.dumps(data, ensure_ascii=False, indent=2).encode()
    )


def load(root, relative):
    return json.loads(private_path(root, relative).read_text())


def verify_imports(root, ep):
    if ep.get("mode") == "magistral_dialogue":
        from .magistral import verify_sources

        return verify_sources(root, ep)
    imports = None
    if "import_fingerprint" in ep:
        imports = {
            key: load(root, "import-" + key + ".json") for key in ("source", "program")
        }
        if digest(imports) != ep["import_fingerprint"]:
            raise FreeCloudError("document_import_manifest_modified")
        for key, item in imports.items():
            suffix = "." + item["format"]
            # Keep .markdown inputs distinguishable from .md; TXT/PDF/DOCX are exact.
            candidate = private_path(root, "inputs/" + key + suffix)
            if not candidate.is_file() or file_hash(candidate) != item["sha256"]:
                raise FreeCloudError("original_input_file_modified")
    return imports


def actions_privacy_guard(source=None, program=None, public_demo=False):
    if os.getenv("GITHUB_ACTIONS") != "true":
        return
    private = os.getenv("GITHUB_REPOSITORY_VISIBILITY") == "private"
    if private:
        if os.getenv("AAS_FREE_ACTIONS_CONFIRMED") != "1":
            raise FreeCloudError(
                "private_actions_requires_verified_free_quota_and_zero_spending_limit"
            )
    else:
        if not public_demo or source is None or program is None:
            raise FreeCloudError("private_material_forbidden_on_public_actions")
        for supplied, fixture in [(source, "unidad.md"), (program, "programa.md")]:
            if file_hash(supplied) != file_hash(REPO / "studio/examples" / fixture):
                raise FreeCloudError("public_demo_must_match_committed_public_fixture")


def chapters_for(episode, max_words=1200):
    if episode.get("mode") == "magistral_dialogue":
        return episode["chapter_plan"]
    if not 100 <= max_words <= 15000:
        raise FreeCloudError("invalid_chapter_word_limit")
    blocks = {b["id"]: b for b in episode["blocks"]}
    chapters = []
    current = None
    for segment in episode["segments"]:
        block = blocks[segment["source_ids"][0]]
        heading = block.get("path", [block["heading"]])
        title = (
            heading[1]
            if len(heading) > 1
            else heading[0]
            if heading
            else block["heading"]
        )
        words = len(segment["text"].split())
        if (
            current is None
            or (current["title"] != title and current["segment_ids"])
            or (current["words"] + words > max_words and current["segment_ids"])
        ):
            current = {
                "id": f"c{len(chapters) + 1:03}",
                "title": title,
                "segment_ids": [],
                "source_ids": [],
                "words": 0,
            }
            chapters.append(current)
        current["segment_ids"].append(segment["id"])
        current["words"] += words
        for ref in segment["source_ids"]:
            if ref not in current["source_ids"]:
                current["source_ids"].append(ref)
    return chapters


def documentary_dialogue(blocks, points, mapping):
    """Give the voice context: merge nearby source lines without losing a single span.

    Repeated headings in different parent units never get merged. Every statement is
    still the exact concatenation of its immutable source_ids, which core.audit checks.
    """
    groups = []
    for block in blocks:
        path = block.get("path", [block["heading"]])
        if (
            not groups
            or groups[-1]["path"] != path
            or sum(len(b["text"]) + 1 for b in groups[-1]["blocks"])
            + len(block["text"])
            > 1000
        ):
            groups.append({"path": path, "blocks": []})
        groups[-1]["blocks"].append(block)
    segments = []
    previous_path = None
    for i, group in enumerate(groups):
        refs = [b["id"] for b in group["blocks"]]
        pids = [pid for pid, bids in mapping.items() if set(bids) & set(refs)]
        speaker = "profesora" if i % 2 == 0 else "profesor"
        if group["path"] != previous_path:
            segments.append(
                {
                    "id": f"s{len(segments) + 1}",
                    "speaker": "profesor" if speaker == "profesora" else "profesora",
                    "kind": "question",
                    "text": f"Pregunta de examen oral: ¿qué desarrolla el material sobre {group['blocks'][0]['heading']}?",
                    "source_ids": [refs[0]],
                    "topic_ids": [
                        pid for pid, bids in mapping.items() if refs[0] in bids
                    ],
                }
            )
        segments.append(
            {
                "id": f"s{len(segments) + 1}",
                "speaker": speaker,
                "kind": "source",
                "text": "\n".join(b["text"] for b in group["blocks"]),
                "source_ids": refs,
                "topic_ids": pids,
            }
        )
        previous_path = group["path"]
    return segments


def faithful_reading(blocks, mapping, voice_count=1):
    if voice_count not in (1, 2):
        raise FreeCloudError("one_or_two_voices_required")
    groups = []
    chapter_keys = []
    for b in blocks:
        path = b.get("path", [])
        chapter = tuple(path[:2]) if path else ("Documento",)
        if chapter not in chapter_keys:
            chapter_keys.append(chapter)
        if (
            not groups
            or groups[-1]["chapter"] != chapter
            or sum(len(x["text"]) + 1 for x in groups[-1]["blocks"]) + len(b["text"])
            > 1000
        ):
            groups.append({"chapter": chapter, "blocks": []})
        groups[-1]["blocks"].append(b)
    segments = []
    for group in groups:
        ids = [b["id"] for b in group["blocks"]]
        segments.append(
            {
                "id": f"s{len(segments) + 1}",
                "kind": "source",
                "speaker": "profesora"
                if voice_count == 1 or chapter_keys.index(group["chapter"]) % 2 == 0
                else "profesor",
                "text": "\n".join(b["text"] for b in group["blocks"]),
                "source_ids": ids,
                "topic_ids": [p for p, bids in mapping.items() if set(ids) & set(bids)],
            }
        )
    return segments


def prepare(
    source,
    program,
    directory,
    *,
    max_words=1200,
    wpm=140,
    target_minutes=10,
    public_demo=False,
    mode="documentary",
    voice_count=None,
):
    actions_privacy_guard(source, program, public_demo)
    root = private_root(directory)
    if private_path(root, "state.json").exists():
        raise FreeCloudError("workspace_already_exists_use_new_private_directory")
    from .documents import extract

    imported = extract(source)
    program_imported = extract(program)
    source_text = imported["source"]
    program_text = program_imported["source"]
    if mode not in ("documentary", "reading"):
        raise FreeCloudError("unsupported_reading_mode")
    voice_count = (
        voice_count if voice_count is not None else 1 if mode == "reading" else 2
    )
    blocks = imported.get("blocks") or parse_source(
        source_text, include_headings=mode == "reading"
    )
    points = parse_program(program_text)
    save(root, "import-source.json", imported)
    save(root, "import-program.json", program_imported)
    write_bytes(
        root, "inputs/source" + Path(source).suffix.lower(), Path(source).read_bytes()
    )
    write_bytes(
        root,
        "inputs/program" + Path(program).suffix.lower(),
        Path(program).read_bytes(),
    )
    mapping = map_topics(blocks, points)
    if not 100 <= wpm <= 190:
        raise FreeCloudError("invalid_speech_rate")
    episode = {
        "source": source_text,
        "program": program_text,
        "blocks": blocks,
        "points": points,
        "mapping": mapping,
        "segments": faithful_reading(blocks, mapping, voice_count)
        if mode == "reading"
        else documentary_dialogue(blocks, points, mapping),
        "pronunciation": {
            "CCCN": "Código Civil y Comercial de la Nación",
            "Art.": "artículo",
            "Arts.": "artículos",
            "v.gr.": "por ejemplo",
            "DNU": "decreto de necesidad y urgencia",
        },
        "wpm": wpm,
        "target_minutes": target_minutes,
        "approved_hash": None,
    }
    episode.update(
        {
            "mode": mode,
            "voice_count": voice_count,
            "import_fingerprint": digest(
                {"source": imported, "program": program_imported}
            ),
        }
    )
    if mode == "reading":
        episode["pronunciation"]["__policy__"] = "es-ar-reading-v1"
    from .speech import compile_speech

    save(
        root,
        "spoken-plan-draft.json",
        [
            {
                "segment_id": s["id"],
                **compile_speech(s["text"], episode["pronunciation"]),
            }
            for s in episode["segments"]
        ],
    )
    revision = revision_hash(episode)
    save(root, f"revisions/{revision}.json", episode)
    save(root, "review.json", episode)
    report = audit(episode)
    save(root, "coverage-draft.json", report)
    plan = chapters_for(episode, max_words)
    save(root, "plan.json", plan)
    save(
        root,
        "state.json",
        {
            "prepared_revision": revision,
            "approved_revision": None,
            "max_words": max_words,
            "public_demo": public_demo,
        },
    )
    export_script(root, "script-draft.md", episode)
    return {
        "stage": "prepared",
        "chapters": len(plan),
        "segments": len(episode["segments"]),
        "coverage_percent": report["coverage_percent"],
        "audit_passed": report["passed"],
        "approved": False,
    }


def approve(
    directory,
    *,
    reviewed=False,
    reviewer="workspace-reviewer",
    conversion_reviewed=False,
):
    root = private_root(directory)
    state = load(root, "state.json")
    if not reviewed:
        raise FreeCloudError("explicit_review_required_before_synthesis")
    original = load(root, f"revisions/{state['prepared_revision']}.json")
    if revision_hash(original) != state["prepared_revision"]:
        raise FreeCloudError("prepared_snapshot_modified")
    verify_imports(root, original)
    proposal = load(root, "review.json")
    for filename in ("import-source.json", "import-program.json"):
        if (
            private_path(root, filename).exists()
            and load(root, filename).get("review_required")
            and not conversion_reviewed
        ):
            raise FreeCloudError("ambiguous_document_layout_requires_conversion_review")
    for key in (
        "source",
        "program",
        "blocks",
        "points",
        "mode",
        "voice_count",
        "import_fingerprint",
        "claim_inventory",
        "editorial_reviews",
        "cross_source_decisions",
        "scope",
        "source_documents",
        "chapter_plan",
    ):
        if key in original and proposal.get(key) != original[key]:
            raise FreeCloudError("immutable_source_modified")
    # Only editable fields enter the new revision. No forged LLM verdicts from a JSON editor.
    ep = copy.deepcopy(original)
    for key in ("mapping", "segments", "pronunciation"):
        if key not in proposal:
            raise FreeCloudError("incomplete_review")
        ep[key] = proposal[key]
    if set(ep["mapping"]) != {p["id"] for p in ep["points"]} or any(
        b not in {x["id"] for x in ep["blocks"]}
        for bids in ep["mapping"].values()
        for b in bids
    ):
        raise FreeCloudError("invalid_program_mapping")
    report = audit(ep)
    save(root, "coverage-reviewed.json", report)
    if not report["passed"]:
        raise FreeCloudError("substantial_audit_errors_see_private_report")
    from .speech import compile_speech

    save(
        root,
        "spoken-plan-approved.json",
        [
            {"segment_id": s["id"], **compile_speech(s["text"], ep["pronunciation"])}
            for s in ep["segments"]
        ],
    )
    revision = revision_hash(ep)
    ep["approved_hash"] = revision
    ep["approval"] = {
        "reviewer": reviewer,
        "scope": "source associations and script reviewed; not a certification of current law",
        "time": time.time(),
    }
    save(root, f"revisions/{revision}.json", ep)
    # Preserve previous exports privately, but never present them as the new approval.
    if (
        private_path(root, "deliverables").exists()
        or private_path(root, "academic-audio.zip").exists()
    ):
        archive = private_path(root, f"exports/{time.time_ns()}")
        archive.mkdir(parents=True, mode=0o700)
        for name in ("deliverables", "academic-audio.zip"):
            path = private_path(root, name)
            if path.exists():
                path.rename(archive / name)
    save(root, "plan.json", chapters_for(ep, state["max_words"]))
    state["approved_revision"] = revision
    save(root, "state.json", state)
    export_script(root, "script-approved.md", ep)
    return {
        "stage": "approved",
        "revision": revision,
        "coverage_percent": report["coverage_percent"],
    }


def export_script(root, filename, episode):
    text = "\n\n".join(
        f"[{s['id']}] {s['speaker']} · {s['kind']} · fuentes {', '.join(s['source_ids'])}\n{s['text']}"
        for s in episode["segments"]
    )
    return write_bytes(root, filename, text.encode())


def export_secondary_review(root, report):
    """Bundle only a second recognition bound to these exact audio hashes."""
    if not private_path(root, "audio-review/review.json").is_file():
        return []
    from .quality import QUALITY_VERSION

    review = load(root, "audio-review/review.json")
    hashes = {r["segment_id"]: r["sha256"] for r in report["segments"]}
    if (
        review.get("revision") != report["revision"]
        or review.get("normalizer") != QUALITY_VERSION
        or any(hashes.get(r["segment_id"]) != r["audio_sha256"] for r in review["rows"])
    ):
        return []
    exported = copy.deepcopy(review)
    for row in exported["rows"]:
        row.pop("clip", None)
    exported["note"] += (
        " WAV review clips remain in the private workspace; listen using the complete MP3 and segment IDs."
    )
    save(root, "deliverables/secondary-asr-review.json", exported)
    return ["secondary-asr-review.json"]


@contextmanager
def private_engine_log(root):
    """Capture Python AND native diagnostics: a backend may echo the input on failure."""
    path = private_path(root, "engine-private.log")
    out_fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(1), os.dup(2)]
    try:
        os.dup2(out_fd, 1)
        os.dup2(out_fd, 2)
        # Also replace Python streams: notebooks/test runners can use streams whose
        # file descriptors differ from 1/2, so dup2 alone is not enough.
        with os.fdopen(os.dup(out_fd), "w", encoding="utf-8") as log_stream:
            with redirect_stdout(log_stream), redirect_stderr(log_stream):
                yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        # Flush native stdio while it still points at the private log.
        import ctypes

        ctypes.CDLL(None).fflush(None)
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        for fd in saved + [out_fd]:
            os.close(fd)


def render(
    directory,
    models,
    *,
    voice_a="kokoro:ef_dora",
    voice_b="kokoro:em_alex",
    chapter_ids=None,
    regenerate=None,
    asr=False,
    threads=2,
):
    root = private_root(directory)
    state = load(root, "state.json")
    public_base = None
    if os.getenv("GITHUB_ACTIONS") == "true":
        if os.getenv("GITHUB_REPOSITORY_VISIBILITY") == "private":
            # Even a public fixture must not consume an unknown private-runner quota.
            actions_privacy_guard()
        elif not state.get("public_demo"):
            raise FreeCloudError("private_material_forbidden_on_public_actions")
        else:
            # Original source must still match the committed public fixture; the flag alone is insufficient.
            base = load(root, f"revisions/{state['prepared_revision']}.json")
            if (
                base["source"] != (REPO / "studio/examples/unidad.md").read_text()
                or base["program"] != (REPO / "studio/examples/programa.md").read_text()
            ):
                raise FreeCloudError("private_material_forbidden_on_public_actions")
            public_base = base
    revision = state.get("approved_revision")
    if not revision:
        raise FreeCloudError("explicit_review_required_before_synthesis")
    ep = load(root, f"revisions/{revision}.json")
    imports = verify_imports(root, ep)
    if public_base is not None and any(
        ep[key] != public_base[key]
        for key in (
            "source",
            "program",
            "blocks",
            "points",
            "segments",
            "mapping",
            "pronunciation",
        )
    ):
        raise FreeCloudError("public_actions_demo_edits_forbidden")
    if (
        revision_hash(ep) != revision
        or ep.get("approved_hash") != revision
        or not audit(ep)["passed"]
    ):
        raise FreeCloudError("approved_revision_invalid")
    review = load(root, "review.json")
    if any(
        review.get(key) != ep[key]
        for key in (
            "source",
            "program",
            "blocks",
            "points",
            "segments",
            "mapping",
            "pronunciation",
            *(
                [
                    "claim_inventory",
                    "editorial_reviews",
                    "cross_source_decisions",
                    "scope",
                    "source_documents",
                    "chapter_plan",
                ]
                if ep.get("mode") == "magistral_dialogue"
                else []
            ),
        )
    ):
        raise FreeCloudError("review_has_unapproved_edits")
    if (
        (ep.get("voice_count", 2) == 2 and voice_a == voice_b)
        or voice_a not in VOICES
        or voice_b not in VOICES
    ):
        raise FreeCloudError("two_distinct_open_voices_required")
    chapters = chapters_for(ep, state["max_words"])
    segments = {s["id"]: s for s in ep["segments"]}
    if chapter_ids and set(chapter_ids) - {c["id"] for c in chapters}:
        raise FreeCloudError("unknown_chapter")
    if regenerate and set(regenerate) - set(segments):
        raise FreeCloudError("unknown_segment")
    chosen = [c for c in chapters if not chapter_ids or c["id"] in chapter_ids]
    if regenerate and set(regenerate) - {
        sid for c in chosen for sid in c["segment_ids"]
    }:
        raise FreeCloudError("regenerate_segment_outside_selected_chapters")
    voice_map = {"profesora": voice_a, "profesor": voice_b}
    started = time.monotonic()
    with private_engine_log(root):
        engines = OpenVoices(models, threads=threads)
        identities = {
            name: engines.identity(voice) for name, voice in voice_map.items()
        }
        recognizer = OpenASR(models, threads=threads) if asr else None
    config = {
        "revision": revision,
        "identities": identities,
        "wpm": ep["wpm"],
        "engine_version": engines.version,
        "asr": "whisper-base-int8" if asr else None,
        "comparison_version": __import__(
            "aas.quality", fromlist=["QUALITY_VERSION"]
        ).QUALITY_VERSION,
        "mode": ep.get("mode", "documentary"),
    }
    run_hash = digest(config)
    prefix = f"runs/{run_hash}"
    records = (
        load(root, f"{prefix}/segments.json")
        if private_path(root, f"{prefix}/segments.json").exists()
        else {}
    )
    finished = (
        load(root, f"{prefix}/chapters.json")
        if private_path(root, f"{prefix}/chapters.json").exists()
        else {}
    )
    reused = generated = 0
    for chapter in chosen:
        paths = []
        for sid in chapter["segment_ids"]:
            segment = segments[sid]
            rate = segment.get("rate_wpm", ep["wpm"])
            voice = voice_map[segment["speaker"]]
            from .speech import compile_speech

            speech_plan = compile_speech(segment["text"], ep["pronunciation"])
            text = speech_plan["spoken_text"]
            cache_key = digest(
                {
                    "spoken": text,
                    "voice": identities[segment["speaker"]],
                    "wpm": rate,
                    "version": engines.version,
                }
            )
            rel = f"cache/{cache_key}.wav"
            wav = private_path(root, rel)
            meta = private_path(root, f"cache/{cache_key}.json")
            cached = (
                wav.is_file()
                and meta.is_file()
                and not (regenerate and sid in regenerate)
            )
            if cached:
                cached = (
                    file_hash(wav) == load(root, f"cache/{cache_key}.json")["sha256"]
                )
            if not cached:
                if wav.exists():
                    write_bytes(
                        root,
                        "audio-history/" + file_hash(wav) + ".wav",
                        wav.read_bytes(),
                    )
                with private_engine_log(root):
                    audio = engines.synthesize(text, voice, rate)
                wav = write_bytes(root, rel, audio)
                save(root, f"cache/{cache_key}.json", {"sha256": file_hash(wav)})
                generated += 1
            else:
                reused += 1
            transcript = None
            verification = {
                "passed": None,
                "reason": "ASR not requested; review audio only",
            }
            if recognizer:
                from .open_models import ASSETS

                asr_key = digest(
                    {
                        "audio": file_hash(wav),
                        "model": ASSETS["sherpa-onnx-whisper-base.tar.bz2"][1],
                        "windows": "silence-v1",
                        "lang": "es",
                        "prompt": None,
                    }
                )
                asr_cache = f"asr-cache/{asr_key}.json"
                if private_path(root, asr_cache).exists():
                    transcript = load(root, asr_cache)["transcript"]
                else:
                    with private_engine_log(root):
                        transcript = recognizer.transcribe(wav)
                    save(
                        root,
                        asr_cache,
                        {
                            "audio_sha256": file_hash(wav),
                            "transcript": transcript,
                            "model_profile": "base-int8-es-silence-v1-no-prompt",
                        },
                    )
                from .quality import assess_transcript

                verification = assess_transcript(text, transcript)
            records[sid] = {
                "segment_id": sid,
                "source_ids": segment["source_ids"],
                "voice": voice,
                "cache_file": rel,
                "sha256": file_hash(wav),
                "cached": cached,
                "seconds": probe(wav),
                "spoken_text": text,
                "rate_wpm": rate,
                "speech_transformations": speech_plan["transformations"],
                "transcript": transcript,
                "verification": verification,
            }
            paths.append(wav)
            save(root, f"{prefix}/segments.json", records)
        import tempfile

        with tempfile.TemporaryDirectory(dir=root) as temporary:
            output = Path(temporary) / "chapter.mp3"
            with private_engine_log(root):
                seconds = join_audio(
                    paths,
                    output,
                    pause_seconds=0.03 if ep.get("mode") == "reading" else 0.12,
                )
            mp3 = write_bytes(
                root, f"{prefix}/{chapter['id']}.mp3", output.read_bytes()
            )
        finished[chapter["id"]] = {
            "sha256": file_hash(mp3),
            "seconds": seconds,
            "segment_ids": chapter["segment_ids"],
        }
        save(root, f"{prefix}/chapters.json", finished)
    all_done = all(
        c["id"] in finished
        and private_path(root, f"{prefix}/{c['id']}.mp3").is_file()
        and file_hash(private_path(root, f"{prefix}/{c['id']}.mp3"))
        == finished[c["id"]]["sha256"]
        for c in chapters
    )
    rendered = {sid for c in finished.values() for sid in c["segment_ids"]}
    report = {
        "source_audit": audit(ep),
        "document_import": {
            k: {"format": v["format"], "sha256": v["sha256"], "proof": v["proof"]}
            for k, v in imports.items()
        }
        if imports
        else None,
        "revision": revision,
        "configuration": config,
        "plan": chapters,
        "chapters_completed": len(finished),
        "chapters_total": len(chapters),
        "complete": all_done,
        "rendered_segment_percent": round(100 * len(rendered) / len(segments), 2),
        "new_segments": generated,
        "reused_segments": reused,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "segments": [records[sid] for sid in segments if sid in records],
        "audio_status": "verified"
        if all_done
        and all(records[s]["verification"]["passed"] is True for s in segments)
        else "unverified",
        "privacy": "private cloud workspace, outside repository; no remote API or upload",
        "billing": "CPU inference inside current Codex quota, no commercial API, no provisioned hosting",
        "limitations": [
            "Coverage is structural; not a legal opinion or current-law verification.",
            "No native Argentine listening panel has approved the voices.",
            "ASR is a heuristic and may misrecognize Latin, numbers, or negations.",
        ],
    }
    save(root, f"{prefix}/report.json", report)
    save(root, "latest-run.json", {"prefix": prefix, "complete": all_done})
    if all_done:
        deliver = "deliverables"
        audio_paths = [
            private_path(root, records[sid]["cache_file"]) for sid in segments
        ]
        import tempfile

        with tempfile.TemporaryDirectory(dir=root) as temporary:
            output = Path(temporary) / "podcast.mp3"
            with private_engine_log(root):
                seconds = join_audio(
                    audio_paths,
                    output,
                    pause_seconds=0.03 if ep.get("mode") == "reading" else 0.12,
                )
            write_bytes(root, f"{deliver}/podcast.mp3", output.read_bytes())
        report["duration_seconds"] = seconds
        save(root, f"{deliver}/coverage-audio.json", report)
        save(
            root,
            f"{deliver}/differences.json",
            {
                "comparison_version": config["comparison_version"],
                "audio_status": report["audio_status"],
                "unresolved": [
                    s
                    for s in report["segments"]
                    if s["verification"]["passed"] is not True
                ],
            },
        )
        write_bytes(
            root,
            f"{deliver}/transcript.txt",
            "\n\n".join(
                f"[{s['segment_id']}] {s['transcript'] if s['transcript'] is not None else '[ASR pendiente]'}"
                for s in report["segments"]
            ).encode(),
        )
        export_script(root, f"{deliver}/script.md", ep)
        save(root, f"{deliver}/script.json", ep)
        if ep.get("mode") == "magistral_dialogue":
            from .magistral import export_evidence

            export_evidence(root, ep)
        secondary_exports = export_secondary_review(root, report)
        for chapter in chapters:
            write_bytes(
                root,
                f"{deliver}/{chapter['id']}.mp3",
                private_path(root, f"{prefix}/{chapter['id']}.mp3").read_bytes(),
            )
        # Explicit allowlist: never zip source paths, caches, model files, or native engine logs.
        zip_path = private_path(root, "academic-audio.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for name in (
                [
                    "podcast.mp3",
                    "script.md",
                    "script.json",
                    "coverage-audio.json",
                ]
                + (
                    ["differences.json", "transcript.txt"]
                    if ep.get("mode") in ("reading", "magistral_dialogue")
                    else []
                )
                + (
                    ["claim-matrix.json", "claim-matrix.md", "source-map.json"]
                    if ep.get("mode") == "magistral_dialogue"
                    else []
                )
                + [f"{c['id']}.mp3" for c in chapters]
                + secondary_exports
            ):
                z.write(private_path(root, f"{deliver}/{name}"), arcname=name)
        zip_path.chmod(0o600)
    return {
        "stage": "rendered",
        "complete": all_done,
        "chapters_completed": len(finished),
        "chapters_total": len(chapters),
        "new_segments": generated,
        "reused_segments": reused,
        "audio_status": report["audio_status"],
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }


def recheck(directory):
    """Re-evaluate cached ASR text with new comparison rules, never resynthesize audio."""
    from .quality import assess_transcript, QUALITY_VERSION

    root = private_root(directory)
    state = load(root, "state.json")
    latest = load(root, "latest-run.json")
    report = load(root, latest["prefix"] + "/report.json")
    ep = load(root, f"revisions/{state['approved_revision']}.json")
    verify_imports(root, ep)
    if report["revision"] != revision_hash(ep) or not audit(ep)["passed"]:
        raise FreeCloudError("obsolete_audio_revision")
    save(root, f"quality-history/{time.time_ns()}.json", report)
    for row in report["segments"]:
        wav = private_path(root, row["cache_file"])
        if file_hash(wav) != row["sha256"]:
            raise FreeCloudError("cached_audio_changed")
        row["verification"] = (
            assess_transcript(row["spoken_text"], row["transcript"])
            if row["transcript"] is not None
            else {"passed": None, "reason": "ASR not configured"}
        )
    report["comparison_revision"] = QUALITY_VERSION
    report["audio_status"] = (
        "verified"
        if report["complete"]
        and all(r["verification"]["passed"] is True for r in report["segments"])
        else "unverified"
    )
    save(root, latest["prefix"] + "/report.json", report)
    if report["complete"]:
        old = load(root, "deliverables/coverage-audio.json")
        if "duration_seconds" in old:
            report["duration_seconds"] = old["duration_seconds"]
        save(root, "deliverables/coverage-audio.json", report)
        differences = {
            "comparison_version": QUALITY_VERSION,
            "audio_status": report["audio_status"],
            "unresolved": [
                r for r in report["segments"] if r["verification"]["passed"] is not True
            ],
        }
        save(root, "deliverables/differences.json", differences)
        write_bytes(
            root,
            "deliverables/transcript.txt",
            "\n\n".join(
                f"[{r['segment_id']}] {r['transcript'] if r['transcript'] is not None else '[ASR pendiente]'}"
                for r in report["segments"]
            ).encode(),
        )
        names = [
            "podcast.mp3",
            "script.md",
            "script.json",
            "coverage-audio.json",
            "differences.json",
            "transcript.txt",
        ] + [c["id"] + ".mp3" for c in report["plan"]]
        if ep.get("mode") == "magistral_dialogue":
            from .magistral import export_evidence

            export_evidence(root, ep)
            names += ["claim-matrix.json", "claim-matrix.md", "source-map.json"]
        names += export_secondary_review(root, report)
        import io

        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for name in names:
                z.writestr(
                    name, private_path(root, "deliverables/" + name).read_bytes()
                )
        write_bytes(root, "academic-audio.zip", out.getvalue())
    return {
        "stage": "rechecked",
        "comparison_version": QUALITY_VERSION,
        "audio_status": report["audio_status"],
        "new_audio_segments": 0,
        "pending": sum(
            r["verification"]["passed"] is not True for r in report["segments"]
        ),
    }


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    model = sub.add_parser("models")
    model.add_argument("--directory", required=True)
    model.add_argument("--piper", action="store_true")
    model.add_argument("--asr", action="store_true")
    model.add_argument("--review-asr", dest="review", action="store_true")
    prep = sub.add_parser("prepare")
    prep.add_argument("--source", required=True)
    prep.add_argument("--program", required=True)
    prep.add_argument("--workdir", required=True)
    prep.add_argument("--max-words", type=int, default=1200)
    prep.add_argument("--wpm", type=int, default=140)
    prep.add_argument("--target-minutes", type=int, default=10)
    prep.add_argument("--public-demo", action="store_true")
    prep.add_argument("--mode", choices=["reading", "documentary"], default="reading")
    prep.add_argument("--voice-count", type=int, choices=[1, 2])
    approval = sub.add_parser("approve")
    approval.add_argument("--workdir", required=True)
    approval.add_argument("--reviewed", action="store_true")
    approval.add_argument("--conversion-reviewed", action="store_true")
    approval.add_argument("--reviewer", default="workspace-reviewer")
    r = sub.add_parser("render")
    r.add_argument("--workdir", required=True)
    r.add_argument("--models", required=True)
    r.add_argument("--voice-a", choices=VOICES, default=VOICES[0])
    r.add_argument("--voice-b", choices=VOICES, default=VOICES[1])
    r.add_argument("--chapters")
    r.add_argument("--regenerate")
    r.add_argument("--asr", action="store_true")
    r.add_argument("--threads", type=int, choices=range(1, 5), default=2)
    check = sub.add_parser("recheck")
    check.add_argument("--workdir", required=True)
    review = sub.add_parser("review-audio")
    review.add_argument("--workdir", required=True)
    review.add_argument("--models", required=True)
    review.add_argument("--segments")
    args = vars(p.parse_args())
    command = args.pop("command")
    try:
        if command == "models":
            args["directory"] = private_root(args["directory"])
            result = {"stage": "models_ready", "assets": len(setup_models(**args))}
        elif command == "prepare":
            args["directory"] = args.pop("workdir")
            result = prepare(**args)
        elif command == "review-audio":
            from .review_audio import review_existing

            result = review_existing(
                args["workdir"],
                args["models"],
                args["segments"].split(",") if args["segments"] else None,
            )["counts"]
        elif command == "recheck":
            result = recheck(args["workdir"])
        elif command == "approve":
            args["directory"] = args.pop("workdir")
            result = approve(**args)
        else:
            args["directory"] = args.pop("workdir")
            args["chapter_ids"] = (
                args.pop("chapters").split(",") if args.get("chapters") else None
            )
            args.pop("chapters", None)
            args["regenerate"] = (
                args["regenerate"].split(",") if args["regenerate"] else None
            )
            result = render(**args)
        print(json.dumps(result))
    except Exception as exc:
        # Keep messages from inputs/libraries out of logs; details stay in private workspace.
        from .documents import DocumentError
        from .speech import SpeechPlanError

        code = (
            str(exc)
            if isinstance(exc, (FreeCloudError, DocumentError, SpeechPlanError))
            else type(exc).__name__
        )
        print(json.dumps({"stage": "blocked", "code": code}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
