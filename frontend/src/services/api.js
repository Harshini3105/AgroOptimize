/**
 * Central API client for the AgroOptimize FastAPI backend.
 *
 * Every view should go through the `api` object below instead of calling
 * `fetch` directly -- this file is the single place that knows the
 * backend's base URL, its real field names, and how a free-text user
 * location resolves to one of the 4 Tamil Nadu districts the backend
 * actually has data for (Coimbatore / Erode / Salem / Pollachi).
 *
 * Run the backend locally with:
 *   uvicorn app.main:app --reload --port 8000
 */

// Vite exposes build-time env vars prefixed VITE_ on import.meta.env. Set
// VITE_API_BASE in a Vercel (or other host) project's environment config to
// point the deployed frontend at a real deployed backend -- local dev
// (`npm run dev`) keeps working unchanged via the localhost fallback.
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export const DISTRICTS = ['Coimbatore', 'Erode', 'Salem', 'Pollachi'];

export const SEASONS = ['Kharif', 'Rabi', 'Summer'];

export const PREFERENCES = [
  { value: 'balanced', label: 'Balanced' },
  { value: 'max_yield', label: 'Max Yield' },
  { value: 'min_cost', label: 'Min Cost' },
  { value: 'min_water', label: 'Min Water Use' },
  { value: 'min_env_impact', label: 'Min Environmental Impact' },
];

/**
 * The backend only knows about the 4 districts above. The frontend's user
 * profile stores `location` as one of those 4 names (e.g. "Coimbatore"),
 * chosen from a dropdown during profile setup -- never free text. This
 * pulls out whichever known district name appears in a given string,
 * case-insensitively, and falls back to Coimbatore if none match. That
 * fallback only matters for legacy/malformed values; App.jsx already
 * requires a real, valid district before any dashboard view can render,
 * so in practice every call here receives a genuine user-chosen district.
 */
export function extractDistrict(locationString) {
  if (!locationString) return 'Coimbatore';
  const lower = String(locationString).toLowerCase();
  const found = DISTRICTS.find((d) => lower.includes(d.toLowerCase()));
  return found || 'Coimbatore';
}

/**
 * This project has no real backend user accounts -- districts are the only
 * thing scoping most data, which is fine for live weather/dashboard/plans
 * (that's genuinely regional, not personal). But saved optimization RUNS
 * (History's "Completed" entries) need *some* way to tell "a run this
 * browser generated" apart from "a run anyone else, or the project's own
 * demo/seed data, generated for the same district" -- otherwise every new
 * user who picks an existing district would see other people's saved runs
 * as if they were their own history.
 *
 * This is that mechanism: a random id generated once and kept in
 * localStorage for the lifetime of this browser profile. It identifies a
 * *browser*, not a person -- clearing site data or switching browsers
 * starts a new one, same as the rest of this app's client-only "auth".
 */
function getOrCreateClientId() {
  const KEY = 'agro_client_id';
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : `client-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    localStorage.setItem(KEY, id);
  }
  return id;
}

async function fetchAPI(path, params = {}) {
  const url = new URL(`${API_BASE}${path}`);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, value);
    }
  });
  const res = await fetch(url.toString());
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`GET ${path} failed: ${res.status} ${detail}`);
  }
  return res.json();
}

async function postAPI(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`POST ${path} failed: ${res.status} ${detail}`);
  }
  return res.json();
}

export const api = {
  /** GET /health -- used for the app-startup connectivity check. */
  checkHealth: () => fetchAPI('/health'),

  /** GET /api/catalog -- locations/seasons/years/crops the dataset covers. */
  getCatalog: () => fetchAPI('/api/catalog'),

  /** GET /api/weather/{district} */
  getWeather: (location) =>
    fetchAPI(`/api/weather/${extractDistrict(location).toLowerCase()}`),

  /**
   * GET /api/dashboard/{district} -- KPI summary. Passes this browser's
   * client_id so "Active Plans" only counts runs *it* actually generated
   * (same pattern as getHistory below); a brand-new browser correctly
   * gets 0 instead of counting other people's/seed saved runs.
   */
  getDashboard: (location) =>
    fetchAPI(`/api/dashboard/${extractDistrict(location).toLowerCase()}`, {
      client_id: getOrCreateClientId(),
    }),

  /**
   * GET /api/history/{district} -- past optimization runs. Passes this
   * browser's client_id so only runs *it* actually generated come back
   * flagged "Completed"; a brand-new browser correctly gets none.
   */
  getHistory: (location) =>
    fetchAPI(`/api/history/${extractDistrict(location).toLowerCase()}`, {
      client_id: getOrCreateClientId(),
    }),

  /** GET /api/soil-profile/{district} */
  getSoilProfile: (location) =>
    fetchAPI(`/api/soil-profile/${extractDistrict(location).toLowerCase()}`),

  /** GET /api/catalog for years is on getCatalog above; GET /api/results/{run_id}
   * -- full saved record for one of THIS browser's own past runs (id comes
   * from getHistory's list). Used by the Reports page to build a report
   * from an existing run instead of launching a new optimization. */
  getResult: (runId) => fetchAPI(`/api/results/${runId}`),

  /** GET /api/plans/{district} -- up to ~100 Pareto-optimal plans. */
  getPlans: (location, { totalLandHa, budgetRs } = {}) =>
    fetchAPI(`/api/plans/${extractDistrict(location).toLowerCase()}`, {
      total_land_ha: totalLandHa,
      budget_rs: budgetRs,
    }),

  /** GET /api/comparison/{district} -- Plan A (balanced) / B (max yield) / C (min cost). */
  getComparison: (location, { totalLandHa, budgetRs } = {}) =>
    fetchAPI(`/api/comparison/${extractDistrict(location).toLowerCase()}`, {
      total_land_ha: totalLandHa,
      budget_rs: budgetRs,
    }),

  /**
   * GET /api/compare-fuzzy/{district} -- fuzzy-vs-non-fuzzy comparison
   * study: runs NSGA-II with the Mamdani fuzzy uncertainty adjustment on
   * and off over the same region/season, returns per-hectare summary
   * stats for both so AnalyticsView can render them side by side.
   */
  getFuzzyComparison: (location, { season, year, totalLandHa, budgetRs } = {}) =>
    fetchAPI(`/api/compare-fuzzy/${extractDistrict(location).toLowerCase()}`, {
      season,
      year,
      total_land_ha: totalLandHa,
      budget_rs: budgetRs,
    }),

  /**
   * POST /api/farm-plans -- runs the full preprocessing -> fuzzy -> NSGA-II
   * -> TOPSIS ranking pipeline live and returns the ranked plans.
   *
   * Accepts the friendlier `land_area_ha` / `budget` field names and maps
   * them onto the real FarmPlanRequest schema (`total_land_ha` /
   * `budget_rs`) here, so callers don't need to know the backend's exact
   * schema.
   */
  runOptimization: ({
    location,
    season = 'Kharif',
    year,
    land_area_ha = 5.0,
    budget,
    preference = 'balanced',
  } = {}) =>
    postAPI('/api/farm-plans', {
      location: extractDistrict(location),
      season,
      year,
      total_land_ha: land_area_ha,
      budget_rs: budget || undefined,
      preference,
      save_results: true,
      client_id: getOrCreateClientId(),
    }),
};

export default api;
