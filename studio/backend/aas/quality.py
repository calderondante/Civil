"""Objective CPU checks. No simulated listening score or certification of accent."""

import re
import unicodedata


def words(text):
    text = "".join(
        c
        for c in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(c)
    )
    return re.findall(r"\w+", text)


def assess_transcript(expected, actual):
    a, b = words(expected), words(actual)
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        next_row = [i]
        for j, y in enumerate(b, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j - 1] + (x != y)))
        row = next_row
    wer = row[-1] / max(1, len(a))
    numbers_a = re.findall(r"\b\d+\b", expected)
    numbers_b = re.findall(r"\b\d+\b", actual)
    neg_a = [x for x in a if x in ("no", "nunca", "salvo", "excepto")]
    neg_b = [x for x in b if x in ("no", "nunca", "salvo", "excepto")]
    return {
        "passed": wer <= 0.12 and numbers_a == numbers_b and neg_a == neg_b,
        "word_error_rate": round(wer, 4),
        "numbers_match": numbers_a == numbers_b,
        "negations_match": neg_a == neg_b,
        "method": "independent Whisper-base CPU, punctuation/diacritics normalized; no reference prompt",
        "limitations": "ASR error is not proof of TTS error; number words versus digits can cause a conservative rejection.",
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
        "note": "Signal integrity only; not a MOS/naturalness or Argentine-accent score.",
    }
