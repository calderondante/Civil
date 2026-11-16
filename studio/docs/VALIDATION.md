# Evidencia de validación

## Ejecutado realmente en este entorno

- Instalación Python en virtualenv nuevo desde lockfile; Node/npm con lockfile. FFmpeg y Chromium reales.
- Suite backend (21 pruebas automatizadas): cobertura obligatoria, partición sin pérdida (incluido final de párrafos largos), offsets y asociaciones, títulos padre, alteración de artículos, ejemplos sin respaldo, invalidación de aprobación, concurrencia de versiones, autenticación/límite de tamaño, reparación documentada, audio local, caché/regeneración selectiva, descarga de versiones antiguas y recuperación de lease.
- Prueba de navegador Chromium con la build de producción Next: cargar unidad/programa, matriz 100% estructural, revisar/aprobar, generar MP3 real con dos voces, descargar audio/informe, bloquear publicación sin ASR y verificar diseño móvil sin desborde ni errores JavaScript.
- Resultado de esa prueba: **649,776 segundos (10 min 49,8 s)**, **104 segmentos**, dos variantes eSpeak `es`/`es+f3`, **10.396.844 bytes**, **100% de cobertura estructural**, `audio_status=unverified`. No es evaluación de naturalidad/acento ni confirmación de contenido jurídico.
- El script de navegador y la evidencia resumida están versionados. El MP3, guion y JSON completos están en `web/data/` ignorados por Git.
- `npm run build` compila TypeScript y genera el sitio. `npm audit --omit=dev --audit-level=high` no encontró vulnerabilidades en la ejecución registrada.

## Simulado de forma explícita

- Gemini TTS: test de contrato HTTP/PCM con respuesta simulada según el formato de Interactions; no valida acceso del modelo, precio o voz en una cuenta real.
- Generación ampliada: dos respuestas simuladas para comprobar preservación de fuente, obligatoriedad de auditoría, guardia de artículos e invalidación de veredicto después de editar. No acredita calidad docente del modelo.
- Desacuerdo ASR: transcripción inyectada para comprobar bloqueo. No se ejecutó reconocimiento sobre el MP3 real.

## No ejecutado

Gemini/ElevenLabs reales (faltan claves y acceso al endpoint); faster-whisper real (sin modelo configurado); Supabase/Postgres/Storage reales (sin proyecto/credenciales); despliegue Vercel/cloud y construcción de contenedores. El código y la configuración están preparados, pero estos puntos requieren validación posterior. Las tarifas y condiciones comerciales actuales de APIs no se pudieron leer por CONNECT 403.

La aprobación humana durante la prueba de navegador es una acción de automatización para ejercitar el circuito; no equivale a una revisión docente real del material de ejemplo. El contenido original puede contener errores y no fue cotejado con fuentes normativas externas.
