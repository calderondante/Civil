# Hoja de ruta

## 1. Cerrar la validación de producción

- Ejecutar Gemini TTS y ElevenLabs con cuentas reales; fijar versiones/voz/protocolo, cuotas y costos medidos. Benchmark es-AR con un docente y corpus jurídico; ningún proveedor obtiene aprobación por su ficha comercial.
- Ejecutar faster-whisper real, normalización de cifras/abreviaturas, cotejo de negaciones y regresiones acústicas. Conservar audio defectuoso y evidencia, no aprobar una transcripción por mayoría de tokens.
- Probar PostgreSQL/Storage privados con RLS, worker reiniciado durante un job y restauración de backup. Desplegar Vercel/API/worker con HTTPS, métricas de cola y alertas.
- Auditar ampliaciones IA con una cuenta real, otro modelo de auditoría si se dispone y evaluación docente. Agregar aceptación/rechazo por intervención sin perder revisión de cobertura. El adaptador actual no acredita calidad de explicación por sí solo.

Aceptación: un episodio argentino de diez minutos revisado, costos registrados, sin omisiones de programa, ASR ejecutado y discrepancias resueltas.

## 2. Importación documental

PDF con PyMuPDF (evaluar AGPL/licencia comercial) o pypdf para texto; OCR por separado con marcación de incertidumbre. DOCX con python-docx conservando títulos, tablas, notas y referencias. `source_locator` con página, párrafo, tabla/celda, offsets y hash del archivo original. No convertir silenciosamente un PDF escaneado en una extracción vacía. Interfaz de cotejo contra facsímil y corrección OCR antes de segmentar. Revalidar licencias de parsers y fuentes.

Aceptación: fixtures PDF/DOCX reales con tablas, artículos y notas; medición de extracción y trazabilidad de todos los apartados. La extracción de fuente no debe depender de un resumen por LLM.

## 3. Episodios de 30–90 minutos

Planificador por puntos obligatorios e instituciones: grafo de dependencias y presupuesto de palabras, sin dividir una excepción de su regla. Un apartado puede distribuirse entre episodios, pero el programa conserva estado global. Objetivo por episodio, profundidad y voces; preflight de duración/costos antes de API. Para voz, agrupar turnos cortos en lotes controlados manteniendo IDs y timestamps; no mandar 90 minutos como una única respuesta generativa.

Almacenamiento incremental, revisión por capítulos, checkpoints, reintentos con backoff por proveedor y cancelación cooperativa. Normalización sonora en dos pasadas, loudness medido, silencios y continuidad por locutor. Pruebas de cierre tardío, clipping, voz intercambiada y omisión de últimas páginas. La integridad no se puede medir sólo al principio de un episodio.

Aceptación: 90 minutos con todos los subtemas cubiertos, reinicio recuperable en cualquier segmento y regeneración selectiva que no facture el resto.

## 4. Varias materias y lotes

Modelo relacional por organización → materia → versión de programa → unidad → plan → episodio. Supabase Auth y RLS por propietario/tenant, roles editor/docente/revisor, invitaciones y auditoría de acceso. Migrar snapshots JSON a eventos/revisiones eficientes y contenido direccionado por hash. Las claves de caché deberán aislar tenants o contar con una política explícita de privacidad. No habilitar registro público con el esquema single-workspace del MVP.

Lotes con prioridad, límites por cuenta/proveedor, presupuesto máximo, idempotencia y programación. Dashboard con estado por apartado y costos/errores reales. Políticas de retención/borrado de documentos y voces, exportación de datos y backups.

## 5. Revisión académica avanzada

Vista sincronizada programa/fuente/guion/audio, diff por afirmación, referencias clicables a página, alertas por institución confundida y contradicciones. Tipos separados para doctrina original, explicación inferida, ejemplo hipotético y verificación externa. Registro externo de normas con URL oficial, jurisdicción, fecha de consulta, vigencia y evidencia; nunca presentar búsquedas del modelo como citas comprobadas.

Autocorrección acotada a una deficiencia documentada, explicación del cambio y nueva auditoría; bloqueo hasta aceptación del revisor cuando modifica significado. Diccionario por materia y proveedor (IPA/alias/SSML sólo si soportado), revisiones con ejemplos de audio. Exportar MP3, WAV, guion, fuentes, matriz y transcripción con timestamps/SRT.
