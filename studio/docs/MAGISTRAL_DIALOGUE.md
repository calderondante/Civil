# Conversación magistral personal en Codex Cloud

`magistral_dialogue` permite guiones originales de dos docentes. **Codex en la conversación escribe y coteja el guion usando la suscripción existente**. El programa no invoca una API de lenguaje, no pretende generar una clase original mediante plantillas y no consume Gemini, ElevenLabs ni otro servicio comercial. Lectura fiel y documental conservan sus comandos y pruebas.

## Fuentes y cola de trabajo

Adjuntar las guías a Codex. Conservar originales intactos fuera del checkout, en un directorio privado. Crear también fuera de Git un manifiesto JSON con claves `admin`, `v4`, `v5`, cada una con `path`, `subject` (`administrativo` o `contratos`) y `role`. Roles: `main`, `doctrinal_depth`, `exam_priorities`. Todas las fuentes de este ingreso son DOCX; el importador de Lectura fiel también admite PDF textual.

Desde `studio/backend`, con el entorno del README:

```bash
../.venv/bin/python -m aas.magistral intake \
  --manifest /workspace/aas-private/inbox/manifest.json \
  --workdir /workspace/aas-private/corpus
```

El ingreso copia y verifica originales, inventaría párrafos/tablas/notas, conserva campos PAGE cacheados como texto y localizadores XML. Descubre unidades reales, evita entradas del índice y conserva el último párrafo. Administrativo se prepara en unidades 6–9 y Contratos en 7–14; V4 1–6 permanece reservada. Anexos, notas y fichas quedan localizados para incorporación explícita: no se atribuyen indiscriminadamente a la última unidad.

Cada unidad tiene candidatos textuales, bloques por instituto y lotes de revisión de fuentes. Los duplicados exactos comparten referencias. Las semejanzas entre versiones son una cola de comparación, **no una deduplicación semántica ni un dictamen de conflicto**. Codex debe integrar por instituto: profundidad de V4 y prioridades de V5, sin preferencia automática por fecha. Una remisión a ficha no autoriza inventar su contenido. Los lotes limitan el trabajo de una etapa, nunca la extensión del episodio.

`aas.magistral progress --corpus RUTA --episodes EPISODIO1 EPISODIO2` conserva el mapa global privado `unit-coverage-map.json`. Vincula afirmaciones y fuentes entre unidades y distingue trabajo parcial de unidad completa. La presencia de una referencia nunca marca automáticamente como íntegro todo el párrafo citado.

## Guion e inventario antes del audio

Procesar una unidad por vez. Primero descomponer cada apartado en afirmaciones esenciales; después escribir capítulos y comprobar también el final de cada apartado. Cada afirmación lleva `id`, `source_refs` con `source_id` y cita exacta, `rule`, `conditions`, `exceptions`, `quantities`, `consequences`, `relations`. Hereda materia, unidad e instituto de `scope`; dividir en episodios de alcance distinto cuando corresponda. Una lista vacía declara que esa faceta no corresponde, no que se omitió deliberadamente.

El archivo privado de autoría tiene:

- `title`, `scope` (incluidos límites y apartados pendientes), `source_selection` (`documento: [record_id]`), `claims`.
- `turns`: `id`, `speaker` (`profesora`/`profesor`), `rate_wpm` y `statements`. Cada afirmación tiene `text`, `claim_ids`, `type`: `source_explanation`, `inference`, `example`, `question` o `didactic_recall`.
- Los ejemplos llevan `hypothetical: true` y se reconocen también al escucharlos como supuestos inventados. Una inferencia o un ejemplo no sustituyen el desarrollo de una regla. La reiteración deliberada se tipa como tal.
- `reviews`, por afirmación: `method: codex_source_to_script_editorial_review`, `reviewer`, y `facets`. Para cada faceta no vacía: `status: reviewed`, `reason` con cotejo concreto y `supports` (`turn_id`, `quote` exacta del desarrollo). Es una revisión editorial explícita de Codex, nunca un panel humano ni un oráculo semántico.
- `cross_source_decisions`: decisiones cotejadas y razones; `status: unresolved` bloquea. `chapters`: `id`, `title`, `segment_ids`, partición completa y ordenada.

