/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef5ff',
          100: '#d9e9ff',
          500: '#2474f5',
          600: '#155eef',
          700: '#124dcc',
          900: '#102a56',
        },
        coral: '#ff4d5a',
        graphite: '#172033',
        pearl: '#f7f9fc',
      },
      boxShadow: {
        card: '0 18px 48px rgba(16, 42, 86, 0.08)',
        lift: '0 18px 42px rgba(21, 94, 239, 0.18)',
      },
      animation: {
        'fade-up': 'fadeUp .35s ease-out both',
        'soft-pulse': 'softPulse 2s ease-in-out infinite',
      },
      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        softPulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '.55' },
        },
      },
    },
  },
  plugins: [],
}
