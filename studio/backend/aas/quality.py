"""Traceable comparison; mismatches never establish an error in the synthesizer alone."""

import re
from difflib import SequenceMatcher
from .normalization import canonicalize, plain, MARKERS

QUALITY_VERSION = "es-legal-v2.2"


def words(text):
    return re.findall(r"\w+", plain(text))


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        next_row = [i]
        for j, y in enumerate(b, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j - 1] + (x != y)))
        row = next_row
    return row[-1] / max(1, len(a))


def assess_transcript(expected, actual):
    x, y = canonicalize(expected), canonicalize(actual)
    a, b = x["tokens"], y["tokens"]
    raw_wer = distance(words(expected), words(actual))
    wer = distance(a, b)
    differences = []
    marker_edits = False
    for op, i, j, k, l in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        changed = a[i:j] + b[k:l]
        if any(token in MARKERS for token in changed):
            marker_edits = True
        differences.append(
            {"operation": op, "expected_tokens": a[i:j], "recognized_tokens": b[k:l]}
        )
    numeric = x["numbers"] == y["numbers"] and not (
        x["ambiguous_numbers"] or y["ambiguous_numbers"]
    )
    neg = x["markers"] == y["markers"] and not marker_edits
    terms = x["legal_terms"] == y["legal_terms"]
    articles = x["articles"] == y["articles"]
    units = x["units"] == y["units"]
    substantial = not (numeric and neg and terms and articles and units)
    # A small WER is useful for ranking, never a license to silently accept missing words.
    passed = bool(a and b) and a == b and not substantial
    return {
        "passed": passed,
        "status": "match_after_normalization"
        if passed
        else "substantial_difference"
        if substantial
        else "residual_difference",
        "word_error_rate": round(wer, 4),
        "raw_word_error_rate": round(raw_wer, 4),
        "numbers_match": numeric,
        "negations_match": neg,
        "article_references_match": articles,
        "legal_terms_match": terms,
        "units_match": units,
        "substantial_difference": substantial,
        "differences": differences,
        "normalization": {
            "version": QUALITY_VERSION,
            "expected": x["normalizations"],
            "recognized": y["normalizations"],
        },
        "critical_values": {
            "expected": {
                k: x[k]
                for k in ("numbers", "articles", "markers", "legal_terms", "units")
            },
            "recognized": {
                k: y[k]
                for k in ("numbers", "articles", "markers", "legal_terms", "units")
            },
        },
        "method": "offline ASR versus script; value/order/sign/units/articles/negations/legal terms checked explicitly",
        "limitations": "No listening certification. A discrepancy can come from ASR or TTS. Residual word changes require review even below a WER threshold.",
    }


def acoustic_metrics(path):
    import numpy as np
    import soundfile as sf

    samples, rate = sf.read(path, dtype="float32")
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    return {
        "seconds": round(len(samples) / rate, 3),
        "sample_rate": rate,
        "finite": bool(np.isfinite(samples).all()),
        "peak": round(float(np.max(np.abs(samples))), 5),
        "clipped_fraction": round(float(np.mean(np.abs(samples) >= 0.999)), 6),
        "rms_dbfs": round(
            float(20 * np.log10(max(1e-12, np.sqrt(np.mean(samples * samples))))), 2
        ),
        "note": "Signal integrity only; not an accent or naturalness score.",
    }
