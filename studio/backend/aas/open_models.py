"""Pinned public weights, CPU-only inference; never call a commercial endpoint."""

import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

ASSETS = {
    "kokoro-v1.0.onnx": (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx",
        "beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a",
    ),
    "voices-v1.0.bin": (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin",
        "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
    ),
    "vits-piper-es_AR-daniela-high.tar.bz2": (
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-es_AR-daniela-high.tar.bz2",
        "71cbf6b7f646ab74f3c51336151abef41e6c54467ac929ffdb19ed706a07dd7b",
    ),
    "sherpa-onnx-whisper-base.tar.bz2": (
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-base.tar.bz2",
        "911b2083efd7c0dca2ac3b358b75222660dc09fb716d64fbfc417ba6c99ff3de",
    ),
}


def file_hash(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def setup_models(directory, *, piper=False, asr=False):
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    names = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]
    if piper:
        names.append("vits-piper-es_AR-daniela-high.tar.bz2")
    if asr:
        names.append("sherpa-onnx-whisper-base.tar.bz2")
    manifest = {}
    for name in names:
        url, expected = ASSETS[name]
        dest = root / name
        if not dest.exists():
            temp = dest.with_suffix(dest.suffix + ".part")
            try:
                with (
                    urllib.request.urlopen(url, timeout=120) as response,
                    open(temp, "wb") as out,
                ):
                    while chunk := response.read(1024 * 1024):
                        out.write(chunk)
                if file_hash(temp) != expected:
                    raise ValueError("model_checksum_mismatch")
                temp.replace(dest)
            finally:
                temp.unlink(missing_ok=True)
        if file_hash(dest) != expected:
            raise ValueError("model_checksum_mismatch")
        if name.endswith(".tar.bz2"):
            # Reextract from the verified archive to avoid trusting modified unpacked files.
            with tarfile.open(dest) as archive:
                archive.extractall(root, filter="data")
        manifest[name] = {"url": url, "sha256": expected, "bytes": dest.stat().st_size}
    (root / "model-provenance.json").write_text(json.dumps(manifest, indent=2))
    return manifest


