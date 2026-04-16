/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{vue,js,ts}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Fira Sans", "PingFang SC", "Microsoft YaHei", "sans-serif"],
        mono: ["Fira Code", "ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
      },
      boxShadow: {
        glow: "0 24px 80px rgba(37, 99, 235, 0.16)",
        panel: "0 18px 55px rgba(15, 23, 42, 0.08)",
      },
    },
  },
  daisyui: {
    themes: [
      {
        hongsou: {
          primary: "#1E40AF",
          secondary: "#06B6D4",
          accent: "#F59E0B",
          neutral: "#0F172A",
          "base-100": "#F8FAFC",
          "base-200": "#EEF4FB",
          "base-300": "#D9E5F2",
          info: "#3B82F6",
          success: "#10B981",
          warning: "#F59E0B",
          error: "#EF4444",
        },
      },
    ],
  },
  plugins: [require("daisyui")],
};
