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

interface ChatMessage {
  id: string;
  sender: 'user' | 'saathi';
  text: string;
  timestamp: string;
  branch?: string;
  chip_status?: StatusType;
  explanation_en?: string;
  explanation_hi?: string;
  approval_card?: ApprovalCardData | null;
  approval_decided?: 'APPROVED' | 'REJECTED';
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

  // Chat tab state
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      id: 'msg_welcome',
      sender: 'saathi',
      text: 'Namaste! I am Saathi, your Kirana AI teammate. I actively investigate payment disputes, failed transfers, and Soundbox status. What can I check for you?',
      timestamp: '10:00 AM',
      chip_status: 'verified',
    },
  ]);
  const [chatInput, setChatInput] = useState('');
  const [chatSending, setChatSending] = useState(false);
  const [approvalSubmittingId, setApprovalSubmittingId] = useState<string | null>(null);

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

  // Chat: Send message to Python backend (invoking Resolve Agent)
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
        branch: data.branch,
        chip_status: (data.chip_status as StatusType) || 'verified',
        explanation_en: data.explanation_en,
        explanation_hi: data.explanation_hi,
        approval_card: data.approval_card,
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
              {summary?.payments.today_total_formatted || '₹600.00'}
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
                  <Text style={styles.metricLabel}>Speaker</Text>
                  <Text style={styles.metricValue}>Loud & Clear</Text>
                </View>
                <View style={styles.metricItem}>
                  <Text style={styles.metricLabel}>SIM Network</Text>
                  <Text style={styles.metricValue}>Airtel 4G</Text>
                </View>
              </View>
            </View>

            {/* CARD 2: Payments & Recent Collections */}
            <View style={styles.card}>
              <View style={styles.cardHeaderRow}>
                <View>
                  <Text style={styles.cardTitle}>Today's Payments</Text>
                  <Text style={styles.cardSubtitle}>
                    {summary?.payments.today_count || 2} successful UPI transactions
                  </Text>
                </View>
                <StatusChipNative
                  status={summary?.payments.chip_status || 'verified'}
                  label="Reconciled"
                />
              </View>

              <Text style={styles.collectionsBigAmount}>
                {summary?.payments.today_total_formatted || '₹600.00'}
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

          {/* Floating Mic FAB -> Opens Chat Tab */}
          <TouchableOpacity
            style={styles.micFab}
            activeOpacity={0.88}
            onPress={() => setActiveTab('CHAT')}
          >
            <Text style={styles.micIcon}>🎙</Text>
            <Text style={styles.micText}>Talk to Saathi</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* TAB 2: SAATHI CHAT TAB (Resolve Specialist Agent Enabled) */}
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
              <Text style={styles.chatHeaderTitle}>Saathi Assistant</Text>
              <Text style={styles.chatHeaderSubtitle}>Resolve Agent · Switch Connected</Text>
            </View>
            <StatusChipNative status="verified" size="sm" label="Active" />
          </View>

          {/* Scenario Quick-Test Chips */}
          <View style={styles.quickChipsBar}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.quickChipsScroll}>
              <TouchableOpacity
                style={styles.quickChip}
                onPress={() => handleSendMessage('Check customer Alok ₹250 auto-reversal')}
              >
                <Text style={styles.quickChipText}>⚡ ₹250 Auto-Reversal (Branch A)</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.quickChip}
                onPress={() => handleSendMessage('Deepak Verma ₹500 stuck reversal need refund review')}
              >
                <Text style={styles.quickChipText}>⏱ ₹500 Stuck Reversal (Branch B)</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.quickChip}
                onPress={() => handleSendMessage('Customer Pooja ₹320 chime not heard confirm status')}
              >
                <Text style={styles.quickChipText}>✅ ₹320 Confirmed (Branch C)</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.quickChip}
                onPress={() => handleSendMessage('Suspicious unknown payment ₹1200 potential fraud')}
              >
                <Text style={styles.quickChipText}>🛡 ₹1,200 Security Escalation (Branch D)</Text>
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
                            msg.branch === 'A_AUTO_REVERSAL'
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

                    {/* Bilingual Hindi Explanation Card */}
                    {isSaathi && msg.explanation_hi && (
                      <View style={styles.hindiExplanationCard}>
                        <Text style={styles.hindiLabel}>🇮🇳 ग्राहक के लिए संदेश (HINDI)</Text>
                        <Text style={styles.hindiText}>{msg.explanation_hi}</Text>
                      </View>
                    )}

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
                    Saathi Resolve investigating payment switch...
                  </Text>
                </View>
              </View>
            )}
          </ScrollView>

          {/* Chat Input Bar */}
          <View style={styles.chatInputBar}>
            <TextInput
              style={styles.chatTextInput}
              value={chatInput}
              onChangeText={setChatInput}
              placeholder="Ask Saathi (e.g. 'Customer ₹250 failed')..."
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
    color: colors.success,
    fontWeight: '600',
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
