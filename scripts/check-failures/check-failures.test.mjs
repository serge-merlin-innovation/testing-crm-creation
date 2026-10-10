import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { appendLines, formatLine, oneLine, record } from "./log.mjs";
import { firstErrorLine, parseOutput } from "./parse.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const tmpLog = () => path.join(fs.mkdtempSync(path.join(os.tmpdir(), "cf-")), "check-failures.log");
const read = (file) => fs.readFileSync(file, "utf8").split("\n").filter(Boolean);

test("a line is tab separated with an offset timestamp and a flattened message", () => {
  const line = formatLine(
    { kind: "typecheck", app: "frontend", location: "src/a.ts:1:7", message: "TS2322 Type\n  'string'\tis bad" },
    { now: new Date(2026, 9, 10, 0, 55, 27), rev: "main@abc1234" },
  );
  const [time, rev, kind, app, location, message, extra] = line.split("\t");
  assert.match(time, /^2026-10-10T00:55:27[+-]\d\d:\d\d$/);
  assert.deepEqual([rev, kind, app, location, message, extra], [
    "main@abc1234",
    "typecheck",
    "frontend",
    "src/a.ts:1:7",
    "TS2322 Type 'string' is bad",
    undefined,
  ]);
});

test("long messages are cut to one bounded line", () => {
  assert.equal(oneLine("x".repeat(1000)).length, 300);
});

test("the log keeps only the newest lines", () => {
  const file = tmpLog();
  appendLines(file, ["a", "b", "c"], 4);
  appendLines(file, ["d", "e"], 4);
  assert.deepEqual(read(file), ["b", "c", "d", "e"]);
});

test("nothing is written in CI", () => {
  const file = tmpLog();
  record([{ kind: "lint", app: "x", location: "l", message: "m" }], { env: { CI: "true", CHECK_FAILURES_LOG: file } });
  assert.equal(fs.existsSync(file), false);
});

test("record never throws when the log cannot be written", () => {
  const stderr = process.stderr.write;
  process.stderr.write = () => true;
  try {
    record([{ kind: "lint", app: "x", location: "l", message: "m" }], {
      env: { CHECK_FAILURES_LOG: "/nonexistent-dir/check-failures.log" },
    });
  } finally {
    process.stderr.write = stderr;
  }
});

test("ruff full output", () => {
  const out = `I001 [*] Import block is un-sorted or un-formatted\n --> src/_probe.py:1:1\n  |\nF401 [*] \`os\` imported but unused\n --> src/_probe.py:1:8\n\nFound 2 errors.`;
  assert.deepEqual(parseOutput(out), [
    { location: "src/_probe.py:1:1", message: "I001 Import block is un-sorted or un-formatted" },
    { location: "src/_probe.py:1:8", message: "F401 `os` imported but unused" },
  ]);
});

test("ruff concise output", () => {
  const colored = "\u001b[1msrc/a.py\u001b[0m:1:8: \u001b]8;;https://docs.astral.sh/ruff/rules/x\u001b\\F401\u001b]8;;\u001b\\ [*] `os` imported but unused";
  assert.deepEqual(parseOutput(colored), [{ location: "src/a.py:1:8", message: "F401 `os` imported but unused" }]);
  assert.deepEqual(parseOutput("src/a.py:1:8: F401 [*] `os` imported but unused\nFound 1 error."), [
    { location: "src/a.py:1:8", message: "F401 `os` imported but unused" },
  ]);
});

test("ruff format --check output", () => {
  assert.deepEqual(parseOutput("unformatted: File would be reformatted\n --> src/a.py:1:1\n  |\n1 file would be reformatted"), [
    { location: "src/a.py:1:1", message: "unformatted File would be reformatted" },
  ]);
  assert.deepEqual(parseOutput("Would reformat: src/a.py\n1 file would be reformatted"), [
    { location: "src/a.py", message: "would be reformatted" },
  ]);
});

test("mypy output", () => {
  const colored = "src/a.py:2: \u001b[31merror:\u001b(B\u001b[m Incompatible types  \u001b[33m[assignment]\u001b(B\u001b[m";
  assert.deepEqual(parseOutput(colored), [{ location: "src/a.py:2", message: "Incompatible types  [assignment]" }]);
  const out = `src/a.py:2: error: Incompatible types in assignment  [assignment]\npyproject.toml: note: unused section\nFound 1 error in 1 file`;
  assert.deepEqual(parseOutput(out), [{ location: "src/a.py:2", message: "Incompatible types in assignment  [assignment]" }]);
});

