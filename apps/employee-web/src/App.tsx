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
  TrendingDown,
  Play,
  CheckCircle,
  Sparkles,
  Phone,
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
  evidence_notes?: string;
  evidence_url?: string;
  dispute_amount_formatted?: string;
  created_at: string;
  updated_at: string;
}

interface ReviveFollowupDetail {
  id: string;
  cause_type: string;
  message_title: string;
  message_body: string;
  offer_code?: string;
  offer_details?: string;
  status: string;
  handed_off_to?: string;
  task_id?: string;
  delivered_at: string;
  responded_at?: string;
  merchant_response?: string;
}

interface ReviveMerchantItem {
  id: string;
  merchant_id: string;
  store_name: string;
  city: string;
  baseline_daily_tx_count: number;
  baseline_daily_volume_paise: number;
  baseline_daily_volume_inr: string;
  recent_daily_tx_count: number;
  recent_daily_volume_paise: number;
  recent_daily_volume_inr: string;
  drop_percentage: number;
  health_status: string;
  diagnosed_cause?: string;
  revival_stage: string;
  chip_status: StatusType;
  last_scanned_at: string;
  recovered_at?: string;
  active_followup?: ReviveFollowupDetail;
}

interface ReviveKPIData {
  total_at_risk: number;
  device_issues_count: number;
  settlement_issues_count: number;
  competitor_issues_count: number;
  followups_sent_count: number;
  warm_leads_count: number;
  revived_count: number;
}

interface DocumentItemSchema {
  id: string;
  document_type: string;
  status: string;
  file_name?: string;
  file_url?: string;
  ocr_quality_flag?: string;
  ocr_candidate_fields?: Record<string, any>;
  ocr_confidence?: number;
  is_ocr_passed: boolean;
  rejection_reason?: string;
  authorized_verification_status: string;
  verified_at?: string;
}

interface OnboardingApplicationItem {
  merchant_id: string;
  store_name: string;
  city: string;
  phone: string;
  onboarding_status: string;
  kyc_status: string;
  current_step: string;
  documents: DocumentItemSchema[];
  missing_documents: string[];
  blurry_documents: string[];
  can_submit_for_verification: boolean;
  is_fully_verified: boolean;
}

interface OnboardingPipelineResponse {
  total_applications: number;
  pending_applications: number;
  verified_applications: number;
  blurry_count: number;
  applications: OnboardingApplicationItem[];
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

  // Revive Agent & Dormancy Health State
  const [reviveKPI, setReviveKPI] = useState<ReviveKPIData | null>(null);
  const [reviveMerchants, setReviveMerchants] = useState<ReviveMerchantItem[]>([]);
  const [reviveFilter, setReviveFilter] = useState<string>('ALL');
  const [scanLoading, setScanLoading] = useState(false);
  const [scanNotice, setScanNotice] = useState<string | null>(null);
  const [recoveringMerchantId, setRecoveringMerchantId] = useState<string | null>(null);

