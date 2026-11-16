# Ensayos reales: lectura personal y revisión de audio

## Continuidad

Se trabajó sobre `15a4213`, en `feat/academic-audio-studio`. Se conservan CPU, archivos privados, aprobaciones por versión, capítulos, caché y regeneración selectiva. Las 37 pruebas anteriores se mantienen sin editar. No se usaron APIs comerciales, hosting, base de datos remota ni GPU.

## Los 13 avisos anteriores

Se cotejaron el guion, la transcripción base, los WAV originales verificados por hash y una segunda transcripción Whisper-small int8 offline, sin pasarle el guion como prompt. Se conservaron ambas transcripciones y clips para escuchar. No hubo una escucha humana certificada: no se usa “error confirmado de síntesis” como sinónimo de desacuerdo ASR.

| Clasificación | Cantidad | IDs |
|---|---:|---|
| Equivalencias explícitas de representación | 7 | s9, s19, s21, s29, s31, s33, s35 |
| Probable error del primer reconocedor: la segunda transcripción coincide tras normalización | 3 | s6, s13, s37 |
| Pendientes de escucha/cotejo acústico | 3 | s2, s16, s38 |

Ejemplos: letras/cifras y “examenoral” no son omisiones del apunte. En s37, base produjo `1061.168`, pero small recuperó el rango `1061-1068`. **No se reinterpretó el primer número ambiguo para forzar un aprobado**. En s38 los reconocedores discrepan también entre sí sobre referencias; el guion no se cambia por esa evidencia incierta. No se regeneraron indiscriminadamente esos 13 audios.

La revisión completa, página de escucha y WAV están sólo en el workspace privado, con un ZIP descargable; no se subieron al repositorio.

## Prueba de Word/PDF y lectura continua

Material: **Unidad 9, Persona Jurídica**, completa, del `index.html` que ya estaba en el repositorio. Se construyó un DOCX conservando sus 83 bloques, títulos, listas y párrafos, y se comparó cada párrafo original con la extracción. La misma unidad se exportó como PDF textual de cinco páginas y se verificó el inventario de caracteres. El programa de ensayo procede del índice de esa unidad. **No se recibió un nuevo Word/PDF del usuario ni un programa oficial adjunto**; no se presenta este ensayo como validación de un archivo no suministrado.

- Fuente: **1.483 palabras**, **83/83 párrafos Word recuperados**, PDF de **5 páginas** sin caracteres decodificados perdidos en la prueba.
- Lectura fiel: **una voz Kokoro `ef_dora`**, **15 segmentos**, **8 capítulos**, sin preguntas añadidas ni alternancia de párrafos.
- MP3 final: **686,208 segundos, 11:26**, completo, con **100% de cobertura estructural**.
- Señal: muestras finitas, sin clipping medido, RMS aproximado −16,03 dBFS. No son medidas de acento ni naturalidad subjetiva.
- Se descargó el ZIP privado, se verificó SHA-256 y se extrajo/cotejó el MP3 real.

## Interrupción real y reparación selectiva

Se terminó el proceso con **SIGTERM, salida −15**, después de tres segmentos guardados. Al reanudar la misma revisión, se reutilizaron esos tres WAV y se completaron los restantes. No se perdió texto ni se fabricó un episodio completo mientras faltaban capítulos.

La prueba detectó dos problemas efectivos del frente de pronunciación, además de las incertidumbres ASR:

1. `ARTÍCULO 4°` se fonemizaba con “cuatro **grados**”.
2. `$250.000` se fonemizaba con “**dólar**” aunque su párrafo decía expresamente PESOS.

El análisis de los fonemas de entrada a Kokoro y el reconocimiento del audio coincidían en esas palabras: no eran sólo errores de representación numérica del reconocedor. Se aplicó una política aprobada de lectura de símbolos, manteniendo **intacto el texto jurídico escrito**. El monto se verbaliza con su valor exacto y “pesos”; el marcador ordinal de artículo no se trata como temperatura.

Se regeneraron **únicamente s7, s8, s9, s10 y s11**. Los **10 WAV restantes conservaron exactamente sus hashes**. Se conservaron la revisión y exportación anteriores. En el reconocimiento posterior ya no aparecen “grados” ni “dólar” en esos lugares. Esto acredita la corrección concreta del frente, no una escucha humana de toda la unidad.

## Estado real de verificación

El nuevo comparador es más estricto que el inicial: no acepta un texto por tener WER menor al 12%; cualquier diferencia residual sigue visible, y cifras, unidades, negaciones, referencias y términos tienen controles específicos. Por eso no se comparan directamente porcentajes de aprobados entre ambas políticas.

En la unidad nueva, **2/15 segmentos coincidieron completamente tras normalización y 13 quedaron pendientes**; el archivo continúa **`unverified`**. Entre las diferencias hay nombres propios, léxico jurídico, límites de palabras y “mil” reconocido como “ml”. No se normalizó “ml” a “mil”: podría ocultar una diferencia sustancial de cantidad/unidad. La transcripción automática por sí sola no permite decidir todos esos casos.

El informe privado contiene cada diferencia y sus valores críticos; no se afirma fidelidad acústica completa, vigencia normativa ni un acento argentino certificado. La muestra es una unidad de cinco páginas, no una prueba de libro de cientos de páginas. Los PDF escaneados, contenedores Word no soportados, revisiones pendientes y diseños ambiguos se detectan/bloquean o exigen revisión; no se inventa contenido para continuar.

## Regresiones

La suite conserva las pruebas anteriores y añade cantidades en letras, centavos, decimales, moneda, años/ano, rangos ambiguos, negaciones desplazadas, términos jurídicos confundibles, ordinales/romanos, títulos, orden sin duplicados, una/dos voces, tablas/listas anidadas, escaneados, Word con contenido no soportado, originales alterados, ventanas de audio sin pérdida, caché ASR y reauditoría sin síntesis. Resultados numéricos del ensayo en `reading-validation-evidence.json`; los documentos y audios no se versionan en Git.
