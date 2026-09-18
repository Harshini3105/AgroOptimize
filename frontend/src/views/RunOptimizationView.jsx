import React, { useState, useEffect, useRef } from 'react';
import { api, DISTRICTS, SEASONS, PREFERENCES } from '../services/api';

const stages = [
  { step: 1, label: 'Reading soil & rainfall data', progress: 25 },
  { step: 2, label: 'Modeling uncertainty (fuzzy logic)', progress: 50 },
  { step: 3, label: 'Running optimization (NSGA-II)', progress: 75 },
  { step: 4, label: 'Ranking Pareto-optimal plans', progress: 100 },
];

/**
 * Dedicated page for actually running (and saving) a personalized
 * optimization -- this is the ONE place in the app that calls
 * POST /api/farm-plans. Reports no longer does this silently; it only
 * builds reports from runs already generated and saved here, and History
 * only ever shows runs generated here (see get_history's client_id
 * scoping in the backend). That's the point of this page existing: what
 * creates a saved, personalized result should be obvious and deliberate,
 * not a side effect of clicking something else.
 */
export default function RunOptimizationView({ userLocation, landSizeHa = 5, onNavigate }) {
  const initialDistrict = userLocation && DISTRICTS.includes(userLocation) ? userLocation : DISTRICTS[0];

  const [district, setDistrict] = useState(initialDistrict);
  const [season, setSeason] = useState('Kharif');
  const [year, setYear] = useState(''); // '' = let the backend use the latest year in the dataset
  const [availableYears, setAvailableYears] = useState([]);
  const [landArea, setLandArea] = useState(landSizeHa);
  const [budget, setBudget] = useState('');
  const [preference, setPreference] = useState('balanced');

  const [isRunning, setIsRunning] = useState(false);
  const [step, setStep] = useState(0);
  const [progressWidth, setProgressWidth] = useState(0);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null); // last successful run's full FarmPlanResponse

  const pendingRunRef = useRef(null);
  const runParamsRef = useRef({ district, season });

  useEffect(() => {
    setLandArea(landSizeHa);
  }, [landSizeHa]);

  // Real years the dataset actually covers, for the Year dropdown -- not
  // a guessed/hardcoded range.
  useEffect(() => {
    let cancelled = false;
    api.getCatalog()
      .then((c) => { if (!cancelled) setAvailableYears(c.years || []); })
      .catch(() => { if (!cancelled) setAvailableYears([]); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let timer;
    if (isRunning) {
      if (step === 0) {
        setProgressWidth(5);
        timer = setTimeout(() => setStep(1), 900);
      } else if (step <= 4) {
        const current = stages[step - 1];
        setProgressWidth(current.progress);
        if (step < 4) {
          timer = setTimeout(() => setStep(step + 1), 1300);
        } else {
          // Animation finished -- wait for the real run kicked off in
          // handleSubmit to resolve, then show its actual result. On
          // failure, surface the error -- never a fabricated result.
          timer = setTimeout(async () => {
            try {
              const res = await pendingRunRef.current;
              setResult(res);
              setError('');
            } catch (err) {
              console.warn('Optimization run failed:', err);
              const { district: d, season: s } = runParamsRef.current;
              setError(
                err?.message?.includes('404')
                  ? `No data available for ${d} / ${s}.`
                  : "Couldn't reach the backend. Confirm uvicorn is running on port 8000, then try again."
              );
            } finally {
              setIsRunning(false);
              setStep(0);
              setProgressWidth(0);
              pendingRunRef.current = null;
            }
          }, 900);
        }
      }
    }
    return () => clearTimeout(timer);
  }, [isRunning, step]);

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');
    setResult(null);
    runParamsRef.current = { district, season };
    pendingRunRef.current = api.runOptimization({
      location: district,
      season,
      year: year ? Number(year) : undefined,
      land_area_ha: Number(landArea) || 5,
      budget: budget ? Number(budget) : undefined,
      preference,
    });
    setIsRunning(true);
    setStep(0);
  };

  const runAnother = () => {
    setResult(null);
    setError('');
  };

  const isOffProfileDistrict = district !== userLocation;

  const topPlan = result?.plans?.[0] || null;
  const areaHa = topPlan ? (topPlan.area_ha || []).reduce((a, b) => a + b, 0) || Number(landArea) || 1 : 1;
  const cropSummary = topPlan
    ? topPlan.crop_names
        .map((name, i) => ({ name, pct: topPlan.allocation_percent[i] }))
        .filter((c) => c.pct > 1)
        .map((c) => `${c.name} ${Math.round(c.pct)}%`)
        .join(', ')
    : '';

  return (
    <div className="w-full animate-[fadeIn_0.2s_ease-out]">
      {!isRunning ? (
        <div className="max-w-3xl mx-auto space-y-gutter">
          <header className="mb-8">
            <h2 className="font-headline-lg text-headline-lg-mobile md:text-headline-lg text-primary font-bold">Run Optimization</h2>
            <p className="font-body-md text-body-md text-on-surface-variant mt-2">
              Runs the real preprocessing → fuzzy logic → NSGA-II → TOPSIS pipeline for the district and inputs you choose below,
              then saves the result to your account. This is the only action in the app that creates a personalized, saved
              optimization -- it's what populates your History, and what Reports builds reports from.
            </p>
          </header>

          {error && (
            <div className="mb-6 font-label-sm text-label-sm bg-error-container/40 text-on-error-container px-4 py-3 rounded-lg flex items-center gap-2">
              <span className="material-symbols-outlined text-[18px]">error</span> {error}
            </div>
          )}

          {result && !error ? (
            <div className="bg-surface-container-lowest rounded-xl border border-outline-variant/20 shadow-soft p-6">
              <div className="flex items-center gap-3 mb-4">
                <span className="material-symbols-outlined text-primary text-3xl" style={{ fontVariationSettings: "'FILL' 1" }}>check_circle</span>
                <div>
                  <h3 className="font-headline-md text-headline-md text-on-surface font-bold">Optimization complete and saved</h3>
                  <p className="font-label-sm text-label-sm text-on-surface-variant">
                    {result.region_profile.location} · {result.region_profile.season} {result.region_profile.year}
                  </p>
                </div>
              </div>

              {topPlan && (
                <div className="bg-surface-container-low rounded-lg p-4 mb-4">
                  <p className="font-label-sm text-label-sm text-on-surface-variant mb-2 font-medium">Top-ranked plan · {cropSummary}</p>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <p className="font-label-sm text-label-sm text-on-surface-variant">Yield</p>
                      <p className="font-body-lg text-body-lg font-bold text-primary">{(topPlan.yield_tonnes / areaHa).toFixed(1)} t/ha</p>
                    </div>
                    <div>
                      <p className="font-label-sm text-label-sm text-on-surface-variant">Cost</p>
                      <p className="font-body-lg text-body-lg font-bold text-on-surface">₹{Math.round(topPlan.cost_rs / areaHa).toLocaleString()}/ha</p>
                    </div>
                    <div>
                      <p className="font-label-sm text-label-sm text-on-surface-variant">Confidence</p>
                      <p className="font-body-lg text-body-lg font-bold text-on-surface">{topPlan.confidence_label}</p>
                    </div>
                  </div>
                </div>
              )}

              <p className="font-label-sm text-label-sm text-on-surface-variant mb-4">
                Saved to your History for {result.region_profile.location}. Generate a written report from it any time on the Reports page.
              </p>

              <div className="flex flex-col sm:flex-row gap-3">
                <button
                  onClick={runAnother}
                  className="flex-1 border border-outline text-on-surface font-label-md text-label-md py-3 rounded-lg hover:bg-surface-container-high transition-colors cursor-pointer font-bold"
                >
                  Run Another
                </button>
                <button
                  onClick={() => onNavigate && onNavigate('history')}
                  className="flex-1 border border-primary text-primary font-label-md text-label-md py-3 rounded-lg hover:bg-primary/10 transition-colors cursor-pointer font-bold"
                >
                  View in History
                </button>
                <button
                  onClick={() => onNavigate && onNavigate('reports')}
                  className="flex-1 bg-primary text-on-primary font-label-md text-label-md py-3 rounded-lg hover:opacity-90 transition-opacity shadow-sm cursor-pointer font-bold"
                >
                  Generate Report
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="bg-surface-container-lowest rounded-xl border border-outline-variant/20 shadow-soft p-6 space-y-5">
              <div>
                <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1 font-semibold">District</label>
                <select
                  value={district}
                  onChange={(e) => setDistrict(e.target.value)}
                  className="w-full h-12 px-4 rounded-lg border border-outline-variant bg-surface-bright text-on-surface font-body-md outline-none focus:border-primary focus:ring-1 focus:ring-primary cursor-pointer"
                >
                  {DISTRICTS.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
                {isOffProfileDistrict && (
                  <p className="text-xs text-on-surface-variant mt-1.5">
                    Your profile district is {userLocation}. This run will be saved under {district} and will show up in {district}'s History, not your Home dashboard.
                  </p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1 font-semibold">Season</label>
                  <select
                    value={season}
                    onChange={(e) => setSeason(e.target.value)}
                    className="w-full h-12 px-4 rounded-lg border border-outline-variant bg-surface-bright text-on-surface font-body-md outline-none focus:border-primary focus:ring-1 focus:ring-primary cursor-pointer"
                  >
                    {SEASONS.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1 font-semibold">Year</label>
                  <select
                    value={year}
                    onChange={(e) => setYear(e.target.value)}
                    className="w-full h-12 px-4 rounded-lg border border-outline-variant bg-surface-bright text-on-surface font-body-md outline-none focus:border-primary focus:ring-1 focus:ring-primary cursor-pointer"
                  >
                    <option value="">Latest available</option>
                    {availableYears.map((y) => <option key={y} value={y}>{y}</option>)}
                  </select>
                </div>
              </div>

              <div>
                <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1 font-semibold">Land Area (hectares)</label>
                <input
                  value={landArea}
                  onChange={(e) => setLandArea(e.target.value)}
                  type="number"
                  min="0.5"
                  step="0.5"
                  required
                  className="w-full h-12 px-4 rounded-lg border border-outline-variant bg-surface-bright text-on-surface font-body-md outline-none focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>

              <div>
                <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1 font-semibold">Budget Cap (₹, optional)</label>
                <input
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                  type="number"
                  min="0"
                  placeholder="No limit"
                  className="w-full h-12 px-4 rounded-lg border border-outline-variant bg-surface-bright text-on-surface font-body-md outline-none focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>

              <div>
                <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1 font-semibold">Optimization Preference</label>
                <select
                  value={preference}
                  onChange={(e) => setPreference(e.target.value)}
                  className="w-full h-12 px-4 rounded-lg border border-outline-variant bg-surface-bright text-on-surface font-body-md outline-none focus:border-primary focus:ring-1 focus:ring-primary cursor-pointer"
                >
                  {PREFERENCES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>

              <button
                type="submit"
                className="w-full bg-primary text-on-primary font-label-md text-label-md py-3 rounded-lg hover:opacity-90 transition-opacity shadow-sm cursor-pointer font-bold mt-2 flex items-center justify-center gap-2"
              >
                <span className="material-symbols-outlined">model_training</span>
                Run Optimization
              </button>
            </form>
          )}
        </div>
      ) : (
        /* Progress loader screen -- same visual language as elsewhere in
           the app when a real, potentially-slow backend call is in flight. */
        <div className="fixed inset-0 bg-surface z-50 flex flex-col justify-center items-center overflow-hidden animate-[fadeIn_0.3s_ease-out]">
          <div className="relative z-10 w-full max-w-2xl px-6 flex flex-col items-center">
            <div className="mb-12 flex flex-col items-center">
              <div className="w-24 h-24 bg-primary-container rounded-full flex items-center justify-center shadow-soft mb-6 animate-pulse">
                <span className="material-symbols-outlined text-on-primary text-5xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                  eco
                </span>
              </div>
              <h1 className="font-headline-lg-mobile md:font-headline-lg text-headline-lg-mobile md:text-headline-lg text-primary text-center font-bold">
                AgroOptimize Engine
              </h1>
              <p className="font-body-md text-body-md text-on-surface-variant mt-2 text-center">
                Processing agricultural data models for {district} ({season})...
              </p>
            </div>

            <div className="w-full bg-surface-container-highest rounded-full h-3 mb-8 overflow-hidden relative">
              <div
                className="bg-primary-container h-full rounded-full transition-all duration-500 ease-in-out relative overflow-hidden"
                style={{ width: `${progressWidth}%` }}
              >
                <div className="absolute top-0 left-0 right-0 bottom-0 bg-gradient-to-r from-transparent via-white/30 to-transparent animate-[shimmer_2s_infinite]"></div>
              </div>
            </div>

            <div className="w-full flex flex-col gap-4 max-w-md">
              {stages.map((stage) => {
                const isActive = step === stage.step;
                const isComplete = step > stage.step;
                return (
                  <div
                    key={stage.step}
                    className={`flex items-center gap-4 transition-all duration-300 ${
                      isActive ? 'text-primary font-bold scale-[1.02] pl-2' :
                      isComplete ? 'text-on-surface-variant opacity-80' :
                      'text-outline opacity-60'
                    }`}
                  >
                    <span
                      className={`material-symbols-outlined ${isActive ? 'animate-spin' : ''}`}
                      style={{ fontVariationSettings: isComplete || isActive ? "'FILL' 1" : undefined }}
                    >
                      {isComplete ? 'check_circle' : isActive ? 'sync' : 'radio_button_unchecked'}
                    </span>
                    <span className="font-body-lg text-body-lg">{stage.label}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
