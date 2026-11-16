> Ensayo anterior del MVP gratuito. Las funciones actuales de Lectura fiel, DOCX/PDF y la revisión posterior están en [PERSONAL_READING.md](PERSONAL_READING.md) y [READING_RESULTS.md](READING_RESULTS.md).

# Calidad: audio real, sin APIs pagas

## Qué se ejecutó

Kokoro ONNX y Whisper-base int8 en CPU de Codex Cloud. Fuente y programa: muestra ya pública del repositorio, no apuntes privados nuevos. No hubo llamadas comerciales ni GPU. La revisión automatizada del demo ejercita el circuito; no equivale a aprobación de un docente.

**Resultado descargado y verificado:** MP3 de **607,848 segundos (10:08)**, **38 segmentos**, **8 capítulos**, voces neuronales españolas `ef_dora` y `em_alex`. 9.725.996 bytes. ZIP privado descargado por HTTP efímero interno y comprobado con SHA-256; se extrajo y cotejó también el MP3. Integridad de señal: muestras finitas, clipping 0%, RMS aproximado −16,06 dBFS después de normalización.

Se ejecutó además una regeneración real: se forzó `s37` del capítulo `c008`, **se sintetizó 1 segmento y se reutilizaron los otros 3 del capítulo**. Los demás capítulos conservaron su contenido. El paquete completo se volvió a descargar y verificar. Los valores reproducibles están en `free-cloud-evidence.json`; los archivos académicos completos quedan sólo en el workspace privado.

## Comparación de voces

Corpus breve fijo, escrito para esta prueba: acto jurídico, consentimiento, excepción y voseo (“vos tenés”). Transcripción con Whisper-base sin pasarle el texto como prompt. Puntuación y diacríticos se normalizan para calcular WER.

| Voz | Duración de muestra | WER observado | Decisión |
|---|---:|---:|---|
| Kokoro `ef_dora` | 10,227 s | 0% | Elegida para la profesora. |
| Kokoro `em_alex` | 10,561 s | 0% | Elegida para el profesor. |
| Kokoro `em_santa` | 11,119 s | 7,14% | Disponible como alternativa; discrepancia inicial del reconocimiento. |
| Piper `daniela` Argentina, integración experimental sherpa | 7,883 s | 28,57% | No pasó el umbral de esta muestra; excluida del CLI de producción. No concluye que todos los modelos Piper tengan esa calidad. |

Todas las muestras dieron señal finita y sin clipping medido. El script `tools/benchmark_open_voices.py` permite repetir el ensayo sin publicar archivos. Piper requiere `models --piper` y `--experimental-piper`; no se usa como fallback.

## Fidelidad del episodio completo

- Guion: **100% de cobertura estructural**, conservando todos los bloques de la fuente y su matriz. No se resumió para cumplir la duración.
- ASR: **25/38 segmentos pasaron** los controles; **13 requieren revisión**. El paquete queda **`unverified`**, no publicado ni certificado.
- WER ponderado de reconocimiento frente al texto hablado: **9,06%**, después de la regeneración. Es una comparación ASR/texto, **no un porcentaje demostrado de errores de síntesis**.
- Entre los segmentos marcados hay diferencias de cifras y léxico jurídico; no se observaron desacuerdos de los tokens de negación controlados (`no`, `nunca`, `salvo`, `excepto`). Esto no prueba ausencia de toda alteración semántica.
- IDs a cotejar: `s2, s6, s9, s13, s16, s19, s21, s29, s31, s33, s35, s37, s38`. En el JSON privado están el texto enviado, la transcripción y la referencia de fuente.

Whisper puede reconocer “dolo” como “dolor”, interpretar una enumeración como otro número o separar términos; también el TTS puede pronunciar mal. **Sin escuchar el pasaje no se puede atribuir cada discrepancia a uno u otro.** No se arreglan automáticamente afirmaciones jurídicas a partir de una transcripción insegura. Las ventanas ASR de pasajes largos también pueden introducir errores de frontera. Cifras escritas en letras versus dígitos producen rechazos conservadores.

## Evaluación y límites

La evidencia respalda **inteligibilidad útil en español y funcionamiento técnico**, especialmente en la muestra breve. No acredita fidelidad académica acústica completa, naturalidad conversacional ni dos acentos argentinos auténticos. No se realizó un panel de escucha ni una evaluación subjetiva MOS; no se inventa un puntaje de naturalidad. El modelo Kokoro usa español `es`, no una garantía `es_AR`. Que pronuncie voseo no demuestra acento rioplatense.

La voz explícitamente argentina investigada (Piper Daniela) no pasó esta integración/muestra, por lo que no se siguió produciendo con ella. Se eligió la alternativa Kokoro. Para material de estudio definitivo hay que escuchar las marcas y ajustar el diccionario o regenerar los segmentos defectuosos. El producto puede entregar un audio de revisión descargable, pero no debe ocultar esas marcas ni llamarlo verificado.

**Pruebas de software:** 37 aprobadas en el entorno, incluidas las 21 anteriores, una prueba neural real de dos voces CPU y pruebas de privacidad/descarga. En CI sin pesos, la prueba neural se marca skipped explícitamente. Hay una advertencia de deprecación de TestClient de terceros; no es una prueba fallida. El workflow público no sube los resultados académicos como artefactos.

**Persistencia:** los archivos privados se deben descargar antes de perder acceso a la sesión cloud. Este diseño no promete almacenamiento indefinido ni disponibilidad ilimitada por fuera de la cuota existente.
