#!/usr/bin/env node
// Entry point for reporters that are not written in Node (the pytest plugin).
// Reads a JSON array of {kind, app, location, message} on stdin.
import { record } from "./log.mjs";

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  try {
    const entries = JSON.parse(input);
    if (Array.isArray(entries)) record(entries);
  } catch (err) {
    process.stderr.write(`check-failures: bad input (${err.message})\n`);
  }
});
