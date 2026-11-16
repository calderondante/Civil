"""Public fixed corpus only. Outputs stay private; no subjective listening score."""

import argparse
import json
import time
from aas.free_cloud import private_root, private_engine_log, write_bytes, save
from aas.open_models import OpenVoices, OpenASR
from aas.quality import assess_transcript, acoustic_metrics

CORPUS = "El acto jurídico es voluntario y lícito. El silencio no implica consentimiento, salvo las excepciones que establece la ley. Vos tenés que distinguir la regla de su excepción."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--experimental-piper", action="store_true")
    args = parser.parse_args()
    root = private_root(args.output)
    with private_engine_log(root):
        engine = OpenVoices(args.models)
        asr = OpenASR(args.models)
    voices = ["kokoro:ef_dora", "kokoro:em_alex", "kokoro:em_santa"]
    if args.experimental_piper:
        voices.append("piper:daniela")
    rows = []
    for voice in voices:
        start = time.monotonic()
        with private_engine_log(root):
            audio = engine.synthesize(CORPUS, voice)
        elapsed = time.monotonic() - start
        path = write_bytes(root, voice.replace(":", "-") + ".wav", audio)
        with private_engine_log(root):
            transcript = asr.transcribe(path)
        rows.append(
            {
                "voice": voice,
                "transcript": transcript,
                "assessment": assess_transcript(CORPUS, transcript),
                "signal": acoustic_metrics(path),
                "synthesis_seconds": elapsed,
            }
        )
    save(
        root,
        "comparison.json",
        {
            "public_test_text": CORPUS,
            "results": rows,
            "subjective_listening": "not performed; no native accent certification",
        },
    )
    print(json.dumps({"voices_tested": len(rows), "quality_file": "comparison.json"}))


if __name__ == "__main__":
    main()
