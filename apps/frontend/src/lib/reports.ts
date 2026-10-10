/** Home page, dashboards, fee forecast and win/loss (REP-01..04). Pure: no fetch, no React. */

export const DASHBOARD_AGGREGATED = "dashboard.aggregated";
export const DASHBOARD_FIRM = "dashboard.firm";
export const FEES_READ = "fees.read";

export type HomeDeal = { id: number; code_name: string; stage: string };
export type HomeTask = { id: number; title: string; due_date: string; overdue: boolean; mandate_id: number | null };
export type KeyDate = { mandate_id: number; code_name: string; name: string; planned_date: string };
export type Home = {
  deals_by_stage: { stage: string; deals: HomeDeal[] }[];
  tasks_due_this_week: HomeTask[];
  key_dates: KeyDate[];
  week_start: string;
  week_end: string;
  is_new: boolean;
};

export type Dashboard = {
  total_mandates: number;
  by_stage_and_type: { stage: string; type: string; count: number }[];
  weighted_fees_by_quarter?: { quarter: string; deals: number; expected_fees: string; weighted_fees: string }[];
  other_teams_weighted_fees?: string | null;
};

export type ForecastMonth = {
  month: string;
  retainers: string;
  success_fees: string;
  forecast_total: string;
  actual_invoiced: string;
  actual_paid: string;
};
export type FeeForecast = { months: ForecastMonth[]; deals: number };

export type WinLoss = {
  period_start: string;
  period_end: string;
  pitches: number;
  won: number;
  lost: number;
  win_rate: string | null;
  top_lost_reasons: { reason: string; count: number }[];
  closed_deals: number;
  average_duration_days: string | null;
  ev_ebitda_by_sector: { sector_id: number; sector: string; deals: number; average_ev_ebitda: string }[];
};

/** Read-only holds dashboard permissions only: its home is the dashboard, not a record page (ROLE-01 c3). */
export function hasRecordAccess(permissions: string[]): boolean {
  return permissions.some((permission) => permission !== DASHBOARD_AGGREGATED && permission !== DASHBOARD_FIRM);
}

/** Dashboard rows pivoted to a stage x type grid, with row and column totals. */
export function pivot(rows: Dashboard["by_stage_and_type"]): {
  stages: string[];
  types: string[];
  cell: (stage: string, type: string) => number;
} {
  const stages = [...new Set(rows.map((row) => row.stage))];
  const types = [...new Set(rows.map((row) => row.type))].sort();
  const counts = new Map(rows.map((row) => [`${row.stage}|${row.type}`, row.count]));
  return { stages, types, cell: (stage, type) => counts.get(`${stage}|${type}`) ?? 0 };
}

/** The current calendar year, as the default win/loss period. */
export function defaultPeriod(today: Date): { from: string; to: string } {
  const year = today.getUTCFullYear();
  return { from: `${year}-01-01`, to: `${year}-12-31` };
}

export function winLossQuery(from: string, to: string): string {
  return `?${new URLSearchParams({ from, to }).toString()}`;
}
