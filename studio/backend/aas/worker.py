"""Independent durable worker. Run on a cloud container, never a Vercel request."""
import copy
import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from sqlalchemy import select, update, or_, and_
from .db import Job, Session, init_db
from .core import audit, revision_hash, digest, compare_transcript
from .storage import Storage
from .tts import provider, spoken_text, join_audio, transcribe, probe

log = logging.getLogger('aas.worker')


def claim():
    now = time.time()
    with Session.begin() as s:
        candidates = s.scalars(select(Job).where(or_(Job.status == 'queued', and_(Job.status == 'running', Job.lease_until < now))).order_by(Job.id)).all()
        for job in candidates:
            token = str(uuid.uuid4())
            if job.attempts >= 3:
                s.execute(update(Job).where(Job.id == job.id, Job.lease_until < now).values(status='failed', error='Se agotaron tres intentos; revisá el worker.'))
                continue
            r = s.execute(update(Job).where(Job.id == job.id, Job.status == job.status, Job.lease_until == job.lease_until).values(
                status='running', attempts=job.attempts+1, lease_until=now+1800, lease_token=token))
            if r.rowcount:
                return job.id, token
    return None


def heartbeat(jid, token, result):
    with Session.begin() as s:
        r = s.execute(update(Job).where(Job.id == jid, Job.status == 'running', Job.lease_token == token).values(lease_until=time.time()+1800, result=result))
        if not r.rowcount:
            raise RuntimeError('Se perdió el lease del trabajo.')


def execute(jid, token):
    with Session() as s:
        job = s.get(Job, jid)
        payload = copy.deepcopy(job.payload)
    episode = payload['episode']
    if payload.get('kind') == 'script':
        from .writing import enrich
        candidate = enrich(episode, payload.get('depth', 'explicativo'))
        return {'kind': 'script', 'candidate': candidate, 'audit': audit(candidate), 'base_revision': payload['revision']}
    if not audit(episode)['passed'] or episode.get('approved_hash') != revision_hash(episode):
        raise ValueError('La versión no tiene auditoría y aprobación vigentes.')
    engine = provider(payload['provider'])
    storage = Storage()
    records, paths = [], []
    with tempfile.TemporaryDirectory(prefix='aas-') as tmp:
        folder = Path(tmp)
        for seg in episode['segments']:
            spoken = spoken_text(seg['text'], episode['pronunciation'])
            voice = payload['voices'][seg['speaker']]
            key = digest({'text': spoken, 'voice': voice, 'wpm': episode['wpm'], 'provider': payload['provider'], 'version': engine.version})
            cache_key = f'cache/{key}.wav'
            regenerate = seg['id'] in payload.get('regenerate', [])
            cached = False
            if not regenerate:
                try:
                    audio = storage.get(cache_key); cached = True
                except FileNotFoundError:
                    pass
                except Exception as exc:
                    import httpx
                    if not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code not in (400, 404):
                        raise
            if not cached:
                audio = engine.synthesize(spoken, voice, episode['wpm'])
                storage.put(cache_key, audio, 'audio/wav')
            path = folder / f'{len(paths)}.wav'; path.write_bytes(audio); paths.append(path)
            duration = probe(path)
            transcript = transcribe(path)
            verification = compare_transcript(spoken, transcript) if transcript is not None else {'passed': None, 'reason': 'ASR no configurado; audio de revisión sin verificación automática.'}
            records.append({'segment_id': seg['id'], 'cache_key': cache_key, 'cached': cached,
                            'voice': voice, 'spoken_text': spoken, 'duration_seconds': duration,
                            'transcript': transcript, 'verification': verification})
            heartbeat(jid, token, {'completed_segments': len(records), 'total_segments': len(episode['segments'])})
        output = folder / 'episode.mp3'
        duration = join_audio(paths, output)
        all_verified = all(r['verification']['passed'] is True for r in records)
        status = 'verified' if all_verified else ('mismatch' if any(r['verification']['passed'] is False for r in records) else 'unverified')
        # Artifacts retain immutable revision, source audit, actual speech text, timings, and ASR result.
        report = {'job_id': jid, 'revision_hash': revision_hash(episode), 'provider': payload['provider'],
                  'model': engine.version, 'audio_status': status, 'duration_seconds': duration,
                  'duration_on_target': .8*episode['target_minutes']*60 <= duration <= 1.2*episode['target_minutes']*60,
                  'audit': audit(episode), 'segments': records}
        prefix = f'episodes/{job.episode_id}/{jid}'
        storage.put(prefix+'/audio.mp3', output.read_bytes(), 'audio/mpeg')
        storage.put(prefix+'/report.json', json.dumps(report, ensure_ascii=False, indent=2).encode(), 'application/json')
        script = '\n\n'.join(f'[{s["id"]}] {s["speaker"]} ({s["kind"]}; fuente: {", ".join(s["source_ids"])}):\n{s["text"]}' for s in episode['segments'])
        storage.put(prefix+'/script.md', script.encode(), 'text/markdown')
        asr = '\n\n'.join(f'{r["segment_id"]}: {r["transcript"] or "[ASR pendiente]"}' for r in records)
        storage.put(prefix+'/transcript.txt', asr.encode(), 'text/plain')
        report['artifact_prefix'] = prefix
        return report


def run_once():
    claimed = claim()
    if not claimed:
        return False
    jid, token = claimed
    try:
        result = execute(jid, token)
        state, error = 'done', ''
    except Exception as exc:
        # Never persist exception URLs/headers: they can include API keys.
        log.error('Job %s failed (%s)', jid, type(exc).__name__)
        result, state = {}, 'failed'
        error = str(exc)[:400] if isinstance(exc, (ValueError, FileNotFoundError)) else f'{type(exc).__name__}: consultá configuración, red y logs del proveedor; no se guardan credenciales.'
    with Session.begin() as s:
        s.execute(update(Job).where(Job.id == jid, Job.lease_token == token).values(status=state, result=result, error=error, lease_until=0))
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    while True:
        if not run_once():
            time.sleep(2)

if __name__ == '__main__':
    main()
