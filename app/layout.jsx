import "./globals.css";
import { Fira_Sans, Fira_Code } from "next/font/google";

const firaSans = Fira_Sans({
  subsets: ["latin"], weight: ["300", "400", "500", "600", "700"],
  variable: "--fira-sans", display: "swap",
});
const firaCode = Fira_Code({
  subsets: ["latin"], weight: ["400", "500", "600"],
  variable: "--fira-code", display: "swap",
});

export const metadata = {
  title: "Somerville Rain-Risk — Cyvl × LiDAR",
  description:
    "Elevation-aware stormwater / ponding-risk screening for East Somerville & the Inner Belt, validated against 311 flooding complaints.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${firaSans.variable} ${firaCode.variable}`}>
      <body>{children}</body>
    </html>
  );
}
