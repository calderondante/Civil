import { NextRequest } from "next/server";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
async function forward(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const base = process.env.API_URL || "http://127.0.0.1:8010";
  const url = new URL(
    path.map(encodeURIComponent).join("/") + request.nextUrl.search,
    base.replace(/\/$/, "") + "/",
  );
  const headers: Record<string, string> = {};
  if (process.env.API_BEARER_TOKEN)
    headers.Authorization = `Bearer ${process.env.API_BEARER_TOKEN}`;
  if (request.headers.get("content-type"))
    headers["Content-Type"] = request.headers.get("content-type")!;
  const body = ["GET", "HEAD"].includes(request.method)
    ? undefined
    : await request.arrayBuffer();
  if (body && body.byteLength > 2_000_000)
    return new Response("Máximo 2 MB", { status: 413 });
  try {
    const upstream = await fetch(url, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(25000),
    });
    const resultHeaders = new Headers({
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    });
    for (const h of [
      "content-type",
      "content-disposition",
      "x-audio-verification",
    ])
      if (upstream.headers.has(h))
        resultHeaders.set(h, upstream.headers.get(h)!);
    return new Response(upstream.body, {
      status: upstream.status,
      headers: resultHeaders,
    });
  } catch {
    return Response.json(
      { detail: "El servicio Python no responde. Revisá API_URL y el worker." },
      { status: 502 },
    );
  }
}
export { forward as GET, forward as POST, forward as PUT };
