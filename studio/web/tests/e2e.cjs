// Real browser + API + worker + local speech + MP3. Start the three services first.
const { chromium } = require("playwright");
const fs = require("node:fs/promises");
const fsSync = require("node:fs");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({
    executablePath:
      process.env.CHROMIUM_PATH ||
      (fsSync.existsSync("/usr/bin/chromium")
        ? "/usr/bin/chromium"
        : undefined),
    headless: true,
    args: ["--no-sandbox"],
  });
  try {
    const context = await browser.newContext({
      baseURL: process.env.E2E_URL || "http://127.0.0.1:3000",
      viewport: { width: 1440, height: 1000 },
      httpCredentials: {
        username: process.env.E2E_USER || "studio",
        password: process.env.E2E_PASSWORD || "local-browser-test-only",
      },
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(process.env.E2E_URL || "http://127.0.0.1:3000");
    await page
      .getByRole("button", { name: "Cargar unidad de ejemplo" })
      .click();
    await page.waitForFunction(
      () =>
        document.querySelector('textarea[aria-label="Texto de la unidad"]')
          .value.length > 5000,
    );
    await page
      .getByRole("button", { name: "Descomponer y crear guion" })
      .click();
    await page
      .getByRole("heading", { name: "02 / Matriz obligatoria" })
      .waitFor();
    await page.getByText("100%", { exact: true }).waitFor();
    assert.equal(await page.locator(".missing").count(), 0);
    await page.screenshot({
      path: process.env.E2E_SCREENSHOT || "/tmp/aas-coverage.png",
      fullPage: true,
    });
    await page.getByRole("button", { name: "Revisar guion" }).click();
    await page.getByRole("checkbox", { name: /Revisé el guion/ }).check();
    await page.getByRole("button", { name: "Aprobar esta versión" }).click();
    await page.getByText("Versión aprobada", { exact: true }).waitFor();
    await page.getByRole("button", { name: "Generar MP3 aprobado" }).click();
    await page
      .getByRole("heading", { name: "Tu audio de revisión está listo." })
      .waitFor({ timeout: 180000 });
    const href = await page
      .getByRole("link", { name: "MP3 de revisión" })
      .getAttribute("href");
    const response = await context.request.get(href);
    assert.equal(response.status(), 200);
    const bytes = await response.body();
    assert(bytes.length > 500000);
    await fs.mkdir("data", { recursive: true });
    await fs.writeFile("data/e2e-audio.mp3", bytes);
    const reportHref = await page
      .getByRole("link", { name: "Cobertura + audio" })
      .getAttribute("href");
    const report = await (await context.request.get(reportHref)).json();
    assert(
      report.duration_seconds >= 480 && report.duration_seconds <= 720,
      `duration ${report.duration_seconds}`,
    );
    assert.equal(report.audio_status, "unverified");
    assert.equal(report.audit.coverage_percent, 100);
    assert.equal(new Set(report.segments.map((s) => s.voice)).size, 2);
    assert.equal(errors.length, 0, errors.join(";"));
    const release = await context.request.get(href + "?release=true");
    assert.equal(release.status(), 422);
    await fs.writeFile("data/e2e-report.json", JSON.stringify(report, null, 2));
    await page.screenshot({ path: "/tmp/aas-audio.png", fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: "/tmp/aas-mobile.png", fullPage: true });
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    );
    console.log(
      JSON.stringify({
        passed: true,
        duration_seconds: report.duration_seconds,
        segments: report.segments.length,
        coverage: report.audit.coverage_percent,
        bytes: bytes.length,
        audio_status: report.audio_status,
        page_errors: errors.length,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
