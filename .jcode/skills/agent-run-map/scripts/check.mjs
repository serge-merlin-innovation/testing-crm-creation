// Headless check of the rendered agent maps. Usage:
//   node check.mjs --repo <repo> [--expect <n cards>] [--shots <dir>] <map.html> [<map.html> ...]
// Playwright is resolved from <repo>/apps/frontend (or <repo>, or $PLAYWRIGHT_DIR). Exit code 1 on any failure.
// Checks per file: card count, overlapping cards, page/console errors, network requests (all blocked), and that
// every postmortem link resolves to a file on disk.
import { createRequire } from "module";
import { existsSync } from "fs";
import { resolve, dirname, basename, join } from "path";

const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf(k); if (i < 0) return d; const v = argv[i + 1]; argv.splice(i, 2); return v; };
const repo = resolve(opt("--repo", process.cwd()));
const expect = opt("--expect", null);
const shots = opt("--shots", null);
const files = argv.map(f => resolve(f));

const roots = [process.env.PLAYWRIGHT_DIR, join(repo, "apps/frontend"), join(repo, "frontend"), repo].filter(Boolean);
let chromium;
for (const r of roots) {
  try { chromium = createRequire(join(r, "package.json"))("playwright").chromium; break; } catch {}
  try { chromium = createRequire(join(r, "package.json"))("@playwright/test").chromium; break; } catch {}
}
if (!chromium) { console.error("Playwright not found under " + roots.join(", ")); process.exit(2); }

const browser = await chromium.launch();
let failed = false;
for (const file of files) {
  const p = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  const errors = [], net = [];
  p.on("pageerror", e => errors.push(e.message));
  p.on("console", m => m.type() === "error" && errors.push(m.text()));
  await p.route("**/*", r => { const u = r.request().url(); if (!u.startsWith("file:")) { net.push(u); return r.abort(); } r.continue(); });
  await p.goto("file://" + file);
  const cards = await p.locator(".card").count();
  const wires = await p.locator("svg#wires path").count();
  const overlaps = await p.$$eval(".card", cs => { const r = cs.map(c => c.getBoundingClientRect()); let n = 0;
    for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++)
      if (r[i].left < r[j].right && r[j].left < r[i].right && r[i].top < r[j].bottom && r[j].top < r[i].bottom) n++;
    return n; });
  const hrefs = await p.$$eval("a.pm", as => as.map(a => a.getAttribute("href")));
  const missing = hrefs.filter(h => !existsSync(resolve(dirname(file), decodeURI(h))));
  if (shots) {
    const stem = join(shots, basename(file, ".html"));
    await p.evaluate(() => fit()); await p.screenshot({ path: stem + "-fit.png" });
    await p.evaluate(() => setZoom(1)); await p.screenshot({ path: stem + "-100.png" });
  }
  const ok = cards > 0 && (!expect || cards === +expect) && overlaps === 0 && errors.length === 0 && net.length === 0 && missing.length === 0 && wires > 0;
  failed ||= !ok;
  console.log(JSON.stringify({ file: basename(file), ok, cards, wires, overlaps, pmLinks: hrefs.length, missing, errors, net }));
  await p.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