class OpenVoices:
    """Two distinct neural voices with explicit CPU providers; no automatic downloads."""

    def __init__(self, directory, *, threads=2):
        self.root = Path(directory).resolve()
        self.threads = max(1, min(int(threads), 4))
        self.kokoro = self.piper = None
        self._validate("kokoro-v1.0.onnx")
        self._validate("voices-v1.0.bin")
        self.version = "kokoro-onnx-0.6.1:models-v1.1:piper-sherpa-2.0.1:cpu"

    def _validate(self, name):
        if (
            not (self.root / name).is_file()
            or file_hash(self.root / name) != ASSETS[name][1]
        ):
            raise ValueError("missing_or_modified_model_run_models_setup")

    def identity(self, voice):
        if voice in ("kokoro:ef_dora", "kokoro:em_alex", "kokoro:em_santa"):
            return {
                "engine": "kokoro-onnx",
                "voice": voice,
                "model_sha256": ASSETS["kokoro-v1.0.onnx"][1],
                "voices_sha256": ASSETS["voices-v1.0.bin"][1],
                "lang": "es",
                "device": "CPU",
            }
        if voice == "piper:daniela":
            self._validate("vits-piper-es_AR-daniela-high.tar.bz2")
            return {
                "engine": "piper-vits/sherpa-onnx",
                "voice": voice,
                "archive_sha256": ASSETS["vits-piper-es_AR-daniela-high.tar.bz2"][1],
                "locale": "es_AR (model-card declaration)",
                "device": "CPU",
            }
        raise ValueError("only_reviewed_open_spanish_voices_allowed")

    def synthesize(self, text, voice, wpm=140):
        import numpy as np
        import soundfile as sf

        self.identity(voice)
        speed = max(0.65, min(1.35, wpm / 140))
        if voice.startswith("kokoro:"):
            if self.kokoro is None:
                import onnxruntime as rt

                rt.disable_telemetry_events()
                from kokoro_onnx import Kokoro

                opts = rt.SessionOptions()
                opts.intra_op_num_threads = self.threads
                opts.inter_op_num_threads = 1
                session = rt.InferenceSession(
                    str(self.root / "kokoro-v1.0.onnx"),
                    sess_options=opts,
                    providers=["CPUExecutionProvider"],
                )
                self.kokoro = Kokoro.from_session(
                    session, str(self.root / "voices-v1.0.bin")
                )
            samples, rate = self.kokoro.create(
                text, voice=voice.split(":")[1], lang="es", speed=speed
            )
        else:
            if self.piper is None:
                import sherpa_onnx as so

                directory = self.root / "vits-piper-es_AR-daniela-high"
                # Verify the unpacked model/configuration as well as its original archive.
                verify_extraction(
                    self.root / "vits-piper-es_AR-daniela-high.tar.bz2", self.root
                )
                vits = so.OfflineTtsVitsModelConfig(
                    model=str(directory / "es_AR-daniela-high.onnx"),
                    tokens=str(directory / "tokens.txt"),
                    data_dir=str(directory / "espeak-ng-data"),
                )
                self.piper = so.OfflineTts(
                    so.OfflineTtsConfig(
                        model=so.OfflineTtsModelConfig(
                            vits=vits,
                            num_threads=self.threads,
                            provider="cpu",
                            debug=False,
                        )
                    )
                )
            # sherpa-onnx 2.x expects frontend phonemes for these older Piper exports.
            from kokoro_onnx.tokenizer import Tokenizer
            from phonemizer.backend import EspeakBackend

            Tokenizer()  # Configure the bundled eSpeak library AND its data path.
            phonemes = EspeakBackend(
                "es", preserve_punctuation=True, with_stress=True
            ).phonemize([text], strip=True)
            import sherpa_onnx as so

            generation = so.GenerationConfig()
            generation.sid = 0
            generation.speed = speed
            generation.phoneme_codepoints = [
                [ord(ch) for ch in sentence] for sentence in phonemes
            ]
            audio = self.piper.generate(text, generation)
            samples, rate = audio.samples, audio.sample_rate
        samples = np.asarray(samples, dtype=np.float32)
        if (
            samples.size < rate * 0.05
            or not np.isfinite(samples).all()
            or float(np.max(np.abs(samples))) < 1e-5
        ):
            raise ValueError("invalid_or_silent_audio")
        out = io.BytesIO()
        sf.write(out, samples, rate, format="WAV", subtype="PCM_16")
        return out.getvalue()


def verify_extraction(archive, root):
    with tarfile.open(archive) as tf:
        for item in tf:
            if not item.isfile():
                continue
            path = (Path(root) / item.name).resolve()
            if not path.is_relative_to(Path(root).resolve()) or not path.is_file():
                raise ValueError("model_extraction_invalid")
            with tf.extractfile(item) as f:
                expected = hashlib.file_digest(f, "sha256").hexdigest()
            if file_hash(path) != expected:
                raise ValueError("model_extraction_modified")


class OpenASR:
    def __init__(self, directory, threads=2):
        import sherpa_onnx as so

        root = Path(directory).resolve()
        name = "sherpa-onnx-whisper-base.tar.bz2"
        if file_hash(root / name) != ASSETS[name][1]:
            raise ValueError("asr_checksum_mismatch")
        verify_extraction(root / name, root)
        p = root / "sherpa-onnx-whisper-base"
        self.recognizer = so.OfflineRecognizer.from_whisper(
            encoder=str(p / "base-encoder.int8.onnx"),
            decoder=str(p / "base-decoder.int8.onnx"),
            tokens=str(p / "base-tokens.txt"),
            language="es",
            task="transcribe",
            num_threads=threads,
            provider="cpu",
        )

    def transcribe(self, path):
        import subprocess
        import numpy as np

        raw = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(path),
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "f32le",
                "-",
            ],
            check=True,
            capture_output=True,
        ).stdout
        samples = np.frombuffer(raw, dtype="<f4")
        if len(samples) > 16000 * 29:
            # Independent windows, never silently truncate material longer than Whisper's context.
            pieces = []
            for start in range(0, len(samples), 16000 * 25):
                pieces.append(self._decode(samples[start : start + 16000 * 25]))
            return " ".join(pieces)
        return self._decode(samples)

    def _decode(self, samples):
        stream = self.recognizer.create_stream()
        stream.accept_waveform(16000, samples)
        self.recognizer.decode_stream(stream)
        return stream.result.text.strip()
