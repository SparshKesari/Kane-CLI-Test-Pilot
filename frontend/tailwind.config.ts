import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cream: "rgb(var(--cream) / <alpha-value>)",
        panel: "rgb(var(--panel) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        clay: {
          DEFAULT: "rgb(var(--clay) / <alpha-value>)",
          soft: "rgb(var(--clay-soft) / <alpha-value>)",
          wash: "rgb(var(--clay-wash) / <alpha-value>)",
        },
        ok: "rgb(var(--ok) / <alpha-value>)",
        warn: "rgb(var(--warn) / <alpha-value>)",
        bad: "rgb(var(--bad) / <alpha-value>)",
        // Theme-independent: terminal / code surfaces stay dark in both themes.
        term: "#1c1b18",
        termfg: "#ece8df",
      },
      fontFamily: {
        serif: ["Newsreader", "Georgia", "serif"],
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        soft: "0 1px 2px rgba(31,30,29,.04), 0 6px 24px rgba(31,30,29,.06)",
      },
      borderRadius: { xl2: "1.1rem" },
    },
  },
  plugins: [],
};
export default config;
