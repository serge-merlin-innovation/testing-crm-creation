import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const LOG_NAME = "check-failures.log";
export const MAX_LINES = 500;
const MAX_MESSAGE = 300;
const LOCK_STALE_MS = 10_000;
const LOCK_WAIT_MS = 3_000;

const scriptRepoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

function git(args, cwd) {
  try {
    return execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

// Every worktree shares one log, kept in the main checkout next to its `.git` directory.
export function logPath(env = process.env) {
  if (env.CHECK_FAILURES_LOG) return env.CHECK_FAILURES_LOG;
  const common = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], scriptRepoRoot);
  const root = common && path.basename(common) === ".git" ? path.dirname(common) : scriptRepoRoot;
  return path.join(root, LOG_NAME);
}

export function isDisabled(env = process.env) {
  return Boolean(env.CI) || env.CHECK_FAILURES_DISABLE === "1";
}

function timestamp(date = new Date()) {
  const pad = (n) => String(Math.trunc(Math.abs(n))).padStart(2, "0");
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}` +
    `${sign}${pad(offset / 60)}:${pad(offset % 60)}`
  );
}

export function revision(cwd = process.cwd()) {
  const branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd) || "nogit";
  const sha = git(["rev-parse", "--short", "HEAD"], cwd) || "0000000";
  return `${branch}@${sha}`;
}

// CSI colour codes, charset resets (mypy's `ESC ( B`) and OSC 8 hyperlinks (ruff links rule codes).
// eslint-disable-next-line no-control-regex
export const ANSI = /\u001b\[[0-9;?]*[A-Za-z]|\u001b[()][A-Za-z0-9]|\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)/g;

export function oneLine(text, max = MAX_MESSAGE) {
  const flat = String(text ?? "")
    .replace(ANSI, "")
    .replace(/\s+/g, " ")
    .trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

export function formatLine({ kind, app, location, message }, { now = new Date(), rev } = {}) {
  return [timestamp(now), rev, kind, app, oneLine(location, 200) || "-", oneLine(message) || "-"].join("\t");
}

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

// mkdir is atomic, so it serialises the parallel writers turbo starts (one per app).
function withLock(file, fn) {
  const lock = `${file}.lock`;
  const deadline = Date.now() + LOCK_WAIT_MS;
  let held = false;
  while (!held) {
    try {
      fs.mkdirSync(lock);
      held = true;
    } catch (err) {
      if (err.code !== "EEXIST") throw err;
      try {
        if (Date.now() - fs.statSync(lock).mtimeMs > LOCK_STALE_MS) fs.rmSync(lock, { recursive: true, force: true });
      } catch {
        /* lock vanished between calls */
      }
      if (Date.now() > deadline) break;
      sleep(25);
    }
  }
  try {
    return fn();
  } finally {
    if (held) fs.rmSync(lock, { recursive: true, force: true });
  }
}

export function appendLines(file, lines, max = MAX_LINES) {
  withLock(file, () => {
    let existing = [];
    try {
      existing = fs.readFileSync(file, "utf8").split("\n").filter(Boolean);
    } catch {
      /* first write */
    }
    const kept = [...existing, ...lines].slice(-max);
    const tmp = `${file}.${process.pid}.tmp`;
    fs.writeFileSync(tmp, `${kept.join("\n")}\n`);
    fs.renameSync(tmp, file);
  });
}

// Logging must never change the outcome of the check it observes, so every error is swallowed.
export function record(entries, { env = process.env, cwd = process.cwd() } = {}) {
  if (!entries.length || isDisabled(env)) return;
  try {
    const rev = revision(cwd);
    const now = new Date();
    appendLines(
      logPath(env),
      entries.map((e) => formatLine(e, { now, rev })),
    );
    if (env.CHECK_FAILURES_SENTINEL) fs.writeFileSync(env.CHECK_FAILURES_SENTINEL, "");
  } catch (err) {
    process.stderr.write(`check-failures: could not write log (${err.message})\n`);
  }
}

export function appName(cwd = process.cwd()) {
  return path.basename(cwd);
}
