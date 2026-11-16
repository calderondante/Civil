# Operación cloud gratuita y privacidad

## Decisión ejecutada

Se comprobó Codex Cloud primero: 4 CPU de cuota efectiva, 32 GiB de memoria, FFmpeg/ffprobe, descarga pública por GitHub/PyPI, sin GPU. Se instalaron Kokoro ONNX y reconocimiento Whisper ONNX. Se generó voz real en este entorno. Hugging Face respondió CONNECT 403; se usaron los archivos distribuidos por sus mantenedores en GitHub Releases, no se eludió la política de red. No se contrató ni activó ningún servicio.

El producto actual es una tarea cloud efímera: importar → preparar guion/matriz → revisar → aprobar → renderizar capítulos → descargar. No corre un servidor permanente. Next/FastAPI/Supabase y los adaptadores comerciales se conservan, pero quedan fuera de este flujo y no son requisitos.

## Costos y límites reales

“Inferencia sin costo adicional” significa CPU dentro de la cuota existente de Codex; no significa cómputo ilimitado ni una garantía de disponibilidad futura. Si se agota la cuota, detener/reanudar cuando vuelva a estar disponible; nunca comprar créditos, activar facturación ni sustituir por API paga. No se inspeccionó ni alteró un medio de pago.

GitHub Actions estándar tiene uso gratuito en repositorios públicos según la documentación consultada; los recursos privados, almacenamiento, retención y cuentas tienen cuotas/condiciones propias. **No se puede garantizar costo cero en una cuenta privada desconocida con facturación habilitada.** Por eso no se creó un workflow de producción privado ni un nuevo repositorio/hosting. La CI actual sólo valida código y material público, sin `upload-artifact` ni caches de escritura. No usa larger runners, GPU ni minutos de un servicio comercial.

## Por qué no usar artefactos de este repositorio público

[GitHub documenta](https://github.com/github/docs/blob/main/content/actions/how-tos/manage-workflow-runs/download-workflow-artifacts.md) que cualquier persona autenticada con lectura del repositorio puede descargar sus artefactos. En un repositorio público eso **no protege los apuntes**, aunque los artefactos no aparezcan en el árbol Git.

El CLI falla cerrado en Actions público o de visibilidad desconocida. La única excepción es `--public-demo`, que además exige que fuente y programa coincidan byte a byte con las muestras públicas versionadas. Un flag no permite enviar otro documento. En Actions privado exige visibilidad `private` y confirmación explícita de cuota/límite de gasto cero antes de cualquier procesamiento. No se creó ni ejecutó esa alternativa privada: el flujo Codex es el que sí se probó.

## Dónde quedan los datos

- Entradas privadas, revisiones, guiones, matrices, caché PCM, logs de motor y MP3: `/workspace/aas-private/<episodio>/`, fuera de cualquier checkout Git, con directorio 0700 y archivos 0600.
- El CLI rechaza salidas dentro del repo, dentro de otro checkout y a través de enlaces simbólicos. No confía sólo en `.gitignore`.
- La consola informa cantidades/estado, no texto de apuntes. Se capturan también los diagnósticos nativos porque un motor puede repetir el texto de entrada cuando falla. Esos logs quedan privados y se excluyen del ZIP.
- Sólo se descargan modelos públicos durante preparación. Fuente, guion y audio no se mandan a una API de inferencia, transcripción, base de datos ni almacenamiento externo.
- Los ZIP se construyen con una lista explícita de archivos permitidos. Contienen material académico para su dueño; **no deben subirse como artefactos de un repo público**.
- Descargas: enlaces de archivos del workspace de la conversación. La prueba de transferencia interna usa loopback, un token efímero, sin logs, una sola ruta, SHA-256 y cierre del servidor al terminar. No es un endpoint público ni alojamiento permanente.

La retención depende del ciclo de vida del entorno/chat, no de un hosting contratado. Descargar el ZIP antes de perder acceso a la sesión. No publicar una conversación compartida que contenga material privado. No prometer retención indefinida ni restauración en otro entorno sin una copia privada verificada.

## Fidelidad y versiones

`prepare` conserva texto original, offsets y jerarquía; cada apartado del programa sigue siendo obligatorio. Las líneas cercanas pueden agruparse en un turno conservando todas las referencias, sin cambiar su texto. Se mantiene cada bloque en el guion; no se acorta para lograr una duración artificial.

`review.json` permite editar asociaciones, turnos y pronunciación. La fuente, el programa y los bloques originales se cotejan contra el snapshot. `approve --reviewed` audita y firma la revisión exacta. No acepta certificados semánticos inyectados en el editor. El modo gratuito usa lectura dialogada documental; no ejecuta ampliación Gemini. Una revisión docente real sigue siendo necesaria para validar pertinencia y vigencia de normas.

`render` vuelve a validar la firma y bloquea cambios pendientes. Divide por apartados padre y presupuesto de palabras, conserva todos los segmentos y genera capítulos recuperables. Si falta un capítulo, el reporte dice incompleto y no entrega un ZIP/MP3 total. Al completar, produce el episodio con la misma secuencia del guion.

La caché depende del texto hablado, voz, velocidad, versión y hashes de modelos. Verifica hash del WAV antes de reutilizarlo. `--regenerate` fuerza sólo los IDs seleccionados. Las exportaciones anteriores se archivan privadamente cuando hay nueva aprobación.

## Audio y ASR

Kokoro ONNX usa exclusivamente `CPUExecutionProvider`, sin telemetría de sesión habilitada y sin descargas implícitas. Se fija el número de hilos. FFmpeg normaliza, agrega pausas cortas, aplica fades de extremos y exporta MP3; no mezcla fonemas de dos voces.

Whisper-base int8 en CPU se carga desde un archivo público verificado. No recibe el guion como prompt. Audita el texto realmente enviado a TTS por segmento; entradas largas se dividen en ventanas, no se truncan a 30 segundos. Se normalizan puntuación/diacríticos, se registra WER y se controlan cifras/negaciones. El rechazo de ASR es una señal para revisar, no una prueba automática de error del sintetizador. Un audio con discrepancias queda `unverified` aunque todo el guion tenga cobertura estructural.
