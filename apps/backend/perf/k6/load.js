// NFR-02 c1: 50 concurrent users on the 200k-contact dataset.
// 95% of page loads under 2 s and searches under 1 s, measured on the API calls behind each page.
// Seed first: `uv run python -m scripts.seed_load_test` writes tokens.json (one bearer token per user).
import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

const BASE = __ENV.BASE_URL || "http://localhost:8000";
const tokens = new SharedArray("tokens", () => JSON.parse(open("./tokens.json")));

export const options = {
  scenarios: {
    users: { executor: "constant-vus", vus: 50, duration: __ENV.DURATION || "3m" },
  },
  thresholds: {
    "http_req_duration{kind:page}": ["p(95)<2000"],
    "http_req_duration{kind:search}": ["p(95)<1000"],
    http_req_failed: ["rate<0.01"],
  },
  summaryTrendStats: ["avg", "med", "p(90)", "p(95)", "p(99)", "max"],
};

const TERMS = ["peeters", "maes", "claire", "dubois", "brabant", "hainaut", "janssens", "lien", "escaut", "wouters"];
const PAGES = ["/api/v1/mandates/", "/api/v1/tasks/mine", "/api/v1/notifications/", "/api/v1/reports/home", "/api/v1/users/me"];

export default function () {
  // The API allows 100 requests per minute per token: each user does about one per second.
  const user = tokens[(__VU - 1) % tokens.length];
  const params = (kind) => ({ headers: { Authorization: `Bearer ${user.token}` }, tags: { kind } });
  if (user.dashboards_only) {
    check(http.get(`${BASE}/api/v1/reports/dashboard`, params("page")), { "dashboard 200": (r) => r.status === 200 });
    sleep(1.8);
    return;
  }
  const term = TERMS[Math.floor(Math.random() * TERMS.length)];
  const search = [`/api/v1/contacts/?q=${term}&limit=25`, `/api/v1/search/?q=${term}`, `/api/v1/companies/?q=${term}&limit=25`][
    Math.floor(Math.random() * 3)
  ];
  check(http.get(`${BASE}${search}`, params("search")), { "search 200": (r) => r.status === 200 });
  sleep(0.6);

  const page = PAGES[Math.floor(Math.random() * PAGES.length)];
  const response = http.get(`${BASE}${page}`, params("page"));
  check(response, { "page 200": (r) => r.status === 200 });
  if (page === "/api/v1/mandates/" && response.status === 200) {
    const deals = response.json();
    if (deals.length) {
      sleep(0.6);
      const deal = deals[Math.floor(Math.random() * deals.length)];
      check(http.get(`${BASE}/api/v1/mandates/${deal.id}`, params("page")), { "deal 200": (r) => r.status === 200 });
    }
  }
  sleep(0.6);
}

export function handleSummary(data) {
  return { "summary.json": JSON.stringify(data, null, 2), stdout: textSummary(data) };
}

function textSummary(data) {
  const trend = (name) => data.metrics[name]?.values ?? {};
  const page = trend("http_req_duration{kind:page}");
  const search = trend("http_req_duration{kind:search}");
  return [
    `pages:    p95 ${page["p(95)"]?.toFixed(0)} ms (budget 2000)`,
    `searches: p95 ${search["p(95)"]?.toFixed(0)} ms (budget 1000)`,
    `requests: ${data.metrics.http_reqs.values.count}, failed ${(data.metrics.http_req_failed.values.rate * 100).toFixed(2)}%`,
    "",
  ].join("\n");
}
