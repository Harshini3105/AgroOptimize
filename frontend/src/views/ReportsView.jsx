import React, { useState, useEffect } from 'react';
import { api } from '../services/api';

// Builds a report card from a full FarmPlanResponse -- fetched here via
// api.getResult(runId) for one of this browser's own saved runs. Reports
// never launches a new optimization itself; it only reads an already-saved
// one (see Run Optimization view), so there's nothing to fabricate here --
// on failure we surface the error instead of a fake report.
function buildReportEntry(result) {
  const dateStr = new Date().toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
  const top = result.plans[0];
  const cropSummary = top.crop_names
    .map((name, i) => ({ name, pct: top.allocation_percent[i] }))
    .filter((c) => c.pct > 1)
    .map((c) => `${c.name} ${Math.round(c.pct)}%`)
    .join(', ');
  const areaHa = (top.area_ha || []).reduce((a, b) => a + b, 0) || 1;
  return {
    id: `${result.run_id || Date.now()}`,
    title: `${result.region_profile.location} ${result.region_profile.season} ${result.region_profile.year} -- ${cropSummary}`,
    date: dateStr,
    tag: 'NEW',
    subtitle: `Yield ${(top.yield_tonnes / areaHa).toFixed(1)} t/ha · Cost ₹${Math.round(top.cost_rs / areaHa).toLocaleString()}/ha · ${top.confidence_label}`,
  };
}

