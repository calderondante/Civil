# Ensayo real de conversación magistral

Fecha: 2026-11-16. Base conservada: `d0b496c`, rama `feat/academic-audio-studio`. No se publican fuentes, citas privadas, guiones ni audio en Git. Evidencia agregada en `magistral-validation-evidence.json`; los entregables completos quedan en el workspace privado de la conversación.

## Ingreso y alcance

Se conservaron tres Word byte por byte fuera del checkout. El tercero se identifica internamente como V4; no se presumió por el nombre del archivo. Se extrajeron respectivamente 492, 405 y 1.332 registros, con cotejo de texto visible e inventario XML de párrafos no vacíos. Las notas y el campo PAGE de un pie expusieron dos fallos del extractor; ambos fueron corregidos y tienen regresiones sintéticas. Esa comprobación no certifica por sí sola el significado jurídico ni el diseño visual de Word.

Se descubrieron doce unidades, con 358 bloques de fuentes y lotes de revisión por instituto: Administrativo 6–9 y Contratos 7–14. V4 1–6 queda reservada. El mapa global conserva trabajo parcial, conexiones entre unidades y apartados pendientes; no declara completas las doce unidades. Falta cotejar un programa oficial independiente si se requiere certificar cobertura curricular: no se adjuntó uno separado en este pedido.

En Contratos se integraron V4 y V5 para el alcance elegido, sin duplicar exposiciones ni asignar prevalencia por fecha. Los demás pares de versiones están en una cola de revisión, sin resolver diferencias jurídicas mediante similitud textual. Las remisiones a fichas no adjuntadas no se usaron para inventar fallos.

## Dos MP3 generados y descargados

| Medición | Administrativo | Contratos |
|---|---:|---:|
| Duración real | 416,568 s · 6:57 | 422,928 s · 7:03 |
| Palabras del guion | 1.099 | 1.135 |
| Intervenciones / capítulos | 21 / 3 | 21 / 3 |
| Afirmaciones del alcance | 12 | 12 |
| Facetas con cotejo editorial registrado | 42 | 40 |
| Pares consecutivos de la misma voz | 2 | 3 |
| Coincidencias completas con Whisper base, tras normalización | 1 de 21 | 3 de 21 |
| Avisos de base resueltos por coincidencia completa de small | 9 | 3 |
| Pendientes después del segundo reconocimiento | 11 | 15 |
| De esos pendientes, diferencias críticas | 9 | 8 |

Kokoro ONNX, sólo CPU, dos voces `ef_dora`/`em_alex`, dos hilos por proceso. Parámetro de velocidad 145 en explicación ordinaria y 128–130 en distinciones densas. El parámetro regula una velocidad relativa: no implica que el motor produzca exactamente esas palabras por minuto. MP3 a 128 kb/s. La señal decodificada es finita, sin clipping medido, RMS de aproximadamente −16,02 dBFS en ambas muestras. Es una medición de señal, no una valoración de naturalidad.

Se generaron tres capítulos y un MP3 total por muestra. Se descargaron ambos ZIP por HTTP interno efímero, verificando SHA-256, integridad ZIP y coincidencia del MP3 extraído. No se contrató infraestructura ni se utilizó una API comercial, GPU o procesamiento en el equipo del usuario.

Los ZIP contienen guion, audio total y capítulos, matriz editorial Markdown/JSON, mapa de fuentes, transcripción, diferencias y segundo cotejo ASR. No contienen los Word originales, modelos, cachés o logs nativos. Los clips individuales para escucha quedan además en el workspace privado.

## Evaluación editorial y límites acústicos

Los guiones son redacciones originales cotejadas por Codex en la sesión suscripta. Ambos docentes desarrollan conceptos, varían hechos relevantes y recuperan distinciones. Hay continuidad del caso y reiteración deliberada; no se insertan preguntas de plantilla cada dos párrafos. Los ejemplos están reconocidos como hipotéticos y separados de las explicaciones de fuente. Las intervenciones consecutivas de una voz permiten completar una explicación sin alternancia mecánica.

El cotejo registra requisitos, excepciones, consecuencias y referencias dentro del alcance declarado. Cada faceta tiene evidencia de fuente, desarrollo concreto y razón editorial. Los hashes sólo invalidan revisiones después de cambios: no prueban equivalencia jurídica. **No se certifica cobertura semántica del cien por ciento**, exhaustividad de toda la unidad, vigencia normativa externa ni revisión docente independiente.

Whisper-base y Whisper-small int8 se ejecutaron sin prompt del guion. El segundo reconocimiento aporta evidencia de error del primero en doce segmentos, pero deja veintiséis abiertos. Persisten confusiones de límites de palabras, términos jurídicos, sufijos de artículos, números y al menos una negación. Se amplió el vocabulario crítico del comparador para no tratar las diferencias de excusión/exclusión o bis/ter como cambios menores. No se agregaron equivalencias que oculten esas diferencias.

**Ambos audios siguen `unverified`.** No se realizó escucha humana: no se confirmaron defectos de TTS por esa vía ni se regeneraron segmentos indiscriminadamente. Dos reconocedores no sustituyen la escucha humana. Las voces no están certificadas como rioplatenses, y la prosodia sigue siendo la de un TTS por turnos, con menor espontaneidad que una conversación humana. No se declara equivalencia con NotebookLM ni calidad acústica completa. Para una aceptación auditiva conviene priorizar los diecisiete segmentos con diferencias críticas y luego los nueve residuales.

## Regresiones y siguiente etapa

La suite final ejecutó **103 pruebas aprobadas, ninguna omitida**, incluida síntesis real Kokoro con las dos voces; sólo hubo un aviso previo de deprecación de TestClient. Se mantienen las pruebas anteriores. Se añaden inventarios, facetas, ejemplos que no sustituyen reglas, revisiones vencidas, artículos con sufijos/rangos, excepciones, partición completa de capítulos, originales alterados, privacidad de Actions, caché y ritmo por segmento, reanudación, regeneración selectiva, descarga de matriz, progreso parcial y vinculación del segundo ASR a los hashes correctos. La síntesis neural real y los MP3 extensos se probaron; los tests rápidos de recuperación usan además eSpeak como motor de integración, sin presentarlo como Kokoro.

La siguiente producción está preparada por unidades y lotes: inventario sustantivo → cotejo e integración de versiones → guion por capítulos → revisión de cada faceta → aprobación → audio → ASR y escucha. Las doce unidades completas todavía no están redactadas ni sintetizadas. La duración final dependerá del contenido; no se elimina texto para alcanzar una duración prefijada.
