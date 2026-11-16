"use client";
import { useState, useEffect } from "react";
type Block = {
  id: string;
  text: string;
  heading: string;
  line: number;
  start: number;
  end: number;
};
type Segment = {
  id: string;
  speaker: string;
  kind: string;
  text: string;
  source_ids: string[];
  topic_ids: string[];
};
type Audit = {
  passed: boolean;
  coverage_percent: number;
  estimated_minutes: number;
  word_count: number;
  duration_warning: string | null;
  method: string;
  findings: { code: string; message: string; segment_id: string | null }[];
  coverage: {
    id: string;
    title: string;
    source_ids: string[];
    covered: boolean;
  }[];
};
type Episode = {
  id: string;
  revision: number;
  title: string;
  blocks: Block[];
  segments: Segment[];
  mapping: Record<string, string[]>;
  pronunciation: Record<string, string>;
  approved: boolean;
  audit: Audit;
};
type Job = {
  id: string;
  status: string;
  error: string;
  result: {
    audio_status?: string;
    completed_segments?: number;
    total_segments?: number;
    duration_seconds?: number;
    segments?: {
      segment_id: string;
      cached: boolean;
      verification: { passed: boolean | null };
    }[];
  };
};
async function api(path: string, method = "GET", body?: unknown) {
  const r = await fetch("/api" + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const d = await r.json();
  if (!r.ok)
    throw Error(
      typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail),
    );
  return d;
}
export default function Studio() {
  const [tab, setTab] = useState("Material");
  const [source, setSource] = useState("");
  const [program, setProgram] = useState("");
  const [title, setTitle] = useState("Unidad 10 · Hechos y actos jurídicos");
  const [minutes, setMinutes] = useState(10);
  const [wpm, setWpm] = useState(170);
  const [ep, setEp] = useState<Episode | null>(null);
  const [episodes, setEpisodes] = useState<{ id: string; title: string }[]>([]);
  const [selected, setSelected] = useState(0);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [engine, setEngine] = useState("local");
  const [voices, setVoices] = useState(["es", "es+f3"]);
  const [caps, setCaps] = useState<Record<string, boolean | string>>({});
  const [job, setJob] = useState<Job | null>(null);
  const [dictionary, setDictionary] = useState("");
  const [regen, setRegen] = useState("");
  const [scriptJob, setScriptJob] = useState<Job | null>(null);
  const [depth, setDepth] = useState("explicativo");
  useEffect(() => {
    api("/episodes")
      .then(setEpisodes)
      .catch((e) => setError(e.message));
    api("/capabilities")
      .then(setCaps)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (ep) {
      setText(ep.segments[selected]?.text || "");
      setDictionary(JSON.stringify(ep.pronunciation, null, 2));
    }
  }, [ep, selected]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const timer = setInterval(() => {
      api("/jobs/" + job.id)
        .then(setJob)
        .catch((e) => setError(e.message));
    }, 1500);
    return () => clearInterval(timer);
  }, [job]);
  useEffect(() => {
    if (!scriptJob || !["queued", "running"].includes(scriptJob.status)) return;
    const timer = setInterval(
      () =>
        api("/jobs/" + scriptJob.id)
          .then(setScriptJob)
          .catch((e) => setError(e.message)),
      1500,
    );
    return () => clearInterval(timer);
  }, [scriptJob]);
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function receive(next: Episode) {
    setEp(next);
    setScriptJob(null);
    setReviewed(false);
    setSelected(0);
    setJob(null);
    localStorage.setItem("aas-last", next.id);
  }
  async function demo() {
    const [a, b] = await Promise.all([
      fetch("/demo-unit.md").then((r) => r.text()),
      fetch("/demo-program.md").then((r) => r.text()),
    ]);
    setSource(a);
    setProgram(b);
    setNotice(
      "Unidad de ejemplo extraída íntegramente del HTML original de este repositorio. No es una verificación de vigencia normativa.",
    );
  }
  async function upload(file: File | undefined, kind: string) {
    if (!file) return;
    if (!/\.(md|markdown|txt)$/i.test(file.name))
      throw Error(
        "El MVP admite Markdown o texto UTF-8. PDF y DOCX están en la hoja de ruta.",
      );
    if (file.size > 1000000) throw Error("Máximo 1 MB por archivo");
    const t = await file.text();
    if (kind === "source") setSource(t);
    else setProgram(t);
  }
  async function create() {
    receive(
      await api("/episodes", "POST", {
        title,
        source,
        program,
        target_minutes: minutes,
        wpm,
      }),
    );
    setTab("Cobertura");
    setEpisodes(await api("/episodes"));
  }
  async function changeMapping(pid: string, ids: string[]) {
    if (!ep) return;
    setEp(
      await api("/episodes/" + ep.id, "PUT", {
        revision: ep.revision,
        mapping: { ...ep.mapping, [pid]: ids },
      }),
    );
    setReviewed(false);
    setJob(null);
  }
  function chooseEngine(value: string) {
    setEngine(value);
    setVoices(
      value === "local"
        ? ["es", "es+f3"]
        : value === "gemini"
          ? ["Kore", "Puck"]
          : ["", ""],
    );
  }
  const seg = ep?.segments[selected];
  return (
    <div className="app">
      <aside className="rail">
        <a className="brand" href="/">
          a<span>·</span>a{" "}
          <small>
            ACADEMIC
            <br />
            AUDIO STUDIO
          </small>
        </a>
        <div className="workspace-label">ESPACIO DE PRODUCCIÓN</div>
        <nav>
          {["Material", "Cobertura", "Guion", "Audio"].map((t, i) => (
            <button
              key={t}
              className={tab === t ? "nav active" : "nav"}
              onClick={() => setTab(t)}
            >
              <span className="step">0{i + 1}</span>
              {t}
              {i > 0 && ep && <span className="dot" />}
            </button>
          ))}
        </nav>
        <div className="saved">
          <p>UNIDADES GUARDADAS</p>
          {episodes.length === 0 ? (
            <small>Tus unidades aparecerán acá.</small>
          ) : (
            episodes.map((e) => (
              <button
                key={e.id}
                onClick={() =>
                  action(async () => {
                    receive(await api("/episodes/" + e.id));
                    setTab("Cobertura");
                  })
                }
              >
                {e.title}
              </button>
            ))
          )}
        </div>
        <div className="rail-foot">
          <span className="live" /> Estudio privado
          <small>
            Fuentes antes que síntesis.
            <br />
            Cada versión deja una huella.
          </small>
        </div>
      </aside>
      <main>
        <header>
          <div className="eyebrow">DEL MATERIAL FUENTE AL AUDIO</div>
          <div className="header-row">
            <h1>
              {tab === "Material"
                ? "Una clase, sin perder el contenido."
                : tab === "Cobertura"
                  ? "Cada apartado tiene que estar."
                  : tab === "Guion"
                    ? "Primero las palabras. Después las voces."
                    : "Dos voces. Una versión aprobada."}
            </h1>
            <span className="badge">MVP · MODO DOCUMENTAL</span>
          </div>
          <p className="lede">
            Prepará un diálogo académico con fuentes a la vista, cobertura
            verificable y revisión antes de la síntesis.
          </p>
        </header>
        {error && (
          <div role="alert" className="message error">
            {error}
          </div>
        )}
        {notice && (
          <div role="status" className="message">
            {notice}
          </div>
        )}
        {tab === "Material" ? (
          <>
            <div className="section-heading">
              <h2>01 / Material de trabajo</h2>
              <button
                className="text-button"
                disabled={busy}
                onClick={() => action(demo)}
              >
                Cargar unidad de ejemplo ↗
              </button>
            </div>
            <div className="settings card">
              <label>
                Nombre de la unidad
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <label>
                Duración objetivo
                <select
                  value={minutes}
                  onChange={(e) => setMinutes(Number(e.target.value))}
                >
                  {[5, 10, 15, 30, 60, 90].map((n) => (
                    <option key={n} value={n}>
                      {n} minutos
                    </option>
                  ))}
                </select>
              </label>
              <div>
                <label>
                  Ritmo de síntesis
                  <select
                    value={wpm}
                    onChange={(e) => setWpm(Number(e.target.value))}
                  >
                    {[120, 140, 170, 190].map((n) => (
                      <option key={n} value={n}>
                        {n} palabras/min
                      </option>
                    ))}
                  </select>
                </label>
                <span className="tag">2 profesores</span>
                <p className="muted">
                  La duración se estima. Nunca se recorta la fuente para
                  ajustarla.
                </p>
              </div>
            </div>
            <div className="columns">
              <section className="card">
                <div className="card-title">
                  <h3>La unidad</h3>
                  <label className="upload">
                    Importar .md
                    <input
                      type="file"
                      accept=".md,.markdown,.txt"
                      onChange={(e) =>
                        action(() => upload(e.target.files?.[0], "source"))
                      }
                    />
                  </label>
                </div>
                <p className="muted">
                  Texto completo. Conservá títulos, artículos y excepciones.
                </p>
                <textarea
                  aria-label="Texto de la unidad"
                  className="material"
                  placeholder={"# Unidad\n## Concepto\nTexto de la fuente…"}
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                />
                <div className="caption">
                  {source.split(/\s+/).filter(Boolean).length} palabras · UTF-8
                </div>
              </section>
              <section className="card">
                <div className="card-title">
                  <h3>El programa obligatorio</h3>
                  <label className="upload">
                    Importar .md
                    <input
                      type="file"
                      accept=".md,.markdown,.txt"
                      onChange={(e) =>
                        action(() => upload(e.target.files?.[0], "program"))
                      }
                    />
                  </label>
                </div>
                <p className="muted">
                  Un punto por línea; cada punto entra en la matriz.
                </p>
                <textarea
                  aria-label="Programa obligatorio"
                  className="material"
                  placeholder={
                    "- Concepto y clasificación\n- Fundamento normativo\n- Excepciones y efectos"
                  }
                  value={program}
                  onChange={(e) => setProgram(e.target.value)}
                />
                <div className="caption">
                  Sin omisiones automáticas ni resumen por defecto.
                </div>
              </section>
            </div>
            <div className="bottom-bar">
              <p>
                Se genera una lectura dialogada íntegra con preguntas de examen.
                Podés pedir una ampliación con Gemini después; requiere clave y
                auditoría adicional.
              </p>
              <button
                className="primary"
                disabled={busy || !source || !program}
                onClick={() => action(create)}
              >
                {busy ? "Procesando…" : "Descomponer y crear guion →"}
              </button>
            </div>
          </>
        ) : !ep ? (
          <div className="card empty">
            <h2>Primero incorporá una unidad.</h2>
            <p>
              Necesitamos el material y el programa para construir una matriz
              verificable.
            </p>
            <button className="primary" onClick={() => setTab("Material")}>
              Ir al material
            </button>
          </div>
        ) : (
          <>
            <div className="summary">
              <div>
                <span className="eyebrow">
                  UNIDAD EN REVISIÓN · V{ep.revision}
                </span>
                <h2>{ep.title}</h2>
              </div>
              <div className="metric">
                <strong>{ep.audit.coverage_percent}%</strong>
                <span>Cobertura estructural</span>
              </div>
              <div className="metric">
                <strong>
                  {ep.audit.estimated_minutes}
                  <small> min</small>
                </strong>
                <span>{ep.audit.word_count} palabras estimadas</span>
              </div>
              <span className={"badge " + (ep.approved ? "good" : "")}>
                {ep.approved ? "Versión aprobada" : "Revisión pendiente"}
              </span>
            </div>
            {ep.audit.duration_warning && (
              <div className="message">{ep.audit.duration_warning}</div>
            )}
            {tab === "Cobertura" && (
              <>
                <div className="section-heading">
                  <h2>02 / Matriz obligatoria</h2>
                  <span className="muted">
                    {ep.blocks.length} bloques de fuente ·{" "}
                    {ep.audit.coverage.length} apartados
                  </span>
                </div>
                <div className="card matrix">
                  <div className="matrix-head">
                    APARTADO DEL PROGRAMA <span>FUENTES ASOCIADAS</span>
                  </div>
                  {ep.audit.coverage.map((p) => (
                    <details key={p.id}>
                      <summary>
                        <span className={p.covered ? "check" : "missing"}>
                          {p.covered ? "✓" : "!"}
                        </span>
                        <strong>{p.title}</strong>
                        <span className="source-count">
                          {p.source_ids.length} bloques ·{" "}
                          {p.covered ? "Cubierto" : "Falta cobertura"}
                        </span>
                      </summary>
                      <div className="mapping">
                        <p>
                          Revisá la asociación propuesta por coincidencia de
                          términos. Marcar un bloque sólo establece el vínculo;
                          debés comprobar su pertinencia académica.
                        </p>
                        {ep.blocks.map((b) => (
                          <label key={b.id}>
                            <input
                              type="checkbox"
                              checked={(ep.mapping[p.id] || []).includes(b.id)}
                              disabled={busy}
                              onChange={(e) =>
                                action(() =>
                                  changeMapping(
                                    p.id,
                                    e.target.checked
                                      ? [...ep.mapping[p.id], b.id]
                                      : ep.mapping[p.id].filter(
                                          (x) => x !== b.id,
                                        ),
                                  ),
                                )
                              }
                            />
                            <span>
                              <b>
                                {b.id} · {b.heading} · línea {b.line}
                              </b>
                              <br />
                              {b.text}
                            </span>
                          </label>
                        ))}
                      </div>
                    </details>
                  ))}
                </div>
                <p className="method">{ep.audit.method}</p>
                <div className="bottom-bar">
                  <a href={`/api/episodes/${ep.id}/export/report`}>
                    Descargar informe JSON ↓
                  </a>
                  <button className="primary" onClick={() => setTab("Guion")}>
                    Revisar guion →
                  </button>
                </div>
              </>
            )}
            {tab === "Guion" && (
              <>
                <div className="section-heading">
                  <h2>03 / Mesa de revisión</h2>
                  <a href={`/api/episodes/${ep.id}/export/script`}>
                    Descargar guion ↓
                  </a>
                </div>
                <div className="card" style={{ marginBottom: 20 }}>
                  <h3>Ampliar el diálogo con IA (opcional)</h3>
                  <p className="muted">
                    Gemini propone explicaciones y ejemplos con citas y una
                    segunda llamada los audita. Se conserva toda la fuente.
                    Requiere clave, consume API y necesita revisión docente;
                    todavía no se probó con una cuenta real.
                  </p>
                  <div className="voice-grid">
                    <label>
                      Profundidad
                      <select
                        value={depth}
                        onChange={(e) => setDepth(e.target.value)}
                      >
                        <option value="explicativo">
                          Fundamentos y excepciones
                        </option>
                        <option value="examen">
                          Preparación de examen oral
                        </option>
                      </select>
                    </label>
                    <button
                      disabled={
                        busy ||
                        (!!scriptJob &&
                          ["queued", "running"].includes(scriptJob.status))
                      }
                      onClick={() =>
                        action(async () => {
                          const j = await api(
                            "/episodes/" + ep.id + "/generate-dialogue",
                            "POST",
                            { revision: ep.revision, depth },
                          );
                          setScriptJob({ ...j, result: {}, error: "" });
                        })
                      }
                    >
                      Proponer diálogo con Gemini
                    </button>
                  </div>
                  {scriptJob && (
                    <p role="status">
                      Propuesta IA: {scriptJob.status} {scriptJob.error}
                    </p>
                  )}
                  {scriptJob?.status === "done" && (
                    <button
                      onClick={() =>
                        action(async () => {
                          setEp(
                            await api(
                              "/episodes/" +
                                ep.id +
                                "/apply-dialogue/" +
                                scriptJob.id,
                              "POST",
                              { revision: ep.revision, depth },
                            ),
                          );
                          setScriptJob(null);
                          setReviewed(false);
                          setJob(null);
                          setSelected(0);
                        })
                      }
                    >
                      Incorporar propuesta y revisar su auditoría
                    </button>
                  )}
                </div>
                <div className="editor-layout">
                  <section className="card segment-list">
                    {ep.segments.map((s, i) => (
                      <button
                        key={s.id}
                        onClick={() => setSelected(i)}
                        className={i === selected ? "selected" : ""}
                      >
                        <small>
                          {s.id} ·{" "}
                          {s.speaker === "profesora"
                            ? "PROFESORA A"
                            : "PROFESOR B"}{" "}
                          ·{" "}
                          {s.kind === "source"
                            ? "FUENTE"
                            : s.kind === "analysis"
                              ? "EXPLICACIÓN IA"
                              : s.kind === "example"
                                ? "EJEMPLO INVENTADO"
                                : "PREGUNTA"}
                        </small>
                        <span>{s.text.slice(0, 100)}…</span>
                      </button>
                    ))}
                  </section>
                  <section className="card editor">
                    {seg && (
                      <>
                        <div className="card-title">
                          <h3>
                            {seg.speaker === "profesora"
                              ? "Profesora A"
                              : "Profesor B"}
                          </h3>
                          <span className="tag">
                            {seg.id} · {seg.kind}
                          </span>
                        </div>
                        <textarea
                          aria-label="Editar segmento"
                          value={text}
                          onChange={(e) => setText(e.target.value)}
                        />
                        <button
                          disabled={busy || text === seg.text}
                          onClick={() =>
                            action(async () => {
                              setEp(
                                await api("/episodes/" + ep.id, "PUT", {
                                  revision: ep.revision,
                                  segments: ep.segments.map((s, i) =>
                                    i === selected ? { ...s, text } : s,
                                  ),
                                }),
                              );
                              setReviewed(false);
                              setJob(null);
                            })
                          }
                        >
                          Guardar y auditar
                        </button>
                        <h4>Respaldo en la fuente original</h4>
                        {seg.source_ids.map((id) => {
                          const b = ep.blocks.find((b) => b.id === id);
                          return (
                            <blockquote key={id}>
                              <small>
                                {id} · línea {b?.line} · caracteres {b?.start}–
                                {b?.end}
                              </small>
                              {b?.text}
                            </blockquote>
                          );
                        })}
                        <p className="muted">
                          El modo documental bloquea cambios doctrinarios sin
                          respaldo literal. Las ediciones invalidan la
                          aprobación y el audio anterior.
                        </p>
                      </>
                    )}
                  </section>
                </div>
                <div className="card audit">
                  <h3>
                    {ep.audit.passed
                      ? "✓ Auditoría estructural sin errores"
                      : "Errores que bloquean la síntesis"}
                  </h3>
                  {ep.audit.findings.map((f, i) => (
                    <p key={i}>
                      <b>{f.segment_id || f.code}</b> {f.message}
                    </p>
                  ))}
                  {!ep.audit.passed && (
                    <button
                      disabled={busy}
                      onClick={() =>
                        action(async () => {
                          if (
                            !confirm(
                              "Se restaurará todo el guion desde la fuente original. Tus ediciones quedan en el historial de versiones. ¿Continuar?",
                            )
                          )
                            return;
                          setEp(
                            await api(
                              "/episodes/" + ep.id + "/repair",
                              "POST",
                              { revision: ep.revision, matrix_reviewed: false },
                            ),
                          );
                          setReviewed(false);
                          setJob(null);
                        })
                      }
                    >
                      Corregir desde la fuente (restaura el guion completo)
                    </button>
                  )}
                  <label className="approval">
                    <input
                      type="checkbox"
                      checked={reviewed}
                      onChange={(e) => setReviewed(e.target.checked)}
                    />
                    Revisé el guion y la pertinencia de las asociaciones del
                    programa. Las fuentes conservan sus términos y referencias.
                  </label>
                  <button
                    className="primary"
                    disabled={busy || !reviewed || !ep.audit.passed}
                    onClick={() =>
                      action(async () => {
                        setEp(
                          await api("/episodes/" + ep.id + "/approve", "POST", {
                            revision: ep.revision,
                            matrix_reviewed: reviewed,
                          }),
                        );
                        setTab("Audio");
                      })
                    }
                  >
                    Aprobar esta versión →
                  </button>
                </div>
              </>
            )}
            {tab === "Audio" && (
              <>
                <div className="section-heading">
                  <h2>04 / Producción por segmentos</h2>
                  <span className="muted">
                    Se reutilizan los segmentos que ya están correctos.
                  </span>
                </div>
                <div className="columns">
                  <section className="card">
                    <h3>Dirección de voces</h3>
                    <label>
                      Proveedor
                      <select
                        value={engine}
                        onChange={(e) => chooseEngine(e.target.value)}
                      >
                        <option value="local">
                          Local · eSpeak · voz de prueba
                        </option>
                        <option value="gemini">
                          Gemini TTS {caps.gemini ? "" : "· falta API key"}
                        </option>
                        <option value="elevenlabs">
                          ElevenLabs {caps.elevenlabs ? "" : "· falta API key"}
                        </option>
                      </select>
                    </label>
                    <div className="voice-grid">
                      {voices.map((v, i) => (
                        <label key={i}>
                          {i === 0 ? "Profesora A" : "Profesor B"}
                          <input
                            aria-label={i === 0 ? "Voz A" : "Voz B"}
                            value={v}
                            onChange={(e) =>
                              setVoices(
                                voices.map((x, j) =>
                                  i === j ? e.target.value : x,
                                ),
                              )
                            }
                          />
                        </label>
                      ))}
                    </div>
                    <p className="muted">
                      {engine === "local"
                        ? "Español sintético de prueba, sin garantía de acento argentino. Dos variantes fijas; no clona personas."
                        : "El acento rioplatense y las pronunciaciones requieren una prueba de escucha con las voces elegidas."}
                    </p>
                    <details>
                      <summary>Diccionario de pronunciación</summary>
                      <textarea
                        aria-label="Diccionario de pronunciación"
                        value={dictionary}
                        onChange={(e) => setDictionary(e.target.value)}
                      />
                      <button
                        disabled={busy}
                        onClick={() =>
                          action(async () => {
                            setEp(
                              await api("/episodes/" + ep.id, "PUT", {
                                revision: ep.revision,
                                pronunciation: JSON.parse(dictionary),
                              }),
                            );
                            setJob(null);
                            setNotice(
                              "Diccionario guardado. Volvé a revisar y aprobar la versión.",
                            );
                            setTab("Guion");
                          })
                        }
                      >
                        Guardar diccionario e invalidar aprobación
                      </button>
                    </details>
                    <label>
                      Regenerar sólo estos segmentos (opcional)
                      <input
                        placeholder="s3, s8"
                        value={regen}
                        onChange={(e) => setRegen(e.target.value)}
                      />
                    </label>
                    <button
                      className="primary"
                      disabled={
                        busy ||
                        !ep.approved ||
                        (!!job && ["queued", "running"].includes(job.status))
                      }
                      onClick={() =>
                        action(async () => {
                          const j = await api(
                            "/episodes/" + ep.id + "/synthesize",
                            "POST",
                            {
                              revision: ep.revision,
                              provider: engine,
                              voices: {
                                profesora: voices[0],
                                profesor: voices[1],
                              },
                              regenerate: regen
                                .split(",")
                                .map((s) => s.trim())
                                .filter(Boolean),
                            },
                          );
                          setJob({ ...j, result: {}, error: "" });
                        })
                      }
                    >
                      Generar MP3 aprobado →
                    </button>
                    {!ep.approved && (
                      <p>
                        El guion necesita aprobación en la mesa de revisión.
                      </p>
                    )}
                  </section>
                  <section className="card audio-output">
                    <span className="audio-mark">◖◗</span>
                    <h3>
                      {!job
                        ? "El audio empieza en un buen guion."
                        : job.status === "done"
                          ? "Tu audio de revisión está listo."
                          : job.status === "failed"
                            ? "La síntesis necesita atención."
                            : "El worker está produciendo el audio…"}
                    </h3>
                    {job && (
                      <p role="status">
                        {job.status}{" "}
                        {job.result.completed_segments
                          ? `· ${job.result.completed_segments}/${job.result.total_segments} segmentos`
                          : ""}
                      </p>
                    )}
                    {job?.error && <p className="error">{job.error}</p>}
                    {job?.status === "done" && (
                      <>
                        <p>
                          {((job.result.duration_seconds || 0) / 60).toFixed(1)}{" "}
                          minutos reales ·{" "}
                          {job.result.audio_status === "verified"
                            ? "ASR aprobado"
                            : job.result.audio_status === "mismatch"
                              ? "ASR detectó diferencias"
                              : "ASR pendiente: borrador sin verificar"}
                        </p>
                        <audio
                          controls
                          src={`/api/jobs/${job.id}/download/audio`}
                        />
                        <div className="downloads">
                          {[
                            ["audio", "MP3 de revisión"],
                            ["script", "Guion"],
                            ["report", "Cobertura + audio"],
                            ["transcript", "Transcripción ASR"],
                          ].map(([key, label]) => (
                            <a
                              key={key}
                              href={`/api/jobs/${job.id}/download/${key}`}
                            >
                              {label} ↓
                            </a>
                          ))}
                        </div>
                        <p className="muted">
                          {job.result.segments?.filter((s) => s.cached)
                            .length || 0}{" "}
                          segmentos reutilizados. La descarga de publicación
                          está bloqueada hasta aprobar el cotejo ASR.
                        </p>
                      </>
                    )}
                    <p className="muted">
                      Los trabajos corren en un worker independiente. Cambiar de
                      pantalla no los cancela. El MP3 de revisión no implica
                      verificación académica ni acústica.
                    </p>
                  </section>
                </div>
              </>
            )}
          </>
        )}
        <footer>
          ACADEMIC AUDIO STUDIO{" "}
          <span>
            Material íntegro · referencias persistentes · aprobación por versión
          </span>
        </footer>
      </main>
    </div>
  );
}
