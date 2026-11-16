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
from .tts import spoken_text, join_audio, probe

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


def prepare(
    source,
    program,
    directory,
    *,
    max_words=1200,
    wpm=140,
    target_minutes=10,
    public_demo=False,
):
    actions_privacy_guard(source, program, public_demo)
    root = private_root(directory)
    if private_path(root, "state.json").exists():
        raise FreeCloudError("workspace_already_exists_use_new_private_directory")
    source_text = Path(source).read_text(encoding="utf-8")
    program_text = Path(program).read_text(encoding="utf-8")
    blocks, points = parse_source(source_text), parse_program(program_text)
    mapping = map_topics(blocks, points)
    if not 100 <= wpm <= 190:
        raise FreeCloudError("invalid_speech_rate")
    episode = {
        "source": source_text,
        "program": program_text,
        "blocks": blocks,
        "points": points,
        "mapping": mapping,
        "segments": documentary_dialogue(blocks, points, mapping),
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


def approve(directory, *, reviewed=False, reviewer="workspace-reviewer"):
    root = private_root(directory)
    state = load(root, "state.json")
    if not reviewed:
        raise FreeCloudError("explicit_review_required_before_synthesis")
    original = load(root, f"revisions/{state['prepared_revision']}.json")
    if revision_hash(original) != state["prepared_revision"]:
        raise FreeCloudError("prepared_snapshot_modified")
    proposal = load(root, "review.json")
    for key in ("source", "program", "blocks", "points"):
        if proposal.get(key) != original[key]:
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
        )
    ):
        raise FreeCloudError("review_has_unapproved_edits")
    if voice_a == voice_b or voice_a not in VOICES or voice_b not in VOICES:
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
            voice = voice_map[segment["speaker"]]
            text = spoken_text(segment["text"], ep["pronunciation"])
            cache_key = digest(
                {
                    "spoken": text,
                    "voice": identities[segment["speaker"]],
                    "wpm": ep["wpm"],
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
                with private_engine_log(root):
                    audio = engines.synthesize(text, voice, ep["wpm"])
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
                with private_engine_log(root):
                    transcript = recognizer.transcribe(wav)
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
                "transcript": transcript,
                "verification": verification,
            }
            paths.append(wav)
            save(root, f"{prefix}/segments.json", records)
        import tempfile

        with tempfile.TemporaryDirectory(dir=root) as temporary:
            output = Path(temporary) / "chapter.mp3"
            with private_engine_log(root):
                seconds = join_audio(paths, output)
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
                seconds = join_audio(audio_paths, output)
            write_bytes(root, f"{deliver}/podcast.mp3", output.read_bytes())
        report["duration_seconds"] = seconds
        save(root, f"{deliver}/coverage-audio.json", report)
        export_script(root, f"{deliver}/script.md", ep)
        save(root, f"{deliver}/script.json", ep)
        for chapter in chapters:
            write_bytes(
                root,
                f"{deliver}/{chapter['id']}.mp3",
                private_path(root, f"{prefix}/{chapter['id']}.mp3").read_bytes(),
            )
        # Explicit allowlist: never zip source paths, caches, model files, or native engine logs.
        zip_path = private_path(root, "academic-audio.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for name in [
                "podcast.mp3",
                "script.md",
                "script.json",
                "coverage-audio.json",
            ] + [f"{c['id']}.mp3" for c in chapters]:
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


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    model = sub.add_parser("models")
    model.add_argument("--directory", required=True)
    model.add_argument("--piper", action="store_true")
    model.add_argument("--asr", action="store_true")
    prep = sub.add_parser("prepare")
    prep.add_argument("--source", required=True)
    prep.add_argument("--program", required=True)
    prep.add_argument("--workdir", required=True)
    prep.add_argument("--max-words", type=int, default=1200)
    prep.add_argument("--wpm", type=int, default=140)
    prep.add_argument("--target-minutes", type=int, default=10)
    prep.add_argument("--public-demo", action="store_true")
    approval = sub.add_parser("approve")
    approval.add_argument("--workdir", required=True)
    approval.add_argument("--reviewed", action="store_true")
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
    args = vars(p.parse_args())
    command = args.pop("command")
    try:
        if command == "models":
            args["directory"] = private_root(args["directory"])
            result = {"stage": "models_ready", "assets": len(setup_models(**args))}
        elif command == "prepare":
            args["directory"] = args.pop("workdir")
            result = prepare(**args)
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
        code = str(exc) if isinstance(exc, FreeCloudError) else type(exc).__name__
        print(json.dumps({"stage": "blocked", "code": code}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
