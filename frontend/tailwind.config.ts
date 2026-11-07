import path from "path";
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    path.join(__dirname, "./src/pages/**/*.{js,ts,jsx,tsx,mdx}"),
    path.join(__dirname, "./src/components/**/*.{js,ts,jsx,tsx,mdx}"),
    path.join(__dirname, "./src/app/**/*.{js,ts,jsx,tsx,mdx}"),
  ],
  theme: {
    extend: {
      colors: {
        veritas: {
          navy: "#050811",
          midnight: "#080D1A",
          surface: "#0C1324",
          panel: "#10192E",
          elevated: "#15213B",
          border: "#1E2D4A",
          electric: "#2563EB",
          cyan: "#06B6D4",
          neon: "#22D3EE",
        },
      },
      boxShadow: {
        glow: "0 0 24px -4px rgba(6, 182, 212, 0.28)",
        "glow-blue": "0 0 28px -4px rgba(37, 99, 235, 0.35)",
      },
    },
  },
  plugins: [],
};

export default config;
