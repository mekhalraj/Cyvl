"use client";
import dynamic from "next/dynamic";

const RainRiskMap = dynamic(() => import("../components/RainRiskMap"), {
  ssr: false,
  loading: () => <div className="loading">Loading map…</div>,
});

export default function Page() {
  return (
    <main className="stage">
      <RainRiskMap />
    </main>
  );
}
