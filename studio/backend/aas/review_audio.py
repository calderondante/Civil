"""Reassess existing audio without resynthesis or a claim of human listening."""

import json
from .free_cloud import (
    private_root,
    private_path,
    private_engine_log,
    save,
    write_bytes,
)
from .quality import assess_transcript, QUALITY_VERSION
from .open_models import OpenASR, file_hash


def review_existing(directory, models, segment_ids=None):
    root = private_root(directory)
    latest = json.loads(private_path(root, "latest-run.json").read_text())
    report = json.loads(
        private_path(root, latest["prefix"] + "/report.json").read_text()
    )
    selected = (
        [r for r in report["segments"] if r["segment_id"] in segment_ids]
        if segment_ids
        else [r for r in report["segments"] if not r["verification"]["passed"]]
    )
    with private_engine_log(root):
        second = OpenASR(models, threads=2, size="small")
    rows = []
    for record in selected:
        wav = private_path(root, record["cache_file"])
        if file_hash(wav) != record["sha256"]:
            raise ValueError("original_audio_changed")
        expected = record["spoken_text"]
        primary = assess_transcript(expected, record["transcript"] or "")
        cache = "audio-review/asr-small-" + record["sha256"] + "-silence-v1.json"
        if private_path(root, cache).exists():
            transcript = json.loads(private_path(root, cache).read_text())["transcript"]
        else:
            with private_engine_log(root):
                transcript = second.transcribe(wav)
            save(root, cache, {"transcript": transcript})
        comparison = assess_transcript(expected, transcript)
        status = (
            "representation_only"
            if primary["passed"]
            else "likely_recognizer_error"
            if comparison["passed"]
            else "pending_audio_review"
        )
        clip = "audio-review/clips/" + record["segment_id"] + ".wav"
        write_bytes(root, clip, wav.read_bytes())
        rows.append(
            {
                "segment_id": record["segment_id"],
                "source_ids": record["source_ids"],
                "audio_sha256": record["sha256"],
                "clip": clip,
                "expected": expected,
                "original_asr": record["transcript"],
                "second_asr": transcript,
                "primary_comparison": primary,
                "second_comparison": comparison,
                "classification": status,
                "confirmed_tts_error": False,
                "human_listening": False,
                "regeneration": "not performed without evidence of a synthesis defect",
            }
        )
    result = {
        "normalizer": QUALITY_VERSION,
        "second_recognizer": "Whisper-small int8 CPU, no reference prompt, measured-silence windows",
        "rows": rows,
        "counts": {
            key: sum(r["classification"] == key for r in rows)
            for key in (
                "representation_only",
                "likely_recognizer_error",
                "pending_audio_review",
            )
        },
        "verified_complete": False,
        "note": "Two recognitions are evidence, not human listening. Unresolved items remain open; no blanket regeneration.",
    }
    save(root, "audio-review/review.json", result)
    html = [
        '<!doctype html><html lang="es"><meta charset="utf-8"><title>Revisión privada</title><body><h1>Comparación de audio</h1><p>Sin escucha humana certificada. No publicar este directorio.</p>'
    ]
    import html as h

    for r in rows:
        html.append(
            f'<section><h2>{h.escape(r["segment_id"])} · {r["classification"]}</h2><audio controls src="clips/{r["segment_id"]}.wav"></audio><h3>Guion</h3><p>{h.escape(r["expected"])}</p><h3>Whisper base</h3><p>{h.escape(r["original_asr"] or "")}</p><h3>Whisper small</h3><p>{h.escape(r["second_asr"])}</p></section>'
        )
    write_bytes(
        root, "audio-review/index.html", ("".join(html) + "</body></html>").encode()
    )
    return result
