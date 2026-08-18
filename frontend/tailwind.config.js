/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Neutral enterprise palette. Information density first: the accent is
        // reserved for interactive elements so RAG status colours stay the
        // most saturated thing on screen and remain scannable.
        brand: {
          50: "#eef4ff",
          100: "#d9e6ff",
          200: "#bcd3ff",
          300: "#8eb5ff",
          400: "#598cff",
          500: "#3363f5",
          600: "#1f45db",
          700: "#1b37b0",
          800: "#1c318b",
          900: "#1c2d6e",
        },
        ink: {
          50: "#f6f7f9",
          100: "#eceef2",
          200: "#d5dae2",
          300: "#b0bac9",
          400: "#8494ab",
          500: "#647691",
          600: "#4f5f78",
          700: "#414d61",
          800: "#384252",
          900: "#323a47",
        },
        rag: {
          green: "#16a34a",
          greenBg: "#dcfce7",
          amber: "#d97706",
          amberBg: "#fef3c7",
          red: "#dc2626",
          redBg: "#fee2e2",
        },
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Consolas", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.1)",
        pop: "0 12px 32px rgba(16,24,40,.12)",
      },
    },
  },
  plugins: [],
};
