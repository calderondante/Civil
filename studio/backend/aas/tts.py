import base64
import ctypes
import io
import os
import re
import subprocess
import threading
import wave
from pathlib import Path
import httpx

_LOCK = threading.Lock()


def pcm_wave(data, rate=24000):
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(data)
    return out.getvalue()


def spoken_text(text, dictionary):
    for term, pronunciation in sorted(dictionary.items(), key=lambda x: -len(x[0])):
        # Match tokens, never substitute inside other legal words.
        text = re.sub(r'(?<!\w)'+re.escape(term)+r'(?!\w)', lambda _: pronunciation, text)
    return text


class LocalTTS:
    """Actual offline Spanish speech; deliberately NOT advertised as Argentine neural TTS.

    eSpeak NG is GPL-3.0-or-later, isolated in the worker. See docs licensing.
    """
    version = 'espeak-ng-loader-0.2.4'
    def synthesize(self, text, voice, wpm):
        import espeakng_loader
        with _LOCK:
            lib = ctypes.CDLL(espeakng_loader.get_library_path())
            lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
            # AUDIO_OUTPUT_SYNCHRONOUS = 2; data parent contains espeak-ng-data.
            rate = lib.espeak_Initialize(2, 0, str(Path(espeakng_loader.get_data_path()).parent).encode(), 0)
            if rate <= 0:
                raise RuntimeError('No se pudo inicializar eSpeak.')
            chunks = []
            callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p)
            @callback_type
            def callback(samples, count, events):
                if count and samples:
                    chunks.append(ctypes.string_at(samples, count*2))
                return 0
            lib.espeak_SetSynthCallback(callback)
            lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
            if lib.espeak_SetVoiceByName(voice.encode()) != 0:
                lib.espeak_Terminate(); raise ValueError('Voz eSpeak inexistente.')
            lib.espeak_SetParameter(1, wpm, 0)
            encoded = text.encode('utf-8') + b'\0'
            lib.espeak_Synth.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
            try:
                code = lib.espeak_Synth(encoded, len(encoded), 0, 1, 0, 1, None, None)
                lib.espeak_Synchronize()
                if code or not chunks:
                    raise RuntimeError('eSpeak no produjo audio.')
                return pcm_wave(b''.join(chunks), rate)
            finally:
                lib.espeak_Terminate()


