"use client";
import dynamic from "next/dynamic";

const RainRiskMap = dynamic(() => import("../components/RainRiskMap"), {
  ssr: false,
  loading: () => <div className="loading">Loading map…</div>,
});

export default function Page() {
  return (
    <div className="layout">
      <header className="header">
        <h1>
          Somerville Rain-Risk <span className="badge">East Somerville · Inner Belt</span>
        </h1>
        <p>
          Cyvl drainage &amp; pavement draped on a LiDAR terrain surface — an elevation-aware
          ponding-risk screen (not a hydraulic simulation).
        </p>
      </header>
      <div className="main">
        <RainRiskMap />
      </div>
    </div>
  );
}
