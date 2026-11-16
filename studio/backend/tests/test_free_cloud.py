import json
import os
from pathlib import Path
import zipfile
import pytest
from aas import free_cloud as free
from aas.tts import LocalTTS
from aas.quality import assess_transcript


@pytest.fixture(autouse=True)
def isolated_runner_context(monkeypatch):
    # Unit tests use their own synthetic files. Test the production Actions guard
    # explicitly below instead of accidentally inheriting the CI runner context.
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY_VISIBILITY", raising=False)


@pytest.fixture
def private_job(tmp_path, body):
    source = tmp_path / "unit.md"
    source.write_text(body["source"])
    program = tmp_path / "program.md"
    program.write_text(body["program"])
    directory = tmp_path / "private"
    free.prepare(source, program, directory, max_words=100)
    return directory


def test_chapters_preserve_every_source_and_segment(private_job):
    ep = free.load(private_job, "review.json")
    chapters = free.load(private_job, "plan.json")
    assert len(chapters) == 2
    ids = [sid for c in chapters for sid in c["segment_ids"]]
    assert ids == [s["id"] for s in ep["segments"]]
    assert {b for c in chapters for b in c["source_ids"]} == {
        b["id"] for b in ep["blocks"]
    }
    assert len(ids) == len(set(ids))


def test_no_synthesis_without_review(private_job, monkeypatch):
    monkeypatch.setattr(
        free,
        "OpenVoices",
        lambda *a, **k: pytest.fail("Must not load/synthesize before approval"),
    )
    with pytest.raises(free.FreeCloudError, match="explicit_review"):
        free.render(private_job, "unused")


def test_source_change_or_article_substitution_cannot_be_approved(private_job):
    ep = free.load(private_job, "review.json")
    original = ep["source"]
    ep["source"] = "Un reemplazo malicioso."
    free.save(private_job, "review.json", ep)
    with pytest.raises(free.FreeCloudError, match="immutable_source"):
        free.approve(private_job, reviewed=True)
    ep["source"] = original
    for s in ep["segments"]:
        if s["kind"] == "source":
            s["text"] = s["text"].replace("259", "999")
            break
    free.save(private_job, "review.json", ep)
    with pytest.raises(free.FreeCloudError, match="substantial_audit"):
        free.approve(private_job, reviewed=True)


def test_repository_and_symlink_outputs_are_rejected(tmp_path):
    with pytest.raises(free.FreeCloudError, match="outside_repository"):
        free.private_root(free.REPO / "studio/data/private")
    private = free.private_root(tmp_path / "private")
    (private / "leak").symlink_to(free.REPO, target_is_directory=True)
    with pytest.raises(free.FreeCloudError):
        free.write_bytes(private, "leak/private-note.md", b"do not leak")


def test_private_inputs_cannot_enter_public_github_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY_VISIBILITY", "public")
    s = tmp_path / "s.md"
    s.write_text("PRIVATE NOTES")
    p = tmp_path / "p.md"
    p.write_text("PRIVATE PROGRAM")
    with pytest.raises(free.FreeCloudError, match="private_material_forbidden"):
        free.prepare(s, p, tmp_path / "private")
    with pytest.raises(free.FreeCloudError, match="public_demo_must_match"):
        free.prepare(s, p, tmp_path / "private", public_demo=True)


