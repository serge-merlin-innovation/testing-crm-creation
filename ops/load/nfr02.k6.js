// NFR-02: 50 concurrent users; p95 page-data loads < 2 s, searches < 1 s, all-deals report < 10 s.
// Only for a throwaway stack seeded by `scripts.seed_load_data`. BASE_URL must be a local URL.
//   BASE_URL=http://localhost:8611 API_TOKENS=crm_pat_a,crm_pat_b,... k6 run ops/load/nfr02.k6.js
import http from "k6/http";
import { check, fail, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "";
const TOKENS = (__ENV.API_TOKENS || "").split(",").filter(Boolean);
if (!/^http:\/\/(localhost|127\.0\.0\.1|backend)(:\d+)?$/.test(BASE_URL)) {
  fail(`Refusing to load-test ${BASE_URL || "an empty BASE_URL"}: only a local throwaway stack.`);
}
if (TOKENS.length < 50) fail("API_TOKENS needs one token per virtual user (50).");
// The public API allows 100 requests a minute per token: one token per virtual user, and a pause
// between iterations, keep each user under it so the run measures latency, not the rate limiter.
const auth = () => ({ headers: { Authorization: `Bearer ${TOKENS[(__VU - 1) % TOKENS.length]}` } });
const WORDS = ["peeters", "maes", "jan", "anna", "willems", "claes"];

export const options = {
  scenarios: {
    users: { executor: "constant-vus", vus: 50, duration: __ENV.DURATION || "2m" },
    report: { executor: "per-vu-iterations", vus: 1, iterations: 3, exec: "report" },
  },
  thresholds: {
    "http_req_duration{kind:page}": ["p(95)<2000"],
    "http_req_duration{kind:search}": ["p(95)<1000"],
    "http_req_duration{kind:report}": ["max<10000"],
    checks: ["rate>0.99"],
  },
};

export default function () {
  const word = WORDS[Math.floor(Math.random() * WORDS.length)];
  const pages = http.batch([
    ["GET", `${BASE_URL}/api/v1/contacts/?limit=50`, null, { ...auth(), tags: { kind: "page" } }],
    ["GET", `${BASE_URL}/api/v1/companies/?limit=50`, null, { ...auth(), tags: { kind: "page" } }],
    ["GET", `${BASE_URL}/api/v1/reports/home`, null, { ...auth(), tags: { kind: "page" } }],
  ]);
  pages.forEach((response) => check(response, { "page 200": (r) => r.status === 200 }));
  const search = http.get(`${BASE_URL}/api/v1/search/?q=${word}`, { ...auth(), tags: { kind: "search" } });
  check(search, { "search 200": (r) => r.status === 200 });
  sleep(2 + Math.random() * 2);
}

export function report() {
  const response = http.get(`${BASE_URL}/api/v1/reports/dashboard`, { ...auth(), tags: { kind: "report" } });
  check(response, { "report 200": (r) => r.status === 200 });
}
