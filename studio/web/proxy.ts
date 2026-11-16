import { NextRequest, NextResponse } from "next/server";
export function proxy(request: NextRequest) {
  const user = process.env.STUDIO_LOGIN_USER;
  const password = process.env.STUDIO_LOGIN_PASSWORD;
  if (!user || !password) {
    if (process.env.NODE_ENV === "production")
      return new NextResponse(
        "Configurá STUDIO_LOGIN_USER y STUDIO_LOGIN_PASSWORD en el servidor.",
        { status: 503 },
      );
    return NextResponse.next();
  }
  let valid = false;
  try {
    const [scheme, encoded] = (
      request.headers.get("authorization") || ""
    ).split(" ");
    if (scheme === "Basic" && encoded) {
      const decoded = atob(encoded);
      const expected = `${user}:${password}`;
      let diff = decoded.length ^ expected.length;
      for (let i = 0; i < expected.length; i++)
        diff |= (decoded.charCodeAt(i) || 0) ^ expected.charCodeAt(i);
      valid = diff === 0;
    }
  } catch {
    valid = false;
  }
  if (!valid)
    return new NextResponse("Acceso privado a Academic Audio Studio", {
      status: 401,
      headers: {
        "WWW-Authenticate":
          'Basic realm="Academic Audio Studio", charset="UTF-8"',
        "Cache-Control": "no-store",
      },
    });
  // Basic auth over HTTPS is the explicit single-workspace MVP boundary. No public multi-tenant mode.
  if (["POST", "PUT", "DELETE", "PATCH"].includes(request.method)) {
    const origin = request.headers.get("origin");
    if (
      origin &&
      origin !== request.nextUrl.origin &&
      new URL(origin).host !== request.headers.get("host")
    )
      return new NextResponse("Origen no permitido", { status: 403 });
  }
  return NextResponse.next();
}
export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
