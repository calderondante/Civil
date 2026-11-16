import copy
import hmac
import json
import os
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .db import Episode, Revision, Job, Session, init_db
from .core import parse_source, parse_program, map_topics, draft, audit, revision_hash, repair
from .storage import Storage


@asynccontextmanager
async def lifespan(app):
    if os.getenv('STUDIO_ENV') == 'production' and not os.getenv('API_BEARER_TOKEN'):
        raise RuntimeError('API_BEARER_TOKEN es obligatorio en producción.')
    init_db()
    yield


def authorize(authorization: str = Header(default='')):
    token = os.getenv('API_BEARER_TOKEN')
    if token and not hmac.compare_digest(authorization, f'Bearer {token}'):
        raise HTTPException(401, 'Autenticación requerida.')
    if not token and os.getenv('STUDIO_ENV') == 'production':
        raise HTTPException(503, 'Servicio sin configurar.')

app = FastAPI(title='Academic Audio Studio', version='0.1.0', lifespan=lifespan, dependencies=[Depends(authorize)])

@app.exception_handler(IntegrityError)
async def conflict_handler(request, exc):
    return JSONResponse({'detail':'Ya existe un trabajo activo o una versión concurrente.'}, status_code=409)

@app.middleware('http')
async def body_limit(request: Request, call_next):
    if request.method in ('POST', 'PUT', 'PATCH'):
        # Count actual bytes as well as Content-Length, including chunked requests.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 2_000_000:
                return Response('Archivo demasiado grande para el MVP (2 MB).', status_code=413)
        request._body = bytes(body)
    return await call_next(request)

