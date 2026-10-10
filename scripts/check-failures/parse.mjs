import path from "node:path";

import { ANSI, oneLine } from "./log.mjs";

const rel = (file, cwd) => (path.isAbsolute(file) ? path.relative(cwd, file) || file : file);

// Each parser reads a tool's default human output, so the scripts keep printing exactly what they did.
const parsers = [
  function ruffConcise(lines) {
    const out = [];
    for (const line of lines) {
      const m = line.match(/^(\S+?):(\d+):(\d+): ([A-Z]+\d+) (?:\[\*\] )?(.*)$/);
      if (m) out.push({ location: `${m[1]}:${m[2]}:${m[3]}`, message: `${m[4]} ${m[5]}` });
    }
    return out;
  },
  function ruffFull(lines) {
    const out = [];
    lines.forEach((line, i) => {
      const head = line.match(/^([A-Z]+\d+|unformatted|invalid-syntax)(?: \[\*\])?: ?(.*)$/) ?? line.match(/^([A-Z]+\d+) (?:\[\*\] )?(.*)$/);
      const arrow = lines[i + 1]?.match(/^\s*-->\s+(\S+)$/);
      if (head && arrow) out.push({ location: arrow[1], message: `${head[1]} ${head[2]}` });
    });
    return out;
  },
  function ruffWouldReformat(lines) {
    return lines
      .map((l) => l.match(/^Would reformat: (.+)$/))
      .filter(Boolean)
      .map((m) => ({ location: m[1], message: "would be reformatted" }));
  },
  function mypy(lines) {
    return lines
      .map((l) => l.match(/^(\S+?):(\d+)(?::\d+)?: error: (.*)$/))
      .filter(Boolean)
      .map((m) => ({ location: `${m[1]}:${m[2]}`, message: m[3] }));
  },
  function tsc(lines) {
    return lines
      .map((l) => l.match(/^(.+?)\((\d+),(\d+)\): error (TS\d+): (.*)$/) ?? l.match(/^(\S+?):(\d+):(\d+) - error (TS\d+): (.*)$/))
      .filter(Boolean)
      .map((m) => ({ location: `${m[1]}:${m[2]}:${m[3]}`, message: `${m[4]} ${m[5]}` }));
  },
  function eslintStylish(lines, cwd) {
    const out = [];
    let file = null;
    for (const line of lines) {
      if (/^\/|^[A-Za-z]:\\/.test(line)) {
        file = rel(line.trim(), cwd);
        continue;
      }
      const m = line.match(/^\s+(\d+):(\d+)\s+error\s+(.+?)(?:\s{2,}(\S+))?\s*$/);
      if (file && m) out.push({ location: `${file}:${m[1]}:${m[2]}`, message: m[4] ? `${m[4]} ${m[3]}` : m[3] });
    }
    return out;
  },
];

export function parseOutput(text, cwd = process.cwd()) {
  const lines = text.replace(ANSI, "").split(/\r?\n/);
  for (const parse of parsers) {
    const found = parse(lines, cwd);
    if (found.length) return found;
  }
  return [];
}

// For a run whose tool printed nothing we can parse: a crash, a config error, a missing binary.
export function firstErrorLine(text) {
  const lines = text
    .replace(ANSI, "")
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  const hit = lines.find((l) => /\b(error|exception|failed|cannot|not found|no such)\b/i.test(l) && !/^collect(ing|ed)\b/i.test(l));
  return oneLine(hit ?? lines.at(-1) ?? "");
}