export default function ReportsView({ userLocation, onNavigate }) {
  const [recentReports, setRecentReports] = useState([]);
  const [savedRuns, setSavedRuns] = useState([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [fetchFailed, setFetchFailed] = useState(false);
  const [generatingId, setGeneratingId] = useState(null);
  const [genError, setGenError] = useState('');

  // This district's real, saved optimization runs (this browser's own --
  // see dashboard_service.get_history's client_id scoping). Reports is
  // read-only with respect to the optimizer: it lists runs already
  // generated and saved on the Run Optimization page, and builds a report
  // from whichever one you pick -- it never triggers a new run itself.
  useEffect(() => {
    let cancelled = false;
    setRunsLoading(true);
    api.getHistory(userLocation)
      .then((data) => {
        if (cancelled) return;
        setSavedRuns(data.history || []);
        setFetchFailed(false);
      })
      .catch(() => {
        if (cancelled) return;
        setSavedRuns([]);
        setFetchFailed(true);
      })
      .finally(() => { if (!cancelled) setRunsLoading(false); });
    return () => { cancelled = true; };
  }, [userLocation]);

  const handleGenerateReport = async (run) => {
    setGenError('');
    setGeneratingId(run.id);
    try {
      const result = await api.getResult(run.id);
      setRecentReports((prev) => [buildReportEntry(result), ...prev]);
    } catch (err) {
      console.warn('Failed to load saved run for report:', err);
      setGenError(`Couldn't load the saved run "${run.season}" to build a report from. Confirm uvicorn is running on port 8000.`);
    } finally {
      setGeneratingId(null);
    }
  };

  return (
    <div className="w-full animate-[fadeIn_0.2s_ease-out] max-w-6xl mx-auto space-y-gutter">
      <header className="mb-8">
        <h2 className="font-headline-lg text-headline-lg-mobile md:text-headline-lg text-primary font-bold">Decision Reports</h2>
        <p className="font-body-md text-body-md text-on-surface-variant mt-1">
          Build a report from one of your saved optimization runs for {userLocation}. Reports doesn't run the optimizer itself --
          it reads a run you've already generated and saved.
        </p>
      </header>

      {genError && (
        <div className="mb-6 font-label-sm text-label-sm bg-error-container/40 text-on-error-container px-4 py-3 rounded-lg flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px]">error</span> {genError}
        </div>
      )}

      {/* Recently Generated Section */}
      <section className="space-y-6 pt-4">
        <h3 className="font-headline-md text-headline-md text-on-surface border-b border-outline-variant/30 pb-2 font-bold">Recently Generated</h3>

        {recentReports.length === 0 ? (
          <div className="text-center py-12 bg-surface-container-lowest rounded-xl border border-dashed border-outline-variant/30">
            <span className="material-symbols-outlined text-4xl text-outline mb-2">description</span>
            <p className="text-on-surface-variant">No reports generated yet this session.</p>
            <p className="text-sm text-on-surface-variant mt-1">Pick a saved run below and click "Generate Report."</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {recentReports.map((rep) => (
              <div key={rep.id} className="bg-surface-container-lowest rounded-xl p-4 shadow-soft hover:shadow-ambient transition-shadow duration-300 flex flex-col group border border-outline-variant/20">
                <div className="flex-grow flex flex-col justify-between">
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <h4 className="font-label-md text-label-md text-on-surface font-semibold group-hover:text-primary transition-colors">
                      {rep.title}
                    </h4>
                    {rep.tag && (
                      <div className="flex-shrink-0 bg-primary text-on-primary text-xs font-bold px-2 py-1 rounded">
                        {rep.tag}
                      </div>
                    )}
                  </div>
                  {rep.subtitle && (
                    <p className="font-label-sm text-label-sm text-on-surface-variant mb-1">{rep.subtitle}</p>
                  )}
                  <p className="font-label-sm text-label-sm text-on-surface-variant mb-4 flex items-center gap-1">
                    <span className="material-symbols-outlined text-[14px]">calendar_today</span>
                    {rep.date}
                  </p>
                </div>
                <div className="flex justify-between items-center pt-3 border-t border-outline-variant/20 gap-3">
                  <button
                    onClick={() => alert(`Downloading "${rep.title}" PDF report...`)}
                    className="min-h-touch-target-min px-4 py-2 rounded-lg bg-primary text-on-primary font-label-md text-label-md flex items-center gap-2 hover:opacity-90 transition-opacity cursor-pointer font-bold"
                  >
                    <span className="material-symbols-outlined text-[18px]">download</span> PDF
                  </button>
                  <button
                    onClick={() => alert("Copied shareable link to clipboard!")}
                    className="min-h-touch-target-min w-10 h-10 flex items-center justify-center rounded-full text-primary border border-outline hover:bg-surface-container-high transition-colors cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[18px]">share</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Your saved optimization runs -- pick one to build a report from */}
      <section className="space-y-6 mt-12 pt-4">
        <h3 className="font-headline-md text-headline-md text-on-surface border-b border-outline-variant/30 pb-2 font-bold">Your Saved Optimization Runs</h3>
        {runsLoading ? (
          <div className="space-y-2">
            {[0, 1].map((i) => <div key={i} className="h-16 bg-surface-container-lowest rounded-xl border border-outline-variant/20 animate-pulse"></div>)}
          </div>
        ) : savedRuns.length === 0 ? (
          <div className="text-center py-12 bg-surface-container-lowest rounded-xl border border-dashed border-outline-variant/30">
            <span className="material-symbols-outlined text-4xl text-outline mb-2">model_training</span>
            <p className="text-on-surface-variant">
              {fetchFailed ? "Couldn't reach the backend. Confirm uvicorn is running on port 8000." : `You haven't run any optimizations yet for ${userLocation}.`}
            </p>
            {!fetchFailed && (
              <>
                <p className="text-sm text-on-surface-variant mt-1">Reports are built from a saved run -- generate one first.</p>
                {onNavigate && (
                  <button
                    onClick={() => onNavigate('run-optimization')}
                    className="mt-4 inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-primary text-on-primary font-label-md text-label-md hover:opacity-90 transition-opacity cursor-pointer font-bold"
                  >
                    <span className="material-symbols-outlined text-[18px]">model_training</span>
                    Run Optimization
                  </button>
                )}
              </>
            )}
          </div>
        ) : (
          <div className="bg-surface-container-lowest rounded-xl border border-outline-variant/20 shadow-soft overflow-hidden">
            <ul className="divide-y divide-outline-variant/20">
              {savedRuns.map((run) => (
                <li key={run.id} className="p-4 hover:bg-surface-container-low transition-colors flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                  <div className="flex items-center gap-4 flex-1">
                    <div className="w-12 h-16 bg-surface-container-low rounded border border-outline-variant/20 flex items-center justify-center text-outline">
                      <span className="material-symbols-outlined">description</span>
                    </div>
                    <div>
                      <h4 className="font-label-md text-label-md text-on-surface font-semibold">
                        {run.season} Optimization Run ({run.num_plans} plans, {run.preference || 'balanced'})
                      </h4>
                      <p className="font-label-sm text-label-sm text-on-surface-variant">Generated {run.date}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => handleGenerateReport(run)}
                    disabled={generatingId === run.id}
                    className="min-h-touch-target-min px-4 py-2 rounded-lg bg-primary text-on-primary font-label-md text-label-md flex items-center gap-2 hover:opacity-90 transition-opacity cursor-pointer font-bold disabled:opacity-50 disabled:cursor-wait flex-shrink-0"
                  >
                    <span className="material-symbols-outlined text-[18px]">{generatingId === run.id ? 'hourglass_empty' : 'description'}</span>
                    {generatingId === run.id ? 'Loading...' : 'Generate Report'}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}
