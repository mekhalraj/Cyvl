import "./globals.css";

export const metadata = {
  title: "Somerville Rain-Risk — Cyvl × LiDAR",
  description:
    "Elevation-aware stormwater / ponding-risk screening for East Somerville & the Inner Belt. Cyvl infrastructure draped on a LiDAR terrain surface.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
