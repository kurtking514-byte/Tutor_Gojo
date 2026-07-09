/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Background layers, darkest to lightest
        void: "#0B0A14",
        surface: "#15131F",
        elevated: "#1E1C2B",
        hairline: "#2A2839",

        // Text
        ink: {
          DEFAULT: "#F1EFFA",
          muted: "#9C97B3",
        },

        // Brand accent
        accent: {
          DEFAULT: "#7C5CFF",
          dim: "#5B43BF",
          soft: "#B6A6FF",
        },
      },
      fontFamily: {
        display: ["Sora", "ui-sans-serif", "system-ui", "sans-serif"],
        body: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glow: "0 0 20px rgba(124, 92, 255, 0.45)",
      },
      keyframes: {
        bounceDot: {
          "0%, 80%, 100%": { transform: "translateY(0)", opacity: "0.6" },
          "40%": { transform: "translateY(-4px)", opacity: "1" },
        },
        fadeInUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseGlow: {
          "0%, 100%": { opacity: "0.35", transform: "scale(1)" },
          "50%": { opacity: "0.7", transform: "scale(1.15)" },
        },
      },
      animation: {
        "bounce-dot": "bounceDot 1.4s ease-in-out infinite",
        "fade-in-up": "fadeInUp 0.3s ease-out",
        "pulse-glow": "pulseGlow 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
