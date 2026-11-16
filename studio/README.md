# Academic Audio Studio — cloud, CPU y costo adicional cero

El flujo actual corre **por demanda dentro de Codex Cloud**, con voces neuronales abiertas en CPU y descargas privadas desde la conversación. No necesita tu PC, hosting permanente, Supabase, tarjetas, facturación ni APIs comerciales. Usa recursos de la cuota de Codex/ChatGPT que ya tengas disponible; esa cuota tiene límites y no se compra capacidad adicional automáticamente.

Se conserva la aplicación Next/FastAPI anterior, sus adaptadores y pruebas como implementación legacy opcional. **No es necesario levantarla para producir un podcast.** El flujo nuevo no importa su DB/Storage, no llama Gemini/ElevenLabs y no crea servicios persistentes.

- [Operación cloud gratuita y privada](docs/FREE_CLOUD.md)
- [Investigación TTS y licencias](docs/OPEN_TTS.md)
- [Calidad medida y limitaciones](docs/FREE_QUALITY.md)
- [Arquitectura anterior, conservada como referencia](docs/ARCHITECTURE.md)

## Uso desde Codex Cloud

Adjuntá una unidad y su programa en la conversación y pedí a Codex que use `aas.free_cloud`. Los archivos privados van en `/workspace/aas-private/`, **fuera del repositorio**, nunca en commits, issues ni parámetros públicos de Actions. Este MVP recibe Markdown/texto UTF-8; PDF/DOCX y OCR siguen pendientes de una importación estructurada y validada.

Preparación del entorno (dentro de Codex, no en tu PC):

```bash
cd /workspace/Civil/studio
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-free.lock
cd backend
# Descarga pesos públicos fijados por SHA-256; después la inferencia es local al cloud.
../.venv/bin/python -m aas.free_cloud models --directory /workspace/aas-private/models --asr
```

Producción, desde `studio/backend`:

```bash
../.venv/bin/python -m aas.free_cloud prepare \
  --source /workspace/aas-private/inbox/unidad.md \
  --program /workspace/aas-private/inbox/programa.md \
  --workdir /workspace/aas-private/mi-episodio
```

Revisar `review.json`, `plan.json`, `script-draft.md` y `coverage-draft.json`. No se sintetiza hasta auditar y aprobar explícitamente:

```bash
../.venv/bin/python -m aas.free_cloud approve \
  --workdir /workspace/aas-private/mi-episodio --reviewed
../.venv/bin/python -m aas.free_cloud render \
  --workdir /workspace/aas-private/mi-episodio \
  --models /workspace/aas-private/models --asr --threads 2
```

Voces predeterminadas: Kokoro `ef_dora` y `em_alex`, españolas y distintas. Se conserva íntegra la fuente, agrupando líneas cercanas para dar contexto a la voz; no se resume. El informe no certifica vigencia jurídica ni acento argentino. Ver evaluación.

El resultado privado contiene `academic-audio.zip`, `deliverables/podcast.mp3`, MP3 por capítulo, guion Markdown/JSON e informe de cobertura/audio. Codex entrega enlaces de descarga a estos archivos. `aas.delivery.download_bundle` prueba además una descarga HTTP efímera interna, verifica SHA-256 y extrae el MP3; no deja un servidor corriendo ni hace una publicación.

## Capítulos y regeneración

```bash
# Producir sólo un capítulo; no se arma un episodio completo mientras falten otros.
../.venv/bin/python -m aas.free_cloud render \
  --workdir /workspace/aas-private/mi-episodio \
  --models /workspace/aas-private/models --chapters c002 --asr
# Forzar sólo un segmento defectuoso. Los demás se reutilizan desde caché verificada.
../.venv/bin/python -m aas.free_cloud render \
  --workdir /workspace/aas-private/mi-episodio \
  --models /workspace/aas-private/models --regenerate s4 --asr
```

Cada aprobación conserva una revisión inmutable. Una edición sin aprobar bloquea render; una nueva aprobación archiva las exportaciones anteriores para no confundirlas con la versión nueva. Un apartado faltante o una cita alterada bloquea la síntesis. El cotejo ASR registra discrepancias reales, sin dar por verificado un audio sólo porque existe un MP3.

## GitHub y pruebas

El repositorio público guarda **sólo código, tests, documentación y la muestra que ya era pública**. El workflow CI usa runners Linux estándar y no sube artefactos ni escribe caches. No se usa Actions público para apuntes privados. Se eligió Codex porque la inferencia y la entrega privadas funcionan aquí sin agregar infraestructura; no hace falta contratar otra cosa.

```bash
# Desde studio/backend, con los modelos ya preparados:
AAS_OPEN_MODEL_DIR=/workspace/aas-private/models ../.venv/bin/python -m pytest -q
```

La suite conserva las 21 pruebas anteriores y añade pruebas de privacidad, capítulos, versiones, regeneración, descarga real y dos voces Kokoro en CPU. Sin pesos configurados, el test neural se marca **skipped**, no aprobado. Los contratos de los adaptadores comerciales anteriores siguen simulados y no consumen sus APIs.
