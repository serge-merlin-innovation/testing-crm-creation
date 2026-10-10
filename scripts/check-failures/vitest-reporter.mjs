// Vitest reporter: one log line per failed test, failed module and unhandled error, after every
// run, watch-mode reruns included.
import path from "node:path";

import { record } from "./log.mjs";

const firstLine = (err) => String(err?.message ?? err ?? "").split("\n").find((l) => l.trim()) ?? "";

export default class CheckFailuresReporter {
  onInit(vitest) {
    this.root = vitest.config.root;
  }

  onTestRunEnd(testModules, unhandledErrors, reason) {
    if (reason === "interrupted") return;
    const app = path.basename(this.root);
    const entries = [];
    const add = (location, message) => entries.push({ kind: "test:unit", app, location, message });

    for (const mod of testModules) {
      const file = path.relative(this.root, mod.moduleId);
      for (const err of mod.errors()) add(file, firstLine(err));
      for (const test of mod.children.allTests()) {
        const result = test.result();
        const where = `${file} > ${test.fullName}`;
        if (result.state === "failed") add(where, firstLine(result.errors?.[0]));
        else if (result.state === "passed" && test.diagnostic()?.flaky) add(where, "FLAKY passed on retry");
      }
    }
    for (const err of unhandledErrors) add("<unhandled>", firstLine(err));

    record(entries, { cwd: this.root });
  }
}
