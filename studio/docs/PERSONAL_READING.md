# Escuchar apuntes personales: Lectura fiel

La herramienta es personal y por demanda en Codex Cloud. No requiere PC para procesar, cuentas de base de datos, hosting, GPU ni APIs comerciales. El cómputo consume la cuota existente: no se compra capacidad cuando se agota. Se conserva el código anterior y sus pruebas; no se reconstruyó la aplicación.

## Adjuntar y generar

Adjuntar el DOCX o PDF **textual** y el programa correspondiente a la unidad en esta conversación. Codex guarda los originales en `/workspace/aas-private/inbox/`, fuera de Git. El programa puede ser DOCX, PDF, Markdown o texto. Cada punto importado es obligatorio: un programa de toda la materia debe acotarse explícitamente a la unidad; no se descartan puntos silenciosamente.

Desde `studio/backend`, dentro de Codex:

```bash
../.venv/bin/python -m aas.free_cloud prepare \
  --source /workspace/aas-private/inbox/unidad.docx \
  --program /workspace/aas-private/inbox/programa.pdf \
  --workdir /workspace/aas-private/mi-lectura \
  --mode reading --voice-count 1
```

El CLI predetermina Lectura fiel; la función Python conserva el default documental por compatibilidad. Revisar `review.json`, `coverage-draft.json`, `import-source.json`, `import-program.json` y `spoken-plan-draft.json` antes de aprobar. Los originales se copian privadamente y se fijan por SHA-256; las revisiones incluyen el fingerprint de conversión.

```bash
../.venv/bin/python -m aas.free_cloud approve \
  --workdir /workspace/aas-private/mi-lectura --reviewed
../.venv/bin/python -m aas.free_cloud render \
  --workdir /workspace/aas-private/mi-lectura \
  --models /workspace/aas-private/models --asr --threads 2
```

No hay preguntas añadidas en Lectura fiel. Se leen todos los bloques y títulos, en orden, exactamente una vez. Una voz mantiene el narrador; con `--voice-count 2` cambia por capítulo, no por párrafo. Se conserva el modo anterior mediante `--mode documentary --voice-count 2`. La segmentación es técnica, no un resumen; se usan pausas breves entre fragmentos del mismo narrador.

## Importación y sus límites

**DOCX:** encabezados por estilos/outline, párrafos, listas automáticas, tablas en el orden del documento y celdas por fila. Las numeraciones anidadas conservan el formato de cada nivel. Cabeceras/pies de Word se conservan una vez por parte; no se inventa paginación. Notas se retienen con su ID y referencias. El inventario XML independiente exige recuperar todo párrafo no vacío y comparar su texto visible; los párrafos vacíos se contabilizan aparte. Los cuadros de texto o contenedores no soportados, numeraciones no resueltas y cambios controlados pendientes bloquean la importación; no se omiten sin aviso. No se acepta `.doc` binario como si fuera DOCX.

**PDF textual:** se conserva el orden geométrico y se detectan tablas con bordes. Se coteja que cada carácter decodificado no blanco se incorpore exactamente una vez. Esto **no equivale a recuperar una estructura nativa de párrafos que PDF no tiene**. Columnas ambiguas e imágenes requieren revisar la conversión; `approve --conversion-reviewed` registra esa revisión. Texto dentro de imágenes no se inventa. Páginas escaneadas o dominadas por una imagen y sin texto suficiente bloquean el documento, incluso cuando otras páginas sí tienen texto. OCR sigue fuera de este flujo.

Los lectores no ejecutan macros, acciones JavaScript del PDF ni instrucciones de los apuntes. No hay subida a una API de extracción.

## Guion escrito y representación hablada

El guion conserva literalmente el texto fuente. El plan hablado distingue expansiones de siglas, números, rangos y símbolos, con un registro `from/to` por regla. La política `es-ar-reading-v1` explicita cantidades para la voz; `es-ar-symbols-v1` aplica sólo reparaciones acotadas de símbolos, útil al corregir audio existente.

Ejemplos: `ARTÍCULO 4°` se pronuncia “artículo cuatro”, no “cuatro grados”; `1061-1068`, en una referencia plural a artículos, “mil sesenta y uno a mil sesenta y ocho”. `$250.000` se dice en pesos **sólo cuando el contexto declara pesos**; un símbolo monetario ambiguo exige una entrada explícita del diccionario y no se interpreta a ciegas. Las cifras escritas, nombres y afirmaciones jurídicas no se reescriben.

La política se guarda en `pronunciation.__policy__`, forma parte de la revisión aprobada y deja `spoken-plan-approved.json`. Editar pronunciación invalida aprobación. Render verifica los hashes de los originales y del manifiesto. Una modificación del Word, del programa, de los bloques o del modo no conserva una aprobación vieja.

## Diferencias y revisión de audio

La comparación normaliza cardinales en letras/cifras, millones, decimales, separadores españoles, importes con centavos y referencias ordinales/romanas contextualizadas. Controla valor, orden, signo, unidades, moneda, artículos, negaciones y términos jurídicos. Conserva `ñ`: año no equivale a ano. No convierte intención en intensión, dolo en dolor, lícito en ilícito ni prescripción en caducidad. Un WER pequeño ya **no basta** para aceptar palabras omitidas: cualquier diferencia residual queda para revisar.

Las equivalencias de representación aparecen en el informe; no se borra la transcripción original. Formatos ambiguos como `1061.168` no se reinterpretan como un rango para hacer pasar la prueba. Las ventanas largas de Whisper se cortan en intervalos silenciosos medidos y particionan todo el audio sin eliminar muestras. Se guarda caché del reconocimiento por hash de WAV y perfil del modelo, independiente de las reglas del comparador.

```bash
# Cambiar sólo la evaluación de transcripciones ya guardadas: cero síntesis nueva.
../.venv/bin/python -m aas.free_cloud recheck --workdir /workspace/aas-private/mi-lectura
# Segundo reconocedor para los casos señalados (CPU y pesos públicos, sin API).
../.venv/bin/python -m aas.free_cloud models --directory /workspace/aas-private/models --review-asr
../.venv/bin/python -m aas.free_cloud review-audio \
  --workdir /workspace/aas-private/mi-lectura --models /workspace/aas-private/models
```

La segunda transcripción es evidencia, no escucha humana ni certificación. Se distinguen representación equivalente, probable error del reconocedor y casos pendientes. No se regenera todo un episodio porque Whisper discrepe. El directorio privado `audio-review/` contiene guion, dos transcripciones, WAV y una página de escucha local; no se publica ni requiere hosting.

## Recuperar y descargar

Se puede reanudar el mismo `render` o producir sólo `--chapters c003`. Se reutilizan WAV verificados y reconocimientos guardados. `--regenerate s9` fuerza sólo ese segmento; versiones previas de audio se conservan privadamente. Una aprobación nueva archiva exportaciones anteriores. Usar un solo render activo por workspace; para lotes, carpetas privadas distintas.

El ZIP contiene MP3 completo, capítulos, guion, cobertura, `differences.json` y `transcript.txt`. `aas.delivery.download_bundle` verifica la descarga privada con SHA-256 y extrae el MP3. Un paquete completo en cantidad de capítulos puede seguir `unverified` por diferencias de audio. No se publica en GitHub ni se promete retención indefinida del entorno: descargar antes de perder la sesión.

El producto permite cotejar el material; no verifica vigencia de normas ni sustituye escucha personal. Las voces Kokoro no tienen una certificación humana de acento argentino.
