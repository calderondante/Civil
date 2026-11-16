from aas.core import parse_source, audit, compare_transcript

def make(client, body):
    response=client.post('/episodes',json=body)
    assert response.status_code==200,response.text
    return response.json()

def test_lossless_segmentation_with_long_paragraph():
    original='# Unidad\n## Un artículo\n'+('No se pierde esta excepción. '*90)+'FIN DE LA FUENTE'
    blocks=parse_source(original)
    assert len(blocks)>1
    assert ''.join(b['text'] for b in blocks)==original.split('\n',2)[2]
    assert all(original[b['start']:b['end']]==b['text'] for b in blocks)
    assert blocks[-1]['text'].endswith('FIN DE LA FUENTE')
    assert max(len(b['text']) for b in blocks)<=850

def test_every_program_point_is_mandatory(client,body):
    body['program']+='\n- Lesión subjetiva'
    ep=make(client,body)
    assert not ep['audit']['passed']
    assert any(f['code']=='program_omission' and 'Lesión' in f['message'] for f in ep['audit']['findings'])
    assert client.post(f'/episodes/{ep["id"]}/approve',json={'revision':1,'matrix_reviewed':True}).status_code==422

def test_immutable_sources_and_correct_initial_coverage(client,body):
    ep=make(client,body)
    assert ep['audit']['passed']
    assert ep['audit']['coverage_percent']==100
    assert not ep['approved']
    for s in ep['segments']:
        if s['kind']=='source':
            b=next(b for b in ep['blocks'] if b['id']==s['source_ids'][0])
            assert s['text']==body['source'][b['start']:b['end']]
    assert {s['speaker'] for s in ep['segments']}=={'profesora','profesor'}

def test_article_substitution_blocks_audio_and_repair_is_logged(client,body):
    ep=make(client,body)
    s=next(s for s in ep['segments'] if s['kind']=='source')
    s['text']=s['text'].replace('259','999')
    changed=client.put(f'/episodes/{ep["id"]}',json={'revision':1,'segments':ep['segments']}).json()
    assert any(f['code']=='unsupported_claim' for f in changed['audit']['findings'])
    assert client.post(f'/episodes/{ep["id"]}/synthesize',json={'revision':2,'provider':'local'}).status_code==422
    repaired=client.post(f'/episodes/{ep["id"]}/repair',json={'revision':2,'matrix_reviewed':False}).json()
    assert repaired['audit']['passed']
    assert repaired['repair_log']['before']
    assert not repaired['approved']

def test_wrong_source_and_omission_detected(client,body):
    ep=make(client,body)
    for s in ep['segments']:
        if s['kind']=='source':
            s['source_ids']=['b2']
            break
    result=audit(ep)
    assert {'unsupported_claim','wrong_association','source_omission'} <= {f['code'] for f in result['findings']}

def test_edit_invalidates_approval_and_conflicts_are_rejected(client,body):
    ep=make(client,body);route=f'/episodes/{ep["id"]}'
    approved=client.post(route+'/approve',json={'revision':1,'matrix_reviewed':True}).json()
    assert approved['approved']
    response=client.put(route,json={'revision':2,'pronunciation':{'CCCN':'Código Civil y Comercial'}})
    assert response.status_code==200
    assert not response.json()['approved']
    assert client.put(route,json={'revision':2,'pronunciation':{}}).status_code==409
    assert client.post(route+'/approve',json={'revision':3,'matrix_reviewed':False}).status_code==422

def test_matrix_reassociation_requires_reapproval(client,body):
    ep=make(client,body);ep['mapping']['p1']=[]
    changed=client.put(f'/episodes/{ep["id"]}',json={'revision':1,'mapping':ep['mapping']}).json()
    assert not changed['audit']['passed'] and not changed['approved']

def test_examples_cannot_smuggle_unsupported_doctrine(client,body):
    ep=make(client,body)
    ep['segments'].append({**ep['segments'][0], 'id':'inventado','kind':'example','text':'Ejemplo inventado: el artículo 999 deroga toda nulidad.'})
    assert 'example_needs_review' in {f['code'] for f in audit(ep)['findings']}

def test_transcription_detects_article_and_negation_changes():
    assert compare_transcript('El artículo 259 no lo permite.', 'El artículo 259 no lo permite')['passed']
    assert not compare_transcript('El artículo 259 no lo permite.', 'El artículo 299 no lo permite.')['passed']
    assert not compare_transcript('El artículo 259 no lo permite.', 'El artículo 259 lo permite.')['passed']

def test_auth_and_size_limit(client,body,monkeypatch):
    monkeypatch.setenv('API_BEARER_TOKEN','test-private-only')
    assert client.get('/episodes').status_code==401
    assert client.get('/episodes',headers={'Authorization':'Bearer test-private-only'}).status_code==200
    assert client.post('/episodes',content=b'x'*2_000_001).status_code==413

def test_duration_never_causes_automatic_summary(client,body):
    ep=make(client,body)
    assert ep['audit']['duration_warning']
    assert len([s for s in ep['segments'] if s['kind']=='source'])==len(ep['blocks'])

def test_subheadings_preserve_parent_syllabus_association(client):
    ep=make(client,{'title':'Jerarquía','source':'# Unidad\n## Hechos involuntarios y actos ilícitos\n### Discernimiento\nSe conserva la explicación completa bajo el subtítulo.','program':'- Hechos involuntarios y actos ilícitos'})
    assert ep['audit']['passed']
    assert 'Hechos involuntarios y actos ilícitos' in ep['blocks'][0]['path']
