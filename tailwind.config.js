/** @type {import('tailwindcss').Config} */
module.exports = {
    // `overline` is a Tailwind utility; without this an app's own eyebrow-label class draws a line above the text.
    blocklist: ["overline"],
    darkMode: ["class"],
    content: [
      './pages/**/*.{js,jsx}',
      './components/**/*.{js,jsx}',
      './app/**/*.{js,jsx}',
      './src/**/*.{js,jsx}',
      './features/**/*.{js,jsx}',
      './lib/**/*.{js,jsx}',
    ],
    prefix: "",
    theme: {
      container: {
        center: true,
        padding: '2rem',
        screens: {
          '2xl': '1400px'
        }
      },
      extend: {
        fontFamily: {
          sans: ['Plus Jakarta Sans Variable', 'Arial', 'sans-serif'],
          serif: ['Playfair Display Variable', 'Georgia', 'serif'],
          mono: ['DM Mono', 'monospace'],
        },
        colors: {
          border: '#e6dfd5',
          input: '#e6dfd5',
          ring: '#8b5a2b',
          background: '#fdfbf7',
          foreground: '#2c221e',
          primary: {
            DEFAULT: '#8b5a2b',
            foreground: '#ffffff'
          },
          secondary: {
            DEFAULT: '#eee4d6',
            foreground: '#6f451f'
          },
          destructive: { DEFAULT: '#9b2226', foreground: '#ffffff' },
          muted: { DEFAULT: '#f4ede3', foreground: '#796a63' },
          accent: { DEFAULT: '#f4ede0', foreground: '#6f451f' },
          popover: { DEFAULT: '#ffffff', foreground: '#2c221e' },
          card: { DEFAULT: '#ffffff', foreground: '#2c221e' },
          chart: {
            '1': 'hsl(var(--chart-1))',
            '2': 'hsl(var(--chart-2))',
            '3': 'hsl(var(--chart-3))',
            '4': 'hsl(var(--chart-4))',
            '5': 'hsl(var(--chart-5))'
          },
          sidebar: {
            DEFAULT: '#faf6ef',
            foreground: '#6f451f',
            primary: 'hsl(var(--sidebar-primary))',
            'primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
            accent: 'hsl(var(--sidebar-accent))',
            'accent-foreground': 'hsl(var(--sidebar-accent-foreground))',
            border: 'hsl(var(--sidebar-border))',
            ring: 'hsl(var(--sidebar-ring))'
          }
        },
        borderRadius: {
          lg: 'var(--radius)',
          md: 'calc(var(--radius) - 2px)',
          sm: 'calc(var(--radius) - 4px)'
        },
        keyframes: {
          'accordion-down': {
            from: {
              height: '0'
            },
            to: {
              height: 'var(--radix-accordion-content-height)'
            }
          },
          'accordion-up': {
            from: {
              height: 'var(--radix-accordion-content-height)'
            },
            to: {
              height: '0'
            }
          }
        },
        animation: {
          'accordion-down': 'accordion-down 0.2s ease-out',
          'accordion-up': 'accordion-up 0.2s ease-out'
        }
      }
    },
    plugins: [require("tailwindcss-animate")],
  }