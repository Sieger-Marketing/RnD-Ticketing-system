/** @type {import('tailwindcss').Config} */

/**
 * Sieger brand palette.
 *
 * The guideline permits three colours: Signal Red, Standard Black and Cream.
 * Two deliberate decisions follow from applying that to a dashboard.
 *
 * 1. Signal Red is reserved for signals. It marks critical status, destructive
 *    actions and the brand mark -- nothing else. Primary buttons are black, so
 *    a red control and a red status never mean two different things on the
 *    same screen. The colour is literally named Signal Red; using it for "save"
 *    would waste it.
 *
 * 2. RAG health is kept, because spec section 21 mandates GREEN / AMBER / RED
 *    by name and a health engine cannot speak in three brand colours. The
 *    greens and ambers here are desaturated and warmed so they sit against
 *    cream rather than shouting over it, and RED is Signal Red itself.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Signal Red #9B2423, with a working scale around it.
        signal: {
          50: "#fbf2f1",
          100: "#f6e2e1",
          200: "#eec7c6",
          300: "#e0a09e",
          400: "#c96d6a",
          500: "#b03e3c",
          600: "#9b2423", // the brand value
          700: "#801d1c",
          800: "#6a1918",
          900: "#581817",
        },
        // Cream #F3ECE0, the permitted light background.
        cream: {
          50: "#fdfbf8",
          100: "#f9f5ef",
          200: "#f3ece0", // the brand value
          300: "#e7dccb",
          400: "#d6c7b0",
          500: "#bda98d",
        },
        // Neutral greys derived from Standard Black, warmed slightly so they
        // read as part of a cream-based palette rather than a cold grey UI.
        ink: {
          50: "#faf8f5",
          100: "#f2efea",
          200: "#e2ddd4",
          300: "#c6bfb2",
          400: "#948b7c",
          500: "#6f6759",
          600: "#544d42",
          700: "#3d382f",
          800: "#26231d",
          900: "#000000", // Standard Black
        },
        rag: {
          green: "#3f6d44",
          greenBg: "#e8efe6",
          amber: "#8a6212",
          amberBg: "#f7eeda",
          red: "#9b2423",
          redBg: "#f6e2e1",
        },
      },
      fontFamily: {
        // Effra is the brand face but is licensed and not on Google Fonts.
        // Poppins carries headings and Sora the interface text, which is the
        // approved web fallback pairing.
        sans: ["Sora", "Poppins", "Segoe UI", "system-ui", "sans-serif"],
        display: ["Poppins", "Sora", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Consolas", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        card: "0 1px 2px rgba(38,35,29,.05), 0 1px 3px rgba(38,35,29,.08)",
        pop: "0 12px 32px rgba(38,35,29,.16)",
      },
      screens: {
        // Narrow phones exist and the app has dense tables; this gives a
        // breakpoint below Tailwind's smallest to work with.
        xs: "420px",
      },
    },
  },
  plugins: [],
};