def test_unknown_actions_visibility_and_private_quota_fail_closed(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("GITHUB_REPOSITORY_VISIBILITY", raising=False)
    with pytest.raises(free.FreeCloudError):
        free.actions_privacy_guard()
    monkeypatch.setenv("GITHUB_REPOSITORY_VISIBILITY", "private")
    with pytest.raises(free.FreeCloudError, match="zero_spending_limit"):
        free.actions_privacy_guard()


def test_public_actions_accepts_only_exact_committed_public_fixture(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY_VISIBILITY", "public")
    result = free.prepare(
        free.REPO / "studio/examples/unidad.md",
        free.REPO / "studio/examples/programa.md",
        tmp_path / "public-demo",
        public_demo=True,
    )
    assert result["audit_passed"] and result["coverage_percent"] == 100


class CIOnlySpeechEngine:
    """Real speech for fast CI pipeline tests; never represents Kokoro quality."""

    version = "test-only-espeak"

    def __init__(self, *a, **k):
        self.tts = LocalTTS()

    def identity(self, voice):
        return {"voice": voice, "test_engine": "espeak"}

    def synthesize(self, text, voice, wpm):
        return self.tts.synthesize(
            text, "es" if voice.endswith("dora") else "es+f3", wpm
        )


def test_partial_chapters_resume_and_regenerate_only_defective_segment(
    private_job, monkeypatch
):
    monkeypatch.setattr(free, "OpenVoices", CIOnlySpeechEngine)
    free.approve(private_job, reviewed=True)
    first = free.render(private_job, "unused", chapter_ids=["c001"])
    assert not first["complete"]
    assert not (private_job / "academic-audio.zip").exists()
    second = free.render(private_job, "unused", chapter_ids=["c002"])
    assert second["complete"]
    with zipfile.ZipFile(private_job / "academic-audio.zip") as z:
        assert set(z.namelist()) == {
            "podcast.mp3",
            "script.md",
            "script.json",
            "coverage-audio.json",
            "c001.mp3",
            "c002.mp3",
        }
        assert len(z.read("podcast.mp3")) > 10000
    last = free.render(private_job, "unused", chapter_ids=["c001"], regenerate=["s2"])
    assert (
        last["new_segments"] == 1 and last["reused_segments"] >= 1 and last["complete"]
    )
    assert (private_job / "academic-audio.zip").stat().st_mode & 0o777 == 0o600


def test_review_edit_invalidates_render_and_reapproval_archives_outputs(
    private_job, monkeypatch
):
    monkeypatch.setattr(free, "OpenVoices", CIOnlySpeechEngine)
    free.approve(private_job, reviewed=True)
    free.render(private_job, "unused")
    ep = free.load(private_job, "review.json")
    ep["pronunciation"]["CCCN"] = "Código Civil y Comercial"
    free.save(private_job, "review.json", ep)
    with pytest.raises(free.FreeCloudError, match="unapproved_edits"):
        free.render(private_job, "unused")
    free.approve(private_job, reviewed=True)
    assert not (private_job / "academic-audio.zip").exists()
    assert list((private_job / "exports").glob("*/academic-audio.zip"))


def test_free_renderer_rejects_paid_provider_and_unknown_ids(private_job, monkeypatch):
    free.approve(private_job, reviewed=True)
    with pytest.raises(free.FreeCloudError, match="open_voices"):
        free.render(private_job, "unused", voice_a="gemini:Kore")
    with pytest.raises(free.FreeCloudError, match="unknown_chapter"):
        free.render(private_job, "unused", chapter_ids=["not-existing"])


def test_quality_checks_are_conservative():
    assert assess_transcript(
        "No se permite, salvo excepción.", "No se permite salvo excepción"
    )["passed"]
    assert not assess_transcript("No se permite.", "Se permite.")["passed"]
    assert not assess_transcript("Artículo 259.", "Artículo 299.")["passed"]


def test_real_kokoro_two_voices_cpu_when_weights_configured(tmp_path):
    models = os.getenv("AAS_OPEN_MODEL_DIR")
    if not models:
        pytest.skip(
            "Optional real model test: set AAS_OPEN_MODEL_DIR; never pretend a skipped test passed"
        )
    from aas.open_models import OpenVoices
    from aas.quality import acoustic_metrics

    engine = OpenVoices(models, threads=2)
    for voice in ["kokoro:ef_dora", "kokoro:em_alex"]:
        path = tmp_path / (voice.split(":")[1] + ".wav")
        path.write_bytes(
            engine.synthesize(
                "El silencio no implica consentimiento, salvo excepción legal.", voice
            )
        )
        metrics = acoustic_metrics(path)
        assert (
            metrics["seconds"] > 1
            and metrics["finite"]
            and metrics["clipped_fraction"] < 0.01
        )


def test_grouped_source_turns_keep_all_literals_and_parent_identity():
    from aas.core import parse_source, parse_program, map_topics, audit

    source = "# Unidad\n## Concepto\nUna primera regla.\nOtra regla con su excepción.\n## Efectos\nLa consecuencia se conserva.\n"
    blocks = parse_source(source)
    points = parse_program("- Concepto\n- Efectos")
    mapping = map_topics(blocks, points)
    segments = free.documentary_dialogue(blocks, points, mapping)
    sources = [s for s in segments if s["kind"] == "source"]
    assert sources[0]["source_ids"] == ["b1", "b2"]
    assert sources[0]["text"] == "Una primera regla.\nOtra regla con su excepción."
    ep = {
        "source": source,
        "program": "- Concepto\n- Efectos",
        "blocks": blocks,
        "points": points,
        "mapping": mapping,
        "segments": segments,
    }
    assert audit(ep)["passed"]


def test_private_bundle_round_trip_is_downloaded_and_checksum_verified(
    private_job, monkeypatch
):
    monkeypatch.setattr(free, "OpenVoices", CIOnlySpeechEngine)
    free.approve(private_job, reviewed=True)
    free.render(private_job, "unused")
    from aas.delivery import download_bundle

    result = download_bundle(private_job)
    assert result["download_verified"] and result["mp3_bytes"] > 10000
    assert (private_job / "downloads/podcast.mp3").read_bytes() == (
        private_job / "deliverables/podcast.mp3"
    ).read_bytes()


def test_native_and_python_engine_diagnostics_remain_private(tmp_path, capfd):
    import ctypes

    root = free.private_root(tmp_path / "private")
    secret = b"PRIVATE TEST MATERIAL MUST NOT ENTER PUBLIC LOGS"
    with free.private_engine_log(root):
        print(secret.decode())
        ctypes.CDLL(None).printf(b"%s\n", secret)
        os.write(2, secret + b"\n")
    captured = capfd.readouterr()
    assert secret.decode() not in captured.out + captured.err
    assert secret in (root / "engine-private.log").read_bytes()


def test_public_demo_flag_does_not_allow_private_spoken_edits_or_unknown_quota(
    tmp_path, monkeypatch
):
    directory = tmp_path / "public-demo"
    free.prepare(
        free.REPO / "studio/examples/unidad.md",
        free.REPO / "studio/examples/programa.md",
        directory,
        public_demo=True,
    )
    episode = free.load(directory, "review.json")
    episode["pronunciation"]["CCCN"] = "PRIVATE SPOKEN CONTENT"
    free.save(directory, "review.json", episode)
    free.approve(directory, reviewed=True)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY_VISIBILITY", "public")
    with pytest.raises(free.FreeCloudError, match="demo_edits_forbidden"):
        free.render(directory, "unused")
    monkeypatch.setenv("GITHUB_REPOSITORY_VISIBILITY", "private")
    with pytest.raises(free.FreeCloudError, match="zero_spending_limit"):
        free.render(directory, "unused")
