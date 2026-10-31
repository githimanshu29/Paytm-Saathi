import React, { useState, useEffect } from 'react';
import {
  colors,
  StatusChip,
  StatusType,
} from '@paytm-saathi/design-tokens';
import {
  LayoutDashboard,
  ShieldAlert,
  Wrench,
  Scale,
  Activity,
  UserCheck,
  MapPin,
  Coins,
  History,
  Bell,
  Search,
  CheckCircle2,
  AlertTriangle,
  LogOut,
  Lock,
  Mail,
  ArrowRight,
  ShieldCheck,
} from 'lucide-react';

const API_BASE_URL = 'http://localhost:8000';

interface EmployeeUser {
  id: string;
  name: string;
  email: string;
  role: string;
}

export function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('saathi_employee_token'));
  const [user, setUser] = useState<EmployeeUser | null>(() => {
    const saved = localStorage.getItem('saathi_employee_user');
    return saved ? JSON.parse(saved) : null;
  });

  // Login form state
  const [email, setEmail] = useState('support@paytm.demo');
  const [password, setPassword] = useState('Demo@1234');
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  // App navigation state
  const [activeTab, setActiveTab] = useState('dashboard');

  // Verify token on mount / route protection
  useEffect(() => {
    if (!token) return;

    fetch(`${API_BASE_URL}/auth/me`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })
      .then(async (res) => {
        if (!res.ok) {
          throw new Error('Token expired or invalid');
        }
        return res.json();
      })
      .then((data) => {
        setUser({
          id: data.id,
          name: data.name,
          email: data.email || '',
          role: data.role,
        });
      })
      .catch(() => {
        handleLogout();
      });
  }, [token]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginLoading(true);
    setLoginError(null);

    try {
      const res = await fetch(`${API_BASE_URL}/auth/employee/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), password }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Login failed. Please check credentials.');
      }

      localStorage.setItem('saathi_employee_token', data.access_token);
      localStorage.setItem('saathi_employee_user', JSON.stringify(data.user));
      setToken(data.access_token);
      setUser(data.user);
    } catch (err: any) {
      setLoginError(err.message || 'Network error connecting to backend.');
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('saathi_employee_token');
    localStorage.removeItem('saathi_employee_user');
    setToken(null);
    setUser(null);
  };

  const fillCredentials = (presetEmail: string) => {
    setEmail(presetEmail);
    setPassword('Demo@1234');
    setLoginError(null);
  };

  // 1. Unauthenticated Route Protection -> Render Login Screen
  if (!token || !user) {
    return (
      <div className="min-h-screen w-screen bg-[#F5F7FA] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white rounded-card shadow-elevated border border-[#E5E7EB] overflow-hidden">
          {/* Branded Header */}
          <div className="bg-[#002E6E] p-8 text-white relative">
            <div className="w-12 h-12 rounded-2xl bg-[#00BAF2] flex items-center justify-center font-bold text-white text-2xl shadow-md mb-4">
              P
            </div>
            <h1 className="text-2xl font-bold">Paytm Saathi Control Tower</h1>
            <p className="text-xs text-[#00BAF2] mt-1 font-medium tracking-wide">
              EMPLOYEE CONSOLE · MULTI-AGENT GOVERNANCE
            </p>
          </div>

          <div className="p-8 space-y-6">
            {loginError && (
              <div className="p-3 bg-red-50 border border-red-200 text-[#EB5757] rounded-lg text-xs font-medium flex items-center space-x-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span>{loginError}</span>
              </div>
            )}

            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-[#1A1A1A] mb-1.5">
                  Corporate Email
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-[#6B7280] absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@paytm.demo"
                    className="w-full pl-9 pr-3 py-2 bg-[#F5F7FA] border border-[#D1D5DB] rounded-lg text-sm text-[#1A1A1A] focus:outline-none focus:border-[#00BAF2] transition-colors"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#1A1A1A] mb-1.5">
                  Password
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-[#6B7280] absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full pl-9 pr-3 py-2 bg-[#F5F7FA] border border-[#D1D5DB] rounded-lg text-sm text-[#1A1A1A] focus:outline-none focus:border-[#00BAF2] transition-colors"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loginLoading}
                className="w-full py-2.5 bg-[#00BAF2] hover:bg-[#009fd0] text-white font-semibold text-sm rounded-lg shadow-sm flex items-center justify-center space-x-2 transition-all disabled:opacity-60"
              >
                <span>{loginLoading ? 'Authenticating...' : 'Sign In to Control Tower'}</span>
                {!loginLoading && <ArrowRight className="w-4 h-4" />}
              </button>
            </form>

            {/* Seeded Demo Accounts Quick Selector */}
            <div className="pt-4 border-t border-[#E5E7EB] space-y-2">
              <p className="text-[11px] font-semibold text-[#6B7280] uppercase tracking-wider text-center">
                Quick-Select Seeded Demo Accounts (Password: Demo@1234)
              </p>
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => fillCredentials('support@paytm.demo')}
                  className="p-2 border border-[#E5E7EB] hover:border-[#00BAF2] rounded-lg bg-[#F5F7FA] hover:bg-blue-50/50 text-[11px] font-medium text-left transition-colors"
                >
                  <p className="font-bold text-[#002E6E] truncate">Support Agent</p>
                  <p className="text-[#6B7280] truncate">Rajesh S.</p>
                </button>
                <button
                  type="button"
                  onClick={() => fillCredentials('manager@paytm.demo')}
                  className="p-2 border border-[#E5E7EB] hover:border-[#00BAF2] rounded-lg bg-[#F5F7FA] hover:bg-blue-50/50 text-[11px] font-medium text-left transition-colors"
                >
                  <p className="font-bold text-[#002E6E] truncate">Manager</p>
                  <p className="text-[#6B7280] truncate">Pooja M.</p>
                </button>
                <button
                  type="button"
                  onClick={() => fillCredentials('sales@paytm.demo')}
                  className="p-2 border border-[#E5E7EB] hover:border-[#00BAF2] rounded-lg bg-[#F5F7FA] hover:bg-blue-50/50 text-[11px] font-medium text-left transition-colors"
                >
                  <p className="font-bold text-[#002E6E] truncate">Sales Rep</p>
                  <p className="text-[#6B7280] truncate">Amit V.</p>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 2. Authenticated Dashboard Shell
  const navItems = [
    { id: 'dashboard', label: 'Control Tower', icon: LayoutDashboard },
    { id: 'resolve', label: 'Resolve (Payments)', icon: ShieldAlert },
    { id: 'fix', label: 'Fix (Devices/Soundbox)', icon: Wrench },
    { id: 'reconcile', label: 'Reconcile (Settlements)', icon: Scale },
    { id: 'revive', label: 'Revive (Dormant)', icon: Activity },
    { id: 'onboard', label: 'Onboard (KYC)', icon: UserCheck },
    { id: 'fieldmate', label: 'FieldMate (Sales Copilot)', icon: MapPin },
    { id: 'vasooli', label: 'Vasooli (Receivables)', icon: Coins },
    { id: 'audit', label: 'Activity & Audit Log', icon: History },
  ];

  const chipStates: StatusType[] = [
    'verified',
    'executed',
    'pending',
    'awaiting_approval',
    'needs_human',
  ];

  return (
    <div className="flex h-screen w-screen bg-[#F5F7FA] overflow-hidden">
      {/* 1. Navy Sidebar */}
      <aside className="w-64 flex-shrink-0 bg-[#002E6E] text-white flex flex-col justify-between shadow-xl">
        <div>
          {/* Logo & Header */}
          <div className="p-6 border-b border-blue-900/60 flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-[#00BAF2] flex items-center justify-center font-bold text-white text-xl shadow-md">
              P
            </div>
            <div>
              <h1 className="font-bold text-lg leading-tight tracking-tight">Paytm Saathi</h1>
              <p className="text-xs text-[#00BAF2] font-medium">Employee Control Tower</p>
            </div>
          </div>

          {/* Navigation links */}
          <nav className="p-3 space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`w-full flex items-center space-x-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-[#00BAF2] text-white shadow-sm'
                      : 'text-blue-100/80 hover:bg-white/10 hover:text-white'
                  }`}
                >
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate">{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Footer Role Card & Logout */}
        <div className="p-4 border-t border-blue-900/60 bg-blue-950/40 space-y-3">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-full bg-[#00BAF2]/20 border border-[#00BAF2] text-[#00BAF2] flex items-center justify-center font-bold text-xs uppercase">
              {user.name.substring(0, 2)}
            </div>
            <div className="overflow-hidden flex-1">
              <p className="text-xs font-semibold text-white truncate">{user.name}</p>
              <p className="text-[11px] text-blue-200/70 truncate capitalize">
                {user.role.replace('_', ' ')}
              </p>
            </div>
          </div>

          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center space-x-2 px-3 py-1.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-300 text-xs font-medium transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main Content Shell */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* 2. Top Bar */}
        <header className="h-16 bg-white border-b border-[#E5E7EB] px-8 flex items-center justify-between shadow-sm sticky top-0 z-10">
          <div className="flex items-center space-x-4">
            <div className="relative">
              <Search className="w-4 h-4 text-[#6B7280] absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search merchant, UTR, Soundbox serial..."
                disabled
                className="pl-9 pr-4 py-1.5 bg-[#F5F7FA] border border-[#D1D5DB] rounded-full text-xs text-[#1A1A1A] w-72 focus:outline-none cursor-not-allowed opacity-80"
              />
            </div>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-[#0077A8] border border-blue-200">
              DEMO ENVIRONMENT
            </span>
          </div>

          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2 text-xs text-[#6B7280] bg-[#F5F7FA] px-3 py-1.5 rounded-lg border border-[#E5E7EB]">
              <span className="w-2 h-2 rounded-full bg-[#0B8457] animate-pulse"></span>
              <span>Backend Connected (Port 8000)</span>
            </div>
            <button
              onClick={handleLogout}
              title="Logout"
              className="p-2 text-[#6B7280] hover:text-[#EB5757] hover:bg-red-50 rounded-full transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* 3. Empty Shell Workspace Content */}
        <main className="p-8 space-y-8 max-w-7xl">
          {/* Header Banner */}
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold text-[#1A1A1A]">Autonomous Agent Command Hub</h2>
              <p className="text-sm text-[#6B7280] mt-1">
                Authenticated as <strong className="text-[#002E6E]">{user.name}</strong> ({user.role}) · Session Active
              </p>
            </div>
            <div className="flex items-center space-x-2 bg-emerald-50 border border-emerald-200 px-3 py-1.5 rounded-lg text-xs font-semibold text-emerald-700">
              <ShieldCheck className="w-4 h-4" />
              <span>JWT Authenticated</span>
            </div>
          </div>

          {/* Design System Status Chips Showcase */}
          <div className="bg-white rounded-card p-6 shadow-soft border border-[#E5E7EB] space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-sm text-[#1A1A1A]">
                  Shared Design System · Unified Status Chips
                </h3>
                <p className="text-xs text-[#6B7280]">
                  Imported directly from <code className="text-[#00BAF2]">@paytm-saathi/design-tokens</code>
                </p>
              </div>
              <span className="text-xs text-[#0B8457] font-medium flex items-center gap-1">
                <CheckCircle2 className="w-4 h-4" /> 5 Master States Ready
              </span>
            </div>

            <div className="flex flex-wrap gap-3 pt-2">
              {chipStates.map((st) => (
                <div key={st} className="flex flex-col gap-1">
                  <StatusChip status={st} />
                </div>
              ))}
            </div>
          </div>

          {/* KPI Cards Placeholder Row */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
            {[
              { label: 'Active Monitored Kiranas', value: '4 Merchants', sub: 'Synthetic Demo dataset' },
              { label: 'Soundboxes Online', value: '2 / 3 Active', sub: '1 device error detected' },
              { label: 'Pending Approvals (R2)', value: '1 Action', sub: 'SIM OTA restart queued' },
              { label: 'Human Review Needed (R3)', value: '1 Case', sub: 'KYC Document mismatch' },
            ].map((kpi, idx) => (
              <div
                key={idx}
                className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB] hover:shadow-elevated transition-shadow"
              >
                <p className="text-xs font-medium text-[#6B7280] uppercase tracking-wider">{kpi.label}</p>
                <p className="text-2xl font-bold text-[#1A1A1A] mt-2">{kpi.value}</p>
                <p className="text-xs text-[#00BAF2] mt-1 font-medium">{kpi.sub}</p>
              </div>
            ))}
          </div>

          {/* Empty Table Shell / Slide-over detail mockup */}
          <div className="bg-white rounded-card shadow-soft border border-[#E5E7EB] overflow-hidden">
            <div className="px-6 py-4 border-b border-[#E5E7EB] flex items-center justify-between bg-gray-50/50">
              <h4 className="font-semibold text-sm text-[#1A1A1A]">Saathi Agent Workflows Shell</h4>
              <span className="text-xs text-[#6B7280]">Phase 1 Authenticated Session</span>
            </div>
            <div className="p-12 text-center space-y-3">
              <div className="w-12 h-12 rounded-full bg-blue-50 text-[#00BAF2] flex items-center justify-center mx-auto">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <p className="font-semibold text-base text-[#1A1A1A]">Control Tower Ready</p>
              <p className="text-sm text-[#6B7280] max-w-md mx-auto">
                Logged in as <strong>{user.email}</strong>. The JWT token is securely stored and all requests pass through backend authentication.
              </p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
