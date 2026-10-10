#!/usr/bin/env node
// Runs a check, passes its output and exit code through untouched, and logs each error it reported.
// Usage: node scripts/check-failures/run.mjs <kind> -- <command> [args...]
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { appName, record } from "./log.mjs";
import { firstErrorLine, parseOutput } from "./parse.mjs";

const MAX_CAPTURE = 5 * 1024 * 1024;

const argv = process.argv.slice(2);
const sep = argv.indexOf("--");
const kind = argv[0];
const command = sep === -1 ? [] : argv.slice(sep + 1);
if (!kind || sep !== 1 || command.length === 0) {
  process.stderr.write("usage: run.mjs <kind> -- <command> [args...]\n");
  process.exit(2);
}

// A test runner's own reporter touches this file when it logs, so the wrapper only adds a line
// for a run that died before any reporter could speak.
const sentinel = path.join(os.tmpdir(), `check-failures-${process.pid}-${Date.now()}`);

// Piping the child's output makes tools think they are not on a terminal, so colour is forced back
// on for interactive runs; the parsers strip it.
const forceColor = process.stdout.isTTY && process.env.FORCE_COLOR === undefined && !process.env.NO_COLOR;

const child = spawn(command[0], command.slice(1), {
  stdio: ["inherit", "pipe", "pipe"],
  env: { ...process.env, ...(forceColor ? { FORCE_COLOR: "1" } : {}), CHECK_FAILURES_SENTINEL: sentinel },
});

let captured = "";
const tee = (stream, target) =>
  stream.on("data", (chunk) => {
    target.write(chunk);
    if (captured.length < MAX_CAPTURE) captured += chunk.toString();
  });
tee(child.stdout, process.stdout);
tee(child.stderr, process.stderr);

// Ctrl-C reaches the child through the process group; the wrapper waits to mirror its exit.
const ignore = () => {};
const forwarded = ["SIGINT", "SIGTERM", "SIGHUP"];
for (const sig of forwarded) process.on(sig, ignore);

child.on("error", (err) => {
  record([{ kind, app: appName(), location: "<run>", message: `${command.join(" ")}: ${err.message}` }]);
  process.exit(127);
});

child.on("close", (code, signal) => {
  const interrupted = signal !== null || code === 130 || code === 143;
  const reporterSpoke = fs.existsSync(sentinel);
  fs.rmSync(sentinel, { force: true });

  if (code !== 0 && !interrupted && !reporterSpoke) {
    const cwd = process.cwd();
    const app = appName(cwd);
    const errors = kind.startsWith("test") ? [] : parseOutput(captured, cwd);
    record(
      errors.length
        ? errors.map((e) => ({ kind, app, ...e }))
        : [{ kind, app, location: "<run>", message: `exit ${code}: ${firstErrorLine(captured) || command.join(" ")}` }],
    );
  }

  if (signal) {
    for (const sig of forwarded) process.off(sig, ignore);
    process.kill(process.pid, signal);
    process.exit(128 + (os.constants.signals[signal] ?? 0));
  }
  process.exit(code ?? 1);
});
