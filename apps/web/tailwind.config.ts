import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-geist)", "Geist", "Inter", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "Geist Mono", "JetBrains Mono", "monospace"],
      },
      colors: {
        /* Surfaces */
        bg: {
          base: "var(--bg-base)",
          subtle: "var(--bg-subtle)",
          muted: "var(--bg-muted)",
        },
        surface: {
          1: "var(--surface-1)",
          2: "var(--surface-2)",
          3: "var(--surface-3)",
          DEFAULT: "var(--surface-1)",
          raised: "var(--surface-2)",
          hover: "var(--surface-hover)",
          active: "var(--surface-active)",
        },
        /* Borders */
        border: {
          subtle: "var(--border-subtle)",
          DEFAULT: "var(--border-default)",
          strong: "var(--border-strong)",
        },
        /* Text */
        text: {
          primary: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          tertiary: "var(--text-tertiary)",
          disabled: "var(--text-disabled)",
          inverse: "var(--text-inverse)",
        },
        /* Accent */
        accent: {
          DEFAULT: "var(--accent)",
          light: "var(--accent-light)",
          dark: "var(--accent-dark)",
          subtle: "var(--accent-subtle)",
          muted: "var(--accent-muted)",
          foreground: "var(--text-on-accent)",
        },
        /* Semantic */
        success: {
          DEFAULT: "var(--success)",
          subtle: "var(--success-subtle)",
        },
        warning: {
          DEFAULT: "var(--warning)",
          subtle: "var(--warning-subtle)",
        },
        danger: {
          DEFAULT: "var(--danger)",
          subtle: "var(--danger-subtle)",
        },
        info: {
          DEFAULT: "var(--info)",
          subtle: "var(--info-subtle)",
        },
        /* Legacy aliases */
        background: "var(--background)",
        foreground: "var(--foreground)",
        "muted-foreground": "var(--muted-foreground)",
        "accent-foreground": "var(--accent-foreground)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        DEFAULT: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        "2xl": "var(--radius-2xl)",
        full: "var(--radius-full)",
      },
      boxShadow: {
        xs: "var(--shadow-xs)",
        sm: "var(--shadow-sm)",
        DEFAULT: "var(--shadow-md)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        xl: "var(--shadow-xl)",
      },
      transitionDuration: {
        fast: "120ms",
        base: "200ms",
        slow: "300ms",
      },
      animation: {
        "fade-in": "fadeIn 200ms ease forwards",
        "slide-in-left": "slideInLeft 200ms ease forwards",
        "slide-in-up": "slideInUp 200ms ease forwards",
        "scale-in": "scaleIn 150ms ease forwards",
        shimmer: "shimmer 1.5s infinite",
        blink: "blink 1s step-end infinite",
        spin: "spin 0.65s linear infinite",
        pulse: "pulse 1.8s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideInLeft: {
          "0%": { opacity: "0", transform: "translateX(-8px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        slideInUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        scaleIn: {
          "0%": { opacity: "0", transform: "scale(0.95)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      width: {
        sidebar: "var(--sidebar-width)",
        "sidebar-collapsed": "var(--sidebar-collapsed-width)",
      },
      maxWidth: {
        chat: "var(--chat-max-width)",
      },
      spacing: {
        "4.5": "1.125rem",
        "13": "3.25rem",
        "15": "3.75rem",
        "18": "4.5rem",
      },
      zIndex: {
        sidebar: "40",
        header: "50",
        overlay: "60",
        modal: "70",
        toast: "80",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
