import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/**
 * The three files allowed to call `fetch` directly, per `CONSTITUTION.md` § 2: `services/api.ts`
 * is the browser's only egress, `lib/backend-relay.ts` is the server side of that same call, and
 * `lib/session-identity.ts` is the gate asking a question of its own accord.
 *
 * A fork that genuinely needs server-side fetching adds its file here rather than reaching for an
 * inline disable, so the exception lands in the diff.
 */
const BACKEND_CALL_SITES = [
  "src/services/api.ts",
  "src/lib/backend-relay.ts",
  "src/lib/session-identity.ts",
];

/** `process.env` is read through a `lib/` accessor, never inline in a component or service. */
const ENVIRONMENT_ACCESSORS = ["src/lib/**/*.ts"];

/**
 * Flat config REPLACES a rule's options rather than merging them, so two config objects that both
 * set `no-restricted-syntax` for the same file leave only the last one active. Every selector list
 * below is therefore composed from these constants instead of being written per block.
 */
const PUBLIC_ENVIRONMENT_VARIABLE = {
  selector: "Identifier[name=/^NEXT_PUBLIC_/]",
  message:
    "NEXT_PUBLIC_ ships the value to the browser. Nothing here needs that, and a secret behind it is public.",
};

const TEST_ID_ATTRIBUTE = {
  selector: 'JSXAttribute[name.name="data-testid"]',
  message:
    "Every element the E2E suite needs already has an accessible name. A testid is a signal the markup needs fixing, not the test.",
};

const CSRF_TOKEN_LITERAL = {
  selector: "Literal[value=/[Xx]-[Cc][Ss][Rr][Ff]-[Tt]oken|csrf_token/]",
  message:
    "Never read or set the CSRF token outside services/api.ts - apiFetch already mints, caches and retries it.",
};

const RESTRICTED_SYNTAX = [PUBLIC_ENVIRONMENT_VARIABLE, TEST_ID_ATTRIBUTE];

const RELATIVE_SOURCE_IMPORT = {
  group: ["..", "../*", "../**"],
  message: "Import source through the @/ alias (@/lib/backend-relay), not relatively.",
};

const HAND_MEMOISATION = {
  name: "react",
  importNames: ["useMemo", "useCallback"],
  message:
    "React Compiler is on - it memoises for you. A hand-added useMemo/useCallback is noise.",
};

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),

  // House rules that live only here: each message is the rule's documentation. All are at zero
  // violations, so they act as ratchets rather than a cleanup backlog.
  {
    name: "merlin/house-rules",
    files: ["src/**/*.{ts,tsx}", "tests/**/*.ts"],
    linterOptions: {
      // Without this, the rules below can be switched off in passing by the code they govern.
      reportUnusedDisableDirectives: "error",
    },
    rules: {
      "no-console": "error",
      "no-throw-literal": "error",
      "no-restricted-syntax": ["error", ...RESTRICTED_SYNTAX],
      "no-restricted-imports": ["error", { paths: [HAND_MEMOISATION] }],
    },
  },

  {
    name: "merlin/csrf-stays-in-api",
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/services/api.ts"],
    rules: {
      "no-restricted-syntax": ["error", ...RESTRICTED_SYNTAX, CSRF_TOKEN_LITERAL],
    },
  },

  // `fetch` is a global, so restricting it here cannot collide with the selector lists above.
  {
    name: "merlin/one-door-to-the-backend",
    files: ["src/**/*.{ts,tsx}"],
    ignores: BACKEND_CALL_SITES,
    rules: {
      "no-restricted-globals": [
        "error",
        {
          name: "fetch",
          message:
            "Go through apiFetch from services/api.ts. A raw fetch silently skips CSRF and 401 handling. If this really is a new server-side path, add the file to BACKEND_CALL_SITES in eslint.config.mjs.",
        },
      ],
    },
  },

  // Likewise a property restriction, so it composes with everything above.
  {
    name: "merlin/environment-reads-live-in-lib",
    files: ["src/**/*.{ts,tsx}"],
    ignores: ENVIRONMENT_ACCESSORS,
    rules: {
      "no-restricted-properties": [
        "error",
        {
          object: "process",
          property: "env",
          message:
            "Read process.env in a lib/ accessor and pass the value on - lib/ is the accessor layer. Inline reads scatter configuration.",
        },
      ],
    },
  },

  // `src/components/ui/` is shadcn CLI output and is never edited by hand, so the house rules
  // that would force an edit there are off. The code that composes these components still obeys them.
  {
    name: "merlin/shadcn-output-is-untouched",
    files: ["src/components/ui/**/*.tsx"],
    rules: {
      "no-restricted-imports": "off",
    },
  },

  // A test sits at a different depth from its source, so a relative import breaks as soon as
  // either moves. Sibling imports inside the test tree stay relative.
  {
    name: "merlin/tests-import-through-the-alias",
    files: ["tests/**/*.ts"],
    rules: {
      "no-restricted-imports": [
        "error",
        { paths: [HAND_MEMOISATION], patterns: [RELATIVE_SOURCE_IMPORT] },
      ],
    },
  },
]);

export default eslintConfig;
