"""Closed-world, lossless drafting. No model or user input can bypass the audit gate."""
import hashlib
import re
import unicodedata
from difflib import SequenceMatcher


def digest(value):
    import json
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', text).split()).casefold()


def tokens(text):
    return set(re.findall(r'\w{3,}', normalize(text))) - {'los', 'las', 'del', 'una', 'por', 'con', 'para', 'que', 'como', 'son'}


def parse_source(markdown, include_headings=False):
    """Offsets address the immutable original, including original Markdown punctuation."""
    blocks, heading, hierarchy = [], 'Unidad', {}
    for match in re.finditer(r'[^\n]+', markdown):
        line = match.group()
        if not line.strip():
            continue
        if re.match(r'^#{1,6}\s', line):
            heading = re.sub(r'^#+\s+', '', line).strip()
            level = len(line) - len(line.lstrip('#'))
            hierarchy = {k: v for k, v in hierarchy.items() if k < level}
            hierarchy[level] = heading
            if include_headings:
                start=match.start()+len(re.match(r'^#+\s+',line).group())
                blocks.append({'id':f'b{len(blocks)+1}','heading':heading,'path':list(hierarchy.values()),'text':markdown[start:match.end()], 'start':start,'end':match.end(),'line':markdown.count('\n',0,start)+1,'kind':'heading'})
            continue
        # Bounded spans; never drop the tail, even when a sentence exceeds the limit.
        start, end = match.start(), match.end()
        while start < end:
            stop = min(start + 850, end)
            if stop < end:
                boundary = markdown.rfind(' ', start + 400, stop)
                if boundary > start:
                    stop = boundary
            if markdown[start:stop].strip():
                blocks.append({'id': f'b{len(blocks)+1}', 'heading': heading,
                               'path': list(hierarchy.values()),
                               'start': start, 'end': stop, 'line': markdown.count('\n', 0, start)+1,
                               'text': markdown[start:stop]})
            start = stop
    if not blocks:
        raise ValueError('La unidad debe contener texto, además de títulos.')
    return blocks


def parse_program(program):
    points = []
    for line in program.splitlines():
        line = re.sub(r'^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+)', '', line).strip()
        if not line or line.casefold().startswith(('programa:', 'programa de ')):
            continue
        # Each explicit bullet/line and semicolon is mandatory; no generative pruning.
        for title in line.split(';'):
            if title.strip():
                points.append({'id': f'p{len(points)+1}', 'title': title.strip()})
    if not points:
        raise ValueError('El programa no tiene puntos verificables.')
    return points


def map_topics(blocks, points):
    mapping = {p['id']: [] for p in points}
    for b in blocks:
        context = ' '.join(b.get('path', [b['heading']])) + ' ' + b['text']
        ranked = [(len(tokens(p['title']) & tokens(context)) / max(1, len(tokens(p['title']))), p['id']) for p in points]
        for score, pid in ranked:
            if score >= .5:
                mapping[pid].append(b['id'])
    return mapping


def draft(blocks, points, mapping):
    segments = []
    for index, b in enumerate(blocks):
        pids = [pid for pid, ids in mapping.items() if b['id'] in ids]
        speaker = 'profesora' if index % 2 == 0 else 'profesor'
        # Questions are fixed templates and do not assert new doctrine.
        if not segments or b['heading'] != blocks[blocks.index(b)-1]['heading']:
            segments.append({'id': f's{len(segments)+1}', 'speaker': speaker, 'kind': 'question',
                             'text': f'Pregunta de examen oral: ¿qué desarrolla el material sobre {b["heading"]}?',
                             'source_ids': [b['id']], 'topic_ids': pids})
        segments.append({'id': f's{len(segments)+1}', 'speaker': 'profesor' if speaker == 'profesora' else 'profesora',
                         'kind': 'source', 'text': b['text'], 'source_ids': [b['id']], 'topic_ids': pids})
    return segments


