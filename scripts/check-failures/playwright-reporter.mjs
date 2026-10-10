// Playwright reporter: one log line per failed or flaky test and per global error.
import path from "node:path";

import { record } from "./log.mjs";

const firstLine = (err) => String(err?.message ?? err?.value ?? "").split("\n").find((l) => l.trim()) ?? "";

export default class CheckFailuresReporter {
  onBegin(config, suite) {
    this.root = config.configFile ? path.dirname(config.configFile) : process.cwd();
    this.suite = suite;
    this.globalErrors = [];
  }

  onError(error) {
    this.globalErrors.push(error);
  }

  onEnd(result) {
    if (result.status === "interrupted" || !this.suite) return;
    const cwd = this.root;
    const app = path.basename(cwd);
    const entries = [];
    const add = (location, message) => entries.push({ kind: "test:e2e", app, location, message });

    for (const test of this.suite.allTests()) {
      const outcome = test.outcome();
      if (outcome !== "unexpected" && outcome !== "flaky") continue;
      const file = path.relative(cwd, test.location.file);
      const where = `${file}:${test.location.line} > ${test.titlePath().filter(Boolean).slice(1).join(" > ")}`;
      const failed = test.results.findLast((r) => r.status !== "passed" && r.status !== "skipped");
      const message = firstLine(failed?.error) || failed?.status || "failed";
      add(where, outcome === "flaky" ? `FLAKY ${message}` : message);
    }
    for (const err of this.globalErrors) add("<global>", firstLine(err));

    record(entries, { cwd });
  }

  printsToStdio() {
    return false;
  }
}
