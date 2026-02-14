/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#f4efe4',
        ink: '#1f2937',
        accent: '#0f766e',
        amberish: '#d97706',
        coral: '#be123c',
      },
      boxShadow: {
        card: '0 14px 45px -24px rgba(17, 24, 39, 0.5)',
      },
      fontFamily: {
        display: ['Space Grotesk', 'sans-serif'],
        body: ['IBM Plex Sans', 'sans-serif'],
      },
      keyframes: {
        floatIn: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        floatIn: 'floatIn 320ms ease-out both',
      },
    },
  },
  plugins: [],
}
