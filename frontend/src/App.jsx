import React, { useState, useEffect } from 'react';
import OnboardingView from './views/OnboardingView';
import AuthView from './views/AuthView';
import ProfileSetupView from './views/ProfileSetupView';
import DashboardView from './views/DashboardView';
import AnalyticsView from './views/AnalyticsView';
import ComparisonView from './views/ComparisonView';
import RunOptimizationView from './views/RunOptimizationView';
import HistoryView from './views/HistoryView';
import ReportsView from './views/ReportsView';
import SettingsView from './views/SettingsView';
import { api, DISTRICTS } from './services/api';

const defaultAvatar = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23707a6f'><path d='M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z'/></svg>";

export default function App() {
  const [currentView, setCurrentView] = useState(() => {
    return localStorage.getItem('agro_currentView') || 'onboarding';
  }); // onboarding, login, register, profile-setup, dashboard, analytics, comparison, run-optimization, history, reports, settings
  const [selectedLanguage, setSelectedLanguage] = useState('en');
  const [dashboardLayout, setDashboardLayout] = useState('sidebar'); // 'sidebar' | 'topbar'
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [langMenuOpen, setLangMenuOpen] = useState(false);

  // Global user state populated via auth & profile completion. No fake
  // "Jane Doe" default -- a genuinely new user (nothing in localStorage
  // yet) has no identity and no profile until they actually provide one
  // via the onboarding -> auth -> profile-setup flow.
  const [user, setUser] = useState(() => {
    const stored = localStorage.getItem('agro_user');
    return stored ? JSON.parse(stored) : null;
  });

  useEffect(() => {
    localStorage.setItem('agro_currentView', currentView);
  }, [currentView]);

  useEffect(() => {
    if (user) {
      localStorage.setItem('agro_user', JSON.stringify(user));
    } else {
      localStorage.removeItem('agro_user');
    }
  }, [user]);

  const [activePlanId, setActivePlanId] = useState('A');

  // A "complete" profile means we actually have a real district on file --
  // every dashboard-shell view depends on this to call the backend. Full
  // name is intentionally not required here: it's a cosmetic greeting
  // field a user can skip during profile setup, and DashboardView already
  // falls back gracefully when it's blank.
  const hasCompleteProfile = Boolean(user?.location && DISTRICTS.includes(user.location));

  // Startup health check -- confirms the FastAPI backend (localhost:8000)
  // is reachable so the shell can show a subtle "offline" indicator
  // instead of letting every view discover it independently.
  const [backendOnline, setBackendOnline] = useState(true);
  useEffect(() => {
    let cancelled = false;
    api.checkHealth()
      .then(() => { if (!cancelled) setBackendOnline(true); })
      .catch(() => { if (!cancelled) setBackendOnline(false); });
    return () => { cancelled = true; };
  }, []);

  const handleAuthSuccess = (userData, goToDashboard = false) => {
    const merged = { ...(user || {}), ...userData };
    setUser(merged);
    // Even a "returning login" only goes straight to the dashboard if we
    // actually have a real district on file -- otherwise (e.g. a brand
    // new visitor who used the Login tab) they still have to complete a
    // real profile first, same as Register does.
    const mergedHasProfile = Boolean(merged.location && DISTRICTS.includes(merged.location));
    setCurrentView(goToDashboard && mergedHasProfile ? 'dashboard' : 'profile-setup');
  };

  const handleProfileComplete = (profileData) => {
    setUser(prev => ({
      ...(prev || {}),
      ...profileData
    }));
    setCurrentView('dashboard');
  };

  const handleLogout = () => {
    localStorage.removeItem('agro_currentView');
    localStorage.removeItem('agro_user');
    setUser(null);
    setCurrentView('onboarding');
  };

  const handleToggleLayout = () => {
    setDashboardLayout(prev => (prev === 'sidebar' ? 'topbar' : 'sidebar'));
  };

  // Check if current view is a general dashboard page (needs navigation shell)
  const isDashboardShell = [
    'dashboard',
    'analytics',
    'comparison',
    'run-optimization',
    'history',
    'reports',
    'settings'
  ].includes(currentView);

  // Safety net: if something puts us on a dashboard-shell view without a
  // real profile (e.g. stale localStorage from a previous session, or a
  // logout that didn't fully clear state), bounce to profile-setup instead
  // of letting the shell render against a null/incomplete user.
  useEffect(() => {
    if (isDashboardShell && !hasCompleteProfile) {
      setCurrentView(user ? 'profile-setup' : 'onboarding');
    }
  }, [isDashboardShell, hasCompleteProfile, user]);

  const navigateTo = (view) => {
    setCurrentView(view);
    setMobileMenuOpen(false);
  };

  // Nav links helper
  const navLinks = [
    { id: 'dashboard', label: 'Home', icon: 'home' },
    { id: 'analytics', label: 'Analytics', icon: 'analytics' },
    { id: 'comparison', label: 'Comparison', icon: 'compare' },
    { id: 'run-optimization', label: 'Run Optimization', icon: 'model_training' },
    { id: 'history', label: 'History', icon: 'history' },
    { id: 'reports', label: 'Reports', icon: 'description' },
    { id: 'settings', label: 'Settings', icon: 'settings' },
  ];

  return (
    <div className="min-h-screen bg-background text-on-background font-body-md antialiased">
      {/* 1. Linear/Transactional Views (No Shell) */}
      {currentView === 'onboarding' && (
        <OnboardingView 
          onNavigate={setCurrentView} 
          selectedLanguage={selectedLanguage}
          onChangeLanguage={setSelectedLanguage}
        />
      )}

      {(currentView === 'login' || currentView === 'register') && (
        <AuthView 
          initialMode={currentView}
          onSuccess={handleAuthSuccess}
          selectedLanguage={selectedLanguage}
        />
      )}

      {currentView === 'profile-setup' && (
        <ProfileSetupView 
          initialProfile={user}
          onComplete={handleProfileComplete}
        />
      )}

      {/* 2. Main Application Navigation Shell */}
      {isDashboardShell && hasCompleteProfile && user && (
        <div className={`min-h-screen flex flex-col ${dashboardLayout === 'sidebar' ? 'md:flex-row' : ''}`}>
          
          {/* A. SIDEBAR LAYOUT (Layout 1) */}
          {dashboardLayout === 'sidebar' && (
            <aside className="hidden md:flex flex-col w-64 bg-surface-container-low border-r border-outline-variant/30 h-screen fixed left-0 top-0 py-4 z-40">
              <div className="px-6 py-4 flex items-center gap-3">
                <span className="material-symbols-outlined text-primary text-3xl font-bold" style={{ fontVariationSettings: "'FILL' 1" }}>spa</span>
                <div>
                  <h1 className="font-headline-md text-headline-md text-primary font-bold">AgroOptimize</h1>
                  <p className="font-label-sm text-label-sm text-on-surface-variant font-medium">Digital Stewardship</p>
                </div>
              </div>
              
              <nav className="flex-1 mt-6 px-3 space-y-1 overflow-y-auto">
                {navLinks.map((link) => {
                  const isActive = currentView === link.id;
                  return (
                    <button
                      key={link.id}
                      onClick={() => navigateTo(link.id)}
                      className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg font-label-md text-label-md transition-colors cursor-pointer text-left ${
                        isActive 
                          ? 'text-primary font-bold border-r-4 border-primary bg-primary-container/10' 
                          : 'text-on-surface-variant hover:bg-surface-container-high'
                      }`}
                    >
                      <span className="material-symbols-outlined" style={{ fontVariationSettings: isActive ? "'FILL' 1" : undefined }}>
                        {link.icon}
                      </span>
                      {link.label}
                    </button>
                  );
                })}
              </nav>

              <div className="mt-auto px-3 space-y-2 border-t border-outline-variant/30 pt-3">
                {/* Language Switcher in Sidebar */}
                <div className="relative">
                  <button 
                    onClick={() => setLangMenuOpen(!langMenuOpen)}
                    className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-on-surface-variant hover:bg-surface-container-high transition-colors font-label-md text-label-md text-left cursor-pointer"
                  >
                    <span className="material-symbols-outlined">language</span>
                    Language
                  </button>
                  {langMenuOpen && (
                    <div className="absolute bottom-12 left-4 w-40 bg-surface-container-lowest border border-outline-variant rounded-lg shadow-ambient z-50">
                      {['en', 'hi', 'ta'].map(langCode => (
                        <button
                          key={langCode}
                          onClick={() => { setSelectedLanguage(langCode); setLangMenuOpen(false); }}
                          className={`w-full text-left px-4 py-2 hover:bg-surface-container-low font-label-sm text-label-sm ${selectedLanguage === langCode ? 'text-primary font-bold' : 'text-on-surface'}`}
                        >
                          {langCode === 'en' ? 'English' : langCode === 'hi' ? 'Hindi (हिंदी)' : 'Tamil (தமிழ்)'}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <button 
                  onClick={handleLogout}
                  className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-on-surface-variant hover:bg-error-container/30 hover:text-error transition-colors font-label-md text-label-md text-left cursor-pointer"
                >
                  <span className="material-symbols-outlined">logout</span>
                  Logout
                </button>

                {/* Profile card at the bottom of sidebar */}
                <div 
                  onClick={() => navigateTo('settings')}
                  className="px-4 py-3 flex items-center gap-3 hover:bg-surface-container-high rounded-lg cursor-pointer transition-colors"
                >
                  <img 
                    alt="User profile" 
                    className="w-10 h-10 rounded-full object-cover border border-outline-variant" 
                    src={user.avatar || defaultAvatar}
                  />
                  <div className="overflow-hidden">
                    <p className="font-label-md text-label-md text-on-surface truncate font-semibold">{user.fullName}</p>
                    <p className="font-label-sm text-label-sm text-on-surface-variant truncate">Farmer/Steward</p>
                  </div>
                </div>
              </div>
            </aside>
          )}

          {/* B. TOPBAR LAYOUT (Layout 2) */}
          {dashboardLayout === 'topbar' && (
            <nav className="hidden md:flex w-full top-0 sticky bg-surface border-b border-surface-container-highest shadow-sm z-50 flex justify-between items-center h-16 px-8 max-w-full mx-auto">
              <div className="flex items-center gap-8">
                <span className="font-headline-md text-headline-md font-bold text-primary flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary text-3xl font-bold" style={{ fontVariationSettings: "'FILL' 1" }}>spa</span>
                  AgroOptimize
                </span>
                <div className="flex gap-4 items-center h-full">
                  {navLinks.map((link) => {
                    const isActive = currentView === link.id;
                    return (
                      <button
                        key={link.id}
                        onClick={() => navigateTo(link.id)}
                        className={`px-3 py-1.5 rounded-md font-label-md text-label-md cursor-pointer transition-all ${
                          isActive 
                            ? 'bg-primary-container/10 text-primary font-bold' 
                            : 'text-on-surface-variant hover:text-primary'
                        }`}
                      >
                        {link.label}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="flex items-center gap-4">
                <button 
                  onClick={handleLogout}
                  className="text-on-surface-variant hover:bg-error-container/20 hover:text-error px-3 py-1.5 rounded-md transition-colors text-sm font-semibold cursor-pointer"
                >
                  Logout
                </button>
                <img 
                  onClick={() => navigateTo('settings')}
                  alt="User profile" 
                  className="w-10 h-10 rounded-full object-cover border border-outline-variant hover:border-primary transition-colors cursor-pointer" 
                  src={user.avatar || defaultAvatar}
                />
              </div>
            </nav>
          )}

          {/* C. MOBILE TOP NAVBAR */}
          <header className="flex justify-between items-center h-16 px-4 bg-surface border-b border-surface-container-high shadow-sm sticky top-0 z-40 md:hidden">
            <div className="flex items-center">
              <button 
                onClick={() => setMobileMenuOpen(true)}
                className="mr-3 text-on-surface-variant hover:bg-surface-container-high rounded-full p-2 transition-all cursor-pointer flex items-center"
              >
                <span className="material-symbols-outlined">menu</span>
              </button>
              <h2 className="font-headline-md text-headline-md font-bold text-primary flex items-center gap-1.5">
                <span className="material-symbols-outlined text-primary text-2xl font-bold" style={{ fontVariationSettings: "'FILL' 1" }}>spa</span>
                AgroOptimize
              </h2>
            </div>
            
            <div className="flex items-center gap-3">
              <img 
                onClick={() => navigateTo('settings')}
                alt="User avatar" 
                className="w-9 h-9 rounded-full object-cover border border-outline-variant cursor-pointer" 
                src={user.avatar || defaultAvatar}
              />
            </div>
          </header>

          {/* D. MOBILE MENU DRAWER OVERLAY */}
          {mobileMenuOpen && (
            <div className="fixed inset-0 z-50 flex md:hidden bg-inverse-surface/40 backdrop-blur-sm animate-[fadeIn_0.2s_ease-out]">
              <div className="w-64 bg-surface-container-lowest h-full flex flex-col p-4 space-y-4 animate-[slideIn_0.2s_ease-out]">
                <div className="flex justify-between items-center px-2 py-2">
                  <span className="font-headline-md text-headline-md font-bold text-primary flex items-center gap-1">
                    <span className="material-symbols-outlined text-primary text-2xl font-bold" style={{ fontVariationSettings: "'FILL' 1" }}>spa</span>
                    AgroOptimize
                  </span>
                  <button 
                    onClick={() => setMobileMenuOpen(false)}
                    className="text-on-surface-variant hover:text-primary cursor-pointer p-1"
                  >
                    <span className="material-symbols-outlined">close</span>
                  </button>
                </div>

                <nav className="flex-1 space-y-1">
                  {navLinks.map((link) => {
                    const isActive = currentView === link.id;
                    return (
                      <button
                        key={link.id}
                        onClick={() => navigateTo(link.id)}
                        className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg font-label-md text-label-md cursor-pointer text-left ${
                          isActive 
                            ? 'text-primary font-bold bg-primary-container/10' 
                            : 'text-on-surface-variant hover:bg-surface-container-high'
                        }`}
                      >
                        <span className="material-symbols-outlined" style={{ fontVariationSettings: isActive ? "'FILL' 1" : undefined }}>
                          {link.icon}
                        </span>
                        {link.label}
                      </button>
                    );
                  })}
                </nav>

                <div className="border-t border-outline-variant/30 pt-4 space-y-2">
                  <button
                    onClick={() => { navigateTo('settings'); setMobileMenuOpen(false); }}
                    className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-on-surface-variant hover:bg-surface-container-high text-left cursor-pointer"
                  >
                    <span className="material-symbols-outlined">settings</span>
                    Settings
                  </button>
                  <button 
                    onClick={handleLogout}
                    className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-on-surface-variant hover:bg-error-container/30 hover:text-error text-left cursor-pointer"
                  >
                    <span className="material-symbols-outlined">logout</span>
                    Logout
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* E. MAIN PAGE CANVAS WRAPPER */}
          <div className={`flex-grow flex flex-col min-h-screen ${dashboardLayout === 'sidebar' ? 'md:pl-64' : ''}`}>
            
            {/* View Canvas Content */}
            <main className="flex-grow p-4 md:p-8 max-w-7xl mx-auto w-full">
              {currentView === 'dashboard' && (
                <DashboardView
                  user={user}
                  onNavigate={navigateTo}
                  layout={dashboardLayout}
                  onToggleLayout={handleToggleLayout}
                />
              )}

              {currentView === 'analytics' && (
                <AnalyticsView
                  onNavigate={navigateTo}
                  userLocation={user.location}
                />
              )}

              {currentView === 'comparison' && (
                <ComparisonView
                  activePlanId={activePlanId}
                  onSelectPlan={setActivePlanId}
                  userLocation={user.location}
                  onNavigate={navigateTo}
                />
              )}

              {currentView === 'run-optimization' && (
                <RunOptimizationView
                  userLocation={user.location}
                  landSizeHa={Number(user.landSize) || 5}
                  onNavigate={navigateTo}
                />
              )}

              {currentView === 'history' && (
                <HistoryView userLocation={user.location} onNavigate={navigateTo} />
              )}

              {currentView === 'reports' && (
                <ReportsView userLocation={user.location} onNavigate={navigateTo} />
              )}

              {currentView === 'settings' && (
                <SettingsView 
                  user={user}
                  onUpdateUser={(updated) => setUser(prev => ({ ...prev, ...updated }))}
                  onLogout={handleLogout}
                  onChangeLanguage={setSelectedLanguage}
                  selectedLanguage={selectedLanguage}
                />
              )}
            </main>

            {/* Footer */}
            <footer className="w-full py-6 mt-auto bg-surface-container-lowest border-t border-outline-variant/30 flex flex-col md:flex-row justify-between items-center px-4 md:px-8 gap-4">
              <div className="text-center md:text-left">
                <span className="font-label-md text-label-md font-semibold text-primary block mb-1">AgroOptimize</span>
                <span className="font-label-sm text-label-sm text-on-surface-variant">© 2026 AgroOptimize. Digital Stewardship for Modern Farming.</span>
                <span className="font-label-sm text-label-sm text-on-surface-variant flex items-center gap-1.5 justify-center md:justify-start mt-1">
                  <span className={`inline-block w-1.5 h-1.5 rounded-full ${backendOnline ? 'bg-primary' : 'bg-error'}`}></span>
                  {backendOnline ? 'Live data connected' : 'Offline — showing cached data'}
                </span>
              </div>
              <div className="flex gap-4">
                <a className="font-label-sm text-label-sm text-on-surface-variant hover:text-primary transition-colors min-h-[48px] flex items-center" href="#" onClick={(e) => e.preventDefault()}>Privacy Policy</a>
                <a className="font-label-sm text-label-sm text-on-surface-variant hover:text-primary transition-colors min-h-[48px] flex items-center" href="#" onClick={(e) => e.preventDefault()}>Terms of Service</a>
                <a className="font-label-sm text-label-sm text-on-surface-variant hover:text-primary transition-colors min-h-[48px] flex items-center" href="#" onClick={(e) => e.preventDefault()}>Help Center</a>
              </div>
            </footer>

          </div>
        </div>
      )}
    </div>
  );
}
