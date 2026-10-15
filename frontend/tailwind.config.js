/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ---- Reference design palette -------------------------------------- //
        // Neutral workspace: white surfaces, off-white section fills.
        canvas: {
          DEFAULT: "#FFFFFF", // primary background
          soft: "#FAFAFA", // secondary background
          section: "#F8F9FA", // subtle section background
          hover: "#F4F5F7", // row / item hover
        },
        // Primary accent — royal blue.
        brand: {
          DEFAULT: "#3B65D9",
          hover: "#3257C4",
          active: "#2A4AAB",
          soft: "#EEF2FD", // tinted fill
          ring: "rgba(59,101,217,0.35)",
        },
        // Text ramp.
        txt: {
          DEFAULT: "#171717", // primary
          muted: "#737373", // secondary
          faint: "#A3A3A3", // tertiary / metadata
          inverse: "#FFFFFF",
        },
        // Borders — subtle grey.
        line: {
          DEFAULT: "#E5E7EB",
          soft: "#F0F1F3",
          strong: "#D4D7DD",
        },
        // Status pills: soft pastel background + dark readable text.
        pill: {
          green: "#DCFCE7",
          "green-txt": "#166534",
          lavender: "#F3E8FF",
          "lavender-txt": "#6B21A8",
          blue: "#DBEAFE",
          "blue-txt": "#1D4ED8",
          amber: "#FEF3C7",
          "amber-txt": "#92400E",
          rose: "#FEE2E2",
          "rose-txt": "#991B1B",
          slate: "#F1F5F9",
          "slate-txt": "#475569",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "Geist",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: ["Geist Mono", "JetBrains Mono", "Consolas", "Menlo", "monospace"],
      },
      fontSize: {
        // Tight, compact information density.
        greeting: ["30px", { lineHeight: "1.15", letterSpacing: "-0.022em", fontWeight: "600" }],
        section: ["15px", { lineHeight: "1.35", letterSpacing: "-0.01em", fontWeight: "600" }],
        th: ["12px", { lineHeight: "1.3", letterSpacing: "0.01em", fontWeight: "500" }],
        body: ["13px", { lineHeight: "1.5" }],
        meta: ["11.5px", { lineHeight: "1.45" }],
      },
      borderRadius: {
        card: "14px",
        panel: "12px",
        control: "9px",
        pill: "9999px",
      },
      boxShadow: {
        // Almost no shadows — only for overlays.
        pop: "0 8px 24px -6px rgba(23,23,23,0.12), 0 2px 6px -2px rgba(23,23,23,0.06)",
        modal: "0 24px 64px -12px rgba(23,23,23,0.22), 0 4px 12px -4px rgba(23,23,23,0.10)",
      },
      transitionDuration: {
        fast: "150ms",
        base: "200ms",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.97)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        "slide-in-right": {
          "0%": { transform: "translateX(100%)" },
          "100%": { transform: "translateX(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 200ms ease-out both",
        "fade-in": "fade-in 150ms ease-out both",
        "scale-in": "scale-in 180ms ease-out both",
        "slide-in-right": "slide-in-right 220ms cubic-bezier(0.22,1,0.36,1) both",
      },
    },
  },
  plugins: [],
};
