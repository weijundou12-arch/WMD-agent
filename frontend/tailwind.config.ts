import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        ink: "#14213d",
        pine: "#176b5c",
        coral: "#d65f45",
        wheat: "#f4efe6",
        mist: "#e8eef2"
      },
      boxShadow: {
        panel: "0 12px 32px rgba(20, 33, 61, 0.08)"
      }
    }
  },
  plugins: []
};

export default config;