class GeminiTTS:
    """REST Interactions (3.8, current official cookbook) and legacy generateContent.
    Network/keys/model access must be verified with an actual account before production.
    """
    def __init__(self):
        self.key = os.getenv('GEMINI_API_KEY', '')
        if not self.key:
            raise ValueError('Falta GEMINI_API_KEY en el entorno del worker.')
        self.model = os.getenv('GEMINI_TTS_MODEL', 'gemini-3.8-flash-tts')
        self.protocol = os.getenv('GEMINI_TTS_PROTOCOL', 'interactions')
        self.version = f'{self.protocol}:{self.model}:rioplatense-v1'

    def synthesize(self, text, voice, wpm):
        style = f'Español argentino rioplatense. Profesor universitario, tono claro y sereno. Ritmo aproximado: {wpm} palabras por minuto. Leé exactamente el texto, sin agregar ni omitir palabras.'
        headers = {'x-goog-api-key': self.key}
        with httpx.Client(timeout=180) as client:
            if self.protocol == 'interactions':
                response = client.post('https://generativelanguage.googleapis.com/v1beta/interactions', headers=headers, json={
                    'model': self.model, 'input': [{'type': 'text', 'text': text, 'annotations': [{'type': 'speech_metadata', 'style': style}]}],
                    'response_format': {'type': 'audio'}, 'generation_config': {'speech_config': [{'voice': voice}]}, 'store': False})
                response.raise_for_status()
                data = response.json()
                outputs = data.get('outputs', []) + [item for step in data.get('steps', []) if step.get('type') == 'model_output' for item in step.get('content', [])]
                if data.get('output_audio'):
                    outputs.append(data['output_audio'])
                audio = next((o for o in outputs if o.get('type') == 'audio' and o.get('data')), None)
                if not audio:
                    raise ValueError('Gemini no devolvió audio en Interactions.')
                raw = base64.b64decode(audio['data'], validate=True)
                mime = audio.get('mime_type', 'audio/pcm;rate=24000')
            elif self.protocol == 'generateContent':
                response = client.post(f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent', headers=headers, json={
                    'contents': [{'parts': [{'text': f'{style}\n\nTexto:\n{text}'}]}],
                    'generationConfig': {'responseModalities': ['AUDIO'], 'speechConfig': {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': voice}}}}})
                response.raise_for_status()
                parts = response.json()['candidates'][0]['content']['parts']
                part = next(p['inlineData'] for p in parts if 'inlineData' in p)
                raw, mime = base64.b64decode(part['data'], validate=True), part['mimeType']
            else:
                raise ValueError('GEMINI_TTS_PROTOCOL debe ser interactions o generateContent.')
        if mime.startswith(('audio/wav', 'audio/x-wav')):
            return raw
        if mime.lower().startswith(('audio/pcm', 'audio/l16')):
            rate = re.search(r'rate=(\d+)', mime)
            return pcm_wave(raw, int(rate.group(1)) if rate else 24000)
        raise ValueError(f'Formato Gemini no soportado: {mime}')


class ElevenLabsTTS:
    version = 'eleven-multilingual-v2:v1'
    def __init__(self):
        self.key = os.getenv('ELEVENLABS_API_KEY', '')
        if not self.key:
            raise ValueError('Falta ELEVENLABS_API_KEY en el entorno del worker.')
        self.model = os.getenv('ELEVENLABS_TTS_MODEL', 'eleven_multilingual_v2')
        self.version = self.model+':v1'
    def synthesize(self, text, voice, wpm):
        if not re.fullmatch(r'[\w-]{1,100}', voice):
            raise ValueError('Identificador de voz inválido.')
        r = httpx.post(f'https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=pcm_24000',
                       headers={'xi-api-key': self.key}, json={'text': text, 'model_id': self.model,
                       'voice_settings': {'stability': .65, 'similarity_boost': .8, 'speed': max(.7, min(1.2, wpm/140))}}, timeout=180)
        r.raise_for_status()
        return pcm_wave(r.content)


def provider(name):
    return {'local': LocalTTS, 'gemini': GeminiTTS, 'elevenlabs': ElevenLabsTTS}[name]()


def transcribe(path):
    if not os.getenv('ASR_MODEL'):
        return None
    from faster_whisper import WhisperModel
    model = WhisperModel(os.environ['ASR_MODEL'], device=os.getenv('ASR_DEVICE', 'cpu'), compute_type='int8')
    segments, _ = model.transcribe(str(path), language='es', beam_size=5, vad_filter=False)
    return ' '.join(s.text.strip() for s in segments)


def probe(path):
    import json
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(path)], check=True, capture_output=True)
    return float(json.loads(r.stdout)['format']['duration'])


def join_audio(paths, output):
    """Normalize each turn, fade only 8 ms at edges, add 120 ms pause; no speech overlap."""
    normalized = []
    for i, path in enumerate(paths):
        dest = output.parent / f'normalized-{i}.wav'
        duration = probe(path)
        if duration <= .02:
            raise ValueError('Segmento vacío o truncado.')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(path), '-af',
                        f'aresample=24000,afade=t=in:d=0.008,afade=t=out:st={max(0,duration-.008)}:d=0.008,apad=pad_dur=0.12',
                        '-ac', '1', '-c:a', 'pcm_s16le', str(dest)], check=True, capture_output=True)
        normalized.append(dest)
    concat = output.parent / 'concat.txt'
    concat.write_text(''.join(f"file '{p.name}'\n" for p in normalized))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '1', '-i', str(concat),
                    '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-c:a', 'libmp3lame', '-b:a', '128k', str(output)], check=True, capture_output=True)
    return probe(output)