def audit(episode):
    if episode.get('mode')=='magistral_dialogue':
        from .magistral import audit_dialogue
        return audit_dialogue(episode)
    blocks = {b['id']: b for b in episode['blocks']}
    point_ids = {p['id'] for p in episode['points']}
    findings, covered, valid_blocks, seen = [], set(), set(), set()
    def issue(code, message, segment=None):
        findings.append({'code': code, 'severity': 'error', 'message': message, 'segment_id': segment})
    for seg in episode['segments']:
        sid = seg['id']
        if sid in seen:
            issue('duplicate_id', 'Identificador de segmento repetido.', sid)
        seen.add(sid)
        if episode.get('mode')=='reading' and seg['kind']!='source':
            issue('reading_inserted_content','Lectura fiel sólo admite texto de la fuente, sin preguntas ni añadidos.',sid)
        if seg['speaker'] not in ('profesora', 'profesor'):
            issue('voice', 'Voz desconocida.', sid)
        refs = seg['source_ids']
        if not refs or any(r not in blocks for r in refs):
            issue('source_missing', 'La referencia no existe en el documento original.', sid)
            continue
        if any(pid not in point_ids for pid in seg['topic_ids']):
            issue('topic_unknown', 'Punto del programa inexistente.', sid)
        allowed_topics = {pid for pid, bids in episode['mapping'].items() if set(refs) & set(bids)}
        if set(seg['topic_ids']) - allowed_topics:
            issue('wrong_association', 'La asociación no coincide con la matriz revisada.', sid)
        for ref in refs:
            b = blocks[ref]
            if episode['source'][b['start']:b['end']] != b['text']:
                issue('source_integrity', 'La fuente o sus offsets fueron alterados.', sid)
        if seg['kind'] == 'source':
            expected = '\n'.join(blocks[r]['text'] for r in refs)
            if (seg['text'] != expected if episode.get('mode')=='reading' else normalize(seg['text']) != normalize(expected)):
                issue('unsupported_claim', 'Cambio doctrinario, contradicción o afirmación sin respaldo literal. Restaurá la cita o incorporá una fuente.', sid)
            else:
                valid_blocks.update(refs)
                covered.update(set(seg['topic_ids']) & allowed_topics)
        elif seg['kind'] in ('analysis', 'example') or (seg['kind'] == 'question' and sid.startswith('ai')):
            from .writing import review_key
            review = episode.get('semantic_reviews', {}).get(review_key(seg, episode['blocks']), {})
            if seg['kind'] == 'example' and not seg['text'].startswith('Ejemplo inventado:'):
                issue('example_label', 'El ejemplo debe identificarse expresamente como inventado.', sid)
            if review.get('passed') is not True:
                issue('example_needs_review' if seg['kind'] == 'example' else 'semantic_review_required', review.get('reason', 'La intervención requiere auditoría semántica del servidor; una edición invalida el veredicto.'), sid)
        elif seg['kind'] == 'question':
            expected = f'Pregunta de examen oral: ¿qué desarrolla el material sobre {blocks[refs[0]]["heading"]}?'
            if seg['text'] != expected:
                issue('question_changed', 'La pregunta editada requiere una verificación semántica aún no disponible; usá la pregunta de fuente.', sid)
        else:
            issue('external_unverified', 'La verificación normativa externa no está habilitada. No se confunde con la fuente original.', sid)
    for b in blocks:
        if b not in valid_blocks:
            issue('source_omission', f'Falta desarrollar el bloque {b}, línea {blocks[b]["line"]}.')
    if episode.get('mode')=='reading':
        ordered=[ref for seg in episode['segments'] for ref in seg['source_ids']]
        if ordered!=list(blocks):issue('reading_order_or_duplicate','La lectura debe conservar todos los bloques en su orden original, exactamente una vez.')
        if episode.get('voice_count',1)==1 and any(s['speaker']!='profesora' for s in episode['segments']):issue('reading_voice','La narración de una voz no puede alternar locutores.')
    coverage = []
    for p in episode['points']:
        ids = episode['mapping'].get(p['id'], [])
        complete = bool(ids) and set(ids) <= valid_blocks and p['id'] in covered
        coverage.append({**p, 'source_ids': ids, 'covered': complete})
        if not complete:
            issue('program_omission', f'Punto sin cobertura completa: {p["title"]}.')
    words = sum(len(s['text'].split()) for s in episode['segments'])
    minutes = words / episode.get('wpm', 140)
    target = episode.get('target_minutes', 10)
    return {'passed': not findings, 'findings': findings, 'coverage': coverage,
            'coverage_percent': round(100 * sum(p['covered'] for p in coverage)/len(coverage), 1),
            'word_count': words, 'estimated_minutes': round(minutes, 2), 'target_minutes': target,
            'duration_warning': None if .8*target <= minutes <= 1.2*target else 'La fuente completa no coincide con la duración objetivo. No se omite contenido ni se agrega relleno: ajustá el plan o incorporá material.',
            'method': 'Cotejo literal conservador + cobertura íntegra + revisión humana de asociaciones. Si hay ampliaciones IA, exigen auditoría semántica separada y revisión docente. No determina verdad jurídica ni vigencia normativa.'}


def repair(episode):
    """Only documented, safe corrections: restore the immutable source, never invent a fix."""
    before = audit(episode)
    episode['segments'] = draft(episode['blocks'], episode['points'], episode['mapping'])
    episode['repair_log'] = {'before': before['findings'], 'action': 'Regeneración extractiva íntegra desde la fuente; se descartan ediciones del guion, no de la fuente.'}
    episode['approved_hash'] = None
    return episode


def revision_hash(episode):
    fields=('source', 'program', 'mapping', 'segments', 'wpm', 'target_minutes', 'pronunciation','mode','voice_count','import_fingerprint','claim_inventory','editorial_reviews','cross_source_decisions','scope','source_documents','chapter_plan')
    return digest({k:episode[k] for k in fields if k in episode})


def compare_transcript(expected, actual):
    a, b = normalize(expected).split(), normalize(actual).split()
    # Punctuation-insensitive sequence alignment; numeric changes remain hard errors.
    a = re.findall(r'\w+', ' '.join(a)); b = re.findall(r'\w+', ' '.join(b))
    similarity = SequenceMatcher(None, a, b, autojunk=False).ratio()
    nums_a = re.findall(r'\b\d+\b', expected)
    nums_b = re.findall(r'\b\d+\b', actual)
    negations_a = [t for t in a if t in ('no', 'nunca', 'salvo', 'excepto')]
    negations_b = [t for t in b if t in ('no', 'nunca', 'salvo', 'excepto')]
    return {'passed': similarity >= .92 and nums_a == nums_b and negations_a == negations_b,
            'similarity': round(similarity, 4), 'numbers_match': nums_a == nums_b,
            'negations_match': negations_a == negations_b,
            'note': 'Un desacuerdo de ASR requiere revisión; no demuestra por sí mismo un error de TTS.'}
