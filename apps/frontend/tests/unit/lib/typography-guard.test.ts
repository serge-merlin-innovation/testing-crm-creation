import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "../../../src");
const UI = join(SRC, "components/ui");
const TYPOGRAPHY = /(?<![\w-])(text-(xs|sm|base|lg|xl|[2-9]xl|muted-foreground)|font-(?!sans\b)[a-z]+)(?![\w-])/g;

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return path === UI ? [] : sources(path);
    return /\.(tsx|ts)$/.test(entry.name) ? [path] : [];
  });
}

describe("typography", () => {
  it("comes from primitive slots, never from Tailwind classes outside components/ui", () => {
    const hits = sources(SRC).flatMap((file) =>
      readFileSync(file, "utf8")
        .split("\n")
        .flatMap((line, index) =>
          [...line.matchAll(TYPOGRAPHY)].map((match) => `${relative(SRC, file)}:${index + 1} ${match[0]}`),
        ),
    );
    expect(hits).toEqual([]);
  });
});
