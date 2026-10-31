import React, { useState, useEffect } from 'react';
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
} from 'react-native';
import {
  colors,
  radii,
  spacing,
  StatusChipNative,
  StatusType,
} from '@paytm-saathi/design-tokens';

// In Expo/React Native local dev, Android emulator uses 10.0.2.2, Web uses localhost
const API_BASE_URL = 'http://localhost:8000';

type ScreenState = 'PHONE_ENTRY' | 'OTP_ENTRY' | 'HOME';

interface MerchantUser {
  id: string;
  store_name: string;
  merchant_name: string;
  phone: string;
  city: string;
  status: string;
  role: string;
}

const chipStates: StatusType[] = [
  'verified',
  'executed',
  'pending',
  'awaiting_approval',
  'needs_human',
];

export default function App() {
  const [screen, setScreen] = useState<ScreenState>('PHONE_ENTRY');
  const [token, setToken] = useState<string | null>(null);
  const [merchant, setMerchant] = useState<MerchantUser | null>(null);

  // Form states
  const [phone, setPhone] = useState('9876543210');
  const [otp, setOtp] = useState('123456');
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  // Check token on mount / route protection
  useEffect(() => {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        const savedToken = window.localStorage.getItem('saathi_merchant_token');
        const savedMerchant = window.localStorage.getItem('saathi_merchant_user');
        if (savedToken && savedMerchant) {
          setToken(savedToken);
          setMerchant(JSON.parse(savedMerchant));
          setScreen('HOME');
          
          // Verify with backend
          fetch(`${API_BASE_URL}/auth/me`, {
            headers: { Authorization: `Bearer ${savedToken}` },
          })
            .then((res) => {
              if (!res.ok) throw new Error('Token expired');
              return res.json();
            })
            .catch(() => {
              handleLogout();
            });
        }
      }
    } catch (_e) {
      // Storage unavailable fallback
    }
  }, []);

  const handleRequestOtp = async () => {
    if (!phone.trim() || phone.trim().length < 10) {
      setErrorMessage('Please enter a valid 10-digit mobile number');
      return;
    }

    setLoading(true);
    setErrorMessage(null);
    setInfoMessage(null);

    try {
      const res = await fetch(`${API_BASE_URL}/auth/merchant/request-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: phone.trim() }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Could not send OTP');
      }

      setInfoMessage(data.message || 'OTP sent! Use demo code: 123456');
      setScreen('OTP_ENTRY');
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to connect to backend server');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async () => {
    if (!otp.trim()) {
      setErrorMessage('Please enter the 6-digit OTP');
      return;
    }

    setLoading(true);
    setErrorMessage(null);

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
      if (!res.ok) {
        throw new Error(data.detail || 'Invalid OTP code');
      }

      // Store JWT token
      setToken(data.access_token);
      setMerchant(data.user);
      try {
        if (typeof window !== 'undefined' && window.localStorage) {
          window.localStorage.setItem('saathi_merchant_token', data.access_token);
          window.localStorage.setItem('saathi_merchant_user', JSON.stringify(data.user));
        }
      } catch (_e) {}

      setScreen('HOME');
    } catch (err: any) {
      setErrorMessage(err.message || 'OTP verification failed');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    setToken(null);
    setMerchant(null);
    setScreen('PHONE_ENTRY');
    setErrorMessage(null);
    setInfoMessage(null);
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.removeItem('saathi_merchant_token');
        window.localStorage.removeItem('saathi_merchant_user');
      }
    } catch (_e) {}
  };

  // SCREEN 1: Phone Number Entry
  if (screen === 'PHONE_ENTRY') {
    return (
      <SafeAreaView style={styles.authSafeArea}>
        <StatusBar barStyle="light-content" backgroundColor={colors.paytmBlue} />
        
        {/* Top Brand Banner */}
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

          {errorMessage && (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{errorMessage}</Text>
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
            style={[styles.primaryButton, loading && styles.buttonDisabled]}
            disabled={loading}
            onPress={handleRequestOtp}
            activeOpacity={0.85}
          >
            {loading ? (
              <ActivityIndicator color="#FFFFFF" size="small" />
            ) : (
              <Text style={styles.primaryButtonText}>Get OTP</Text>
            )}
          </TouchableOpacity>

          <View style={styles.demoHintBox}>
            <Text style={styles.demoHintTitle}>DEMO ACCOUNT</Text>
            <Text style={styles.demoHintDesc}>
              Seeded Merchant: Sharma Kirana (+91 9876543210) · Demo OTP: 123456
            </Text>
          </View>
        </View>
      </SafeAreaView>
    );
  }

  // SCREEN 2: OTP Verification
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
            {infoMessage || 'Enter the demo OTP to access your Kirana dashboard.'}
          </Text>

          {errorMessage && (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{errorMessage}</Text>
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
            style={[styles.primaryButton, loading && styles.buttonDisabled]}
            disabled={loading}
            onPress={handleVerifyOtp}
            activeOpacity={0.85}
          >
            {loading ? (
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

  // SCREEN 3: Authenticated Merchant Home Shell
  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="light-content" backgroundColor={colors.paytmBlue} />

      {/* 1. Paytm Brand Header */}
      <View style={styles.header}>
        <View style={styles.headerTop}>
          <View>
            <Text style={styles.headerSubtitle}>
              {merchant?.city?.toUpperCase() || 'JAIPUR'} · DEMO ENVIRONMENT
            </Text>
            <Text style={styles.headerTitle}>
              {merchant?.store_name || 'Sharma Kirana Store'}
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

        {/* Quick Balance / Summary pill */}
        <View style={styles.summaryBar}>
          <View>
            <Text style={styles.summaryLabel}>TODAY'S COLLECTION</Text>
            <Text style={styles.summaryValue}>₹600.00</Text>
          </View>
          <View style={styles.summaryDivider} />
          <View>
            <Text style={styles.summaryLabel}>SOUNDBOX 4G</Text>
            <Text style={styles.summaryValue}>Connected · 88%</Text>
          </View>
        </View>
      </View>

      {/* 2. Scrollable Body */}
      <ScrollView
        style={styles.container}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Status Chips Showcase Card */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Design Tokens · Shared Status Chips</Text>
          <Text style={styles.cardSubtitle}>
            Authenticated session for {merchant?.merchant_name || 'Ramesh Sharma'}
          </Text>

          <View style={styles.chipsContainer}>
            {chipStates.map((st) => (
              <View key={st} style={styles.chipWrapper}>
                <StatusChipNative status={st} />
              </View>
            ))}
          </View>
        </View>

        {/* Quick Action Pills */}
        <View style={styles.pillRow}>
          <TouchableOpacity style={styles.actionPill}>
            <Text style={styles.actionPillText}>Check Soundbox</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionPill}>
            <Text style={styles.actionPillText}>Customer Udhaar</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionPill}>
            <Text style={styles.actionPillText}>Settlement Info</Text>
          </TouchableOpacity>
        </View>

        {/* Empty State Banner */}
        <View style={styles.emptyStateCard}>
          <View style={styles.saathiIconCircle}>
            <Text style={styles.saathiIconText}>S</Text>
          </View>
          <Text style={styles.emptyTitle}>Merchant Shell Initialized</Text>
          <Text style={styles.emptySubtitle}>
            JWT token is verified. Saathi is monitoring payments and Soundbox telemetry. Press the microphone below to talk to Saathi.
          </Text>
        </View>
      </ScrollView>

      {/* 3. Floating Mic FAB */}
      <TouchableOpacity
        style={styles.micFab}
        activeOpacity={0.85}
        onPress={() => alert('Talk to Saathi voice assistant will activate in Phase 2!')}
      >
        <Text style={styles.micIcon}>🎙</Text>
        <Text style={styles.micText}>Talk to Saathi</Text>
      </TouchableOpacity>

      {/* 4. Bottom Tab Bar Shell */}
      <View style={styles.bottomTabBar}>
        <TouchableOpacity style={styles.tabItem}>
          <Text style={styles.tabIconActive}>🏠</Text>
          <Text style={styles.tabLabelActive}>Home</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.tabItem}>
          <Text style={styles.tabIcon}>📜</Text>
          <Text style={styles.tabLabel}>Passbook</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.tabItem}>
          <Text style={styles.tabIcon}>📒</Text>
          <Text style={styles.tabLabel}>Udhaar</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.tabItem}>
          <Text style={styles.tabIcon}>⚙️</Text>
          <Text style={styles.tabLabel}>Settings</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  // Auth Screen Styles
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

  // Main App Shell Styles
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
    backgroundColor: 'rgba(235, 87, 87, 0.2)',
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
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollContent: {
    padding: spacing.lg,
    paddingBottom: 100,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.card,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.borderLight,
    marginBottom: spacing.lg,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 2,
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
    marginBottom: spacing.md,
  },
  chipsContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  chipWrapper: {
    marginVertical: 4,
  },
  pillRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.lg,
  },
  actionPill: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: colors.borderDefault,
    borderRadius: radii.pill,
    paddingVertical: 8,
    paddingHorizontal: 14,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 2,
    elevation: 1,
  },
  actionPillText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.textPrimary,
  },
  emptyStateCard: {
    backgroundColor: colors.surface,
    borderRadius: radii.card,
    padding: spacing.xl,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.borderLight,
    marginBottom: spacing.lg,
  },
  saathiIconCircle: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: 'rgba(0, 186, 242, 0.12)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  saathiIconText: {
    color: colors.paytmBlue,
    fontSize: 24,
    fontWeight: '800',
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.textPrimary,
    marginBottom: 6,
  },
  emptySubtitle: {
    fontSize: 13,
    color: colors.textSecondary,
    textAlign: 'center',
    lineHeight: 18,
    maxWidth: 280,
  },
  micFab: {
    position: 'absolute',
    bottom: 74,
    alignSelf: 'center',
    backgroundColor: colors.paytmBlue,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: radii.pill,
    shadowColor: colors.paytmBlue,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.4,
    shadowRadius: 10,
    elevation: 8,
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
