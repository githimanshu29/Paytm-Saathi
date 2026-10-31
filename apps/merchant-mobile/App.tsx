import React, { useState, useEffect, useCallback } from 'react';
import {
  StyleSheet,
  Text,
  View,
  SafeAreaView,
  ScrollView,
  TouchableOpacity,
  TextInput,
  StatusBar,
  ActivityIndicator,
  RefreshControl,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import {
  colors,
  radii,
  spacing,
  StatusChipNative,
  StatusType,
} from '@paytm-saathi/design-tokens';

const API_BASE_URL = 'http://localhost:8000';

type AppTab = 'HOME' | 'CHAT' | 'PASSBOOK' | 'SETTINGS';
type ScreenState = 'PHONE_ENTRY' | 'OTP_ENTRY' | 'APP';

interface MerchantUser {
  id: string;
  store_name: string;
  merchant_name: string;
  phone: string;
  city: string;
  status: string;
  role: string;
}

interface DeviceSummary {
  device_type: string;
  serial_number: string;
  battery_level: number;
  status: string;
  chip_status: StatusType;
  last_heartbeat?: string;
  signal_strength_dbm?: number;
  technician_visit_booked?: boolean;
  technician_slot?: string;
}

interface TransactionItem {
  id: string;
  amount: number;
  amount_formatted: string;
  customer_name?: string;
  status: string;
  payment_rail: string;
  created_at: string;
}

interface PaymentSummary {
  today_total_paise: number;
  today_total_formatted: string;
  today_count: number;
  chip_status: StatusType;
  recent_transactions: TransactionItem[];
}

interface ReceivableItem {
  id: string;
  customer_name: string;
  amount: number;
  amount_formatted: string;
  due_date?: string;
  status: string;
}

interface DuesSummary {
  total_dues_paise: number;
  total_dues_formatted: string;
  pending_count: number;
  chip_status: StatusType;
  receivables: ReceivableItem[];
}

interface MerchantSummary {
  merchant_id: string;
  store_name: string;
  merchant_name: string;
  phone: string;
  city: string;
  status: string;
  kyc_status: string;
  device?: DeviceSummary;
  payments: PaymentSummary;
  dues: DuesSummary;
}

interface ApprovalCardData {
  type: string;
  task_id: string;
  approval_id: string;
  title: string;
  utr?: string;
  customer?: string;
  risk_tier: string;
  reason: string;
  note: string;
  status: string;
}

interface ActionCardData {
  type: string;
  task_id?: string;
  serial_number?: string;
  slot?: string;
  battery_level?: number;
  assigned_to?: string;
  action?: string;
  status: string;
}

interface SettlementBreakdownCardData {
  type: string;
  settlement_date: string;
  gross_sales: string;
  refunds: string;
  fees: string;
  chargebacks: string;
  net_expected: string;
  net_settled: string;
  discrepancy: string;
  is_reconciled: boolean;
  status: string;
  bank_utr?: string;
  dispute_case_id?: string;
  evidence_status?: string;
}

interface ChatMessage {
  id: string;
  sender: 'user' | 'saathi';
  text: string;
  timestamp: string;
  agent?: string; // RESOLVE | FIX | RECONCILE | ORCHESTRATOR
  branch?: string;
  step?: string;
  chip_status?: StatusType;
  explanation_en?: string;
  explanation_hi?: string;
  approval_card?: ApprovalCardData | null;
  action_card?: ActionCardData | null;
  breakdown_card?: SettlementBreakdownCardData | null;
  settlement_date?: string;
  approval_decided?: 'APPROVED' | 'REJECTED';
  evidence_uploaded?: boolean;
  speech_audio_base64?: string;
  speech_duration_seconds?: number;
}

export default function App() {
  const [screen, setScreen] = useState<ScreenState>('PHONE_ENTRY');
  const [activeTab, setActiveTab] = useState<AppTab>('HOME');
  const [token, setToken] = useState<string | null>(null);
  const [merchant, setMerchant] = useState<MerchantUser | null>(null);

  // Home Screen live data state
  const [summary, setSummary] = useState<MerchantSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // Auth Form state
  const [phone, setPhone] = useState('9876543210');
  const [otp, setOtp] = useState('123456');
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authInfo, setAuthInfo] = useState<string | null>(null);

  // Chat & Voice tab state
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      id: 'msg_welcome',
      sender: 'saathi',
      text: 'Namaste! I am Saathi, your Kirana AI teammate. I can resolve payment disputes, verify auto-reversals, or troubleshoot your Soundbox voice announcements. What can I check for you?',
      timestamp: '10:00 AM',
      chip_status: 'verified',
      agent: 'ORCHESTRATOR',
    },
  ]);
  const [chatInput, setChatInput] = useState('');
  const [chatSending, setChatSending] = useState(false);
  const [voiceActive, setVoiceActive] = useState(false);
  const [approvalSubmittingId, setApprovalSubmittingId] = useState<string | null>(null);
  const [demoToggleLoading, setDemoToggleLoading] = useState(false);

  // Load saved token on mount
  useEffect(() => {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        const savedToken = window.localStorage.getItem('saathi_merchant_token');
        const savedUser = window.localStorage.getItem('saathi_merchant_user');
        if (savedToken && savedUser) {
          setToken(savedToken);
          setMerchant(JSON.parse(savedUser));
          setScreen('APP');
        }
      }
    } catch (_e) {}
  }, []);

  // Fetch live summary from Python backend
  const fetchSummary = useCallback(async (authToken?: string) => {
    const activeToken = authToken || token;
    if (!activeToken) return;

    setSummaryLoading(true);
    setSummaryError(null);

    try {
      const res = await fetch(`${API_BASE_URL}/merchant/me/summary`, {
        headers: { Authorization: `Bearer ${activeToken}` },
      });

      if (!res.ok) {
        if (res.status === 401) {
          handleLogout();
          return;
        }
        throw new Error('Could not load summary');
      }

      const data: MerchantSummary = await res.json();
      setSummary(data);
    } catch (_err) {
      setSummaryError('Unable to load your live store summary. Please check your network and tap Retry.');
    } finally {
      setSummaryLoading(false);
      setRefreshing(false);
    }
  }, [token]);

  // Trigger summary fetch when logged in
  useEffect(() => {
    if (token && screen === 'APP') {
      fetchSummary();
    }
  }, [token, screen, fetchSummary]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchSummary();
  };

  // Auth: Request OTP
  const handleRequestOtp = async () => {
    if (!phone.trim() || phone.trim().length < 10) {
      setAuthError('Please enter a valid 10-digit mobile number');
      return;
    }

    setAuthLoading(true);
    setAuthError(null);
    setAuthInfo(null);

    try {
      const res = await fetch(`${API_BASE_URL}/auth/merchant/request-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: phone.trim() }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Could not send OTP');

      setAuthInfo(data.message || 'OTP sent! Use demo code: 123456');
      setScreen('OTP_ENTRY');
    } catch (err: any) {
      setAuthError(err.message || 'Failed to connect to backend server');
    } finally {
      setAuthLoading(false);
    }
  };

  // Auth: Verify OTP
  const handleVerifyOtp = async () => {
    if (!otp.trim()) {
      setAuthError('Please enter the 6-digit OTP');
      return;
    }

    setAuthLoading(true);
    setAuthError(null);

    try {
      const res = await fetch(`${API_BASE_URL}/auth/merchant/verify-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phone: phone.trim(),
          otp: otp.trim(),
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Invalid OTP code');

      setToken(data.access_token);
      setMerchant(data.user);
      try {
        if (typeof window !== 'undefined' && window.localStorage) {
          window.localStorage.setItem('saathi_merchant_token', data.access_token);
          window.localStorage.setItem('saathi_merchant_user', JSON.stringify(data.user));
        }
      } catch (_e) {}

      setScreen('APP');
      setActiveTab('HOME');
      fetchSummary(data.access_token);
    } catch (err: any) {
      setAuthError(err.message || 'OTP verification failed');
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = () => {
    setToken(null);
    setMerchant(null);
    setSummary(null);
    setScreen('PHONE_ENTRY');
    setActiveTab('HOME');
    setAuthError(null);
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.removeItem('saathi_merchant_token');
        window.localStorage.removeItem('saathi_merchant_user');
      }
    } catch (_e) {}
  };

  // Chat: Send message to Python backend (invoking Orchestrator -> Resolve / Fix)
  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || chatInput).trim();
    if (!text || !token) return;

    const userMsg: ChatMessage = {
      id: `usr_${Date.now()}`,
      sender: 'user',
      text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setChatMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setChatInput('');
    setChatSending(true);

    try {
      const res = await fetch(`${API_BASE_URL}/merchant/chat/message`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message: text }),
      });

      if (!res.ok) throw new Error('Chat service unavailable');
      const data = await res.json();

      const saathiMsg: ChatMessage = {
        id: `saathi_${Date.now()}`,
        sender: 'saathi',
        text: data.reply,
        timestamp: data.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        agent: data.agent,
        branch: data.branch,
        step: data.step,
        chip_status: (data.chip_status as StatusType) || 'verified',
        explanation_en: data.explanation_en,
        explanation_hi: data.explanation_hi,
        approval_card: data.approval_card,
        action_card: data.action_card,
        breakdown_card: data.breakdown_card,
        settlement_date: data.settlement_date,
        speech_audio_base64: data.speech_audio_base64,
        speech_duration_seconds: data.speech_duration_seconds,
      };

      setChatMessages((prev) => [...prev, saathiMsg]);
    } catch (_err) {
      const errorMsg: ChatMessage = {
        id: `err_${Date.now()}`,
        sender: 'saathi',
        text: 'Unable to reach Saathi Brain right now. Please check your connection.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        chip_status: 'needs_human',
      };
      setChatMessages((prev) => [...prev, errorMsg]);
    } finally {
      setChatSending(false);
    }
  };

  // Voice Interaction Simulation
  const handleTriggerVoiceSpeech = () => {
    setVoiceActive(true);
    setTimeout(() => {
      setVoiceActive(false);
      handleSendMessage('Soundbox light is red and not speaking payment chime');
    }, 1500);
  };

  // Chat: Handle merchant decision on inline approval card
  const handleDecideApproval = async (messageId: string, approvalId: string, decision: 'APPROVED' | 'REJECTED') => {
    if (!token) return;
    setApprovalSubmittingId(approvalId);
    try {
      const res = await fetch(`${API_BASE_URL}/merchant/approvals/${approvalId}/decide`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ decision }),
      });

      if (res.ok) {
        setChatMessages((prev) =>
          prev.map((m) => {
            if (m.id === messageId) {
              return {
                ...m,
                approval_decided: decision,
                chip_status: (decision === 'APPROVED' ? 'executed' : 'needs_human') as StatusType,
              };
            }
            return m;
          })
        );
      }
    } catch (_e) {
    } finally {
      setApprovalSubmittingId(null);
    }
  };

  // Demo Toggle: Flips Soundbox status on demand
  const handleDemoToggle = async () => {
    if (!token) return;
    setDemoToggleLoading(true);
    try {
      const serial = summary?.device?.serial_number || 'SB-JAI-101';
      const res = await fetch(`${API_BASE_URL}/demo/device/${serial}/toggle`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        await fetchSummary();
        handleSendMessage(`Soundbox status toggled to ${data.new_status}. Please recheck.`);
      }
    } catch (_e) {
    } finally {
      setDemoToggleLoading(false);
    }
  };

  // 1. SCREEN: Phone Entry
  if (screen === 'PHONE_ENTRY') {
    return (
      <SafeAreaView style={styles.authSafeArea}>
        <StatusBar barStyle="light-content" backgroundColor={colors.paytmBlue} />
        
        <View style={styles.authHero}>
          <View style={styles.authLogoBadge}>
            <Text style={styles.authLogoText}>P</Text>
          </View>
          <Text style={styles.authHeroTitle}>Paytm Saathi</Text>
          <Text style={styles.authHeroSubtitle}>Your Kirana AI Teammate</Text>
        </View>

        <View style={styles.authCard}>
          <Text style={styles.authCardTitle}>Enter Mobile Number</Text>
          <Text style={styles.authCardSubtitle}>
            We will verify your Kirana account via a one-time passcode.
          </Text>

          {authError && (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{authError}</Text>
            </View>
          )}

          <View style={styles.phoneInputContainer}>
            <Text style={styles.phonePrefix}>+91</Text>
            <TextInput
              style={styles.phoneInput}
              keyboardType="phone-pad"
              maxLength={10}
              value={phone}
              onChangeText={setPhone}
              placeholder="9876543210"
              placeholderTextColor="#9CA3AF"
            />
          </View>

          <TouchableOpacity
            style={[styles.primaryButton, authLoading && styles.buttonDisabled]}
            disabled={authLoading}
            onPress={handleRequestOtp}
            activeOpacity={0.85}
          >
            {authLoading ? (
              <ActivityIndicator color="#FFFFFF" size="small" />
            ) : (
              <Text style={styles.primaryButtonText}>Get OTP</Text>
            )}
          </TouchableOpacity>

          <View style={styles.demoHintBox}>
            <Text style={styles.demoHintTitle}>DEMO ACCOUNT</Text>
            <Text style={styles.demoHintDesc}>
              Seeded Merchant: Sharma Kirana Store (+91 9876543210) · Demo OTP: 123456
            </Text>
          </View>
        </View>
      </SafeAreaView>
    );
  }

  // 2. SCREEN: OTP Entry
  if (screen === 'OTP_ENTRY') {
    return (
      <SafeAreaView style={styles.authSafeArea}>
        <StatusBar barStyle="light-content" backgroundColor={colors.paytmBlue} />

        <View style={styles.authHero}>
          <View style={styles.authLogoBadge}>
            <Text style={styles.authLogoText}>P</Text>
          </View>
          <Text style={styles.authHeroTitle}>Verify OTP</Text>
          <Text style={styles.authHeroSubtitle}>Sent to +91 {phone}</Text>
        </View>

        <View style={styles.authCard}>
          <Text style={styles.authCardTitle}>Enter 6-Digit Code</Text>
          <Text style={styles.authCardSubtitle}>
            {authInfo || 'Enter demo code 123456 to log in.'}
          </Text>

          {authError && (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{authError}</Text>
            </View>
          )}

          <TextInput
            style={styles.otpInput}
            keyboardType="number-pad"
            maxLength={6}
            value={otp}
            onChangeText={setOtp}
            placeholder="123456"
            placeholderTextColor="#9CA3AF"
          />

          <TouchableOpacity
            style={[styles.primaryButton, authLoading && styles.buttonDisabled]}
            disabled={authLoading}
            onPress={handleVerifyOtp}
            activeOpacity={0.85}
          >
            {authLoading ? (
              <ActivityIndicator color="#FFFFFF" size="small" />
            ) : (
              <Text style={styles.primaryButtonText}>Verify & Proceed</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.secondaryButton}
            onPress={() => setScreen('PHONE_ENTRY')}
          >
            <Text style={styles.secondaryButtonText}>← Change Mobile Number</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // 3. SCREEN: Authenticated Application Shell
  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="light-content" backgroundColor={colors.paytmBlue} />

      {/* Top Header */}
      <View style={styles.header}>
        <View style={styles.headerTop}>
          <View style={{ flex: 1 }}>
            <Text style={styles.headerSubtitle}>
              {(summary?.city || merchant?.city || 'JAIPUR').toUpperCase()} · DEMO
            </Text>
            <Text style={styles.headerTitle} numberOfLines={1}>
              {summary?.store_name || merchant?.store_name || 'Sharma Kirana Store'}
            </Text>
          </View>
          <TouchableOpacity
            style={styles.logoutButton}
            onPress={handleLogout}
            activeOpacity={0.7}
          >
            <Text style={styles.logoutText}>Sign Out</Text>
          </TouchableOpacity>
        </View>

        {/* Quick Collections & Device pill */}
        <View style={styles.summaryBar}>
          <View>
            <Text style={styles.summaryLabel}>TODAY'S COLLECTION</Text>
            <Text style={styles.summaryValue}>
              {summary?.payments.today_total_formatted || '₹920.00'}
            </Text>
          </View>
          <View style={styles.summaryDivider} />
          <View>
            <Text style={styles.summaryLabel}>SOUNDBOX STATUS</Text>
            <Text style={styles.summaryValue}>
              {summary?.device ? `${summary.device.status} · ${summary.device.battery_level}%` : 'ONLINE · 88%'}
            </Text>
          </View>
        </View>
      </View>

      {/* TAB 1: HOME TAB */}
      {activeTab === 'HOME' && (
        <View style={styles.tabContentContainer}>
          <ScrollView
            style={styles.container}
            contentContainerStyle={styles.scrollContent}
            showsVerticalScrollIndicator={false}
            refreshControl={
              <RefreshControl
                refreshing={refreshing}
                onRefresh={onRefresh}
                colors={[colors.paytmBlue]}
                tintColor={colors.paytmBlue}
              />
            }
          >
            {/* Friendly Error State */}
            {summaryError && (
              <View style={styles.friendlyErrorCard}>
                <Text style={styles.friendlyErrorTitle}>Connection Notice</Text>
                <Text style={styles.friendlyErrorText}>{summaryError}</Text>
                <TouchableOpacity
                  style={styles.retryButton}
                  onPress={() => fetchSummary()}
                >
                  <Text style={styles.retryButtonText}>Retry Fetch</Text>
                </TouchableOpacity>
              </View>
            )}

            {/* Skeleton / Loading Indicator */}
            {summaryLoading && !refreshing && (
              <View style={styles.loadingCard}>
                <ActivityIndicator size="small" color={colors.paytmBlue} />
                <Text style={styles.loadingText}>Fetching live store telemetry...</Text>
              </View>
            )}

            {/* CARD 1: Device Telemetry Status */}
            <View style={styles.card}>
              <View style={styles.cardHeaderRow}>
                <View>
                  <Text style={styles.cardTitle}>Device Status</Text>
                  <Text style={styles.cardSubtitle}>
                    {summary?.device?.device_type || 'Soundbox 4G Pro'} · S/N: {summary?.device?.serial_number || 'SB-JAI-101'}
                  </Text>
                </View>
                <StatusChipNative
                  status={summary?.device?.chip_status || 'verified'}
                  label={summary?.device?.status || 'ONLINE'}
                />
              </View>

              <View style={styles.deviceMetricsRow}>
                <View style={styles.metricItem}>
                  <Text style={styles.metricLabel}>Battery</Text>
                  <Text style={styles.metricValue}>
                    {summary?.device?.battery_level ? `${summary.device.battery_level}%` : '88%'}
                  </Text>
                </View>
                <View style={styles.metricItem}>
                  <Text style={styles.metricLabel}>Last Heartbeat</Text>
                  <Text style={styles.metricValue}>
                    {summary?.device?.last_heartbeat || '2m ago'}
                  </Text>
                </View>
                <View style={styles.metricItem}>
                  <Text style={styles.metricLabel}>4G Signal</Text>
                  <Text style={styles.metricValue}>
                    {summary?.device?.signal_strength_dbm ? `${summary.device.signal_strength_dbm} dBm` : '-65 dBm'}
                  </Text>
                </View>
              </View>

              {/* Demo Toggle Button */}
              <TouchableOpacity
                style={styles.demoToggleBtn}
                onPress={handleDemoToggle}
                disabled={demoToggleLoading}
              >
                {demoToggleLoading ? (
                  <ActivityIndicator size="small" color={colors.paytmBlue} />
                ) : (
                  <Text style={styles.demoToggleBtnText}>
                    🔄 Toggle Soundbox State (Demo: {summary?.device?.status === 'ONLINE' ? 'Force Offline' : 'Set Online'})
                  </Text>
                )}
              </TouchableOpacity>
            </View>

            {/* CARD 2: Payments & Recent Collections */}
            <View style={styles.card}>
              <View style={styles.cardHeaderRow}>
                <View>
                  <Text style={styles.cardTitle}>Today's Payments</Text>
                  <Text style={styles.cardSubtitle}>
                    {summary?.payments.today_count || 3} successful UPI transactions
                  </Text>
                </View>
                <StatusChipNative
                  status={summary?.payments.chip_status || 'verified'}
                  label="Reconciled"
                />
              </View>

              <Text style={styles.collectionsBigAmount}>
                {summary?.payments.today_total_formatted || '₹920.00'}
              </Text>

              {/* Transactions List */}
              <View style={styles.txListContainer}>
                {(summary?.payments.recent_transactions || []).map((tx) => (
                  <View key={tx.id} style={styles.txRow}>
                    <View style={styles.txIconCircle}>
                      <Text style={styles.txIconText}>₹</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.txCustomerName}>{tx.customer_name}</Text>
                      <Text style={styles.txMetaText}>
                        {tx.payment_rail} · {tx.created_at}
                      </Text>
                    </View>
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={styles.txAmountText}>{tx.amount_formatted}</Text>
                      <StatusChipNative status="verified" size="sm" label="Success" />
                    </View>
                  </View>
                ))}
              </View>
            </View>

            {/* CARD 3: Customer Udhaar & Dues */}
            <View style={styles.card}>
              <View style={styles.cardHeaderRow}>
                <View>
                  <Text style={styles.cardTitle}>Customer Udhaar (Dues)</Text>
                  <Text style={styles.cardSubtitle}>
                    {summary?.dues.pending_count || 1} pending customer receivable
                  </Text>
                </View>
                <StatusChipNative
                  status={summary?.dues.chip_status || 'awaiting_approval'}
                  label="Pending Reminder"
                />
              </View>

              <Text style={[styles.collectionsBigAmount, { color: colors.warning }]}>
                {summary?.dues.total_dues_formatted || '₹850.00'}
              </Text>

              {/* Dues List */}
              <View style={styles.txListContainer}>
                {(summary?.dues.receivables || []).map((rec) => (
                  <View key={rec.id} style={styles.txRow}>
                    <View style={[styles.txIconCircle, { backgroundColor: '#FEF5EC' }]}>
                      <Text style={[styles.txIconText, { color: colors.warning }]}>📒</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.txCustomerName}>{rec.customer_name}</Text>
                      <Text style={styles.txMetaText}>
                        Due: {rec.due_date} · Consensual Udhaar
                      </Text>
                    </View>
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={[styles.txAmountText, { color: colors.warning }]}>
                        {rec.amount_formatted}
                      </Text>
                      <StatusChipNative status="awaiting_approval" size="sm" label="Pending" />
                    </View>
                  </View>
                ))}
              </View>
            </View>

            {/* Pull-to-refresh tip */}
            <Text style={styles.pullHintText}>Pull down to refresh live telemetry from backend</Text>
          </ScrollView>

          {/* Floating Mic FAB -> Opens Chat Tab in Voice Mode */}
          <TouchableOpacity
            style={styles.micFab}
            activeOpacity={0.88}
            onPress={() => {
              setActiveTab('CHAT');
              handleTriggerVoiceSpeech();
            }}
          >
            <Text style={styles.micIcon}>🎙</Text>
            <Text style={styles.micText}>Talk to Saathi (Voice)</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* TAB 2: SAATHI CHAT TAB (Resolve + Fix Specialist Agents Enabled) */}
      {activeTab === 'CHAT' && (
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.chatContainer}
        >
          {/* Chat Sub-header */}
          <View style={styles.chatSubHeader}>
            <TouchableOpacity
              onPress={() => setActiveTab('HOME')}
              style={styles.chatBackButton}
            >
              <Text style={styles.chatBackText}>← Home</Text>
            </TouchableOpacity>
            <View style={{ alignItems: 'center' }}>
              <Text style={styles.chatHeaderTitle}>Saathi Multi-Agent</Text>
              <Text style={styles.chatHeaderSubtitle}>Resolve · Fix · Reconcile Copilot</Text>
            </View>
            <StatusChipNative status="verified" size="sm" label="Active" />
          </View>

          {/* Voice Indicator Banner when Active */}
          {voiceActive && (
            <View style={styles.voiceListeningBanner}>
              <Text style={styles.voiceListeningText}>🎙 Listening via SpeechAdapter (Indic Voice)...</Text>
            </View>
          )}

          {/* Scenario Quick-Test Chips */}
          <View style={styles.quickChipsBar}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.quickChipsScroll}>
              <TouchableOpacity
                style={styles.quickChip}
                onPress={() => handleSendMessage("Check yesterday's settlement breakdown")}
              >
                <Text style={styles.quickChipText}>📊 Yesterday's Settlement (Reconciled)</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.quickChip}
                onPress={() => handleSendMessage('Check 27 Oct settlement discrepancy shortfall')}
              >
                <Text style={styles.quickChipText}>⚠️ 27 Oct Settlement (Discrepancy Shortfall)</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.quickChip}
                onPress={() => handleSendMessage('Soundbox light is red and not announcing payments')}
              >
                <Text style={styles.quickChipText}>🔊 Soundbox Red / Silent (Fix Agent)</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.quickChip}
                onPress={() => handleSendMessage('Restart Soundbox SB-JAI-101 remotely')}
              >
                <Text style={styles.quickChipText}>⚡ Remote Restart & Recheck (Fix)</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.quickChip}
                onPress={() => handleSendMessage('Soundbox still red after restart, book technician')}
              >
                <Text style={styles.quickChipText}>🛠 Book Technician Visit (Fix)</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.quickChip}
                onPress={() => handleSendMessage('Check customer Alok ₹250 auto-reversal')}
              >
                <Text style={styles.quickChipText}>💸 ₹250 Auto-Reversal (Resolve)</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.quickChip}
                onPress={() => handleSendMessage('Deepak Verma ₹500 stuck reversal need refund review')}
              >
                <Text style={styles.quickChipText}>⏱ ₹500 Stuck Refund (Resolve)</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>

          {/* Chat Messages Stream */}
          <ScrollView
            style={styles.chatMessageStream}
            contentContainerStyle={styles.chatStreamContent}
            showsVerticalScrollIndicator={false}
          >
            {chatMessages.map((msg) => {
              const isSaathi = msg.sender === 'saathi';
              return (
                <View
                  key={msg.id}
                  style={[
                    styles.chatMessageRow,
                    isSaathi ? styles.chatRowLeft : styles.chatRowRight,
                  ]}
                >
                  <View
                    style={[
                      styles.chatBubble,
                      isSaathi ? styles.bubbleSaathi : styles.bubbleUser,
                    ]}
                  >
                    {/* Saathi Status Badge Header */}
                    {isSaathi && msg.chip_status && (
                      <View style={styles.chatBubbleHeader}>
                        <StatusChipNative
                          status={msg.chip_status}
                          size="sm"
                          label={
                            msg.agent === 'FIX'
                              ? msg.step === 'TECHNICIAN_DISPATCHED'
                                ? 'Technician Booked'
                                : msg.step === 'LOW_BATTERY_CHARGING'
                                ? 'Low Battery'
                                : 'Fix Agent'
                              : msg.branch === 'A_AUTO_REVERSAL'
                              ? 'Auto-Reversing'
                              : msg.branch === 'B_STUCK_REFUND_REVIEW'
                              ? 'Refund Review'
                              : msg.branch === 'C_PAYMENT_CONFIRMED'
                              ? 'Settled'
                              : msg.branch === 'D_FRAUD_ESCALATED'
                              ? 'Security Escalation'
                              : 'Verified'
                          }
                        />
                      </View>
                    )}

                    <Text
                      style={[
                        styles.chatBubbleText,
                        isSaathi ? styles.textSaathi : styles.textUser,
                      ]}
                    >
                      {msg.text}
                    </Text>

                    {/* Voice Audio Synthesized Pill */}
                    {isSaathi && msg.speech_audio_base64 && (
                      <View style={styles.voicePill}>
                        <Text style={styles.voicePillText}>
                          🔊 Indic Speech Synthesized ({msg.speech_duration_seconds || 3.2}s)
                        </Text>
                      </View>
                    )}

                    {/* Bilingual Hindi Explanation Card */}
                    {isSaathi && msg.explanation_hi && (
                      <View style={styles.hindiExplanationCard}>
                        <Text style={styles.hindiLabel}>🇮🇳 ग्राहक के लिए संदेश (HINDI)</Text>
                        <Text style={styles.hindiText}>{msg.explanation_hi}</Text>
                      </View>
                    )}

                    {/* Action Card: Technician Visit Booked (Fix Agent) */}
                    {isSaathi && msg.action_card?.type === 'TECHNICIAN_VISIT_BOOKED' && (
                      <View style={styles.techCardContainer}>
                        <View style={styles.techCardHeader}>
                          <Text style={styles.techCardTitle}>🛠 Technician Visit Scheduled</Text>
                          <StatusChipNative status="needs_human" size="sm" label="Visit Confirmed" />
                        </View>
                        <Text style={styles.techCardSlotText}>
                          Slot: <strong>{msg.action_card.slot}</strong>
                        </Text>
                        <Text style={styles.techCardMetaText}>
                          Soundbox: {msg.action_card.serial_number} · Case #{msg.action_card.task_id}
                        </Text>
                        <View style={styles.techCardNoticeBox}>
                          <Text style={styles.techCardNoticeText}>
                            Paytm Field Engineer will arrive on-site with replacement SIM & diagnostic tools. Zero service charge.
                          </Text>
                        </View>
                      </View>
                    )}

                    {/* Action Card: Low Battery Alert */}
                    {isSaathi && msg.action_card?.type === 'DEVICE_BATTERY_ALERT' && (
                      <View style={[styles.techCardContainer, { borderColor: '#F59E0B', backgroundColor: '#FFFBEB' }]}>
                        <Text style={[styles.techCardTitle, { color: '#B45309' }]}>⚡ Critical Battery Warning</Text>
                        <Text style={[styles.techCardSlotText, { color: '#92400E' }]}>
                          Battery: {msg.action_card.battery_level}% · Connect Charger Immediately
                        </Text>
                      </View>
                    )}

                    {/* Structured Settlement Breakdown Card (Reconcile Agent) */}
                    {isSaathi && (msg.breakdown_card || (msg.action_card && msg.action_card.type === 'SETTLEMENT_BREAKDOWN')) && (() => {
                      const card = msg.breakdown_card || (msg.action_card as any);
                      return (
                        <View style={styles.settlementCardContainer}>
                          <View style={styles.settlementCardHeader}>
                            <View>
                              <Text style={styles.settlementCardTitle}>📊 Settlement Breakdown</Text>
                              <Text style={styles.settlementCardDate}>{card.settlement_date}</Text>
                            </View>
                            <StatusChipNative
                              status={card.is_reconciled ? 'verified' : 'needs_human'}
                              size="sm"
                              label={card.is_reconciled ? 'Reconciled' : 'Shortfall Detected'}
                            />
                          </View>

                          <View style={styles.settlementTable}>
                            <View style={styles.settlementRow}>
                              <Text style={styles.settlementRowLabel}>Gross Sales</Text>
                              <Text style={[styles.settlementRowVal, { color: '#065F46' }]}>+{card.gross_sales}</Text>
                            </View>
                            <View style={styles.settlementRow}>
                              <Text style={styles.settlementRowLabel}>Customer Refunds</Text>
                              <Text style={[styles.settlementRowVal, { color: '#B91C1C' }]}>-{card.refunds}</Text>
                            </View>
                            <View style={styles.settlementRow}>
                              <Text style={styles.settlementRowLabel}>MDR & Soundbox Fees</Text>
                              <Text style={[styles.settlementRowVal, { color: '#B91C1C' }]}>-{card.fees}</Text>
                            </View>
                            <View style={styles.settlementRow}>
                              <Text style={styles.settlementRowLabel}>Chargebacks Deducted</Text>
                              <Text style={[styles.settlementRowVal, { color: '#B91C1C' }]}>-{card.chargebacks}</Text>
                            </View>
                            <View style={styles.settlementDivider} />
                            <View style={styles.settlementRow}>
                              <Text style={styles.settlementRowBoldLabel}>Calculated Net Due</Text>
                              <Text style={styles.settlementRowBoldVal}>{card.net_expected}</Text>
                            </View>
                            <View style={styles.settlementRow}>
                              <Text style={styles.settlementRowBoldLabel}>Actual Bank Deposit</Text>
                              <Text style={[styles.settlementRowBoldVal, { color: colors.paytmBlue }]}>{card.net_settled}</Text>
                            </View>
                            <View style={styles.settlementDivider} />
                            <View style={[styles.settlementRow, card.is_reconciled ? styles.settlementReconciledBg : styles.settlementDiscrepancyBg]}>
                              <Text style={[styles.settlementDiscrepancyLabel, { color: card.is_reconciled ? '#065F46' : '#991B1B' }]}>
                                {card.is_reconciled ? 'Discrepancy' : 'Unexplained Shortfall'}
                              </Text>
                              <Text style={[styles.settlementDiscrepancyVal, { color: card.is_reconciled ? '#065F46' : '#DC2626' }]}>
                                {card.discrepancy}
                              </Text>
                            </View>
                          </View>

                          {card.bank_utr && (
                            <Text style={styles.settlementUtrText}>
                              Bank UTR: <Text style={{ fontWeight: '700' }}>{card.bank_utr}</Text>
                            </Text>
                          )}

                          {/* Anomaly Dispute Case Banner & Evidence Action */}
                          {!card.is_reconciled && (
                            <View style={styles.settlementDisputeNoticeBox}>
                              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                                <Text style={styles.settlementDisputeTitle}>⚠️ Case #{card.dispute_case_id} Queued</Text>
                                <StatusChipNative status="needs_human" size="sm" label="Nodal Ops" />
                              </View>
                              <Text style={styles.settlementDisputeDesc}>
                                Our Nodal Settlement Desk is investigating the {card.discrepancy} gap against nodal ledger.
                              </Text>
                              {!msg.evidence_uploaded ? (
                                <TouchableOpacity
                                  style={styles.evidenceUploadBtn}
                                  onPress={() => {
                                    setChatMessages((prev) =>
                                      prev.map((m) => (m.id === msg.id ? { ...m, evidence_uploaded: true } : m))
                                    );
                                  }}
                                >
                                  <Text style={styles.evidenceUploadBtnText}>📷 Attach Passbook / Statement Proof</Text>
                                </TouchableOpacity>
                              ) : (
                                <View style={styles.evidenceSuccessBox}>
                                  <Text style={styles.evidenceSuccessText}>
                                    ✓ Passbook photo proof attached to Case #{card.dispute_case_id}. Review priority boosted.
                                  </Text>
                                </View>
                              )}
                            </View>
                          )}
                        </View>
                      );
                    })()}

                    {/* Inline Human Approval Card (Branch B Refund Review) */}
                    {isSaathi && msg.approval_card && (
                      <View style={styles.approvalCardContainer}>
                        <View style={styles.approvalCardHeader}>
                          <Text style={styles.approvalCardTitle}>{msg.approval_card.title}</Text>
                          <StatusChipNative
                            status={
                              msg.approval_decided === 'APPROVED'
                                ? 'executed'
                                : msg.approval_decided === 'REJECTED'
                                ? 'needs_human'
                                : 'awaiting_approval'
                            }
                            size="sm"
                            label={
                              msg.approval_decided === 'APPROVED'
                                ? 'Review Submitted'
                                : msg.approval_decided === 'REJECTED'
                                ? 'Dismissed'
                                : 'Authorization Required'
                            }
                          />
                        </View>

                        <Text style={styles.approvalReasonText}>
                          Reason: {msg.approval_card.reason}
                        </Text>
                        <Text style={styles.approvalMetaText}>
                          Customer: {msg.approval_card.customer} · UTR: {msg.approval_card.utr}
                        </Text>

                        {/* Safety Disclaimer Banner */}
                        <View style={styles.approvalNoteBox}>
                          <Text style={styles.approvalNoteText}>
                            🛡 {msg.approval_card.note}
                          </Text>
                        </View>

                        {/* Decision Buttons */}
                        {!msg.approval_decided ? (
                          <View style={styles.approvalActionRow}>
                            <TouchableOpacity
                              style={[
                                styles.approvalApproveBtn,
                                approvalSubmittingId === msg.approval_card.approval_id && styles.buttonDisabled,
                              ]}
                              disabled={approvalSubmittingId === msg.approval_card.approval_id}
                              onPress={() =>
                                handleDecideApproval(msg.id, msg.approval_card!.approval_id, 'APPROVED')
                              }
                            >
                              {approvalSubmittingId === msg.approval_card.approval_id ? (
                                <ActivityIndicator size="small" color="#FFFFFF" />
                              ) : (
                                <Text style={styles.approvalApproveBtnText}>
                                  ✓ Authorize Review Request
                                </Text>
                              )}
                            </TouchableOpacity>

                            <TouchableOpacity
                              style={styles.approvalRejectBtn}
                              disabled={approvalSubmittingId === msg.approval_card.approval_id}
                              onPress={() =>
                                handleDecideApproval(msg.id, msg.approval_card!.approval_id, 'REJECTED')
                              }
                            >
                              <Text style={styles.approvalRejectBtnText}>Dismiss</Text>
                            </TouchableOpacity>
                          </View>
                        ) : (
                          <View style={styles.approvalDecidedBanner}>
                            <Text style={styles.approvalDecidedText}>
                              {msg.approval_decided === 'APPROVED'
                                ? '✓ Review request authorized by merchant. Operations team notified.'
                                : '✗ Dismissed by merchant.'}
                            </Text>
                          </View>
                        )}
                      </View>
                    )}

                    <Text
                      style={[
                        styles.chatTimestamp,
                        isSaathi ? styles.timeSaathi : styles.timeUser,
                      ]}
                    >
                      {msg.timestamp}
                    </Text>
                  </View>
                </View>
              );
            })}

            {chatSending && (
              <View style={[styles.chatMessageRow, styles.chatRowLeft]}>
                <View style={[styles.chatBubble, styles.bubbleSaathi]}>
                  <ActivityIndicator size="small" color={colors.paytmBlue} />
                  <Text style={[styles.chatBubbleText, styles.textSaathi, { marginTop: 4 }]}>
                    Saathi is diagnosing...
                  </Text>
                </View>
              </View>
            )}
          </ScrollView>

          {/* Chat Input Bar with Voice Mic Button */}
          <View style={styles.chatInputBar}>
            <TouchableOpacity
              style={styles.voiceMicBtn}
              onPress={handleTriggerVoiceSpeech}
            >
              <Text style={{ fontSize: 18 }}>🎙</Text>
            </TouchableOpacity>

            <TextInput
              style={styles.chatTextInput}
              value={chatInput}
              onChangeText={setChatInput}
              placeholder="Ask Saathi (Voice or text)..."
              placeholderTextColor="#9CA3AF"
              onSubmitEditing={() => handleSendMessage()}
              returnKeyType="send"
            />
            <TouchableOpacity
              style={[
                styles.chatSendButton,
                (!chatInput.trim() || chatSending) && styles.sendDisabled,
              ]}
              disabled={!chatInput.trim() || chatSending}
              onPress={() => handleSendMessage()}
              activeOpacity={0.8}
            >
              <Text style={styles.chatSendText}>Send</Text>
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      )}

      {/* TAB 3: PASSBOOK & TAB 4: SETTINGS (Placeholders) */}
      {(activeTab === 'PASSBOOK' || activeTab === 'SETTINGS') && (
        <View style={styles.placeholderTabContent}>
          <Text style={styles.cardTitle}>{activeTab} Module</Text>
          <Text style={styles.cardSubtitle}>Scheduled for subsequent build phase.</Text>
          <TouchableOpacity
            style={styles.actionPill}
            onPress={() => setActiveTab('HOME')}
          >
            <Text style={styles.actionPillText}>Return to Home</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Bottom Tab Bar */}
      <View style={styles.bottomTabBar}>
        <TouchableOpacity
          style={styles.tabItem}
          onPress={() => setActiveTab('HOME')}
        >
          <Text style={activeTab === 'HOME' ? styles.tabIconActive : styles.tabIcon}>
            🏠
          </Text>
          <Text style={activeTab === 'HOME' ? styles.tabLabelActive : styles.tabLabel}>
            Home
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.tabItem}
          onPress={() => setActiveTab('CHAT')}
        >
          <Text style={activeTab === 'CHAT' ? styles.tabIconActive : styles.tabIcon}>
            💬
          </Text>
          <Text style={activeTab === 'CHAT' ? styles.tabLabelActive : styles.tabLabel}>
            Saathi Chat
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.tabItem}
          onPress={() => setActiveTab('PASSBOOK')}
        >
          <Text style={activeTab === 'PASSBOOK' ? styles.tabIconActive : styles.tabIcon}>
            📜
          </Text>
          <Text style={activeTab === 'PASSBOOK' ? styles.tabLabelActive : styles.tabLabel}>
            Passbook
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.tabItem}
          onPress={() => setActiveTab('SETTINGS')}
        >
          <Text style={activeTab === 'SETTINGS' ? styles.tabIconActive : styles.tabIcon}>
            ⚙️
          </Text>
          <Text style={activeTab === 'SETTINGS' ? styles.tabLabelActive : styles.tabLabel}>
            Settings
          </Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.paytmBlue,
  },
  header: {
    backgroundColor: colors.paytmBlue,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.lg,
  },
  headerTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  headerSubtitle: {
    color: 'rgba(255, 255, 255, 0.85)',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.8,
  },
  headerTitle: {
    color: '#FFFFFF',
    fontSize: 20,
    fontWeight: '800',
    marginTop: 2,
  },
  logoutButton: {
    backgroundColor: 'rgba(235, 87, 87, 0.25)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.4)',
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: radii.pill,
  },
  logoutText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '700',
  },
  summaryBar: {
    flexDirection: 'row',
    backgroundColor: '#FFFFFF',
    borderRadius: radii.card,
    marginTop: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    justifyContent: 'space-around',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 3,
  },
  summaryLabel: {
    fontSize: 10,
    color: colors.textSecondary,
    fontWeight: '600',
    letterSpacing: 0.5,
  },
  summaryValue: {
    fontSize: 15,
    color: colors.textPrimary,
    fontWeight: '700',
    marginTop: 2,
  },
  summaryDivider: {
    width: 1,
    height: 24,
    backgroundColor: colors.borderLight,
  },
  tabContentContainer: {
    flex: 1,
    position: 'relative',
    backgroundColor: colors.background,
  },
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollContent: {
    padding: spacing.lg,
    paddingBottom: 110,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.card,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.borderLight,
    marginBottom: spacing.md,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 2,
  },
  cardHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: spacing.sm,
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  cardSubtitle: {
    fontSize: 12,
    color: colors.textSecondary,
    marginTop: 2,
  },
  deviceMetricsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: '#F9FAFB',
    borderRadius: radii.sm,
    padding: 10,
    marginTop: spacing.sm,
  },
  metricItem: {
    alignItems: 'center',
  },
  metricLabel: {
    fontSize: 10,
    color: colors.textSecondary,
    fontWeight: '500',
  },
  metricValue: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.textPrimary,
    marginTop: 2,
  },
  demoToggleBtn: {
    marginTop: spacing.sm,
    backgroundColor: '#EFF6FF',
    borderWidth: 1,
    borderColor: '#BFDBFE',
    borderRadius: radii.sm,
    paddingVertical: 7,
    alignItems: 'center',
    justifyContent: 'center',
  },
  demoToggleBtnText: {
    fontSize: 11,
    color: colors.paytmBlue,
    fontWeight: '700',
  },
  collectionsBigAmount: {
    fontSize: 26,
    fontWeight: '800',
    color: colors.paytmBlue,
    marginVertical: spacing.sm,
  },
  txListContainer: {
    marginTop: spacing.xs,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
    paddingTop: spacing.sm,
  },
  txRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 0.5,
    borderBottomColor: '#F3F4F6',
  },
  txIconCircle: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#E6F8FE',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
  },
  txIconText: {
    color: colors.paytmBlue,
    fontSize: 15,
    fontWeight: '800',
  },
  txCustomerName: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  txMetaText: {
    fontSize: 11,
    color: colors.textSecondary,
    marginTop: 1,
  },
  txAmountText: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.textPrimary,
    marginBottom: 2,
  },
  pullHintText: {
    fontSize: 11,
    color: '#9CA3AF',
    textAlign: 'center',
    marginTop: spacing.sm,
  },
  friendlyErrorCard: {
    backgroundColor: '#FEF2F2',
    borderColor: '#FECACA',
    borderWidth: 1,
    borderRadius: radii.card,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  friendlyErrorTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.error,
  },
  friendlyErrorText: {
    fontSize: 12,
    color: '#7F1D1D',
    marginTop: 2,
    marginBottom: 8,
  },
  retryButton: {
    backgroundColor: colors.error,
    alignSelf: 'flex-start',
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: radii.pill,
  },
  retryButtonText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '700',
  },
  loadingCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.md,
    backgroundColor: '#FFFFFF',
    borderRadius: radii.card,
    marginBottom: spacing.md,
    gap: 8,
  },
  loadingText: {
    fontSize: 12,
    color: colors.textSecondary,
    fontWeight: '500',
  },
  micFab: {
    position: 'absolute',
    bottom: 20,
    alignSelf: 'center',
    backgroundColor: colors.paytmBlue,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 22,
    paddingVertical: 13,
    borderRadius: radii.pill,
    shadowColor: colors.paytmBlue,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.45,
    shadowRadius: 10,
    elevation: 8,
    zIndex: 20,
  },
  micIcon: {
    fontSize: 18,
    marginRight: 8,
  },
  micText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '700',
  },

  // CHAT SCREEN STYLES
  chatContainer: {
    flex: 1,
    backgroundColor: colors.background,
  },
  chatSubHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  chatBackButton: {
    paddingVertical: 4,
    paddingHorizontal: 8,
  },
  chatBackText: {
    color: colors.paytmBlue,
    fontSize: 13,
    fontWeight: '700',
  },
  chatHeaderTitle: {
    fontSize: 14,
    fontWeight: '800',
    color: colors.textPrimary,
  },
  chatHeaderSubtitle: {
    fontSize: 10,
    color: colors.paytmBlue,
    fontWeight: '600',
  },
  voiceListeningBanner: {
    backgroundColor: '#FEF3C7',
    paddingVertical: 6,
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: '#FDE68A',
  },
  voiceListeningText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#B45309',
  },
  quickChipsBar: {
    backgroundColor: '#F0F9FF',
    borderBottomWidth: 1,
    borderBottomColor: '#BAE6FD',
    paddingVertical: 6,
  },
  quickChipsScroll: {
    paddingHorizontal: spacing.md,
    gap: 8,
  },
  quickChip: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#00BAF2',
    borderRadius: radii.pill,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  quickChipText: {
    fontSize: 11,
    color: colors.paytmBlue,
    fontWeight: '700',
  },
  chatMessageStream: {
    flex: 1,
  },
  chatStreamContent: {
    padding: spacing.md,
    paddingBottom: spacing.lg,
  },
  chatMessageRow: {
    marginVertical: 6,
    flexDirection: 'row',
  },
  chatRowLeft: {
    justifyContent: 'flex-start',
  },
  chatRowRight: {
    justifyContent: 'flex-end',
  },
  chatBubble: {
    maxWidth: '85%',
    borderRadius: radii.card,
    paddingHorizontal: 14,
    paddingVertical: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 1,
  },
  bubbleSaathi: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: colors.borderLight,
    borderTopLeftRadius: 4,
  },
  bubbleUser: {
    backgroundColor: colors.paytmBlue,
    borderTopRightRadius: 4,
  },
  chatBubbleHeader: {
    marginBottom: 6,
    alignSelf: 'flex-start',
  },
  chatBubbleText: {
    fontSize: 13,
    lineHeight: 18,
  },
  textSaathi: {
    color: colors.textPrimary,
  },
  textUser: {
    color: '#FFFFFF',
  },
  voicePill: {
    marginTop: 6,
    backgroundColor: '#F0FDF4',
    borderWidth: 1,
    borderColor: '#BBF7D0',
    borderRadius: radii.pill,
    paddingHorizontal: 10,
    paddingVertical: 4,
    alignSelf: 'flex-start',
  },
  voicePillText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#15803D',
  },
  hindiExplanationCard: {
    marginTop: 8,
    backgroundColor: '#FFFBEB',
    borderWidth: 1,
    borderColor: '#FDE68A',
    borderRadius: radii.sm,
    padding: 8,
  },
  hindiLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: '#B45309',
    marginBottom: 2,
  },
  hindiText: {
    fontSize: 12,
    color: '#78350F',
    lineHeight: 16,
  },

  // Technician Card
  techCardContainer: {
    marginTop: 10,
    backgroundColor: '#EFF6FF',
    borderWidth: 1.5,
    borderColor: '#93C5FD',
    borderRadius: radii.card,
    padding: 12,
  },
  techCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  techCardTitle: {
    fontSize: 13,
    fontWeight: '800',
    color: '#1E3A8A',
  },
  techCardSlotText: {
    fontSize: 12,
    color: '#1E40AF',
    lineHeight: 16,
  },
  techCardMetaText: {
    fontSize: 10,
    color: '#3B82F6',
    marginTop: 3,
    fontWeight: '600',
  },
  techCardNoticeBox: {
    backgroundColor: '#DBEAFE',
    borderRadius: 6,
    padding: 6,
    marginTop: 8,
  },
  techCardNoticeText: {
    fontSize: 10,
    color: '#1E3A8A',
    lineHeight: 14,
  },

  // Inline Approval Card
  approvalCardContainer: {
    marginTop: 10,
    backgroundColor: '#FFFBF2',
    borderWidth: 1.5,
    borderColor: '#F6C38B',
    borderRadius: radii.card,
    padding: 12,
  },
  approvalCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  approvalCardTitle: {
    fontSize: 13,
    fontWeight: '800',
    color: '#7C2D12',
    flex: 1,
    marginRight: 6,
  },
  approvalReasonText: {
    fontSize: 12,
    color: '#9A3412',
    lineHeight: 16,
  },
  approvalMetaText: {
    fontSize: 10,
    color: '#C2410C',
    marginTop: 3,
    fontWeight: '600',
  },
  approvalNoteBox: {
    backgroundColor: '#FEF3C7',
    borderRadius: 6,
    padding: 6,
    marginTop: 8,
  },
  approvalNoteText: {
    fontSize: 10,
    color: '#92400E',
    lineHeight: 14,
    fontWeight: '500',
  },
  approvalActionRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 10,
  },
  approvalApproveBtn: {
    flex: 1,
    backgroundColor: colors.paytmBlue,
    borderRadius: radii.pill,
    paddingVertical: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  approvalApproveBtnText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '700',
  },
  approvalRejectBtn: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: '#D1D5DB',
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  approvalRejectBtnText: {
    color: colors.textSecondary,
    fontSize: 11,
    fontWeight: '600',
  },
  approvalDecidedBanner: {
    marginTop: 8,
    backgroundColor: '#ECFDF5',
    borderWidth: 1,
    borderColor: '#A7F3D0',
    borderRadius: 6,
    padding: 6,
  },
  approvalDecidedText: {
    fontSize: 11,
    color: '#065F46',
    fontWeight: '700',
    textAlign: 'center',
  },

  // Structured Settlement Breakdown Card Styles
  settlementCardContainer: {
    marginTop: 10,
    backgroundColor: '#FFFFFF',
    borderWidth: 1.5,
    borderColor: '#BAE6FD',
    borderRadius: radii.card,
    padding: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  settlementCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#F0F9FF',
    paddingBottom: 6,
  },
  settlementCardTitle: {
    fontSize: 13,
    fontWeight: '800',
    color: '#002E6E',
  },
  settlementCardDate: {
    fontSize: 10,
    color: '#6B7280',
    marginTop: 1,
  },
  settlementTable: {
    marginVertical: 4,
  },
  settlementRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 3,
  },
  settlementRowLabel: {
    fontSize: 11,
    color: '#4B5563',
  },
  settlementRowVal: {
    fontSize: 11,
    fontWeight: '700',
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
  settlementDivider: {
    height: 1,
    backgroundColor: '#E5E7EB',
    marginVertical: 4,
  },
  settlementRowBoldLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: '#111827',
  },
  settlementRowBoldVal: {
    fontSize: 12,
    fontWeight: '800',
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
  settlementReconciledBg: {
    backgroundColor: '#ECFDF5',
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 4,
    marginTop: 2,
  },
  settlementDiscrepancyBg: {
    backgroundColor: '#FEF2F2',
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 4,
    marginTop: 2,
  },
  settlementDiscrepancyLabel: {
    fontSize: 11,
    fontWeight: '800',
  },
  settlementDiscrepancyVal: {
    fontSize: 12,
    fontWeight: '900',
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
  settlementUtrText: {
    fontSize: 10,
    color: '#6B7280',
    marginTop: 6,
  },
  settlementDisputeNoticeBox: {
    marginTop: 8,
    backgroundColor: '#FFF7ED',
    borderWidth: 1,
    borderColor: '#FED7AA',
    borderRadius: 8,
    padding: 8,
  },
  settlementDisputeTitle: {
    fontSize: 11,
    fontWeight: '800',
    color: '#9A3412',
  },
  settlementDisputeDesc: {
    fontSize: 10,
    color: '#C2410C',
    marginTop: 2,
    lineHeight: 14,
  },
  evidenceUploadBtn: {
    marginTop: 6,
    backgroundColor: '#002E6E',
    borderRadius: radii.pill,
    paddingVertical: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  evidenceUploadBtnText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '700',
  },
  evidenceSuccessBox: {
    marginTop: 6,
    backgroundColor: '#ECFDF5',
    borderWidth: 1,
    borderColor: '#A7F3D0',
    borderRadius: 6,
    padding: 6,
  },
  evidenceSuccessText: {
    color: '#065F46',
    fontSize: 10,
    fontWeight: '700',
    textAlign: 'center',
  },
  chatTimestamp: {
    fontSize: 9,
    marginTop: 4,
    alignSelf: 'flex-end',
  },
  timeSaathi: {
    color: '#9CA3AF',
  },
  timeUser: {
    color: 'rgba(255, 255, 255, 0.75)',
  },
  chatInputBar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
  },
  voiceMicBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#F0F9FF',
    borderWidth: 1,
    borderColor: '#BAE6FD',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 6,
  },
  chatTextInput: {
    flex: 1,
    backgroundColor: '#F5F7FA',
    borderRadius: radii.pill,
    paddingHorizontal: 16,
    paddingVertical: 8,
    fontSize: 13,
    color: colors.textPrimary,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  chatSendButton: {
    marginLeft: 8,
    backgroundColor: colors.paytmBlue,
    borderRadius: radii.pill,
    paddingHorizontal: 16,
    paddingVertical: 9,
  },
  sendDisabled: {
    opacity: 0.4,
  },
  chatSendText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '700',
  },

  // Auth Styles
  authSafeArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  authHero: {
    backgroundColor: colors.paytmBlue,
    paddingTop: 48,
    paddingBottom: 40,
    alignItems: 'center',
    borderBottomLeftRadius: 28,
    borderBottomRightRadius: 28,
  },
  authLogoBadge: {
    width: 52,
    height: 52,
    borderRadius: 16,
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
  },
  authLogoText: {
    fontSize: 28,
    fontWeight: '900',
    color: colors.paytmBlue,
  },
  authHeroTitle: {
    color: '#FFFFFF',
    fontSize: 24,
    fontWeight: '800',
  },
  authHeroSubtitle: {
    color: 'rgba(255, 255, 255, 0.85)',
    fontSize: 13,
    fontWeight: '600',
    marginTop: 4,
  },
  authCard: {
    backgroundColor: '#FFFFFF',
    marginHorizontal: spacing.lg,
    marginTop: -20,
    borderRadius: radii.cardLg,
    padding: spacing.xl,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.08,
    shadowRadius: 14,
    elevation: 4,
  },
  authCardTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  authCardSubtitle: {
    fontSize: 13,
    color: colors.textSecondary,
    marginTop: 4,
    marginBottom: spacing.lg,
    lineHeight: 18,
  },
  errorBox: {
    backgroundColor: '#FDEEEE',
    borderColor: '#F8B6B6',
    borderWidth: 1,
    borderRadius: radii.sm,
    padding: 10,
    marginBottom: spacing.md,
  },
  errorText: {
    color: colors.error,
    fontSize: 12,
    fontWeight: '600',
  },
  phoneInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1.5,
    borderColor: colors.borderDefault,
    borderRadius: radii.card,
    backgroundColor: '#F9FAFB',
    marginBottom: spacing.lg,
    paddingHorizontal: spacing.md,
    height: 50,
  },
  phonePrefix: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.textPrimary,
    marginRight: 8,
    borderRightWidth: 1,
    borderRightColor: colors.borderLight,
    paddingRight: 8,
  },
  phoneInput: {
    flex: 1,
    fontSize: 16,
    fontWeight: '600',
    color: colors.textPrimary,
  },
  otpInput: {
    borderWidth: 1.5,
    borderColor: colors.borderDefault,
    borderRadius: radii.card,
    backgroundColor: '#F9FAFB',
    marginBottom: spacing.lg,
    paddingHorizontal: spacing.md,
    height: 50,
    fontSize: 22,
    fontWeight: '800',
    letterSpacing: 8,
    textAlign: 'center',
    color: colors.textPrimary,
  },
  primaryButton: {
    backgroundColor: colors.paytmBlue,
    borderRadius: radii.card,
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: colors.paytmBlue,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 3,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  primaryButtonText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '700',
  },
  secondaryButton: {
    marginTop: spacing.md,
    alignItems: 'center',
    paddingVertical: 8,
  },
  secondaryButtonText: {
    color: colors.textSecondary,
    fontSize: 13,
    fontWeight: '600',
  },
  demoHintBox: {
    marginTop: spacing.lg,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
  },
  demoHintTitle: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.paytmBlue,
    letterSpacing: 0.8,
  },
  demoHintDesc: {
    fontSize: 11,
    color: colors.textSecondary,
    marginTop: 2,
  },

  // Bottom Tabs
  placeholderTabContent: {
    flex: 1,
    backgroundColor: colors.background,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  actionPill: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: colors.borderDefault,
    borderRadius: radii.pill,
    paddingVertical: 8,
    paddingHorizontal: 16,
    marginTop: spacing.md,
  },
  actionPillText: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.textPrimary,
  },
  bottomTabBar: {
    flexDirection: 'row',
    height: 60,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
    justifyContent: 'space-around',
    alignItems: 'center',
  },
  tabItem: {
    alignItems: 'center',
    justifyContent: 'center',
    flex: 1,
  },
  tabIconActive: {
    fontSize: 18,
  },
  tabLabelActive: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.paytmBlue,
    marginTop: 2,
  },
  tabIcon: {
    fontSize: 18,
    opacity: 0.6,
  },
  tabLabel: {
    fontSize: 11,
    fontWeight: '500',
    color: colors.textSecondary,
    marginTop: 2,
  },
});
