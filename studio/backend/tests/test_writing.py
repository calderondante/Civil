import copy
from aas.writing import enrich
from aas.core import audit

def test_expansion_retains_all_sources_and_audits_every_new_claim(client,body,monkeypatch):
    ep=client.post('/episodes',json=body).json()
    calls=[]
    def complete(system,data,model):
        calls.append(data)
        if len(calls)==1:
            return {'turns':[{'after_source_id':'b1','speaker':'profesora','kind':'analysis','text':'El fin inmediato es un elemento del concepto del acto jurídico.','source_ids':['b1']}]}
        return {'verdicts':[{'segment_id':'ai1','passed':True,'reason':'Respaldado por la definición citada.'}]}
    monkeypatch.setattr('aas.writing.json_completion',complete)
    candidate=enrich(ep)
    assert len(calls)==2
    assert [s for s in candidate['segments'] if s['kind']=='source']==[s for s in ep['segments'] if s['kind']=='source']
    assert audit(candidate)['passed']
    extra=next(s for s in candidate['segments'] if s['id']=='ai1')
    extra['text']='Una modificación doctrinaria después de la auditoría.'
    assert not audit(candidate)['passed']

def test_independent_audit_rejection_and_numeric_guard(client,body,monkeypatch):
    ep=client.post('/episodes',json=body).json()
    def complete(system,data,model):
        if 'program' in data:
            return {'turns':[{'after_source_id':'b1','speaker':'profesora','kind':'analysis','text':'El artículo 999 cambia la regla.','source_ids':['b1']}]}
        return {'verdicts':[{'segment_id':'ai1','passed':True,'reason':'El modelo se equivoca.'}]}
    monkeypatch.setattr('aas.writing.json_completion',complete)
    assert not audit(enrich(ep))['passed']


def test_queued_dialogue_proposal_requires_explicit_apply_and_reapproval(client,body,monkeypatch):
    from aas.worker import run_once
    monkeypatch.setenv('GEMINI_API_KEY','contract-only-not-a-real-key')
    def complete(system,data,model):
        if 'program' in data:
            return {'turns':[{'after_source_id':'b1','speaker':'profesora','kind':'analysis','text':'La definición contiene un fin inmediato.','source_ids':['b1']}]}
        return {'verdicts':[{'segment_id':'ai1','passed':True,'reason':'La fuente contiene ese elemento.'}]}
    monkeypatch.setattr('aas.writing.json_completion',complete)
    ep=client.post('/episodes',json=body).json();route=f'/episodes/{ep["id"]}'
    job=client.post(route+'/generate-dialogue',json={'revision':1,'depth':'explicativo'}).json()
    assert run_once()
    assert client.get('/jobs/'+job['id']).json()['status']=='done'
    assert client.get(route).json()['revision']==1
    candidate=client.post(route+'/apply-dialogue/'+job['id'],json={'revision':1}).json()
    assert candidate['revision']==2 and candidate['audit']['passed'] and not candidate['approved']
    assert any(s['kind']=='analysis' for s in candidate['segments'])
    assert client.post(route+'/apply-dialogue/'+job['id'],json={'revision':2}).status_code==409
