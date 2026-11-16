import io
import wave
import pytest
from aas.worker import run_once
from aas.tts import spoken_text, GeminiTTS, ElevenLabsTTS
from aas.db import Session, Job
from sqlalchemy import update
VOICES={'profesora':'es','profesor':'es+f3'}

def produce(client,body):
    ep=client.post('/episodes',json=body).json()
    ep=client.post(f'/episodes/{ep["id"]}/approve',json={'revision':1,'matrix_reviewed':True}).json()
    r=client.post(f'/episodes/{ep["id"]}/synthesize',json={'revision':ep['revision'],'provider':'local','voices':VOICES})
    assert r.status_code==200,r.text
    jid=r.json()['id'];assert run_once()
    job=client.get('/jobs/'+jid).json()
    assert job['status']=='done',job
    return ep,jid,job

def test_real_tts_mp3_download_cache_and_stale_version_gate(client,body,tmp_path):
    ep,jid,job=produce(client,body)
    audio=client.get(f'/jobs/{jid}/download/audio')
    assert audio.status_code==200 and len(audio.content)>10000
    path=tmp_path/'real.mp3';path.write_bytes(audio.content)
    from aas.tts import probe
    assert probe(path)>5
    assert job['result']['audio_status']=='unverified'
    assert client.get(f'/jobs/{jid}/download/audio?release=true').status_code==422
    assert client.get(f'/jobs/{jid}/download/report').json()['audit']['passed']
    assert b'ASR pendiente' in client.get(f'/jobs/{jid}/download/transcript').content
    r=client.post(f'/episodes/{ep["id"]}/synthesize',json={'revision':ep['revision'],'provider':'local','voices':VOICES,'regenerate':['s2']})
    jid2=r.json()['id'];assert run_once()
    result=client.get('/jobs/'+jid2).json()['result']
    assert next(s for s in result['segments'] if s['segment_id']=='s2')['cached'] is False
    assert all(s['cached'] for s in result['segments'] if s['segment_id']!='s2')
    client.put(f'/episodes/{ep["id"]}',json={'revision':ep['revision'],'pronunciation':{}})
    assert client.get(f'/jobs/{jid}/download/audio').status_code==409

def test_asr_mismatch_blocks_release(client,body,monkeypatch):
    monkeypatch.setattr('aas.worker.transcribe',lambda path:'Una frase distinta, artículo 999.')
    ep,jid,job=produce(client,body)
    assert job['result']['audio_status']=='mismatch'
    assert client.get(f'/jobs/{jid}/download/audio?release=true').status_code==422

def test_dictionary_boundaries():
    assert spoken_text('Art. 259, CCCN y PRECCCN.', {'Art.':'artículo','CCCN':'Código'})=='artículo 259, Código y PRECCCN.'

def test_gemini_adapter_contract_not_live(monkeypatch):
    import httpx,base64
    monkeypatch.setenv('GEMINI_API_KEY','fake-contract-test');seen=[]
    def handler(request):
        seen.append(request)
        return httpx.Response(200,json={'steps':[{'type':'model_output','content':[{'type':'audio','mime_type':'audio/l16; rate=24000; channels=1','data':base64.b64encode(b'\x00\x01'*240).decode()}]}]})
    original=httpx.Client
    monkeypatch.setattr('aas.tts.httpx.Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    audio=GeminiTTS().synthesize('El artículo 259.','Kore',140)
    with wave.open(io.BytesIO(audio)) as w:
        assert w.getframerate()==24000 and w.getnframes()==240
    assert seen[0].url.path=='/v1beta/interactions'
    assert b'speech_metadata' in seen[0].content

def test_missing_credentials_do_not_fallback_silently(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False);monkeypatch.delenv('ELEVENLABS_API_KEY',raising=False)
    with pytest.raises(ValueError,match='GEMINI_API_KEY'):GeminiTTS()
    with pytest.raises(ValueError,match='ELEVENLABS_API_KEY'):ElevenLabsTTS()

def test_worker_recovers_expired_lease(client,body):
    ep=client.post('/episodes',json=body).json()
    approved=client.post(f'/episodes/{ep["id"]}/approve',json={'revision':1,'matrix_reviewed':True}).json()
    jid=client.post(f'/episodes/{ep["id"]}/synthesize',json={'revision':approved['revision'],'provider':'local','voices':VOICES}).json()['id']
    with Session.begin() as s:
        s.execute(update(Job).where(Job.id==jid).values(status='running',lease_until=0,attempts=1,lease_token='dead-worker'))
    assert run_once()
    assert client.get('/jobs/'+jid).json()['status']=='done'
