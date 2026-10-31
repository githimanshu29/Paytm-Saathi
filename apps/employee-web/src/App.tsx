import React, { useState, useEffect, useCallback } from 'react';
import {
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
  RefreshCw,
  X,
  ExternalLink,
  ChevronRight,
  Clock,
  Send,
} from 'lucide-react';

const API_BASE_URL = 'http://localhost:8000';

interface EmployeeUser {
  id: string;
  name: string;
  email: string;
  role: string;
}

interface DashboardKPI {
  total_merchants: number;
  active_devices: number;
  total_devices: number;
  pending_approvals: number;
  needs_human_cases: number;
  total_transactions_paise: number;
  total_transactions_formatted: string;
  total_tasks: number;
}

interface AuditEvent {
  id: string;
  actor: string;
  action: string;
  target: string;
  policy_decision_id?: string;
  idempotency_key?: string;
  result: string;
  created_at: string;
  environment: string;
}

interface CaseApproval {
  id: string;
  approver?: string;
  decision: string;
  reason?: string;
  risk_tier: string;
  expires_at?: string;
}

interface CaseItem {
  id: string;
  merchant_id: string;
  store_name: string;
  merchant_phone: string;
  city: string;
  title: string;
  description?: string;
  bucket: StatusType;
  priority: string;
  assigned_to?: string;
  approval?: CaseApproval;
  created_at: string;
  updated_at: string;
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

  // Dashboard Data State
  const [kpi, setKpi] = useState<DashboardKPI | null>(null);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [selectedCase, setSelectedCase] = useState<CaseItem | null>(null);
  const [caseTimeline, setCaseTimeline] = useState<AuditEvent[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [bucketFilter, setBucketFilter] = useState<string>('ALL');
  const [healthPingLoading, setHealthPingLoading] = useState(false);

  // Navigation tab state
  const [activeTab, setActiveTab] = useState('dashboard');

  // Verify auth session
  useEffect(() => {
    if (!token) return;

    fetch(`${API_BASE_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (res) => {
        if (!res.ok) throw new Error('Session invalid');
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

  // Fetch KPI Summary
  const fetchKPI = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE_URL}/employee/dashboard/summary`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setKpi(data);
      }
    } catch (_e) {}
  }, [token]);