class Create(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    source: str = Field(min_length=1, max_length=1_000_000)
    program: str = Field(min_length=1, max_length=100_000)
    target_minutes: int = Field(default=10, ge=1, le=90)
    wpm: int = Field(default=170, ge=100, le=190)

class Segment(BaseModel):
    id: str = Field(max_length=80)
    speaker: str
    kind: str
    text: str = Field(max_length=10000)
    source_ids: list[str]
    topic_ids: list[str]

class Edit(BaseModel):
    revision: int
    segments: list[Segment] | None = None
    mapping: dict[str, list[str]] | None = None
    pronunciation: dict[str, str] | None = None

class Approve(BaseModel):
    revision: int
    matrix_reviewed: bool

class Synthesize(BaseModel):
    revision: int
    provider: str = 'gemini'
    voices: dict[str, str] = Field(default_factory=lambda: {'profesora': 'Kore', 'profesor': 'Puck'})
    regenerate: list[str] = Field(default_factory=list)

class Generate(BaseModel):
    revision: int
    depth: str = 'explicativo'

@app.post('/episodes/{eid}/generate-dialogue')
def generate_dialogue(eid: str, body: Generate):
    if not os.getenv('GEMINI_API_KEY'):
        raise HTTPException(422, 'Configurá GEMINI_API_KEY para ampliar y auditar el diálogo. El modo documental funciona sin clave.')
    if body.depth not in ('explicativo', 'examen'):
        raise HTTPException(422, 'Profundidad desconocida.')
    with Session.begin() as s:
        ep = get_episode(s, eid)
        if ep.revision != body.revision:
            raise HTTPException(409, 'La versión cambió.')
        if s.scalar(select(Job).where(Job.episode_id == eid, Job.status.in_(['queued','running']))):
            raise HTTPException(409, 'Ya existe un trabajo activo.')
        job = Job(id=str(uuid.uuid4()), episode_id=eid, status='queued', payload={**body.model_dump(), 'kind':'script', 'episode':copy.deepcopy(ep.data)}, result={}, error='', lease_until=0, lease_token='', attempts=0)
        s.add(job)
        return {'id':job.id, 'status':'queued'}

@app.post('/episodes/{eid}/apply-dialogue/{jid}')
def apply_dialogue(eid: str, jid: str, body: Generate):
    with Session.begin() as s:
        ep = get_episode(s, eid)
        job = s.get(Job, jid)
        if not job or job.episode_id != eid or job.status != 'done' or job.result.get('kind') != 'script':
            raise HTTPException(422, 'No hay una propuesta de diálogo terminada para esta unidad.')
        if job.result['base_revision'] != ep.revision or body.revision != ep.revision:
            raise HTTPException(409, 'La fuente de la propuesta cambió. Generá una nueva propuesta.')
        return save(s, ep, copy.deepcopy(job.result['candidate']), body.revision)


def get_episode(s, eid):
    ep = s.get(Episode, eid)
    if not ep:
        raise HTTPException(404, 'Unidad inexistente.')
    return ep


def view(ep):
    return {'id': ep.id, 'revision': ep.revision, **ep.data, 'audit': audit(ep.data),
            'approved': ep.data.get('approved_hash') == revision_hash(ep.data)}


def save(s, ep, data, expected):
    new_revision = expected+1
    changed = s.execute(update(Episode).where(Episode.id == ep.id, Episode.revision == expected).values(data=data, revision=new_revision))
    if not changed.rowcount:
        raise HTTPException(409, 'La versión cambió. Recargá antes de guardar.')
    s.add(Revision(id=f'{ep.id}:{new_revision}', episode_id=ep.id, data=data))
    ep.data, ep.revision = data, new_revision
    return view(ep)

@app.get('/health')
def health():
    with Session() as s:
        s.execute(select(Episode.id).limit(1))
    return {'ok': True, 'service': 'academic-audio-studio'}

@app.get('/capabilities')
def capabilities():
    return {'gemini': bool(os.getenv('GEMINI_API_KEY')), 'elevenlabs': bool(os.getenv('ELEVENLABS_API_KEY')),
            'asr': bool(os.getenv('ASR_MODEL')), 'local': True, 'mode': 'extractive', 'storage': 'supabase' if os.getenv('SUPABASE_URL') else 'local'}

@app.get('/episodes')
def list_episodes():
    with Session() as s:
        return [{'id': e.id, 'title': e.data['title'], 'revision': e.revision} for e in s.scalars(select(Episode)).all()]

@app.post('/episodes')
def create(body: Create):
    try:
        blocks, points = parse_source(body.source), parse_program(body.program)
        mapping = map_topics(blocks, points)
    except ValueError as e:
        raise HTTPException(422, str(e))
    data = {**body.model_dump(), 'blocks': blocks, 'points': points, 'mapping': mapping,
            'segments': draft(blocks, points, mapping), 'approved_hash': None,
            'pronunciation': {'CCCN': 'Código Civil y Comercial de la Nación', 'DNU': 'decreto de necesidad y urgencia', 'Art.': 'artículo', 'Arts.': 'artículos', 'v.gr.': 'por ejemplo'}}
    ep = Episode(id=str(uuid.uuid4()), revision=1, data=data)
    with Session.begin() as s:
        s.add(ep); s.add(Revision(id=f'{ep.id}:1', episode_id=ep.id, data=data))
    return view(ep)

@app.get('/episodes/{eid}')
def read(eid: str):
    with Session() as s:
        return view(get_episode(s, eid))

@app.put('/episodes/{eid}')
def edit(eid: str, body: Edit):
    with Session.begin() as s:
        ep = get_episode(s, eid); data = copy.deepcopy(ep.data)
        if body.segments is not None:
            if not body.segments:
                raise HTTPException(422, 'El guion no puede estar vacío.')
            data['segments'] = [seg.model_dump() for seg in body.segments]
        if body.mapping is not None:
            if set(body.mapping) != {p['id'] for p in data['points']} or any(b not in {x['id'] for x in data['blocks']} for bids in body.mapping.values() for b in bids):
                raise HTTPException(422, 'Matriz inválida.')
            data['mapping'] = body.mapping
            for seg in data['segments']:
                seg['topic_ids'] = [pid for pid, bids in body.mapping.items() if set(bids) & set(seg['source_ids'])]
        if body.pronunciation is not None:
            if len(body.pronunciation) > 100 or any(not k or len(k)>80 or not v or len(v)>200 for k,v in body.pronunciation.items()):
                raise HTTPException(422, 'Diccionario inválido.')
            data['pronunciation'] = body.pronunciation
        data['approved_hash'] = None
        return save(s, ep, data, body.revision)

@app.post('/episodes/{eid}/repair')
def correct(eid: str, body: Approve):
    with Session.begin() as s:
        ep = get_episode(s, eid)
        return save(s, ep, repair(copy.deepcopy(ep.data)), body.revision)

@app.post('/episodes/{eid}/approve')
def approve(eid: str, body: Approve):
    if not body.matrix_reviewed:
        raise HTTPException(422, 'Revisá las asociaciones del programa antes de aprobar.')
    with Session.begin() as s:
        ep = get_episode(s, eid); data = copy.deepcopy(ep.data)
        if not audit(data)['passed']:
            raise HTTPException(422, 'La auditoría tiene errores sustanciales.')
        data['approved_hash'] = revision_hash(data)
        return save(s, ep, data, body.revision)

@app.post('/episodes/{eid}/synthesize')
def synthesize(eid: str, body: Synthesize):
    if body.provider not in ('local','gemini','elevenlabs'):
        raise HTTPException(422, 'Proveedor desconocido.')
    required = {'gemini': 'GEMINI_API_KEY', 'elevenlabs': 'ELEVENLABS_API_KEY'}
    if body.provider in required and not os.getenv(required[body.provider]):
        raise HTTPException(422, f'Configurá {required[body.provider]} en el worker y API, nunca en el repositorio.')
    if set(body.voices) != {'profesora','profesor'} or any(not v or len(v)>100 for v in body.voices.values()) or len(set(body.voices.values())) != 2:
        raise HTTPException(422, 'Elegí dos voces distintas, una por profesor.')
    with Session.begin() as s:
        ep = get_episode(s, eid)
        if body.revision != ep.revision:
            raise HTTPException(409, 'La versión cambió.')
        if not audit(ep.data)['passed'] or ep.data.get('approved_hash') != revision_hash(ep.data):
            raise HTTPException(422, 'El guion necesita auditoría sin errores y aprobación vigente.')
        if set(body.regenerate) - {seg['id'] for seg in ep.data['segments']}:
            raise HTTPException(422, 'Segmento a regenerar inexistente.')
        active = s.scalar(select(Job).where(Job.episode_id == eid, Job.status.in_(['queued', 'running'])))
        if active:
            raise HTTPException(409, 'Ya existe un trabajo activo para esta unidad.')
        job = Job(id=str(uuid.uuid4()), episode_id=eid, status='queued', payload={**body.model_dump(), 'episode': copy.deepcopy(ep.data)}, result={}, error='', lease_until=0, lease_token='', attempts=0)
        s.add(job)
        return {'id': job.id, 'status': 'queued'}

@app.get('/jobs/{jid}')
def read_job(jid: str):
    with Session() as s:
        job = s.get(Job, jid)
        if not job:
            raise HTTPException(404, 'Trabajo inexistente.')
        return {'id': job.id, 'episode_id': job.episode_id, 'status': job.status, 'result': job.result, 'error': job.error}

@app.get('/episodes/{eid}/export/{kind}')
def export_episode(eid: str, kind: str):
    with Session() as s:
        ep = get_episode(s, eid)
        if kind == 'report':
            return Response(json.dumps({'revision': ep.revision, 'audit': audit(ep.data), 'source_hash': revision_hash(ep.data), 'blocks': ep.data['blocks'], 'mapping': ep.data['mapping'], 'repair_log': ep.data.get('repair_log')}, ensure_ascii=False, indent=2), media_type='application/json', headers={'Content-Disposition': 'attachment; filename="coverage.json"'})
        if kind == 'script':
            text = '\n\n'.join(f'[{seg["id"]}] {seg["speaker"]} ({seg["kind"]}; fuentes {", ".join(seg["source_ids"])}):\n{seg["text"]}' for seg in ep.data['segments'])
            return Response(text, media_type='text/markdown', headers={'Content-Disposition': 'attachment; filename="script.md"'})
        raise HTTPException(404, 'Exportación inexistente.')

@app.get('/jobs/{jid}/download/{kind}')
def download(jid: str, kind: str, release: bool = False):
    choices = {'audio': ('audio.mp3','audio/mpeg'), 'script': ('script.md','text/markdown'), 'report': ('report.json','application/json'), 'transcript': ('transcript.txt','text/plain')}
    if kind not in choices:
        raise HTTPException(404)
    with Session() as s:
        job = s.get(Job, jid)
        if not job or job.status != 'done' or job.payload.get('kind') == 'script':
            raise HTTPException(409, 'El trabajo no está terminado.')
        ep = get_episode(s, job.episode_id)
        if revision_hash(ep.data) != job.result['revision_hash'] or ep.data.get('approved_hash') != revision_hash(ep.data):
            raise HTTPException(409, 'El audio pertenece a una versión anterior. Aprobá y generá la versión actual.')
        if release and job.result['audio_status'] != 'verified':
            raise HTTPException(422, 'La publicación requiere verificación ASR aprobada. Sólo disponible como borrador de revisión.')
        name,mime = choices[kind]
        key = job.result['artifact_prefix']+'/'+name
    return Response(Storage().get(key), media_type=mime, headers={'Content-Disposition': f'attachment; filename="{name}"', 'X-Audio-Verification': job.result['audio_status'], 'Cache-Control': 'private, no-store'})
