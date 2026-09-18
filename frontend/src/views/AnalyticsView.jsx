import React, { useState, useMemo, useEffect } from 'react';
import { api } from '../services/api';
import DataSourceNotice from '../components/DataSourceNotice';

function padRange(lo, hi, frac = 0.1) {
  const range = hi - lo || Math.max(hi, 1) * 0.2;
  return [Math.max(0, lo - range * frac), hi + range * frac];
}

const DEFAULT_BOUNDS = { minCostVal: 0, maxCostVal: 1, minYieldVal: 0, maxYieldVal: 1, minWaterVal: 0, maxWaterVal: 1 };

export default function AnalyticsView({ onNavigate, userLocation }) {
  const [plansData, setPlansData] = useState(null);
  const [plansLoading, setPlansLoading] = useState(true);
  const [isFallback, setIsFallback] = useState(false);
  const [fetchFailed, setFetchFailed] = useState(false);
  const [soilProfile, setSoilProfile] = useState(null);

  const [hoveredPoint, setHoveredPoint] = useState(null);

  // Fuzzy vs non-fuzzy comparison study (Task 4) -- separate fetch, its own
  // loading/error state, independent of the scatter-plot data above.
  const [fuzzyComparison, setFuzzyComparison] = useState(null);
  const [fuzzyLoading, setFuzzyLoading] = useState(true);
  const [fuzzyFailed, setFuzzyFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setPlansLoading(true);
    api.getPlans(userLocation)
      .then((data) => {
        if (cancelled) return;
        setPlansData(data);
        setIsFallback(Boolean(data.is_fallback));
        setFetchFailed(false);
      })
      .catch(() => {
        if (cancelled) return;
        setPlansData(null);
        setFetchFailed(true);
      })
      .finally(() => { if (!cancelled) setPlansLoading(false); });

    api.getSoilProfile(userLocation)
      .then((data) => { if (!cancelled) setSoilProfile(data); })
      .catch(() => { if (!cancelled) setSoilProfile(null); });

    setFuzzyLoading(true);
    api.getFuzzyComparison(userLocation)
      .then((data) => {
        if (cancelled) return;
        setFuzzyComparison(data);
        setFuzzyFailed(false);
      })
      .catch(() => {
        if (cancelled) return;
        setFuzzyComparison(null);
        setFuzzyFailed(true);
      })
      .finally(() => { if (!cancelled) setFuzzyLoading(false); });

    return () => { cancelled = true; };
  }, [userLocation]);

  // Convergence / hypervolume history rides along on GET /api/plans, so it
  // shares plansData's loading state rather than a separate fetch.
  const hypervolumeHistory = plansData?.hypervolume_history || [];
  const hasConvergenceData = hypervolumeHistory.length > 0;

  // Real plans (backend snake_case) adapted onto the shape the chart
  // speaks (camelCase). No synthetic data -- an empty/failed fetch just
  // means zero points, handled by the empty state below.
  const points = useMemo(() => {
    if (plansData?.plans?.length) {
      return plansData.plans.map((p) => ({
        id: p.id,
        cost: p.cost,
        yieldVal: p.yield_val,
        waterVal: p.water_val, // million litres / ha
        isRecommended: p.is_recommended,
      }));
    }
    return [];
  }, [plansData]);

  const hasData = points.length > 0;

  const bounds = useMemo(() => {
    if (!hasData) return DEFAULT_BOUNDS;
    const costs = points.map((p) => p.cost);
    const yields = points.map((p) => p.yieldVal);
    const waters = points.map((p) => p.waterVal);
    const [cLo, cHi] = padRange(Math.min(...costs), Math.max(...costs));
    const [yLo, yHi] = padRange(Math.min(...yields), Math.max(...yields));
    const [wLo, wHi] = padRange(Math.min(...waters), Math.max(...waters));
    return {
      minCostVal: Math.round(cLo),
      maxCostVal: Math.round(cHi),
      minYieldVal: Math.round(yLo * 10) / 10,
      maxYieldVal: Math.round(yHi * 10) / 10,
      minWaterVal: Math.round(wLo * 100) / 100,
      maxWaterVal: Math.round(wHi * 100) / 100,
    };
  }, [points, hasData]);

  const [maxCost, setMaxCost] = useState(bounds.maxCostVal);
  const [minYield, setMinYield] = useState(bounds.minYieldVal);
  const [maxWater, setMaxWater] = useState(bounds.maxWaterVal);

  useEffect(() => {
    setMaxCost(bounds.maxCostVal);
    setMinYield(bounds.minYieldVal);
    setMaxWater(bounds.maxWaterVal);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bounds.minCostVal, bounds.maxCostVal, bounds.minYieldVal, bounds.maxYieldVal, bounds.minWaterVal, bounds.maxWaterVal]);

  const { filteredPoints, validCount, bestCostPlan } = useMemo(() => {
    const valid = points.map((p) => {
      const isCostValid = p.cost <= maxCost;
      const isYieldValid = p.yieldVal >= minYield;
      const isWaterValid = p.waterVal <= maxWater;
      const isValid = isCostValid && isYieldValid && isWaterValid;
      return { ...p, isValid };
    });

    const activeValid = valid.filter((v) => v.isValid);

    let best = null;
    if (activeValid.length > 0) {
      best = [...activeValid].sort((a, b) => a.cost - b.cost)[0];
    }

    return {
      filteredPoints: valid,
      validCount: activeValid.length,
      bestCostPlan: best || { cost: 0, yieldVal: 0, waterVal: 0 },
    };
  }, [points, maxCost, minYield, maxWater]);

  const padding = 50;
  const chartWidth = 500;
  const chartHeight = 300;
  const { minCostVal, maxCostVal, minYieldVal, maxYieldVal, minWaterVal, maxWaterVal } = bounds;

  const getX = (cost) => padding + ((cost - minCostVal) / (maxCostVal - minCostVal || 1)) * (chartWidth - padding * 2);
  const getY = (yieldVal) => chartHeight - padding - ((yieldVal - minYieldVal) / (maxYieldVal - minYieldVal || 1)) * (chartHeight - padding * 2);

  const costTicks = useMemo(() => {
    const n = 6;
    return Array.from({ length: n + 1 }, (_, i) => Math.round(minCostVal + ((maxCostVal - minCostVal) * i) / n));
  }, [minCostVal, maxCostVal]);

  const yieldTicks = useMemo(() => {
    const n = 5;
    return Array.from({ length: n + 1 }, (_, i) => Math.round((minYieldVal + ((maxYieldVal - minYieldVal) * i) / n) * 10) / 10);
  }, [minYieldVal, maxYieldVal]);

  const soilPct = soilProfile ? Math.round(soilProfile.fertility_index * 100) : null;
  const soilLabel = soilPct == null ? null : soilPct >= 70 ? 'Optimal' : soilPct >= 45 ? 'Moderate' : 'Needs Attention';

  // --- Convergence (hypervolume vs generation) chart geometry ---
  const convPadding = 40;
  const convWidth = 500;
  const convHeight = 220;
  const convBounds = useMemo(() => {
    if (!hasConvergenceData) return { minGen: 0, maxGen: 1, minHv: 0, maxHv: 1 };
    const gens = hypervolumeHistory.map((h) => h.generation);
    const hvs = hypervolumeHistory.map((h) => h.hypervolume);
    return {
      minGen: Math.min(...gens),
      maxGen: Math.max(...gens),
      minHv: 0, // hypervolume's meaningful floor is 0, not the observed min
      maxHv: Math.max(...hvs) * 1.05 || 1,
    };
  }, [hypervolumeHistory, hasConvergenceData]);
  const convX = (gen) =>
    convPadding + ((gen - convBounds.minGen) / (convBounds.maxGen - convBounds.minGen || 1)) * (convWidth - convPadding * 2);
  const convY = (hv) =>
    convHeight - convPadding - ((hv - convBounds.minHv) / (convBounds.maxHv - convBounds.minHv || 1)) * (convHeight - convPadding * 2);
  const convergencePath = useMemo(() => {
    if (!hasConvergenceData) return '';
    return hypervolumeHistory
      .map((h, i) => `${i === 0 ? 'M' : 'L'} ${convX(h.generation).toFixed(2)} ${convY(h.hypervolume).toFixed(2)}`)
      .join(' ');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hypervolumeHistory, hasConvergenceData, convBounds]);

  return (
    <div className="animate-[fadeIn_0.2s_ease-out] w-full">
      <DataSourceNotice
        location={userLocation}
        variant="live"
        onRunOptimization={() => onNavigate('run-optimization')}
      />
      {isFallback && (
        <div className="mb-4 font-label-sm text-label-sm bg-surface-container-high text-on-surface-variant px-3 py-2 rounded-lg flex items-center gap-2 w-fit">
          <span className="material-symbols-outlined text-[16px]">info</span> Live optimisation was unavailable -- showing the district's last saved/estimated plans.
        </div>
      )}
      {fetchFailed && (
        <div className="mb-4 font-label-sm text-label-sm bg-error-container/40 text-on-error-container px-3 py-2 rounded-lg flex items-center gap-2 w-fit">
          <span className="material-symbols-outlined text-[16px]">cloud_off</span> Couldn't reach the backend. Confirm uvicorn is running on port 8000.
        </div>
      )}

      {/* KPI Section */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div className="bg-surface-container-lowest rounded-xl p-6 shadow-ambient flex flex-col justify-between">
          <div className="flex justify-between items-start mb-4">
            <h3 className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider font-semibold">Valid Plans</h3>
            <div className="bg-primary-container/10 p-2 rounded-full text-primary">
              <span className="material-symbols-outlined">article</span>
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-headline-lg text-headline-lg text-on-surface">{validCount}</span>
            <span className="font-label-sm text-label-sm text-secondary">out of {points.length}</span>
          </div>
        </div>

        <div className="bg-surface-container-lowest rounded-xl p-6 shadow-ambient flex flex-col justify-between">
          <div className="flex justify-between items-start mb-4">
            <h3 className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider font-semibold">Avg Yield Target</h3>
            <div className="bg-primary-container/10 p-2 rounded-full text-primary">
              <span className="material-symbols-outlined">agriculture</span>
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-headline-lg text-headline-lg text-on-surface">{hasData ? minYield : '--'}</span>
            <span className="font-body-md text-body-md text-on-surface-variant">t/ha (Min)</span>
          </div>
        </div>

        <div className="bg-surface-container-lowest rounded-xl p-6 shadow-ambient flex flex-col justify-between">
          <div className="flex justify-between items-start mb-4">
            <h3 className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider font-semibold">Water Limit</h3>
            <div className="bg-secondary-container/20 p-2 rounded-full text-secondary">
              <span className="material-symbols-outlined">water_drop</span>
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-headline-lg text-headline-lg text-on-surface">{hasData ? maxWater : '--'}</span>
            <span className="font-label-sm text-label-sm text-on-surface-variant">ML/ha (Max)</span>
          </div>
        </div>

        {/* Real soil fertility index for this district */}
        <div className="bg-surface-container-lowest rounded-xl p-6 shadow-ambient flex flex-col justify-between">
          <div className="flex justify-between items-start mb-4">
            <h3 className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider font-semibold">Soil Suitability</h3>
            <div className="bg-primary-container/10 p-2 rounded-full text-primary">
              <span className="material-symbols-outlined">eco</span>
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-headline-lg text-headline-lg text-primary">{soilLabel ?? '--'}</span>
          </div>
          {soilPct != null && (
            <div className="w-full bg-surface-variant rounded-full h-2 mt-3">
              <div className="bg-primary h-2 rounded-full transition-all duration-500" style={{ width: `${soilPct}%` }}></div>
            </div>
          )}
        </div>
      </div>

      {/* Main Charts & Controls Bento Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Cost vs Yield SVG Scatter Plot */}
        <div className="lg:col-span-8 bg-surface-container-lowest rounded-xl p-6 shadow-ambient flex flex-col min-h-[500px]">
          <div className="flex justify-between items-center mb-6">
            <div>
              <h3 className="font-headline-md text-headline-md text-on-surface">Cost vs. Yield Analysis</h3>
              <p className="text-sm text-on-surface-variant mt-0.5">Hover points to see plan details. Non-compliant plans are faded.</p>
            </div>
            <button
              onClick={() => alert("Exporting optimization data as CSV...")}
              disabled={!hasData}
              className="flex items-center gap-2 text-primary font-label-md text-label-md hover:bg-primary-container/10 px-4 py-2 rounded-lg transition-colors min-h-[48px] cursor-pointer font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <span className="material-symbols-outlined">download</span>
              Export
            </button>
          </div>

          <div className="flex-1 relative w-full flex items-center justify-center bg-surface-container-low/30 rounded-lg p-2 min-h-[350px]">
            {plansLoading ? (
              <div className="w-full h-full flex items-center justify-center min-h-[350px]">
                <div className="w-full max-w-md space-y-3">
                  <div className="h-4 w-1/2 bg-surface-container-high rounded animate-pulse mx-auto"></div>
                  <div className="h-64 w-full bg-surface-container-high rounded animate-pulse"></div>
                </div>
              </div>
            ) : !hasData ? (
              <div className="text-center py-16">
                <span className="material-symbols-outlined text-5xl text-outline mb-2">scatter_plot</span>
                <p className="font-body-lg text-on-surface-variant">
                  {fetchFailed ? "Couldn't reach the backend." : 'No optimization plans available for this district yet.'}
                </p>
                <p className="text-sm text-on-surface-variant mt-1">
                  <button onClick={() => onNavigate('run-optimization')} className="text-primary font-semibold hover:underline cursor-pointer">
                    Run your own optimization
                  </button> to generate one.
                </p>
              </div>
            ) : (
              <>
                <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="w-full h-full max-h-[380px]">
                  {costTicks.map((c) => (
                    <g key={c}>
                      <line x1={getX(c)} y1={padding} x2={getX(c)} y2={chartHeight - padding} stroke="#bfc9bd" strokeWidth="0.5" strokeDasharray="4" />
                      <text x={getX(c)} y={chartHeight - padding + 15} fontSize="8" fill="#707a6f" textAnchor="middle" className="font-label-sm">₹{c.toLocaleString()}</text>
                    </g>
                  ))}

                  {yieldTicks.map((y) => (
                    <g key={y}>
                      <line x1={padding} y1={getY(y)} x2={chartWidth - padding} y2={getY(y)} stroke="#bfc9bd" strokeWidth="0.5" strokeDasharray="4" />
                      <text x={padding - 10} y={getY(y) + 3} fontSize="8" fill="#707a6f" textAnchor="end" className="font-label-sm">{y}t</text>
                    </g>
                  ))}

                  <text x={chartWidth / 2} y={chartHeight - 5} fontSize="10" fill="#404940" textAnchor="middle" className="font-semibold">Cost per Hectare (₹)</text>
                  <text x={12} y={chartHeight / 2} fontSize="10" fill="#404940" textAnchor="middle" transform={`rotate(-90 12 ${chartHeight / 2})`} className="font-semibold">Yield (t/ha)</text>

                  {filteredPoints.map((p) => {
                    const cx = getX(p.cost);
                    const cy = getY(p.yieldVal);
                    const isHovered = hoveredPoint?.id === p.id;

                    return (
                      <circle
                        key={p.id}
                        cx={cx}
                        cy={cy}
                        r={p.isRecommended ? 7 : isHovered ? 6 : 4}
                        onMouseEnter={() => setHoveredPoint(p)}
                        onMouseLeave={() => setHoveredPoint(null)}
                        className="transition-all duration-200 cursor-pointer"
                        fill={p.isValid ? (p.isRecommended ? '#ffbf00' : '#1f6b3a') : '#dbdada'}
                        stroke={p.isValid ? (p.isRecommended ? '#795900' : '#005226') : '#bfc9bd'}
                        strokeWidth={isHovered || p.isRecommended ? 1.5 : 0.5}
                        opacity={p.isValid ? 0.85 : 0.25}
                      />
                    );
                  })}
                </svg>

                {hoveredPoint && (
                  <div
                    className="absolute bg-inverse-surface text-inverse-on-surface p-3 rounded-lg shadow-lg text-xs flex flex-col gap-1 z-20 pointer-events-none"
                    style={{
                      left: `${Math.min(getX(hoveredPoint.cost) * (window.innerWidth < 768 ? 0.7 : 1.3), chartWidth - 10)}px`,
                      top: `${Math.max(getY(hoveredPoint.yieldVal) - 60, 10)}px`
                    }}
                  >
                    <p className="font-bold text-primary-fixed">
                      {hoveredPoint.isRecommended ? '★ Recommended Plan' : `Plan Option #${hoveredPoint.id + 1}`}
                    </p>
                    <p>Cost: ₹{hoveredPoint.cost.toLocaleString()}/ha</p>
                    <p>Yield: {hoveredPoint.yieldVal} t/ha</p>
                    <p>Water Usage: {hoveredPoint.waterVal} ML/ha</p>
                    <p className="mt-1 font-semibold">
                      {hoveredPoint.isValid ? '✓ Meets Constraints' : '✗ Violates Constraints'}
                    </p>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* Right Column: Parameters and Constraints */}
        <div className="lg:col-span-4 flex flex-col gap-6 w-full">
          <div className="bg-surface-container-lowest rounded-xl p-6 shadow-ambient w-full">
            <h3 className="font-headline-md text-headline-md text-on-surface mb-6 flex items-center gap-2 font-semibold">
              <span className="material-symbols-outlined">tune</span>
              Constraints Adjuster
            </h3>

            <div className={`space-y-6 ${!hasData ? 'opacity-40 pointer-events-none' : ''}`}>
              <div>
                <div className="flex justify-between mb-2">
                  <label className="font-label-md text-label-md text-on-surface-variant font-medium">Max Cost (₹/ha)</label>
                  <span className="font-label-sm text-label-sm text-on-surface bg-surface-container-low px-2 py-0.5 rounded font-bold">₹{maxCost.toLocaleString()}</span>
                </div>
                <input
                  value={maxCost}
                  onChange={(e) => setMaxCost(Number(e.target.value))}
                  className="w-full h-2 bg-surface-variant rounded-lg appearance-none cursor-pointer accent-primary"
                  max={maxCostVal}
                  min={minCostVal}
                  step={Math.max(1, Math.round((maxCostVal - minCostVal) / 100))}
                  type="range"
                />
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <label className="font-label-md text-label-md text-on-surface-variant font-medium">Min Yield (t/ha)</label>
                  <span className="font-label-sm text-label-sm text-on-surface bg-surface-container-low px-2 py-0.5 rounded font-bold">{minYield}</span>
                </div>
                <input
                  value={minYield}
                  onChange={(e) => setMinYield(Number(e.target.value))}
                  className="w-full h-2 bg-surface-variant rounded-lg appearance-none cursor-pointer accent-primary"
                  max={maxYieldVal}
                  min={minYieldVal}
                  step="0.1"
                  type="range"
                />
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <label className="font-label-md text-label-md text-on-surface-variant font-medium">Max Water (ML/ha)</label>
                  <span className="font-label-sm text-label-sm text-on-surface bg-surface-container-low px-2 py-0.5 rounded font-bold">{maxWater}</span>
                </div>
                <input
                  value={maxWater}
                  onChange={(e) => setMaxWater(Number(e.target.value))}
                  className="w-full h-2 bg-surface-variant rounded-lg appearance-none cursor-pointer accent-secondary"
                  max={maxWaterVal}
                  min={minWaterVal}
                  step="0.01"
                  type="range"
                />
              </div>

              <button
                onClick={() => {
                  setMaxCost(bounds.maxCostVal);
                  setMinYield(bounds.minYieldVal);
                  setMaxWater(bounds.maxWaterVal);
                }}
                className="w-full bg-surface-container-high hover:bg-surface-dim text-on-surface font-label-md text-label-md py-3 rounded-lg shadow-sm transition-colors min-h-[48px] cursor-pointer font-semibold"
              >
                Reset Constraints
              </button>
            </div>
          </div>

          {/* Recommended Highlights Card */}
          <div className="bg-primary text-on-primary rounded-xl p-6 shadow-ambient relative overflow-hidden">
            <div className="absolute top-0 right-0 p-4 opacity-15">
              <span className="material-symbols-outlined text-6xl">verified</span>
            </div>

            <div className="relative z-10">
              <span className="inline-block px-3 py-1 bg-on-primary/20 rounded-full font-label-sm text-label-sm mb-4 font-semibold">Recommended Compliance</span>
              <h3 className="font-headline-md text-headline-md mb-2 font-bold">Best Compliant Plan</h3>
              {bestCostPlan.cost > 0 ? (
                <>
                  <div className="grid grid-cols-2 gap-4 mt-4">
                    <div>
                      <p className="font-label-sm text-label-sm opacity-80">Est. Cost</p>
                      <p className="font-headline-md text-headline-md font-bold">₹{bestCostPlan.cost.toLocaleString()}</p>
                    </div>
                    <div>
                      <p className="font-label-sm text-label-sm opacity-80">Est. Yield</p>
                      <p className="font-headline-md text-headline-md font-bold">{bestCostPlan.yieldVal}t/ha</p>
                    </div>
                  </div>
                  <button
                    onClick={() => onNavigate('comparison')}
                    className="mt-6 w-full bg-on-primary text-primary font-label-md text-label-md py-2.5 rounded-lg hover:bg-surface-bright transition-colors min-h-[48px] cursor-pointer font-semibold"
                  >
                    View Full Plan Detail
                  </button>
                </>
              ) : (
                <div className="py-4">
                  <p className="text-sm font-semibold">
                    {hasData ? 'No valid plans meet current parameters. Try adjusting sliders.' : 'No plan data available yet.'}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Convergence & Fuzzy-vs-Non-Fuzzy Comparison */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start mt-6">
        {/* NSGA-II Convergence (Hypervolume) Chart */}
        <div className="lg:col-span-6 bg-surface-container-lowest rounded-xl p-6 shadow-ambient flex flex-col min-h-[320px]">
          <h3 className="font-headline-md text-headline-md text-on-surface">NSGA-II Convergence</h3>
          <p className="text-sm text-on-surface-variant mt-0.5 mb-4">
            Hypervolume indicator per generation -- a rising, plateauing curve is the signature of the optimizer converging.
          </p>
          <div className="flex-1 flex items-center justify-center bg-surface-container-low/30 rounded-lg p-2 min-h-[220px]">
            {plansLoading ? (
              <div className="w-full h-full flex items-center justify-center min-h-[200px]">
                <div className="h-40 w-full max-w-md bg-surface-container-high rounded animate-pulse"></div>
              </div>
            ) : !hasConvergenceData ? (
              <div className="text-center py-10">
                <span className="material-symbols-outlined text-4xl text-outline mb-2">show_chart</span>
                <p className="font-body-md text-on-surface-variant">No convergence history available for this run.</p>
              </div>
            ) : (
              <svg viewBox={`0 0 ${convWidth} ${convHeight}`} className="w-full h-full max-h-[240px]">
                {[0, 0.25, 0.5, 0.75, 1].map((f) => {
                  const hv = convBounds.minHv + (convBounds.maxHv - convBounds.minHv) * f;
                  return (
                    <g key={f}>
                      <line x1={convPadding} y1={convY(hv)} x2={convWidth - convPadding} y2={convY(hv)} stroke="#bfc9bd" strokeWidth="0.5" strokeDasharray="4" />
                      <text x={convPadding - 8} y={convY(hv) + 3} fontSize="8" fill="#707a6f" textAnchor="end">{hv.toFixed(2)}</text>
                    </g>
                  );
                })}
                <text x={convWidth / 2} y={convHeight - 5} fontSize="10" fill="#404940" textAnchor="middle" className="font-semibold">Generation</text>
                <text x={12} y={convHeight / 2} fontSize="10" fill="#404940" textAnchor="middle" transform={`rotate(-90 12 ${convHeight / 2})`} className="font-semibold">Hypervolume</text>
                <path d={convergencePath} fill="none" stroke="#1f6b3a" strokeWidth="2" />
                {hypervolumeHistory.map((h) => (
                  <circle key={h.generation} cx={convX(h.generation)} cy={convY(h.hypervolume)} r="2" fill="#1f6b3a" />
                ))}
              </svg>
            )}
          </div>
        </div>

        {/* Fuzzy vs Non-Fuzzy Comparison Table */}
        <div className="lg:col-span-6 bg-surface-container-lowest rounded-xl p-6 shadow-ambient flex flex-col min-h-[320px]">
          <h3 className="font-headline-md text-headline-md text-on-surface">Fuzzy vs. Non-Fuzzy Comparison</h3>
          <p className="text-sm text-on-surface-variant mt-0.5 mb-4">
            Same region/season Pareto front, run once with the fuzzy uncertainty adjustment applied and once without.
          </p>
          {fuzzyLoading ? (
            <div className="h-40 w-full bg-surface-container-high rounded animate-pulse"></div>
          ) : fuzzyFailed || !fuzzyComparison ? (
            <div className="text-center py-10">
              <span className="material-symbols-outlined text-4xl text-outline mb-2">difference</span>
              <p className="font-body-md text-on-surface-variant">Couldn't load the fuzzy comparison for this district.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-on-surface-variant border-b border-outline-variant">
                    <th className="py-2 pr-3 font-label-sm text-label-sm uppercase tracking-wide">Metric (per ha)</th>
                    <th className="py-2 px-3 font-label-sm text-label-sm uppercase tracking-wide">Fuzzy-adjusted</th>
                    <th className="py-2 pl-3 font-label-sm text-label-sm uppercase tracking-wide">Non-fuzzy</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-b border-outline-variant/50">
                    <td className="py-2 pr-3 text-on-surface-variant">Best yield (t)</td>
                    <td className="py-2 px-3 font-semibold text-on-surface">{fuzzyComparison.fuzzy.best_yield_tonnes_per_ha ?? '--'}</td>
                    <td className="py-2 pl-3 font-semibold text-on-surface">{fuzzyComparison.non_fuzzy.best_yield_tonnes_per_ha ?? '--'}</td>
                  </tr>
                  <tr className="border-b border-outline-variant/50">
                    <td className="py-2 pr-3 text-on-surface-variant">Min cost (₹)</td>
                    <td className="py-2 px-3 font-semibold text-on-surface">{fuzzyComparison.fuzzy.min_cost_rs_per_ha?.toLocaleString() ?? '--'}</td>
                    <td className="py-2 pl-3 font-semibold text-on-surface">{fuzzyComparison.non_fuzzy.min_cost_rs_per_ha?.toLocaleString() ?? '--'}</td>
                  </tr>
                  <tr className="border-b border-outline-variant/50">
                    <td className="py-2 pr-3 text-on-surface-variant">Min water (L)</td>
                    <td className="py-2 px-3 font-semibold text-on-surface">{fuzzyComparison.fuzzy.min_water_liters_per_ha?.toLocaleString() ?? '--'}</td>
                    <td className="py-2 pl-3 font-semibold text-on-surface">{fuzzyComparison.non_fuzzy.min_water_liters_per_ha?.toLocaleString() ?? '--'}</td>
                  </tr>
                  <tr>
                    <td className="py-2 pr-3 text-on-surface-variant">Min env. impact</td>
                    <td className="py-2 px-3 font-semibold text-on-surface">{fuzzyComparison.fuzzy.min_env_impact_per_ha ?? '--'}</td>
                    <td className="py-2 pl-3 font-semibold text-on-surface">{fuzzyComparison.non_fuzzy.min_env_impact_per_ha ?? '--'}</td>
                  </tr>
                </tbody>
              </table>
              <p className="text-xs text-on-surface-variant mt-4">
                Yield confidence: {fuzzyComparison.fuzzy_assessment?.yield_confidence ?? '--'} &middot; Irrigation risk: {fuzzyComparison.fuzzy_assessment?.irrigation_risk ?? '--'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