  // Onboard Pipeline State
  const [pipelineData, setPipelineData] = useState<OnboardingPipelineResponse | null>(null);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineFilter, setPipelineFilter] = useState<string>('ALL');
  const [selectedApplication, setSelectedApplication] = useState<OnboardingApplicationItem | null>(null);
  const [verifyingMerchantId, setVerifyingMerchantId] = useState<string | null>(null);
  const [verificationFeedback, setVerificationFeedback] = useState<string | null>(null);

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

  // Fetch Revive Merchant Health & KPI
  const fetchReviveData = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE_URL}/employee/revive/merchants`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setReviveKPI(data.kpi);
        setReviveMerchants(data.merchants || []);
      }
    } catch (_e) {}
  }, [token]);

  const fetchPipeline = useCallback(async () => {
    if (!token) return;
    setPipelineLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/employee/onboarding/pipeline`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data: OnboardingPipelineResponse = await res.json();
        setPipelineData(data);
      }
    } catch (_e) {
    } finally {
      setPipelineLoading(false);
    }
  }, [token]);

  const handleEmployeeVerify = async (merchantId: string) => {
    if (!token) return;
    setVerifyingMerchantId(merchantId);
    setVerificationFeedback(null);
    try {
      const res = await fetch(`${API_BASE_URL}/employee/onboarding/verify/${merchantId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Verification failed');
      setVerificationFeedback(data.message);
      await Promise.all([fetchPipeline(), fetchAuditLog(), fetchKPI()]);
      setTimeout(() => setVerificationFeedback(null), 6000);
    } catch (err: any) {
      alert(err.message || 'Verification could not be processed.');
    } finally {
      setVerifyingMerchantId(null);
    }
  };

  // Initial and Polling fetch
  useEffect(() => {
    if (!token) return;

    fetchKPI();
    fetchAuditLog();
    fetchCases();
    fetchReviveData();

    // Live polling intervals (Audit log every 4s, KPI & Cases & Revive every 8s)
    const auditInterval = setInterval(() => {
      fetchAuditLog();
    }, 4000);

    const dataInterval = setInterval(() => {
      fetchKPI();
      fetchCases();
      fetchReviveData();
      fetchPipeline();
    }, 8000);

    return () => {
      clearInterval(auditInterval);
      clearInterval(dataInterval);
    };
  }, [token, fetchKPI, fetchAuditLog, fetchCases, fetchReviveData, fetchPipeline]);

  // Fetch pipeline when switching to onboard tab
  useEffect(() => {
    if (token && activeTab === 'onboard') {
      fetchPipeline();
    }
  }, [token, activeTab, fetchPipeline]);

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
    await Promise.all([fetchKPI(), fetchAuditLog(), fetchCases(), fetchReviveData(), fetchPipeline()]);
    setIsRefreshing(false);
  };

  // Trigger Revive Scan via POST /employee/revive/scan
  const handleTriggerReviveScan = async () => {
    if (!token || scanLoading) return;
    setScanLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/employee/revive/scan`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setScanNotice(`Dormancy scan completed: ${data.scanned_count} kiranas evaluated. Autonomous handoffs/offers dispatched!`);
        await Promise.all([fetchReviveData(), fetchAuditLog(), fetchCases(), fetchKPI()]);
        setTimeout(() => setScanNotice(null), 6000);
      }
    } catch (_e) {
      setScanNotice('Dormancy scan trigger failed.');
      setTimeout(() => setScanNotice(null), 4000);
    } finally {
      setScanLoading(false);
    }
  };

  // Simulate Recovery to prove the Honest Invariant live in UI
  const handleSimulateRecovery = async (merchantId: string) => {
    setRecoveringMerchantId(merchantId);
    try {
      const res = await fetch(`${API_BASE_URL}/demo/revive/${merchantId}/simulate-recovery`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          new_daily_volume_paise: 1200000,
          new_daily_tx_count: 40,
        }),
      });
      if (res.ok) {
        await Promise.all([fetchReviveData(), fetchAuditLog(), fetchKPI()]);
        setScanNotice(`Honest Invariant Verified for ${merchantId}: Fresh volume ≥80% baseline detected → Status updated to REVIVED!`);
        setTimeout(() => setScanNotice(null), 6000);
      }
    } catch (_e) {
      setScanNotice('Simulate recovery failed.');
      setTimeout(() => setScanNotice(null), 4000);
    } finally {
      setRecoveringMerchantId(null);
    }
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
    if (activeTab === 'reconcile') {
      const isReconcile =
        c.title.toLowerCase().includes('settlement') ||
        c.title.toLowerCase().includes('dispute') ||
        c.title.toLowerCase().includes('discrepancy') ||
        c.title.toLowerCase().includes('shortfall') ||
        c.title.toLowerCase().includes('reconcil');
      if (bucketFilter === 'ALL') return isReconcile;
      return isReconcile && c.bucket === bucketFilter;
    }
    if (activeTab === 'revive') {
      const isRevive =
        c.title.toLowerCase().includes('revive') ||
        c.title.toLowerCase().includes('retention') ||
        c.title.toLowerCase().includes('dormant') ||
        c.title.toLowerCase().includes('booster') ||
        c.title.toLowerCase().includes('sales');
      if (bucketFilter === 'ALL') return isRevive;
      return isRevive && c.bucket === bucketFilter;
    }
    if (bucketFilter === 'ALL') return true;
    return c.bucket === bucketFilter;
  });

  const filteredReviveMerchants = reviveMerchants.filter((m) => {
    if (reviveFilter === 'WARM_LEADS') {
      return m.revival_stage === 'WARM_LEAD';
    }
    if (reviveFilter === 'DEVICE') {
      return m.diagnosed_cause === 'DEVICE_ISSUE';
    }
    if (reviveFilter === 'SETTLEMENT') {
      return m.diagnosed_cause === 'SETTLEMENT_ISSUE';
    }
    if (reviveFilter === 'COMPETITOR') {
      return m.diagnosed_cause === 'COMPETITOR_OR_DISENGAGEMENT';
    }
    if (reviveFilter === 'REVIVED') {
      return m.revival_stage === 'REVIVED';
    }
    if (reviveFilter === 'AT_RISK') {
      return m.health_status === 'AT_RISK';
    }
    return true;
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
          {activeTab === 'revive' ? (
            /* MERCHANT HEALTH & REVIVAL WORKSPACE */
            <div className="space-y-6">
              {/* Header Banner */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="p-1.5 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-600">
                      <Activity className="w-5 h-5" />
                    </span>
                    <h2 className="text-2xl font-bold text-[#1A1A1A]">Merchant Health & Dormancy Recovery</h2>
                  </div>
                  <p className="text-sm text-[#6B7280] mt-1">
                    APScheduler decline engine (≥40% drop) · Reusable Fix/Reconcile diagnostics · Honest revival invariant tracking
                  </p>
                </div>
                <div className="flex items-center space-x-3">
                  <button
                    onClick={handleTriggerReviveScan}
                    disabled={scanLoading}
                    className="flex items-center space-x-2 px-4 py-2 bg-[#002E6E] hover:bg-[#002252] text-white text-xs font-bold rounded-lg shadow-sm transition-all disabled:opacity-60 cursor-pointer"
                  >
                    <Play className={`w-3.5 h-3.5 fill-current ${scanLoading ? 'animate-spin' : ''}`} />
                    <span>{scanLoading ? 'Evaluating Kiranas...' : 'Run Dormancy Scan Now'}</span>
                  </button>
                </div>
              </div>

              {/* Notice Banner */}
              {scanNotice && (
                <div className="p-3.5 bg-blue-50 border border-blue-200 rounded-xl text-xs font-semibold text-[#002E6E] flex items-center justify-between shadow-xs">
                  <div className="flex items-center space-x-2">
                    <Sparkles className="w-4 h-4 text-[#00BAF2]" />
                    <span>{scanNotice}</span>
                  </div>
                  <button onClick={() => setScanNotice(null)} className="text-gray-400 hover:text-gray-600 cursor-pointer">
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}

              {/* Revive KPI Row */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                <div className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB]">
                  <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">At-Risk Kiranas</p>
                  <p className="text-2xl font-extrabold text-[#EB5757] mt-2">
                    {reviveKPI?.total_at_risk ?? 3}
                  </p>
                  <p className="text-xs text-[#EB5757] mt-1 font-medium">Decline ≥ 40% Detected</p>
                </div>

                <div className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB]">
                  <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">Causes Diagnosed</p>
                  <p className="text-2xl font-extrabold text-[#F2994A] mt-2">
                    {reviveKPI ? (reviveKPI.device_issues_count + reviveKPI.settlement_issues_count + reviveKPI.competitor_issues_count) : 3}
                  </p>
                  <p className="text-xs text-[#6B7280] mt-1 font-medium">
                    {reviveKPI?.device_issues_count ?? 1} Dev · {reviveKPI?.settlement_issues_count ?? 1} Settle · {reviveKPI?.competitor_issues_count ?? 1} Offer
                  </p>
                </div>

                <div className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB]">
                  <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">Follow-ups Sent</p>
                  <p className="text-2xl font-extrabold text-[#00BAF2] mt-2">
                    {reviveKPI?.followups_sent_count ?? 1}
                  </p>
                  <p className="text-xs text-[#0077A8] mt-1 font-medium">Kirana Booster Delivered</p>
                </div>

                <div className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB]">
                  <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">Warm Leads Queued</p>
                  <p className="text-2xl font-extrabold text-indigo-600 mt-2">
                    {reviveKPI?.warm_leads_count ?? 1}
                  </p>
                  <p className="text-xs text-indigo-700 mt-1 font-medium">Amit V. (Sales Rep)</p>
                </div>

                <div className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB]">
                  <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">Verified Revived</p>
                  <p className="text-2xl font-extrabold text-[#0B8457] mt-2">
                    {reviveKPI?.revived_count ?? 0}
                  </p>
                  <p className="text-xs text-[#0B8457] mt-1 font-medium">Volume ≥80% Rechecked</p>
                </div>
              </div>

              {/* Honest Invariant Callout */}
              <div className="p-4 bg-emerald-50/70 border border-emerald-200 rounded-xl flex items-start space-x-3">
                <CheckCircle className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
                <div className="text-xs text-emerald-950">
                  <p className="font-bold">Core Invariant: Honest Revival Tracking (Follow-up Sent ≠ Revived)</p>
                  <p className="mt-0.5 text-emerald-900 leading-relaxed">
                    A merchant receiving or accepting a follow-up is safely tracked in <span className="font-semibold underline">FOLLOWUP_SENT</span> or <span className="font-semibold underline">WARM_LEAD</span> stage.
                    The merchant is <strong>NEVER</strong> flagged <span className="font-semibold text-emerald-800">REVIVED</span> until authoritative metrics recheck confirms real transaction volume recovery (≥80% of baseline volume).
                    Click <strong>"Simulate Recovery"</strong> below to test this live.
                  </p>
                </div>
              </div>

              {/* At-Risk Merchants Table Card */}
              <div className="bg-white rounded-card shadow-soft border border-[#E5E7EB] flex flex-col">
                <div className="p-5 border-b border-[#E5E7EB] flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-gray-50/50">
                  <div>
                    <h3 className="font-bold text-base text-[#1A1A1A]">Monitored Kiranas Health & Root-Cause Analysis</h3>
                    <p className="text-xs text-[#6B7280]">
                      Real-time decline metrics, multi-adapter diagnostic handoffs, and honest revival status
                    </p>
                  </div>
                  {/* Filters */}
                  <div className="flex flex-wrap gap-1.5">
                    {[
                      { id: 'ALL', label: 'All At-Risk' },
                      { id: 'WARM_LEADS', label: 'Warm Leads' },
                      { id: 'DEVICE', label: 'Device Issues' },
                      { id: 'SETTLEMENT', label: 'Settlement Issues' },
                      { id: 'COMPETITOR', label: 'Kirana Booster' },
                      { id: 'REVIVED', label: 'Revived' },
                    ].map((f) => (
                      <button
                        key={f.id}
                        onClick={() => setReviveFilter(f.id)}
                        className={`px-2.5 py-1 rounded-full text-[11px] font-semibold transition-all cursor-pointer ${
                          reviveFilter === f.id
                            ? 'bg-[#002E6E] text-white shadow-xs'
                            : 'bg-white border border-[#D1D5DB] text-[#6B7280] hover:border-[#002E6E]'
                        }`}
                      >
                        {f.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Table */}
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-[#E5E7EB] text-[11px] font-bold text-[#6B7280] uppercase tracking-wider bg-gray-50/70">
                        <th className="py-3 px-4">Merchant & City</th>
                        <th className="py-3 px-3">Decline Metric</th>
                        <th className="py-3 px-3">Diagnosed Root Cause</th>
                        <th className="py-3 px-3">Revival Stage</th>
                        <th className="py-3 px-3">Follow-up / Handoff</th>
                        <th className="py-3 px-3 text-right">Invariant Test</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#F3F4F6] text-xs">
                      {filteredReviveMerchants.map((m) => (
                        <tr key={m.id} className="hover:bg-blue-50/40 transition-colors">
                          <td className="py-3 px-4">
                            <p className="font-bold text-[#002E6E]">{m.store_name}</p>
                            <p className="text-[11px] text-[#6B7280]">{m.city} · <span className="font-mono text-[10px]">{m.merchant_id}</span></p>
                          </td>
                          <td className="py-3 px-3">
                            <div className="flex items-center space-x-2">
                              <div>
                                <p className="font-bold text-[#1A1A1A]">{m.recent_daily_volume_inr}<span className="text-[10px] font-normal text-[#6B7280]">/day</span></p>
                                <p className="text-[10px] text-[#6B7280]">Base: {m.baseline_daily_volume_inr}/day</p>
                              </div>
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800">
                                -{m.drop_percentage}%
                              </span>
                            </div>
                          </td>
                          <td className="py-3 px-3">
                            {m.diagnosed_cause === 'DEVICE_ISSUE' && (
                              <span className="inline-block px-2 py-1 rounded bg-amber-50 text-amber-900 border border-amber-200 text-[11px] font-medium">
                                🔌 Offline Soundbox → <strong>Fix Agent Handoff</strong>
                              </span>
                            )}
                            {m.diagnosed_cause === 'SETTLEMENT_ISSUE' && (
                              <span className="inline-block px-2 py-1 rounded bg-rose-50 text-rose-900 border border-rose-200 text-[11px] font-medium">
                                ⚖️ Settlement Shortfall (-₹940) → <strong>Reconcile Handoff</strong>
                              </span>
                            )}
                            {m.diagnosed_cause === 'COMPETITOR_OR_DISENGAGEMENT' && (
                              <span className="inline-block px-2 py-1 rounded bg-indigo-50 text-indigo-900 border border-indigo-200 text-[11px] font-medium">
                                🌟 Disengagement → <strong>Kirana Booster Offer</strong>
                              </span>
                            )}
                            {!m.diagnosed_cause && (
                              <span className="text-[11px] text-gray-500 italic">Pending Diagnosis</span>
                            )}
                          </td>
                          <td className="py-3 px-3">
                            <div className="space-y-1">
                              <StatusChip status={m.chip_status} size="sm" />
                              <p className="text-[10px] text-[#6B7280] font-mono">{m.revival_stage}</p>
                            </div>
                          </td>
                          <td className="py-3 px-3">
                            {m.active_followup ? (
                              <div className="space-y-0.5">
                                <p className="font-semibold text-[#1A1A1A] truncate max-w-xs">{m.active_followup.message_title}</p>
                                <p className="text-[10px] text-[#6B7280]">
                                  Status: <strong className="text-[#002E6E]">{m.active_followup.status}</strong>
                                  {m.active_followup.status === 'ACCEPTED' && ' (Warm Lead Queued)'}
                                </p>
                                {m.active_followup.handed_off_to && (
                                  <p className="text-[10px] text-indigo-700 font-medium">
                                    Assigned: {m.active_followup.handed_off_to}
                                  </p>
                                )}
                              </div>
                            ) : m.recovered_at ? (
                              <div className="text-[11px] text-emerald-700 font-semibold flex items-center gap-1">
                                <CheckCircle className="w-3.5 h-3.5" />
                                <span>Recovered: {m.recovered_at.split('T')[0]}</span>
                              </div>
                            ) : (
                              <span className="text-[11px] text-gray-400">None</span>
                            )}
                          </td>
                          <td className="py-3 px-3 text-right">
                            {m.revival_stage !== 'REVIVED' ? (
                              <button
                                onClick={() => handleSimulateRecovery(m.merchant_id)}
                                disabled={recoveringMerchantId === m.merchant_id}
                                className="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-[11px] font-semibold transition-all shadow-xs disabled:opacity-50 cursor-pointer"
                              >
                                {recoveringMerchantId === m.merchant_id ? 'Checking...' : '⚡ Simulate Recovery'}
                              </button>
                            ) : (
                              <span className="px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800 font-bold text-[11px] inline-flex items-center gap-1">
                                <CheckCircle className="w-3 h-3 text-emerald-600" /> Revived
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Tasks & Audit telemetry below */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 pt-2">
                <div className="lg:col-span-7 bg-white rounded-card shadow-soft border border-[#E5E7EB] flex flex-col">
                  <div className="p-4 border-b border-[#E5E7EB] bg-gray-50/50 flex justify-between items-center">
                    <div>
                      <h4 className="font-bold text-sm text-[#1A1A1A]">Revive Tasks & Field Sales Leads</h4>
                      <p className="text-xs text-[#6B7280]">Warm-lead retention follow-ups for Sales Rep (Amit V.)</p>
                    </div>
                    <span className="text-xs font-bold text-[#002E6E]">{filteredCases.length} Tasks</span>
                  </div>
                  <div className="overflow-x-auto flex-1">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-[#E5E7EB] text-[11px] font-bold text-[#6B7280] uppercase tracking-wider bg-gray-50/70">
                          <th className="py-2.5 px-4">Task</th>
                          <th className="py-2.5 px-3">Merchant</th>
                          <th className="py-2.5 px-3">Status</th>
                          <th className="py-2.5 px-3 text-right">Action</th>
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
                            <td className="py-2.5 px-4">
                              <p className="font-bold text-[#1A1A1A] truncate">{c.title}</p>
                              <p className="text-[10px] text-[#6B7280]">{c.assigned_to}</p>
                            </td>
                            <td className="py-2.5 px-3">
                              <p className="font-semibold text-[#002E6E]">{c.store_name}</p>
                              <p className="text-[10px] text-[#6B7280]">{c.city}</p>
                            </td>
                            <td className="py-2.5 px-3">
                              <StatusChip status={c.bucket} size="sm" />
                            </td>
                            <td className="py-2.5 px-3 text-right">
                              <span className="text-[#00BAF2] font-bold text-xs inline-flex items-center">
                                Inspect <ChevronRight className="w-3 h-3 ml-0.5" />
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="lg:col-span-5 bg-white rounded-card shadow-soft border border-[#E5E7EB] flex flex-col h-[460px]">
                  <div className="p-4 border-b border-[#E5E7EB] flex items-center justify-between bg-gray-50/50">
                    <div className="flex items-center space-x-2">
                      <span className="w-2 h-2 rounded-full bg-[#0B8457] animate-pulse"></span>
                      <div>
                        <h4 className="font-bold text-sm text-[#1A1A1A]">Revive Activity & Audit Stream</h4>
                        <p className="text-[11px] text-[#6B7280]">Live audit_events for Revive Agent</p>
                      </div>
                    </div>
                  </div>
                  <div className="p-4 overflow-y-auto space-y-2 flex-1">
                    {auditEvents
                      .filter((ev) => ev.actor.includes('Revive') || ev.action.includes('REVIVE') || ev.action.includes('RETENTION') || ev.action.includes('SCAN') || ev.target.includes('mer_'))
                      .map((ev) => (
                        <div key={ev.id} className="p-2.5 bg-[#F9FAFB] rounded-lg border border-[#E5E7EB] text-xs space-y-1">
                          <div className="flex justify-between items-center">
                            <span className="font-bold text-[#002E6E] text-[11px]">{ev.action}</span>
                            <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-emerald-100 text-emerald-800">
                              {ev.result}
                            </span>
                          </div>
                          <p className="text-[10px] text-[#4B5563]">Actor: {ev.actor} · Target: {ev.target}</p>
                        </div>
                      ))}
                  </div>
                </div>
              </div>
            </div>
          ) : activeTab === 'onboard' ? (
            /* ONBOARDING PIPELINE & KYC CLOSER WORKSPACE */
            <div className="space-y-6">
              {/* Header Banner */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="p-1.5 rounded-lg bg-blue-50 border border-blue-200 text-[#002E6E]">
                      <UserCheck className="w-5 h-5 text-[#00BAF2]" />
                    </span>
                    <h2 className="text-2xl font-bold text-[#1A1A1A]">Onboarding Pipeline & KYC Closer</h2>
                  </div>
                  <p className="text-sm text-[#6B7280] mt-1">
                    Deterministic mock OCR · Untrusted candidate fields · Simulated NSDL & Penny-Drop authorized verification
                  </p>
                </div>

                <div className="flex items-center space-x-3">
                  <button
                    onClick={() => fetchPipeline()}
                    disabled={pipelineLoading}
                    className="px-3.5 py-2 bg-white border border-[#E5E7EB] hover:border-[#00BAF2] text-xs font-semibold text-[#1A1A1A] rounded-lg shadow-sm flex items-center space-x-1.5 transition-colors disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${pipelineLoading ? 'animate-spin text-[#00BAF2]' : ''}`} />
                    <span>Refresh Pipeline</span>
                  </button>

                  <div className="flex items-center space-x-2 bg-emerald-50 border border-emerald-200 px-3 py-1.5 rounded-lg text-xs font-semibold text-emerald-700">
                    <ShieldCheck className="w-4 h-4" />
                    <span>Simulated NSDL Engine Active</span>
                  </div>
                </div>
              </div>

              {/* Feedback / Scan Notification */}
              {verificationFeedback && (
                <div className="p-4 bg-emerald-50 border border-emerald-300 rounded-xl flex items-center space-x-3 text-emerald-800 text-sm font-medium">
                  <CheckCircle2 className="w-5 h-5 flex-shrink-0 text-emerald-600" />
                  <span>{verificationFeedback}</span>
                </div>
              )}

              {/* 1. Onboarding Pipeline KPI Row */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                <div className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB]">
                  <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">Total Pipeline</p>
                  <p className="text-2xl font-extrabold text-[#002E6E] mt-2">
                    {pipelineData?.total_applications ?? 5}
                  </p>
                  <p className="text-xs text-[#6B7280] mt-1 font-medium">Seeded Applications</p>
                </div>

                <div className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB]">
                  <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">Missing Documents</p>
                  <p className="text-2xl font-extrabold text-[#D97706] mt-2">
                    {(pipelineData?.applications || []).filter((a) => a.missing_documents.length > 0).length}
                  </p>
                  <p className="text-xs text-[#D97706] mt-1 font-medium">Bank proof / photo required</p>
                </div>

                <div className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB]">
                  <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">Blurry / Resubmit</p>
                  <p className="text-2xl font-extrabold text-[#DC2626] mt-2">
                    {pipelineData?.blurry_count ?? 1}
                  </p>
                  <p className="text-xs text-[#DC2626] mt-1 font-medium">Quality filter rejected</p>
                </div>

                <div className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB]">
                  <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">Ready for Verification</p>
                  <p className="text-2xl font-extrabold text-[#00BAF2] mt-2">
                    {(pipelineData?.applications || []).filter((a) => a.can_submit_for_verification).length}
                  </p>
                  <p className="text-xs text-[#00BAF2] mt-1 font-medium">All 3 OCR passed</p>
                </div>

                <div className="bg-white rounded-card p-5 shadow-soft border border-[#E5E7EB]">
                  <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">Active & KYC Verified</p>
                  <p className="text-2xl font-extrabold text-[#059669] mt-2">
                    {pipelineData?.verified_applications ?? 1}
                  </p>
                  <p className="text-xs text-[#059669] mt-1 font-medium">Authorized verification done</p>
                </div>
              </div>

              {/* 2. Pipeline Filter Tabs */}
              <div className="flex items-center space-x-2 border-b border-[#E5E7EB] pb-3">
                {[
                  { id: 'ALL', label: 'All Applications' },
                  { id: 'BLURRY', label: 'Blurry / Resubmit' },
                  { id: 'MISSING', label: 'Missing Documents' },
                  { id: 'READY', label: 'Ready for Verification' },
                  { id: 'VERIFIED', label: 'KYC Verified' },
                ].map((f) => (
                  <button
                    key={f.id}
                    onClick={() => setPipelineFilter(f.id)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      pipelineFilter === f.id
                        ? 'bg-[#002E6E] text-white shadow-sm'
                        : 'bg-white text-[#6B7280] hover:text-[#1A1A1A] border border-[#E5E7EB]'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>

              {/* 3. Applications Table */}
              <div className="bg-white rounded-card shadow-soft border border-[#E5E7EB] overflow-hidden">
                <div className="p-4 border-b border-[#E5E7EB] bg-gray-50/50 flex justify-between items-center">
                  <div>
                    <h3 className="font-bold text-sm text-[#1A1A1A]">Merchant Onboarding Applications</h3>
                    <p className="text-xs text-[#6B7280]">
                      Live state of documents, candidate OCR extraction, and simulated verification gate
                    </p>
                  </div>
                  <span className="text-xs font-bold text-[#002E6E]">
                    {(pipelineData?.applications || []).filter((app) => {
                      if (pipelineFilter === 'BLURRY') return app.blurry_documents.length > 0;
                      if (pipelineFilter === 'MISSING') return app.missing_documents.length > 0;
                      if (pipelineFilter === 'READY') return app.can_submit_for_verification;
                      if (pipelineFilter === 'VERIFIED') return app.is_fully_verified;
                      return true;
                    }).length}{' '}
                    Found
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-[#E5E7EB] text-[11px] font-bold text-[#6B7280] uppercase tracking-wider bg-gray-50/70">
                        <th className="py-3 px-4">Merchant / Store</th>
                        <th className="py-3 px-3">City</th>
                        <th className="py-3 px-3">Current Step</th>
                        <th className="py-3 px-3 text-center">PAN Card</th>
                        <th className="py-3 px-3 text-center">Bank Proof</th>
                        <th className="py-3 px-3 text-center">Shop Photo</th>
                        <th className="py-3 px-4 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#F3F4F6] text-xs">
                      {(pipelineData?.applications || [])
                        .filter((app) => {
                          if (pipelineFilter === 'BLURRY') return app.blurry_documents.length > 0;
                          if (pipelineFilter === 'MISSING') return app.missing_documents.length > 0;
                          if (pipelineFilter === 'READY') return app.can_submit_for_verification;
                          if (pipelineFilter === 'VERIFIED') return app.is_fully_verified;
                          return true;
                        })
                        .map((app) => {
                          const panDoc = app.documents.find((d) => d.document_type === 'PAN_CARD');
                          const bankDoc = app.documents.find((d) => d.document_type === 'BANK_PROOF');
                          const photoDoc = app.documents.find((d) => d.document_type === 'SHOP_PHOTO');

                          return (
                            <tr key={app.merchant_id} className="hover:bg-blue-50/40 transition-colors">
                              <td className="py-3 px-4">
                                <p className="font-bold text-[#002E6E]">{app.store_name}</p>
                                <p className="text-[11px] text-[#6B7280]">
                                  {app.merchant_id} · {app.phone}
                                </p>
                              </td>
                              <td className="py-3 px-3">
                                <span className="font-medium text-[#4B5563]">{app.city}</span>
                              </td>
                              <td className="py-3 px-3">
                                <StatusChip
                                  status={
                                    app.is_fully_verified
                                      ? 'verified'
                                      : app.can_submit_for_verification
                                      ? 'executed'
                                      : app.blurry_documents.length > 0
                                      ? 'needs_human'
                                      : 'awaiting_approval'
                                  }
                                  size="sm"
                                  label={
                                    app.is_fully_verified
                                      ? 'ACTIVE / VERIFIED'
                                      : app.can_submit_for_verification
                                      ? 'READY FOR VERIFICATION'
                                      : app.blurry_documents.length > 0
                                      ? 'RESUBMISSION REQUIRED'
                                      : 'DOCUMENTS REQUIRED'
                                  }
                                />
                              </td>
                              <td className="py-3 px-3 text-center">
                                <StatusChip
                                  status={
                                    panDoc?.authorized_verification_status === 'VERIFIED'
                                      ? 'verified'
                                      : panDoc?.is_ocr_passed
                                      ? 'executed'
                                      : panDoc?.ocr_quality_flag === 'BLURRY'
                                      ? 'needs_human'
                                      : 'awaiting_approval'
                                  }
                                  size="sm"
                                  label={
                                    panDoc?.authorized_verification_status === 'VERIFIED'
                                      ? 'Verified'
                                      : panDoc?.is_ocr_passed
                                      ? 'Passed'
                                      : panDoc?.ocr_quality_flag === 'BLURRY'
                                      ? 'Blurry'
                                      : 'Missing'
                                  }
                                />
                              </td>
                              <td className="py-3 px-3 text-center">
                                <StatusChip
                                  status={
                                    bankDoc?.authorized_verification_status === 'VERIFIED'
                                      ? 'verified'
                                      : bankDoc?.is_ocr_passed
                                      ? 'executed'
                                      : 'awaiting_approval'
                                  }
                                  size="sm"
                                  label={
                                    bankDoc?.authorized_verification_status === 'VERIFIED'
                                      ? 'Verified'
                                      : bankDoc?.is_ocr_passed
                                      ? 'Passed'
                                      : 'Missing'
                                  }
                                />
                              </td>
                              <td className="py-3 px-3 text-center">
                                <StatusChip
                                  status={
                                    photoDoc?.authorized_verification_status === 'VERIFIED'
                                      ? 'verified'
                                      : photoDoc?.is_ocr_passed
                                      ? 'executed'
                                      : 'awaiting_approval'
                                  }
                                  size="sm"
                                  label={
                                    photoDoc?.authorized_verification_status === 'VERIFIED'
                                      ? 'Verified'
                                      : photoDoc?.is_ocr_passed
                                      ? 'Passed'
                                      : 'Missing'
                                  }
                                />
                              </td>
                              <td className="py-3 px-4 text-right space-x-2">
                                <button
                                  onClick={() => setSelectedApplication(app)}
                                  className="px-2.5 py-1 text-xs font-semibold text-[#002E6E] bg-blue-50 hover:bg-blue-100 rounded border border-blue-200 transition-colors"
                                >
                                  Inspect OCR
                                </button>
                                {app.can_submit_for_verification && (
                                  <button
                                    onClick={() => handleEmployeeVerify(app.merchant_id)}
                                    disabled={verifyingMerchantId === app.merchant_id}
                                    className="px-2.5 py-1 text-xs font-semibold text-white bg-[#059669] hover:bg-[#047857] rounded shadow-sm transition-colors disabled:opacity-50"
                                  >
                                    {verifyingMerchantId === app.merchant_id ? 'Verifying...' : '⚡ Verify & Activate'}
                                  </button>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* 4. Inspection Drawer Modal */}
              {selectedApplication && (
                <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
                  <div className="bg-white rounded-card shadow-2xl max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden border border-[#E5E7EB]">
                    <div className="p-4 border-b border-[#E5E7EB] bg-gray-50 flex items-center justify-between">
                      <div>
                        <h4 className="font-bold text-base text-[#002E6E]">
                          {selectedApplication.store_name}
                        </h4>
                        <p className="text-xs text-[#6B7280]">
                          {selectedApplication.merchant_id} · {selectedApplication.city} · {selectedApplication.phone}
                        </p>
                      </div>
                      <button
                        onClick={() => setSelectedApplication(null)}
                        className="p-1.5 hover:bg-gray-200 rounded-full text-gray-500"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>

                    <div className="p-6 overflow-y-auto space-y-4">
                      {/* Invariant Warning Banner */}
                      <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-900 text-xs">
                        <p className="font-bold">⚠️ Core Invariant Notice:</p>
                        <p className="mt-0.5">
                          OCR output represents explicitly UNTRUSTED candidate fields. The application can only transition to ACTIVE / VERIFIED through the simulated external verification engine (NSDL & Penny-Drop).
                        </p>
                      </div>

                      {/* Documents Detail */}
                      <div className="space-y-3">
                        <h5 className="font-bold text-xs uppercase tracking-wider text-[#6B7280]">
                          Document Extraction & Quality Telemetry
                        </h5>
                        {selectedApplication.documents.map((d) => (
                          <div
                            key={d.document_type}
                            className={`p-3.5 rounded-xl border text-xs space-y-2 ${
                              d.status === 'OCR_FAILED' || d.ocr_quality_flag === 'BLURRY'
                                ? 'bg-red-50/50 border-red-200'
                                : d.is_ocr_passed
                                ? 'bg-emerald-50/40 border-emerald-200'
                                : 'bg-gray-50 border-gray-200'
                            }`}
                          >
                            <div className="flex justify-between items-center">
                              <span className="font-bold text-sm text-[#1A1A1A]">
                                {d.document_type.replace('_', ' ').toUpperCase()}
                              </span>
                              <StatusChip
                                status={
                                  d.authorized_verification_status === 'VERIFIED'
                                    ? 'verified'
                                    : d.is_ocr_passed
                                    ? 'executed'
                                    : d.ocr_quality_flag === 'BLURRY'
                                    ? 'needs_human'
                                    : 'awaiting_approval'
                                }
                                size="sm"
                              />
                            </div>

                            {d.rejection_reason && (
                              <p className="font-semibold text-red-700 bg-red-100/70 p-2 rounded">
                                Rejection: {d.rejection_reason}
                              </p>
                            )}

                            {d.ocr_candidate_fields && (
                              <div className="bg-white p-2.5 rounded border border-gray-200 space-y-1">
                                <p className="text-[10px] font-bold text-gray-500 uppercase">
                                  Candidate Fields Extracted (Untrusted):
                                </p>
                                {Object.entries(d.ocr_candidate_fields).map(([k, v]) => (
                                  <p key={k} className="text-xs text-gray-800 font-mono">
                                    <span className="text-gray-500">{k}:</span> {String(v)}
                                  </p>
                                ))}
                              </div>
                            )}

                            <div className="flex justify-between text-[11px] text-gray-500 pt-1">
                              <span>File: {d.file_name || 'Not uploaded'}</span>
                              <span>
                                Authorized Verification: {d.authorized_verification_status}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="p-4 border-t border-[#E5E7EB] bg-gray-50 flex justify-between items-center">
                      <button
                        onClick={() => setSelectedApplication(null)}
                        className="px-4 py-2 border border-gray-300 rounded-lg text-xs font-semibold text-gray-700 hover:bg-gray-100"
                      >
                        Close
                      </button>

                      {selectedApplication.can_submit_for_verification && (
                        <button
                          onClick={() => {
                            handleEmployeeVerify(selectedApplication.merchant_id);
                            setSelectedApplication(null);
                          }}
                          className="px-4 py-2 bg-[#059669] hover:bg-[#047857] text-white text-xs font-bold rounded-lg shadow-sm"
                        >
                          Execute Simulated Authorized Verification
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            /* DEFAULT CONTROL TOWER WORKSPACE */
            <>
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
                              {c.dispute_amount_formatted && (
                                <span className="inline-block mt-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
                                  Shortfall: {c.dispute_amount_formatted}
                                </span>
                              )}
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
            </>
          )}
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

              {/* Settlement Audit & Discrepancy Evidence Card (Reconcile Agent) */}
              {(selectedCase.dispute_amount_formatted || selectedCase.evidence_notes) && (
                <div className="p-4 rounded-card border-2 border-rose-200 bg-rose-50/70 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-rose-900 flex items-center gap-1.5">
                      <Scale className="w-4 h-4 text-rose-600" />
                      Nodal Settlement Discrepancy Evidence
                    </span>
                    {selectedCase.dispute_amount_formatted && (
                      <span className="text-[11px] font-bold text-rose-800 bg-rose-200/80 px-2 py-0.5 rounded font-mono">
                        {selectedCase.dispute_amount_formatted} Shortfall
                      </span>
                    )}
                  </div>
                  {selectedCase.evidence_notes && (
                    <p className="text-xs text-rose-950 font-medium leading-relaxed bg-white/80 p-2.5 rounded-lg border border-rose-200">
                      {selectedCase.evidence_notes}
                    </p>
                  )}
                  {selectedCase.evidence_url && (
                    <div className="flex items-center justify-between text-[11px] text-rose-800 pt-1 border-t border-rose-200">
                      <span>Nodal Record: <strong className="font-mono">{selectedCase.evidence_url.split('/').pop()}</strong></span>
                      <a
                        href={selectedCase.evidence_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[#002E6E] font-bold hover:underline inline-flex items-center gap-1"
                      >
                        Statement Attachment <ExternalLink className="w-3 h-3" />
                      </a>
                    </div>
                  )}
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
