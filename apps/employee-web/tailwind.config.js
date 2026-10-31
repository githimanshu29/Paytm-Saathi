/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        paytmBlue: '#00BAF2',
        navy: '#002E6E',
        success: '#0B8457',
        warning: '#F2994A',
        error: '#EB5757',
        bgNeutral: '#F5F7FA',
        textPrimary: '#1A1A1A',
        textSecondary: '#6B7280',
      },
      borderRadius: {
        card: '14px',
        cardLg: '16px',
      },
      boxShadow: {
        soft: '0 2px 8px rgba(0, 0, 0, 0.06)',
        elevated: '0 4px 16px rgba(0, 0, 0, 0.10)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