Hay una fixture sintética de este contrato en `backend/tests/test_magistral.py`. No se versionan guiones de los apuntes personales como ejemplos.

```bash
../.venv/bin/python -m aas.magistral assemble \
  --corpus /workspace/aas-private/corpus \
  --draft /workspace/aas-private/autoría/unidad7.json \
  --workdir /workspace/aas-private/unidad7
```

Leer el guion y el informe privado. Cotejar condiciones, excepciones, sujetos, cifras, artículos y consecuencias contra ambos sentidos fuente→guion y guion→fuente. El control automático exige evidencias, detecta vínculos vencidos, artículos sin respaldo y capítulos incompletos; **no demuestra por sí solo que una paráfrasis sea jurídicamente equivalente**. Un título o un ejemplo aislado no acreditan desarrollo. `coverage_percent` cuenta afirmaciones con registros editoriales válidos dentro del alcance declarado. `semantic_certified` permanece falso: ese porcentaje no debe anunciarse como fidelidad semántica del cien por ciento.

No hace falta alternar voces por párrafo: los dos docentes pueden desarrollar, preguntar o corregir. Usar continuidad, variación de hechos jurídicamente relevantes, ejemplos profesionales y reiteración útil. Evitar elogios enlatados, preguntas de plantilla, metáforas infantiles y extensas presentaciones. Ritmo sugerido: 145 en explicaciones ordinarias, 128–130 en condiciones complejas. `rate_wpm` regula velocidad relativa del motor; la duración real se mide, no se deduce de ese número.

## Aprobación, capítulos y recuperación

```bash
../.venv/bin/python -m aas.free_cloud approve \
  --workdir /workspace/aas-private/unidad7 --reviewed \
  --reviewer 'Codex: cotejo editorial de las fuentes adjuntas, alcance declarado'
../.venv/bin/python -m aas.free_cloud render \
  --workdir /workspace/aas-private/unidad7 \
  --models /workspace/aas-private/models --asr --threads 2
```

Usa Kokoro CPU (`ef_dora` y `em_alex`) y Whisper local sin prompt del guion. Seleccionar `--chapters c001` para una etapa, repetir para reanudar. No aparece un episodio completo mientras falten capítulos. La caché verifica voz, texto hablado, velocidad, motor y SHA-256; cada segmento y capítulo termina con un checkpoint.

Una edición sustantiva obliga a cotejar otra vez las facetas afectadas y crear una revisión:

```bash
../.venv/bin/python -m aas.magistral revise \
  --corpus /workspace/aas-private/corpus \
  --draft /workspace/aas-private/autoría/unidad7-corregida.json \
  --workdir /workspace/aas-private/unidad7
```

Conserva revisiones y audio anteriores, invalida la aprobación y archiva las descargas viejas. Volver a aprobar y renderizar: los WAV inalterados se reutilizan incluso entre revisiones. `--regenerate s4` fuerza únicamente un defecto confirmado de síntesis. Una discrepancia ASR requiere examen; no cambia automáticamente el guion ni sus negaciones o cifras. `review-audio` contrasta Whisper base con small y conserva clips para escuchar.

Después de `review-audio`, ejecutar `recheck --workdir RUTA` para incluir el segundo cotejo en el ZIP. Sólo se exporta si coinciden revisión, versión del comparador y hashes de audio. Los resultados ASR cacheados se reclasifican sin volver a cargar el modelo ni sintetizar voces.

## Entrega y límites

ZIP privado: MP3 completo y por capítulos, guion Markdown/JSON, matriz editorial Markdown/JSON, mapa de fuentes, transcripción e informe de diferencias. `aas.delivery.download_bundle` prueba transferencia interna con checksum y cierre del servidor efímero. Descargas en la conversación, nunca artefactos del repositorio público ni hosting persistente. Los documentos originales, cachés y logs nativos no entran al ZIP.

Las voces españolas de Kokoro no garantizan acento rioplatense ni prosodia de diálogo espontáneo. Integridad de señal y reconocimiento no sustituyen la escucha. La revisión se refiere a las guías adjuntas; no afirma que las normas citadas estén vigentes sin contraste externo. La cuota de Codex sigue siendo finita. No se garantiza equivalencia con NotebookLM, naturalidad completa ni retención indefinida del workspace.
