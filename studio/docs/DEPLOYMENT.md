# Desplegar sin depender de Codex

La instalación local fue ejecutada. **Los despliegues remotos, Docker y Supabase no se ejecutaron aquí.** Los archivos son configuración revisable, no evidencia de publicación.

## Interfaz en Vercel

1. Importar la rama del repositorio GitHub. Root Directory: `studio/web`. Framework: Next.js, build `npm run build`, install `npm ci`.
2. Configurar variables **server-side**: `API_URL` (URL HTTPS de FastAPI), `API_BEARER_TOKEN`, `STUDIO_LOGIN_USER`, `STUDIO_LOGIN_PASSWORD`. Generar secretos aleatorios fuertes desde el gestor del host; nunca escribirlos en Git ni en un chat.
3. Mantener HTTPS. El MVP ofrece un workspace privado con login del servidor, no registro público. Las rutas de proxy usan el bearer internamente. No configurar `NEXT_PUBLIC_GEMINI_API_KEY` ni `NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY`.

## Postgres y almacenamiento privado Supabase

1. Crear proyecto propio. Ejecutar `supabase/migrations/001_studio.sql` en SQL Editor. Crea tablas y bucket privado `academic-audio`, habilita RLS y revoca acceso de `anon`/`authenticated`. No agrega una política pública de descarga.
2. En API y worker: `DATABASE_URL` con la cadena exacta de conexión **session pooler o directa**, usando driver `postgresql+psycopg://` y `sslmode=require`. La contraseña va en secretos; codificar caracteres especiales como URL. No usar un pooler transaction sin comprobar compatibilidad del driver.
3. En API y worker: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_BUCKET=academic-audio`. La service role sólo se usa del lado servidor para Storage. La conexión DB usa el rol server de la cadena, no la clave REST de service role.
4. Usar el mismo proyecto en API y worker. El servidor descarga desde el bucket con credenciales privadas; el navegador recibe los bytes después de autenticarse. No hay URLs públicas permanentes.

El archivo `.env` lo consume Docker Compose; Python y Next no leen automáticamente el mismo archivo ubicado en `studio/`. En ejecución manual exportar las variables en cada proceso o usar el gestor de secretos del host.

## API y worker cloud

Usar `Dockerfile.backend` con contexto `studio/`, o instalar `backend/requirements.lock` y FFmpeg en el host. API: `python -m uvicorn aas.api:app --host 0.0.0.0 --port 8010`; worker: `python -m aas.worker`. Ambos desde el directorio donde está `aas/`.

API y worker: `STUDIO_ENV=production`, `API_BEARER_TOKEN` idéntico al de Vercel, conexión DB y Storage anteriores. Usar sólo HTTPS para el endpoint API o una red privada entre servicios. No exponer el backend de desarrollo sin token.

En local `compose.yaml` proporciona tres servicios reiniciables y volumen compartido. Crear `studio/.env` a partir del ejemplo y configurar login/token antes de `docker compose up --build -d`. Sólo publica web en loopback: para un dominio usar un ingress/reverse proxy HTTPS. No usar SQLite con varios contenedores sobre discos locales independientes; para escalar, Postgres y Storage comunes son obligatorios.

## Configurar Gemini exactamente

Obtener una API key en [Google AI Studio](https://aistudio.google.com/). Agregarla como secreto **GEMINI_API_KEY en el host de API y worker**. No hace falta en Vercel. Asegurar acceso HTTPS a `generativelanguage.googleapis.com` desde los workers.

- `GEMINI_TTS_MODEL=gemini-3.8-flash-tts`
- `GEMINI_TTS_PROTOCOL=interactions`
- Voces iniciales UI: `Kore` y `Puck`.
- `GEMINI_TEXT_MODEL` y `GEMINI_AUDIT_MODEL`: modelo de texto habilitado en tu cuenta (valor de ejemplo: `gemini-2.5-flash`; no se presupone disponibilidad). El modelo TTS no reemplaza al modelo de razonamiento.

El cookbook actual consultado usa 3.8. Confirmar en la cuenta el modelo y su acceso. Si se dispone solamente del modelo legacy, configurar `GEMINI_TTS_PROTOCOL=generateContent` y el ID TTS exacto habilitado. El adaptador no oculta incompatibilidades cambiando a otro modelo.

Prueba requerida después de configurar: una unidad corta, aprobación, síntesis de dos segmentos y verificación de formato/duración/escucha. Después probar ampliación de guion y revisar los dos resultados de modelo. No se efectuaron esas llamadas en este entorno porque no hay clave ni permiso de red al endpoint.

## Configurar ElevenLabs

Crear API key con permiso TTS en la cuenta y guardarla como `ELEVENLABS_API_KEY` en API/worker. Acceso HTTPS a `api.elevenlabs.io`. `ELEVENLABS_TTS_MODEL` configura el modelo (ejemplo conservador `eleven_multilingual_v2`). En la interfaz elegir ElevenLabs e introducir **dos voice IDs distintos**, obtenidos del catálogo autorizado de la cuenta. No usar los nombres de voz de Gemini como IDs. Confirmar tarifa y licencia comercial del plan y de las voces antes de producción.

## ASR y publicación verificada

Instalar el extra desde `backend/`: `../.venv/bin/python -m pip install '.[asr]'`. En contenedor añadirlo a una imagen derivada con un lock revisado. Fijar `ASR_MODEL` a un directorio local de modelo faster-whisper verificado o a un ID disponible, y `ASR_DEVICE=cpu` (o CUDA compatible para GPU). Descargar el modelo durante la preparación del worker para evitar que el primer audio quede esperando pesos. El modelo/versión también debe fijarse para reproducibilidad de producción.

La descarga inicial puede requerir `huggingface.co`, `*.huggingface.co`, `cas-bridge.xethub.hf.co`, `cas-server.xethub.hf.co` u otros hosts que indique la respuesta del proveedor. No desactivar TLS ni checksums. No se descargó ni ejecutó ASR real aquí. Tras configurar, volver a producir el job (el audio se reutiliza de caché; ASR se vuelve a ejecutar). Sólo entonces puede pasar `audio_status=verified` y habilitarse la descarga con `release=true`.

## Red de este entorno

El runtime actual permitió Git por proxy, GitHub público, npm y PyPI. Bloqueó con CONNECT 403 las páginas oficiales de tarifas y los endpoints no incluidos en allowlist. Para investigar precios agregar `ai.google.dev`, `cloud.google.com`, `elevenlabs.io`; para operar, los endpoints de API anteriores y el dominio exacto de tu Supabase. No se conoce todavía ese dominio porque no se configuró proyecto. Una edición de borrador de entorno no aplica cambios automáticamente: revisar/guardar en ajustes y publicar cuando corresponda. No se deben pedir nuevas claves para resolver un bloqueo puramente de red.
