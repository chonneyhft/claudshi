/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Geist Variable"', "Geist", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"Geist Mono Variable"', '"Geist Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        bg: {
          DEFAULT: "#08090a",
          subtle: "#0c0d0f",
          card: "#101113",
        },
        line: {
          DEFAULT: "#1c1d1f",
          subtle: "#16171a",
        },
        ink: {
          DEFAULT: "#e8e9ea",
          muted: "#7d7e80",
          dim: "#525355",
        },
        pos: "#3ecf8e",
        neg: "#f87171",
        accent: "#6366f1",
      },
      animation: {
        "fade-in": "fadeIn 0.4s ease-out",
        "slide-up": "slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        fadeIn: {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        slideUp: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