test("tsc output", () => {
  assert.deepEqual(parseOutput("src/a.ts:1:7 - error TS2322: Type 'string' is bad.\n\n1 const x: number = 'a';"), [
    { location: "src/a.ts:1:7", message: "TS2322 Type 'string' is bad." },
  ]);
  assert.deepEqual(parseOutput("src/a.ts(1,7): error TS2322: Type 'string' is not assignable to type 'number'."), [
    { location: "src/a.ts:1:7", message: "TS2322 Type 'string' is not assignable to type 'number'." },
  ]);
});

test("eslint stylish output keeps errors and drops warnings", () => {
  const out = `\n/repo/apps/frontend/src/a.ts\n  1:7  warning  'x' is unused    @typescript-eslint/no-unused-vars\n  2:1  error    Unexpected var, use let or const instead  no-var\n\n✖ 2 problems (1 error, 1 warning)`;
  assert.deepEqual(parseOutput(out, "/repo/apps/frontend"), [
    { location: "src/a.ts:2:1", message: "no-var Unexpected var, use let or const instead" },
  ]);
});

test("unparseable crashes fall back to the first error-looking line", () => {
  assert.equal(firstErrorLine("starting\nerror: Failed to spawn: `ruff`\n  Caused by: x"), "error: Failed to spawn: `ruff`");
});

const appDir = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "cf-")), "web");
fs.mkdirSync(appDir);

const run = (args, env) =>
  spawnSync(process.execPath, [path.join(here, "run.mjs"), ...args], {
    cwd: appDir,
    encoding: "utf8",
    env: { ...process.env, CI: "", CHECK_FAILURES_DISABLE: "", ...env },
  });

test("the wrapper passes output and exit code through and logs parsed errors", () => {
  const file = tmpLog();
  const script = `console.log("src/a.ts(3,1): error TS2304: Cannot find name 'y'."); process.exit(2)`;
  const res = run(["typecheck", "--", process.execPath, "-e", script], { CHECK_FAILURES_LOG: file });
  assert.equal(res.status, 2);
  assert.match(res.stdout, /TS2304/);
  const [line] = read(file);
  assert.deepEqual(line.split("\t").slice(2), ["typecheck", "web", "src/a.ts:3:1", "TS2304 Cannot find name 'y'."]);
});

test("the wrapper logs nothing on success", () => {
  const file = tmpLog();
  const res = run(["lint", "--", process.execPath, "-e", "console.log('ok')"], { CHECK_FAILURES_LOG: file });
  assert.equal(res.status, 0);
  assert.equal(fs.existsSync(file), false);
});

test("the wrapper logs a test run that died before its reporter spoke", () => {
  const file = tmpLog();
  const res = run(["test:unit", "--", process.execPath, "-e", "console.error('ImportError: boom'); process.exit(4)"], {
    CHECK_FAILURES_LOG: file,
  });
  assert.equal(res.status, 4);
  assert.match(read(file)[0], /\ttest:unit\tweb\t<run>\texit 4: ImportError: boom$/);
});

test("the wrapper adds nothing when the test reporter already logged", () => {
  const file = tmpLog();
  const script = `require("fs").writeFileSync(process.env.CHECK_FAILURES_SENTINEL, ""); process.exit(1)`;
  run(["test:unit", "--", process.execPath, "-e", script], { CHECK_FAILURES_LOG: file });
  assert.equal(fs.existsSync(file), false);
});

test("a run killed by a signal exits like the signal, without logging", () => {
  const file = tmpLog();
  const res = run(["lint", "--", process.execPath, "-e", "process.kill(process.pid, 'SIGTERM')"], { CHECK_FAILURES_LOG: file });
  assert.equal(res.signal ?? res.status, res.signal ? "SIGTERM" : 143);
  assert.equal(fs.existsSync(file), false);
});

test("parallel writers lose no lines", async () => {
  const file = tmpLog();
  const writer = (i) =>
    new Promise((resolve) => {
      const code = `import(${JSON.stringify(path.join(here, "log.mjs"))}).then((m) => m.record(Array.from({ length: 5 }, (_, j) => ({ kind: "lint", app: "w${i}", location: String(j), message: "m" }))))`;
      spawn(process.execPath, ["-e", code], { env: { ...process.env, CI: "", CHECK_FAILURES_LOG: file } }).on("close", resolve);
    });
  await Promise.all(Array.from({ length: 12 }, (_, i) => writer(i)));
  assert.equal(read(file).length, 60);
  assert.equal(fs.existsSync(`${file}.lock`), false);
});

test("an interrupted run is not a failure", () => {
  const file = tmpLog();
  run(["lint", "--", process.execPath, "-e", "process.kill(process.pid, 'SIGINT')"], { CHECK_FAILURES_LOG: file });
  assert.equal(fs.existsSync(file), false);
});
