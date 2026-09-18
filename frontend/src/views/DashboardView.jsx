import React, { useState, useEffect } from 'react';
import { api, DISTRICTS } from '../services/api';
import DataSourceNotice from '../components/DataSourceNotice';

const ACTION_ICONS = {
  nitrogen: 'science',
  phosphorus: 'science',
  potassium: 'science',
  irrigation: 'water',
  monitor: 'task_alt',
};

const ACTION_ICON_STYLES = {
  nitrogen: 'bg-secondary-fixed/30 text-secondary',
  phosphorus: 'bg-secondary-fixed/30 text-secondary',
  potassium: 'bg-secondary-fixed/30 text-secondary',
  irrigation: 'bg-primary-fixed/30 text-primary-container',
  monitor: 'bg-tertiary-fixed/30 text-tertiary',
};

function waterLabel(pct) {
  if (pct >= 70) return 'Optimal';
  if (pct >= 40) return 'Moderate';
  return 'Low';
}

export default function DashboardView({ user, onNavigate, layout = 'sidebar', onToggleLayout }) {
  const [scheduledActions, setScheduledActions] = useState({});
  const [weatherTab, setWeatherTab] = useState('local'); // 'local' | 'districts'

  const [weather, setWeather] = useState(null);
  const [weatherLoading, setWeatherLoading] = useState(true);
  const [weatherFailed, setWeatherFailed] = useState(false);

  const [dashboardData, setDashboardData] = useState(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardFailed, setDashboardFailed] = useState(false);

  const [allDistrictsWeather, setAllDistrictsWeather] = useState({});
  const [districtsLoading, setDistrictsLoading] = useState(true);

  const toggleAction = (key) => {
    setScheduledActions((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // Real weather for the user's district. If the backend truly can't be
  // reached (not running, network error), we show an honest "unavailable"
  // state -- never a fabricated reading. Note the backend itself already
  // has its own real fallback (live Open-Meteo -> historical CSV average)
  // baked into GET /api/weather, so `source` on a successful response
  // tells you which of those two actually produced this reading.
  useEffect(() => {
    let cancelled = false;
    setWeatherLoading(true);
    api.getWeather(user.location)
      .then((data) => {
        if (cancelled) return;
        setWeather(data);
        setWeatherFailed(false);
      })
      .catch(() => {
        if (cancelled) return;
        setWeather(null);
        setWeatherFailed(true);
      })
      .finally(() => { if (!cancelled) setWeatherLoading(false); });
    return () => { cancelled = true; };
  }, [user.location]);

  useEffect(() => {
    let cancelled = false;
    setDashboardLoading(true);
    api.getDashboard(user.location)
      .then((data) => {
        if (cancelled) return;
        setDashboardData(data);
        setDashboardFailed(false);
      })
      .catch(() => {
        if (cancelled) return;
        setDashboardData(null);
        setDashboardFailed(true);
      })
      .finally(() => { if (!cancelled) setDashboardLoading(false); });
    return () => { cancelled = true; };
  }, [user.location]);

  // Weather across all 4 districts, for the "Districts" tab -- real API
  // calls in parallel; a district that fails is simply omitted rather
  // than shown with a made-up reading.
  useEffect(() => {
    let cancelled = false;
    setDistrictsLoading(true);
    Promise.allSettled(DISTRICTS.map((d) => api.getWeather(d).then((data) => [d, data])))
      .then((results) => {
        if (cancelled) return;
        const entries = results.filter((r) => r.status === 'fulfilled').map((r) => r.value);
        setAllDistrictsWeather(Object.fromEntries(entries));
      })
      .finally(() => { if (!cancelled) setDistrictsLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const actions = dashboardData?.recommended_actions ?? [];
  const cropAllocations = dashboardData?.crop_allocations ?? [];

  return (
    <div className="animate-[fadeIn_0.2s_ease-out]">
      <div className="mb-8 flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
        <div>
          <h1 className="font-headline-lg text-headline-lg-mobile md:text-headline-lg text-on-surface mb-1">
            Good Morning{user.fullName ? `, ${user.fullName.split(' ')[0]}` : ''}
          </h1>
          <p className="font-body-md text-on-surface-variant">
            Here is the latest overview of your farm's performance in {user.location}.
          </p>
        </div>
        <button
          onClick={onToggleLayout}
          className="self-start sm:self-center h-10 px-4 rounded-full border border-outline text-primary hover:bg-surface-container-low transition-colors font-label-md text-label-md flex items-center gap-2 cursor-pointer"
        >
          <span className="material-symbols-outlined text-[18px]">splitscreen</span>
          Switch navigation to {layout === 'sidebar' ? 'Top bar' : 'Sidebar'}
        </button>
      </div>

      <DataSourceNotice
        location={user.location}
        variant="historical"
        onRunOptimization={() => onNavigate('run-optimization')}
      />

      {/* Key Metric Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {/* Metric 1 */}
        <div
          onClick={() => onNavigate('comparison')}
          className="bg-surface-container-lowest rounded-xl p-4 soft-shadow border border-outline-variant/30 flex flex-col justify-between min-h-[140px] cursor-pointer hover:border-primary transition-all duration-200"
        >
          <div className="flex justify-between items-start mb-4">
            <div className="p-2 bg-primary-container/10 rounded-lg text-primary">
              <span className="material-symbols-outlined">assignment</span>
            </div>
            <span className="font-label-sm text-label-sm text-on-surface-variant bg-surface-container-low px-2 py-1 rounded-full font-semibold">Active</span>
          </div>
          <div>
            <p className="font-label-md text-label-md text-on-surface-variant mb-1">Active Plans</p>
            {dashboardLoading ? (
              <div className="h-8 w-12 bg-surface-container-high rounded animate-pulse"></div>
            ) : (
              <p className="font-headline-md text-headline-md text-on-surface">{dashboardData?.active_plans ?? '--'}</p>
            )}
          </div>
        </div>

        {/* Metric 2 */}
        <div
          onClick={() => onNavigate('analytics')}
          className="bg-surface-container-lowest rounded-xl p-4 soft-shadow border border-outline-variant/30 flex flex-col justify-between min-h-[140px] cursor-pointer hover:border-primary transition-all duration-200"
        >
          <div className="flex justify-between items-start mb-4">
            <div className="p-2 bg-primary-container/10 rounded-lg text-primary">
              <span className="material-symbols-outlined">agriculture</span>
            </div>
            {dashboardData && (
              <span className="font-label-sm text-label-sm text-primary-fixed-dim bg-primary-fixed/20 px-2 py-1 rounded-full flex items-center gap-1 font-semibold">
                <span className="material-symbols-outlined text-[14px]">
                  {String(dashboardData.yield_trend).trim().startsWith('-') ? 'trending_down' : 'trending_up'}
                </span> {dashboardData.yield_trend}
              </span>
            )}
          </div>
          <div>
            <p className="font-label-md text-label-md text-on-surface-variant mb-1">Estimated Yield</p>
            {dashboardLoading ? (
              <div className="h-8 w-20 bg-surface-container-high rounded animate-pulse"></div>
            ) : (
              <p className="font-headline-md text-headline-md text-on-surface">
                {dashboardData ? dashboardData.estimated_yield : '--'} <span className="text-body-md text-on-surface-variant">t/ha</span>
              </p>
            )}
          </div>
        </div>

        {/* Metric 3 */}
        <div
          onClick={() => onNavigate('comparison')}
          className="bg-surface-container-lowest rounded-xl p-4 soft-shadow border border-outline-variant/30 flex flex-col justify-between min-h-[140px] cursor-pointer hover:border-primary transition-all duration-200"
        >
          <div className="flex justify-between items-start mb-4">
            <div className="p-2 bg-primary-container/10 rounded-lg text-primary">
              <span className="material-symbols-outlined">water_drop</span>
            </div>
            {dashboardData && (
              <span className="font-label-sm text-label-sm text-primary-container bg-primary-fixed/30 px-2 py-1 rounded-full font-semibold">
                {waterLabel(dashboardData.water_utilization_pct)}
              </span>
            )}
          </div>
          <div>
            <p className="font-label-md text-label-md text-on-surface-variant mb-1">Water Utilization</p>
            {dashboardLoading ? (
              <div className="h-2.5 w-full bg-surface-container-high rounded-full mt-3 animate-pulse"></div>
            ) : dashboardData ? (
              <div className="w-full bg-surface-variant rounded-full h-2.5 mt-2">
                <div className="bg-primary-container h-2.5 rounded-full transition-all duration-500" style={{ width: `${Math.min(100, dashboardData.water_utilization_pct)}%` }}></div>
              </div>
            ) : (
              <p className="font-headline-md text-headline-md text-on-surface">--</p>
            )}
          </div>
        </div>

        {/* Metric 4 */}
        <div
          onClick={() => onNavigate('analytics')}
          className="bg-surface-container-lowest rounded-xl p-4 soft-shadow border border-outline-variant/30 flex flex-col justify-between min-h-[140px] cursor-pointer hover:border-primary transition-all duration-200"
        >
          <div className="flex justify-between items-start mb-4">
            <div className="p-2 bg-primary-container/10 rounded-lg text-primary">
              <span className="material-symbols-outlined">eco</span>
            </div>
            {dashboardData && (
              <span className="font-label-sm text-label-sm text-primary-container bg-primary-fixed/30 px-2 py-1 rounded-full font-semibold">{dashboardData.soil_status}</span>
            )}
          </div>
          <div>
            <p className="font-label-md text-label-md text-on-surface-variant mb-1">Soil Health</p>
            {dashboardLoading ? (
              <div className="h-8 w-14 bg-surface-container-high rounded animate-pulse"></div>
            ) : (
              <p className="font-headline-md text-headline-md text-on-surface">{dashboardData ? `${dashboardData.soil_health_pct}%` : '--'}</p>
            )}
          </div>
        </div>
      </div>

      {dashboardFailed && (
        <div className="mb-8 -mt-4 font-label-sm text-label-sm bg-error-container/40 text-on-error-container px-3 py-2 rounded-lg flex items-center gap-2 w-fit">
          <span className="material-symbols-outlined text-[16px]">cloud_off</span>
          Couldn't reach the backend for dashboard data. Confirm uvicorn is running on port 8000.
        </div>
      )}

      {/* Main Sections Layout (Bento Grid Style) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Left Column (Span 2) */}
        <div className="lg:col-span-2 space-y-6">
          {/* Farm / Crop Overview -- real top candidate crops for this
              district+season, ranked by historical revenue (crop.csv).
              There's no GPS/plot-boundary data anywhere in this system, so
              this card shows the real crop-mix breakdown instead of a
              decorative map. */}
          <div className="bg-surface-container-lowest rounded-xl soft-shadow border border-outline-variant/30 overflow-hidden flex flex-col">
            <div className="p-4 border-b border-outline-variant/30 flex justify-between items-center bg-surface-container-lowest">
              <h3 className="font-headline-md text-headline-md text-on-surface">Crop Allocation Overview</h3>
              <button
                onClick={() => onNavigate('analytics')}
                className="text-primary font-label-md text-label-md hover:underline flex items-center min-h-touch-target-min px-2 cursor-pointer font-semibold"
              >
                View Details <span className="material-symbols-outlined ml-1 text-[18px]">arrow_forward</span>
              </button>
            </div>
            <div className="p-4">
              {dashboardLoading ? (
                <div className="space-y-3">
                  {[0, 1, 2].map((i) => <div key={i} className="h-6 w-full bg-surface-container-high rounded animate-pulse"></div>)}
                </div>
              ) : cropAllocations.length > 0 ? (
                <div className="space-y-3">
                  {cropAllocations.map((c) => (
                    <div key={c.crop} className="flex items-center gap-3 text-sm">
                      <span className="w-28 truncate font-semibold text-on-surface">{c.crop}</span>
                      <div className="flex-1 h-2.5 bg-surface-variant rounded-full overflow-hidden">
                        <div className="h-full bg-primary rounded-full" style={{ width: `${c.pct}%` }}></div>
                      </div>
                      <span className="text-on-surface-variant w-20 text-right">{c.pct}% · {c.ha}ha</span>
                    </div>
                  ))}
                  <p className="text-xs text-on-surface-variant pt-1">Top revenue-ranked candidate crops for this district and season, from historical crop data.</p>
                </div>
              ) : (
                <p className="text-sm text-on-surface-variant py-6 text-center">
                  {dashboardFailed ? 'Crop data unavailable -- backend unreachable.' : 'No crop allocation data available for this district/season.'}
                </p>
              )}
            </div>
          </div>

          {/* Recommended Actions */}
          <div className="bg-surface-container-lowest rounded-xl soft-shadow border border-outline-variant/30 p-4">
            <h3 className="font-headline-md text-headline-md text-on-surface mb-4">Recommended Actions</h3>
            {dashboardLoading ? (
              <div className="space-y-3">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="h-16 bg-surface-container-high rounded-lg animate-pulse"></div>
                ))}
              </div>
            ) : actions.length > 0 ? (
              <ul className="space-y-3">
                {actions.map((action) => (
                  <li key={action.id} className="flex items-start gap-4 p-3 rounded-lg hover:bg-surface-container-low transition-colors border border-transparent hover:border-outline-variant/20">
                    <div className={`p-2 rounded-full mt-1 flex-shrink-0 ${ACTION_ICON_STYLES[action.id] || 'bg-tertiary-fixed/30 text-tertiary'}`}>
                      <span className="material-symbols-outlined">{ACTION_ICONS[action.id] || 'task_alt'}</span>
                    </div>
                    <div className="flex-grow">
                      <p className="font-body-md text-on-surface font-semibold">{action.title}</p>
                      <p className="font-label-sm text-label-sm text-on-surface-variant mt-0.5">
                        {action.description}{action.window ? ` (${action.window})` : ''}
                      </p>
                    </div>
                    <button
                      onClick={() => toggleAction(action.id)}
                      className={`font-label-md text-label-md px-5 py-2 rounded-full transition-colors min-h-touch-target-min cursor-pointer font-semibold whitespace-nowrap ${
                        scheduledActions[action.id]
                          ? 'bg-outline-variant text-on-surface-variant hover:bg-surface-container-high'
                          : 'bg-primary text-on-primary hover:opacity-90'
                      }`}
                    >
                      {scheduledActions[action.id] ? 'Scheduled' : 'Schedule'}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-on-surface-variant py-6 text-center">
                {dashboardFailed ? 'Unable to load recommended actions -- backend unreachable.' : 'No recommended actions right now.'}
              </p>
            )}
          </div>
        </div>

        {/* Right Column (Span 1) */}
        <div className="lg:col-span-1 space-y-6">
          {/* Weather Card */}
          <div className="bg-surface-container-lowest rounded-xl soft-shadow border border-outline-variant/30 p-6 relative overflow-hidden flex flex-col justify-between min-h-[350px]">
            {/* Decorative background element */}
            <div className="absolute top-0 right-0 w-32 h-32 bg-primary-fixed/20 rounded-bl-full -mr-4 -mt-4 z-0"></div>
            <div className="relative z-10 w-full">

              {/* Tabs header */}
              <div className="flex bg-surface-container-low p-1 rounded-lg mb-6 text-center border border-outline-variant/20">
                <button
                  onClick={() => setWeatherTab('local')}
                  className={`flex-1 py-1.5 rounded font-label-sm text-label-sm cursor-pointer transition-all ${
                    weatherTab === 'local' ? 'bg-surface-container-lowest text-primary font-bold shadow-sm' : 'text-on-surface-variant hover:text-primary'
                  }`}
                >
                  Local
                </button>
                <button
                  onClick={() => setWeatherTab('districts')}
                  className={`flex-1 py-1.5 rounded font-label-sm text-label-sm cursor-pointer transition-all ${
                    weatherTab === 'districts' ? 'bg-surface-container-lowest text-primary font-bold shadow-sm' : 'text-on-surface-variant hover:text-primary'
                  }`}
                >
                  Districts
                </button>
              </div>

              {weatherTab === 'local' ? (
                <div className="animate-[fadeIn_0.2s_ease-out]">
                  {weatherLoading ? (
                    <div className="space-y-3">
                      <div className="h-6 w-32 bg-surface-container-high rounded animate-pulse"></div>
                      <div className="h-12 w-24 bg-surface-container-high rounded animate-pulse"></div>
                    </div>
                  ) : weather ? (
                    <>
                      <div className="flex justify-between items-start mb-4">
                        <div>
                          <h3 className="font-headline-md text-headline-md text-on-surface">{weather.location}</h3>
                          <p className="font-label-sm text-label-sm text-on-surface-variant">
                            {weather.source === 'Live (Open-Meteo)' ? "Today's Weather (live)" : 'Historical estimate'}
                          </p>
                        </div>
                        <span className="material-symbols-outlined text-4xl text-secondary">{weather.condition}</span>
                      </div>
                      <div className="mb-6 flex items-baseline gap-2">
                        <span className="font-headline-lg text-[48px] leading-none font-bold text-on-surface">{weather.temp}°</span>
                        <span className="font-body-md text-on-surface-variant">C</span>
                      </div>
                      <div className="space-y-3 pt-4 border-t border-outline-variant/30">
                        <p className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider mb-2 font-bold">
                          {weather.source === 'Live (Open-Meteo)' ? '5-Day Forecast' : 'Seasonal Estimate'}
                        </p>
                        {weather.forecast.map((f) => (
                          <div key={f.day} className="flex justify-between items-center text-sm">
                            <span className="font-body-md text-on-surface w-12">{f.day}</span>
                            <span className="material-symbols-outlined text-on-surface-variant text-[20px]">{f.icon}</span>
                            <span className="font-body-md text-on-surface-variant">{f.temp}</span>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="py-10 text-center">
                      <span className="material-symbols-outlined text-4xl text-outline mb-2">cloud_off</span>
                      <p className="text-sm text-on-surface-variant">Weather unavailable -- couldn't reach the backend.</p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="animate-[fadeIn_0.2s_ease-out] w-full">
                  <p className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider mb-3.5 font-bold">Weather across districts</p>
                  {districtsLoading ? (
                    <div className="space-y-3">
                      {[0, 1, 2, 3].map((i) => <div key={i} className="h-8 w-full bg-surface-container-high rounded animate-pulse"></div>)}
                    </div>
                  ) : Object.keys(allDistrictsWeather).length > 0 ? (
                    <div className="space-y-3 max-h-[220px] overflow-y-auto pr-1">
                      {Object.entries(allDistrictsWeather).map(([district, data]) => (
                        <div key={district} className="flex justify-between items-center py-2 border-b border-outline-variant/10 text-sm last:border-b-0">
                          <span className="font-body-md text-on-surface font-semibold">{district}</span>
                          <div className="flex items-center gap-2.5">
                            <span className="material-symbols-outlined text-on-surface-variant text-[20px]">{data.condition}</span>
                            <span className="font-mono text-on-surface font-bold text-right w-8">{data.temp}°C</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-on-surface-variant py-6 text-center">Unable to load -- backend unreachable.</p>
                  )}
                </div>
              )}

            </div>
          </div>

          {/* Quick Links Card */}
          <div className="bg-surface-container-lowest rounded-xl soft-shadow border border-outline-variant/30 p-4">
            <h3 className="font-headline-md text-headline-md text-on-surface mb-4">Quick Links</h3>
            <div className="grid grid-cols-1 gap-3">
              <button
                onClick={() => onNavigate('analytics')}
                className="w-full flex items-center p-3 rounded-lg bg-surface hover:bg-surface-container-high transition-colors border border-outline-variant/20 min-h-touch-target-min group cursor-pointer text-left"
              >
                <div className="p-2 bg-primary-container/10 rounded-md text-primary mr-3 group-hover:bg-primary group-hover:text-on-primary transition-colors">
                  <span className="material-symbols-outlined">analytics</span>
                </div>
                <span className="font-body-md text-on-surface flex-grow">Analytics Dashboard</span>
                <span className="material-symbols-outlined text-on-surface-variant group-hover:translate-x-1 transition-transform">chevron_right</span>
              </button>

              <button
                onClick={() => onNavigate('comparison')}
                className="w-full flex items-center p-3 rounded-lg bg-surface hover:bg-surface-container-high transition-colors border border-outline-variant/20 min-h-touch-target-min group cursor-pointer text-left"
              >
                <div className="p-2 bg-primary-container/10 rounded-md text-primary mr-3 group-hover:bg-primary group-hover:text-on-primary transition-colors">
                  <span className="material-symbols-outlined">compare</span>
                </div>
                <span className="font-body-md text-on-surface flex-grow">Scenario Comparison</span>
                <span className="material-symbols-outlined text-on-surface-variant group-hover:translate-x-1 transition-transform">chevron_right</span>
              </button>

              <button
                onClick={() => onNavigate('reports')}
                className="w-full flex items-center p-3 rounded-lg bg-surface hover:bg-surface-container-high transition-colors border border-outline-variant/20 min-h-touch-target-min group cursor-pointer text-left"
              >
                <div className="p-2 bg-primary-container/10 rounded-md text-primary mr-3 group-hover:bg-primary group-hover:text-on-primary transition-colors">
                  <span className="material-symbols-outlined">description</span>
                </div>
                <span className="font-body-md text-on-surface flex-grow">Generate Reports</span>
                <span className="material-symbols-outlined text-on-surface-variant group-hover:translate-x-1 transition-transform">chevron_right</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
