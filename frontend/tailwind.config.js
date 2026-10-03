/** @type {import('tailwindcss').Config} */
module.exports = {
  // Existing globals.css already defines .flex, .gap-1, .grid, .btn.
  // A prefix keeps those class names exactly as they are.
  prefix: 'tw-',
  // Existing pages depend on the globals.css reset.
  corePlugins: {
    preflight: false,
  },
  content: ['./src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        tillion: {
          brand: 'var(--color-brand)',
          'brand-dark': 'var(--color-brand-dark)',
          'brand-light': 'var(--color-brand-light)',
          success: 'var(--color-success)',
          warning: 'var(--color-warning)',
          danger: 'var(--color-danger)',
          'danger-dark': 'var(--color-danger-dark)',
          info: 'var(--color-info)',
          page: 'var(--bg-page)',
          card: 'var(--bg-card)',
          sidebar: 'var(--bg-sidebar)',
          border: 'var(--border)',
          text: 'var(--text-primary)',
          muted: 'var(--text-secondary)',
          'sidebar-text': 'var(--text-sidebar)',
        },
      },
      boxShadow: {
        tillion: 'var(--shadow-sm)',
        'tillion-md': 'var(--shadow-md)',
        'tillion-lg': 'var(--shadow-lg)',
      },
      width: {
        sidebar: 'var(--sidebar-width)',
      },
    },
  },
  plugins: [],
};
