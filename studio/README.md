# Academic Audio Studio

Aplicación privada para convertir una unidad y su programa en un guion trazable y audio de dos profesores. Next.js + FastAPI + worker durable + FFmpeg. La guía HTML original permanece intacta en la raíz del repositorio.

**Estado:** MVP documental ejecutable sin claves, con síntesis real offline. Adaptadores cloud y generación ampliada Gemini implementados; requieren claves, acceso de red y validación real con la cuenta elegida. La cobertura estructural no acredita verdad doctrinaria ni vigencia normativa. No se desplegó en Vercel/Supabase.

- [Investigación y licencias](docs/RESEARCH.md)
- [Arquitectura y controles académicos](docs/ARCHITECTURE.md)
- [Despliegue y configuración exacta de secretos](docs/DEPLOYMENT.md)
- [Validación ejecutada](docs/VALIDATION.md)
- [Hoja de ruta](docs/ROADMAP.md)

## Ejecutar localmente

Requisitos: Python 3.12, Node 24 y FFmpeg/ffprobe en PATH. En Linux x86_64 el wheel `espeakng-loader` incluye la biblioteca y sus datos; otras plataformas deben verificar wheel compatible. No necesita GPU para el MVP.

Desde `studio/`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
cd web
npm ci
npm run build
```

Tres terminales, con directorios explícitos:

```bash
# Terminal 1 — desde studio/backend
../.venv/bin/python -m uvicorn aas.api:app --host 127.0.0.1 --port 8010
```

```bash
# Terminal 2 — desde studio/backend; misma DATABASE_URL y STUDIO_DATA_DIR que API
../.venv/bin/python -m aas.worker
```

```bash
# Terminal 3 — desde studio/web
# Configurar STUDIO_LOGIN_USER y STUDIO_LOGIN_PASSWORD en el entorno del servidor.
# El servidor de producción rechaza acceso si faltan; no hay contraseña predeterminada.
npm start
# Alternativa sólo local: npm run dev (sin puerta de login si no se configuró).
```

La interfaz usa el puerto 3000 y envía las peticiones al backend mediante un proxy server-side. No hay llamadas TTS desde el navegador. No depender de estos procesos para una instalación permanente: ver despliegue.

## Flujo del MVP

1. Importar Markdown/texto UTF-8 de una unidad y un programa (un punto por línea; `;` divide puntos). PDF/DOCX no están implementados todavía.
2. Revisar la matriz de asociaciones propuesta por coincidencia de términos. Los subtítulos retienen sus ancestros; las asociaciones son editables. Un apartado sin fuente bloquea la síntesis.
3. Leer el guion completo. El modo documental conserva todos los bloques originales y agrega preguntas de examen basadas en los títulos. No resume ni rellena para llegar a una duración.
4. Opcional: proponer ampliaciones con Gemini y auditarlas con una segunda llamada. Explicaciones/ejemplos no reemplazan las citas originales. Los ejemplos deben estar rotulados. Las ampliaciones no verificadas bloquean la aprobación; editar una ampliación invalida su veredicto.
5. Guardar, auditar y aprobar la versión. Una modificación del texto, asociaciones o pronunciación invalida aprobación y audio anterior. “Corregir desde la fuente” restaura el guion completo; la interfaz advierte antes y se conserva el historial.
6. Seleccionar proveedor y dos voces diferentes. El proveedor local genera voz española sintética de **prueba**. Gemini es la primera opción cloud; ElevenLabs la alternativa. No hay fallback silencioso a otra voz.
7. Descargar guion, MP3 de revisión, cobertura/audio JSON y transcripción ASR (si está configurado). Un MP3 sin ASR se identifica como borrador sin verificar. `?release=true` bloquea la descarga de publicación si el cotejo ASR no pasó.
8. Para reparar audio, indicar IDs como `s3, s8`: sólo esos segmentos se fuerzan; los demás se recuperan de caché si texto, voz, velocidad, diccionario y motor coinciden.

La unidad de ejemplo se extrajo del `index.html` del mismo repositorio; no se presenta como una revisión jurídica externa. El objetivo de diez minutos es orientativo: el informe conserva duración estimada y medida. Se conserva todo el material aunque resulte más largo. Los términos escritos no se alteran por el diccionario de pronunciación; el informe registra también el texto efectivamente enviado a TTS.

## Pruebas

```bash
# Desde studio/backend
../.venv/bin/python -m pytest -q
# Desde studio/web
npm run typecheck
npm run build
npm audit --omit=dev
# Con API, worker y web levantados, navegador Chromium disponible:
# Configurar E2E_USER/E2E_PASSWORD según el login del servidor (o usar npm run dev).
node tests/e2e.cjs
```

La prueba de navegador usa el ejemplo completo, aprueba la matriz, genera voz real con dos variantes y descarga el MP3 y el informe. Requiere `CHROMIUM_PATH` si no está en `/usr/bin/chromium`. Los tests Gemini emplean contratos simulados y están nombrados como tales; no prueban la API comercial. Audio y resultados locales quedan ignorados por Git.