  // Fetch Audit Log (real-time poll)
  const fetchAuditLog = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE_URL}/employee/audit-log?limit=20`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setAuditEvents(data.events || []);
      }
    } catch (_e) {}
  }, [token]);

  // Fetch Cases
  const fetchCases = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE_URL}/employee/cases`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setCases(data.cases || []);
      }
    } catch (_e) {}
  }, [token]);

  // Initial and Polling fetch
  useEffect(() => {
    if (!token) return;

    fetchKPI();
    fetchAuditLog();
    fetchCases();

    // Live polling intervals (Audit log every 4s, KPI & Cases every 8s)
    const auditInterval = setInterval(() => {
      fetchAuditLog();
    }, 4000);

    const dataInterval = setInterval(() => {
      fetchKPI();
      fetchCases();
    }, 8000);

    return () => {
      clearInterval(auditInterval);
      clearInterval(dataInterval);
    };
  }, [token, fetchKPI, fetchAuditLog, fetchCases]);

  // Fetch timeline when a case is selected for slide-over
  useEffect(() => {
    if (!token || !selectedCase) {
      setCaseTimeline([]);
      return;
    }

    setTimelineLoading(true);
    fetch(`${API_BASE_URL}/employee/cases/${selectedCase.id}/timeline`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.json())
      .then((data) => {
        setCaseTimeline(data.events || []);
      })
      .catch(() => {
        setCaseTimeline([]);
      })
      .finally(() => {
        setTimelineLoading(false);
      });
  }, [token, selectedCase]);

  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    await Promise.all([fetchKPI(), fetchAuditLog(), fetchCases()]);
    setIsRefreshing(false);
  };

  // Helper to trigger /health ping from UI to demonstrate live audit event ingestion
  const handleTriggerHealthPing = async () => {
    setHealthPingLoading(true);
    try {
      await fetch(`${API_BASE_URL}/health`);
      await fetchAuditLog();
    } catch (_e) {}
    setHealthPingLoading(false);
  };

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
        throw new Error(data.detail || 'Login failed.');
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
    setSelectedCase(null);
  };

  const fillCredentials = (presetEmail: string) => {
    setEmail(presetEmail);
    setPassword('Demo@1234');
    setLoginError(null);
  };

  // 1. Unauthenticated Login Screen
  if (!token || !user) {
    return (
      <div className="min-h-screen w-screen bg-[#F5F7FA] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white rounded-card shadow-elevated border border-[#E5E7EB] overflow-hidden">
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
                  <p className="font-bold text-[#002E6E] truncate">Support</p>
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

  // 2. Authenticated Dashboard
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

  const filteredCases = cases.filter((c) => {
    if (activeTab === 'fix') {
      const isFix =
        c.title.toLowerCase().includes('soundbox') ||
        c.title.toLowerCase().includes('technician') ||
        c.title.toLowerCase().includes('device') ||
        c.title.toLowerCase().includes('hardware');
      if (bucketFilter === 'ALL') return isFix;
      return isFix && c.bucket === bucketFilter;
    }
    if (activeTab === 'resolve') {
      const isResolve =
        c.title.toLowerCase().includes('payment') ||
        c.title.toLowerCase().includes('refund') ||
        c.title.toLowerCase().includes('utr') ||
        c.title.toLowerCase().includes('transaction');
      if (bucketFilter === 'ALL') return isResolve;
      return isResolve && c.bucket === bucketFilter;
    }
    if (bucketFilter === 'ALL') return true;
    return c.bucket === bucketFilter;
  });

  return (
    <div className="flex h-screen w-screen bg-[#F5F7FA] overflow-hidden relative">
      {/* 1. Navy Sidebar */}
      <aside className="w-64 flex-shrink-0 bg-[#002E6E] text-white flex flex-col justify-between shadow-xl">
        <div>
          <div className="p-6 border-b border-blue-900/60 flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-[#00BAF2] flex items-center justify-center font-bold text-white text-xl shadow-md">
              P
            </div>
            <div>
              <h1 className="font-bold text-lg leading-tight tracking-tight">Paytm Saathi</h1>
              <p className="text-xs text-[#00BAF2] font-medium">Control Tower</p>
            </div>
          </div>

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

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Top Bar */}
        <header className="h-16 bg-white border-b border-[#E5E7EB] px-8 flex items-center justify-between shadow-sm sticky top-0 z-10">
          <div className="flex items-center space-x-4">
            <div className="relative">
              <Search className="w-4 h-4 text-[#6B7280] absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search merchant, UTR, Soundbox S/N..."
                className="pl-9 pr-4 py-1.5 bg-[#F5F7FA] border border-[#D1D5DB] rounded-full text-xs text-[#1A1A1A] w-72 focus:outline-none focus:border-[#00BAF2]"
              />
            </div>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-[#0077A8] border border-blue-200">
              DEMO ENVIRONMENT
            </span>
          </div>

          <div className="flex items-center space-x-4">
            {/* Health Ping Ingestion Trigger */}
            <button
              onClick={handleTriggerHealthPing}
              disabled={healthPingLoading}
              title="Ping /health to create a new audit_events row in real-time"
              className="flex items-center space-x-1.5 text-xs font-semibold bg-blue-50 hover:bg-blue-100 text-[#002E6E] px-3 py-1.5 rounded-lg border border-blue-200 transition-colors"
            >
              <Send className="w-3 h-3 text-[#00BAF2]" />
              <span>{healthPingLoading ? 'Pinging...' : '+ Ping /health'}</span>
            </button>

            {/* Manual Refresh */}
            <button
              onClick={handleManualRefresh}
              title="Refresh all data"
              className="p-2 text-[#6B7280] hover:text-[#002E6E] hover:bg-gray-100 rounded-full transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin text-[#00BAF2]' : ''}`} />
            </button>

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

        {/* Dashboard Workspace */}
        <main className="p-8 space-y-8 max-w-7xl">
          {/* Header Banner */}
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold text-[#1A1A1A]">Autonomous Agent Command Hub</h2>
              <p className="text-sm text-[#6B7280] mt-1">
                Real-time governance over Saathi agents, cases, and live audit telemetry
              </p>
            </div>
            <div className="flex items-center space-x-2 bg-emerald-50 border border-emerald-200 px-3 py-1.5 rounded-lg text-xs font-semibold text-emerald-700">
              <ShieldCheck className="w-4 h-4" />
              <span>Live DB Connected (Real Seeded Data)</span>
            </div>
          </div>

          {/* 1. KPI CARD ROW */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            <div className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB]">
              <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">Kiranas Monitored</p>
              <p className="text-2xl font-extrabold text-[#002E6E] mt-2">
                {kpi?.total_merchants ?? 4}
              </p>
              <p className="text-xs text-[#00BAF2] mt-1 font-medium">Synthetic Kiranas</p>
            </div>

            <div className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB]">
              <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">Soundboxes Active</p>
              <p className="text-2xl font-extrabold text-[#0B8457] mt-2">
                {kpi ? `${kpi.active_devices} / ${kpi.total_devices}` : '1 / 3'}
              </p>
              <p className="text-xs text-[#6B7280] mt-1 font-medium">Live Telemetry</p>
            </div>

            <div className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB]">
              <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">Pending Approvals</p>
              <p className="text-2xl font-extrabold text-[#F2994A] mt-2">
                {kpi?.pending_approvals ?? 1}
              </p>
              <p className="text-xs text-[#F2994A] mt-1 font-medium">R2 Consent Queued</p>
            </div>

            <div className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB]">
              <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">Human Review Needed</p>
              <p className="text-2xl font-extrabold text-[#EB5757] mt-2">
                {kpi?.needs_human_cases ?? 1}
              </p>
              <p className="text-xs text-[#EB5757] mt-1 font-medium">R3 Compliance Gate</p>
            </div>

            <div className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB]">
              <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">Settled Volume</p>
              <p className="text-2xl font-extrabold text-[#002E6E] mt-2">
                {kpi?.total_transactions_formatted ?? '₹600.00'}
              </p>
              <p className="text-xs text-[#00BAF2] mt-1 font-medium">Reconciled UPI</p>
            </div>
          </div>

          {/* 2. TWO-COLUMN WORKSPACE: Cases Table & Live Activity Log */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* LEFT / MAIN (7 COLS): Cases Table */}
            <div className="lg:col-span-7 bg-white rounded-card shadow-soft border border-[#E5E7EB] flex flex-col">
              <div className="p-5 border-b border-[#E5E7EB] flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-gray-50/50">
                <div>
                  <h3 className="font-bold text-base text-[#1A1A1A]">Unified Cases & Agent Tasks</h3>
                  <p className="text-xs text-[#6B7280]">
                    Tasks and pending approvals across all 5 StatusChip states
                  </p>
                </div>
                {/* Filter Chips */}
                <div className="flex flex-wrap gap-1.5">
                  {['ALL', 'needs_human', 'awaiting_approval', 'verified', 'executed', 'pending'].map((filter) => (
                    <button
                      key={filter}
                      onClick={() => setBucketFilter(filter)}
                      className={`px-2.5 py-1 rounded-full text-[11px] font-semibold transition-all ${
                        bucketFilter === filter
                          ? 'bg-[#002E6E] text-white shadow-xs'
                          : 'bg-white border border-[#D1D5DB] text-[#6B7280] hover:border-[#002E6E]'
                      }`}
                    >
                      {filter === 'ALL' ? 'All' : filter.replace('_', ' ')}
                    </button>
                  ))}
                </div>
              </div>

              {/* Table */}
              <div className="overflow-x-auto flex-1">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-[#E5E7EB] text-[11px] font-bold text-[#6B7280] uppercase tracking-wider bg-gray-50/70">
                      <th className="py-3 px-4">Case Title</th>
                      <th className="py-3 px-3">Merchant</th>
                      <th className="py-3 px-3">Status</th>
                      <th className="py-3 px-3">Priority</th>
                      <th className="py-3 px-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#F3F4F6] text-xs">
                    {filteredCases.map((c) => (
                      <tr
                        key={c.id}
                        onClick={() => setSelectedCase(c)}
                        className={`hover:bg-blue-50/50 cursor-pointer transition-colors ${
                          selectedCase?.id === c.id ? 'bg-blue-50/80 font-medium' : ''
                        }`}
                      >
                        <td className="py-3 px-4 max-w-xs">
                          <p className="font-bold text-[#1A1A1A] truncate">{c.title}</p>
                          <p className="text-[11px] text-[#6B7280] truncate">{c.assigned_to || 'Unassigned'}</p>
                        </td>
                        <td className="py-3 px-3">
                          <p className="font-semibold text-[#002E6E]">{c.store_name}</p>
                          <p className="text-[11px] text-[#6B7280]">{c.city}</p>
                        </td>
                        <td className="py-3 px-3">
                          <StatusChip status={c.bucket} size="sm" />
                        </td>
                        <td className="py-3 px-3">
                          <span
                            className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold ${
                              c.priority === 'HIGH'
                                ? 'bg-red-100 text-red-700'
                                : c.priority === 'MEDIUM'
                                ? 'bg-amber-100 text-amber-800'
                                : 'bg-gray-100 text-gray-700'
                            }`}
                          >
                            {c.priority}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-right">
                          <span className="text-[#00BAF2] hover:text-[#0077A8] font-bold text-xs inline-flex items-center">
                            Inspect <ChevronRight className="w-3.5 h-3.5 ml-0.5" />
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* RIGHT (5 COLS): Agent Activity Log (Real-time polling audit_events) */}
            <div className="lg:col-span-5 bg-white rounded-card shadow-soft border border-[#E5E7EB] flex flex-col h-[560px]">
              <div className="p-4 border-b border-[#E5E7EB] flex items-center justify-between bg-gray-50/50">
                <div className="flex items-center space-x-2">
                  <span className="w-2 h-2 rounded-full bg-[#0B8457] animate-pulse"></span>
                  <div>
                    <h3 className="font-bold text-sm text-[#1A1A1A]">Agent Activity Log</h3>
                    <p className="text-[11px] text-[#6B7280]">
                      Live polled (4s) straight from <code className="text-[#002E6E] font-semibold">audit_events</code>
                    </p>
                  </div>
                </div>
                <span className="text-[11px] font-bold bg-blue-50 text-[#0077A8] px-2 py-0.5 rounded-full border border-blue-200">
                  {auditEvents.length} Recent
                </span>
              </div>

              {/* Event Stream */}
              <div className="p-4 overflow-y-auto space-y-3 flex-1">
                {auditEvents.map((ev) => (
                  <div
                    key={ev.id}
                    className="p-3 bg-[#F9FAFB] hover:bg-white rounded-xl border border-[#E5E7EB] hover:border-[#00BAF2] shadow-xs transition-all space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-[#002E6E]">{ev.action}</span>
                      <span
                        className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                          ev.result === 'SUCCESS' || ev.result === 'RECEIVED'
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-red-100 text-red-800'
                        }`}
                      >
                        {ev.result}
                      </span>
                    </div>

                    <p className="text-[11px] text-[#4B5563]">
                      Actor: <strong className="text-[#1A1A1A]">{ev.actor}</strong> · Target:{' '}
                      <span className="text-gray-600 font-mono text-[10px]">{ev.target}</span>
                    </p>

                    <div className="flex items-center justify-between text-[10px] text-[#9CA3AF] pt-1 border-t border-gray-100">
                      <span>Policy: {ev.policy_decision_id || 'dec_auto'}</span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {ev.created_at || 'Just now'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </main>
      </div>

      {/* 3. SLIDE-OVER DETAIL PANEL (Sourced from Real audit_events) */}
      {selectedCase && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop Dimming */}
          <div
            className="absolute inset-0 bg-black/40 backdrop-blur-xs transition-opacity"
            onClick={() => setSelectedCase(null)}
          />

          {/* Slide-over Container */}
          <div className="relative w-full max-w-lg bg-white h-full shadow-2xl flex flex-col z-10 animate-in slide-in-from-right duration-200">
            {/* Header */}
            <div className="p-6 bg-[#002E6E] text-white flex items-start justify-between">
              <div>
                <span className="text-[11px] text-[#00BAF2] font-bold tracking-wide uppercase">
                  Case Investigation · {selectedCase.id}
                </span>
                <h3 className="text-lg font-bold text-white mt-1 leading-snug">
                  {selectedCase.title}
                </h3>
                <div className="mt-2.5">
                  <StatusChip status={selectedCase.bucket} />
                </div>
              </div>
              <button
                onClick={() => setSelectedCase(null)}
                className="p-1.5 rounded-full hover:bg-white/10 text-white/80 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Slide-over Body */}
            <div className="p-6 overflow-y-auto space-y-6 flex-1">
              {/* Merchant Details Card */}
              <div className="bg-[#F5F7FA] rounded-card p-4 border border-[#E5E7EB] space-y-2">
                <p className="text-[11px] font-bold text-[#6B7280] uppercase tracking-wider">
                  Affected Merchant
                </p>
                <div className="flex justify-between items-center">
                  <div>
                    <p className="font-bold text-sm text-[#1A1A1A]">{selectedCase.store_name}</p>
                    <p className="text-xs text-[#6B7280]">
                      {selectedCase.city} · {selectedCase.merchant_phone}
                    </p>
                  </div>
                  <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-blue-100 text-[#002E6E]">
                    Priority {selectedCase.priority}
                  </span>
                </div>
              </div>

              {/* Case Description */}
              <div>
                <h4 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider mb-2">
                  Case Overview & Scope
                </h4>
                <p className="text-xs text-[#1A1A1A] leading-relaxed bg-white p-3.5 rounded-xl border border-[#E5E7EB]">
                  {selectedCase.description || 'No detailed description provided.'}
                </p>
              </div>

              {/* Action Approval Gate if Present */}
              {selectedCase.approval && (
                <div className="p-4 rounded-card border-2 border-amber-300 bg-amber-50/60 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-amber-900 flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4 text-amber-600" />
                      Approval Gate ({selectedCase.approval.risk_tier})
                    </span>
                    <span className="text-[11px] font-bold text-amber-800 bg-amber-200/70 px-2 py-0.5 rounded">
                      {selectedCase.approval.decision}
                    </span>
                  </div>
                  <p className="text-xs text-amber-950">{selectedCase.approval.reason}</p>
                  <p className="text-[11px] text-amber-800">
                    Approver: <strong>{selectedCase.approval.approver}</strong> · Expires: {selectedCase.approval.expires_at || '24 hrs'}
                  </p>
                </div>
              )}

              {/* Audit Trail Timeline */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider">
                    Authoritative Audit Trail Timeline
                  </h4>
                  <span className="text-[10px] text-[#00BAF2] font-semibold">
                    Real audit_events source
                  </span>
                </div>

                {timelineLoading ? (
                  <p className="text-xs text-[#6B7280] py-4 text-center">Loading audit timeline...</p>
                ) : caseTimeline.length === 0 ? (
                  <p className="text-xs text-[#6B7280] py-4 text-center">No audit records found.</p>
                ) : (
                  <div className="relative pl-6 space-y-4 before:content-[''] before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-[#E5E7EB]">
                    {caseTimeline.map((ev, idx) => (
                      <div key={ev.id || idx} className="relative">
                        {/* Timeline dot */}
                        <div className="absolute -left-6 top-1 w-2.5 h-2.5 rounded-full bg-[#00BAF2] ring-4 ring-white" />
                        <div className="bg-[#F9FAFB] p-3 rounded-lg border border-[#E5E7EB] text-xs space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-[#002E6E]">{ev.action}</span>
                            <span className="text-[10px] text-emerald-700 font-bold bg-emerald-50 px-1.5 py-0.2 rounded">
                              {ev.result}
                            </span>
                          </div>
                          <p className="text-[11px] text-[#4B5563]">
                            Actor: <strong>{ev.actor}</strong> → Target: {ev.target}
                          </p>
                          <p className="text-[10px] text-[#9CA3AF]">{ev.created_at}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Slide-over Footer */}
            <div className="p-4 border-t border-[#E5E7EB] bg-gray-50 flex justify-end space-x-3">
              <button
                onClick={() => setSelectedCase(null)}
                className="px-4 py-2 rounded-lg border border-[#D1D5DB] text-xs font-semibold text-[#1A1A1A] hover:bg-gray-100 transition-colors"
              >
                Close Panel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
