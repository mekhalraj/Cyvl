"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, GeoJSON, ZoomControl, useMap } from "react-leaflet";
import { motion, useReducedMotion } from "framer-motion";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const CENTER = [42.3905, -71.099];
const prioColor = (p) => (p >= 75 ? "#f87171" : p >= 60 ? "#fb923c" : p >= 40 ? "#fbbf24" : "#34d399");
const pciColor = (v) => (v == null ? "#7f8c99" : v >= 70 ? "#34d399" : v >= 55 ? "#fbbf24" : v >= 40 ? "#fb923c" : "#f87171");
const compColor = (c) => (c >= 10 ? "#f59e0b" : c >= 5 ? "#fbbf24" : "#fcd34d");
const prioBand = (p) => (p >= 75 ? "≥ 75 · highest" : p >= 60 ? "60–75 · high" : p >= 40 ? "40–60 · moderate" : "< 40 · lower");

// app-styled leaflet popups (raw HTML strings — kept lightweight for ~1.7k cells)
const scoreRow = (label, v, color) => {
  const has = v != null && !Number.isNaN(v);
  const pct = has ? Math.round(Math.max(0, Math.min(1, v)) * 100) : 0;
  return `<div class="popup-score"><span class="popup-score-l">${label}</span>`
    + `<span class="popup-bar"><span class="popup-bar-fill" style="width:${pct}%;background:${color}"></span></span>`
    + `<span class="popup-score-v mono">${has ? v.toFixed(2) : "—"}</span></div>`;
};
const rankingPopupHTML = (p, total) => {
  const c = prioColor(p.priority);
  const pci = p.mean_pci != null ? Math.round(p.mean_pci) : "—";
  return `<div class="popup-card">`
    + `<div class="popup-head"><span class="popup-badge mono" style="background:${c}">${Math.round(p.priority)}</span>`
    + `<span class="popup-title"><b>Priority <span class="mono">${p.priority}</span></b>`
    + `<span class="popup-band" style="color:${c}">${prioBand(p.priority)} · rank ${p.rank}/${total}</span></span></div>`
    + `<div class="popup-kpis">`
    + `<div class="popup-kpi"><div class="n mono">${p.ponding_ft}<small> ft</small></div><div class="l">ponding</div></div>`
    + `<div class="popup-kpi"><div class="n mono">${p.basins}</div><div class="l">catch basins</div></div>`
    + `<div class="popup-kpi"><div class="n mono">${pci}</div><div class="l">mean PCI</div></div></div>`
    + `<div class="popup-scores"><div class="popup-sub">Score breakdown</div>`
    + scoreRow("Ponding depth", p.s_pond, c)
    + scoreRow("Basin deficit", p.s_basin_deficit, c)
    + scoreRow("Pavement", p.s_pci, c)
    + `</div></div>`;
};
const miniPopup = (title, color, body = "") =>
  `<div class="popup-mini"><div class="popup-h"><span class="popup-hdot" style="background:${color};color:${color}"></span>${title}</div>`
  + (body ? `<div class="popup-mbody">${body}</div>` : "") + `</div>`;

const I = (d) => (p) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    strokeLinecap="round" strokeLinejoin="round" {...p}>{d}</svg>);
const IcGrid = I(<><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /></>);
const IcAlert = I(<><path d="M12 9v4" /><path d="M12 17h.01" /><path d="M10.3 3.9 2 18a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /></>);
const IcRoad = I(<><path d="M4 19 8 5" /><path d="M20 19 16 5" /><path d="M12 6v2M12 11v2M12 16v2" /></>);
const IcDrop = I(<path d="M12 2.5S5 10 5 14a7 7 0 0 0 14 0c0-4-7-11.5-7-11.5Z" />);
const IcPipe = I(<><path d="M3 8h13a3 3 0 0 1 3 3v10" /><path d="M3 5v6" /><path d="M16 21h6" /></>);
const IcBranch = I(<><path d="M6 3v18" /><path d="M6 9h8a4 4 0 0 1 4 4v3" /></>);
const IcDot = I(<circle cx="12" cy="12" r="7" />);
const IcOut = I(<><path d="M12 3v12" /><path d="m7 10 5 5 5-5" /><path d="M5 21h14" /></>);
const IcDisc = I(<><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /></>);
const IcBolt = I(<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" />);
const IcWaves = I(<>
  <path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1" />
  <path d="M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1" />
  <path d="M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1" /></>);

const LAYERS = [
  { key: "ranking",    label: "Ponding risk",        group: "Risk & validation", file: "ranking.geojson",            on: true,  icon: <IcGrid /> },
  { key: "complaints", label: "311 complaints",       group: "Risk & validation", file: "complaints_blocks.geojson",  on: true,  icon: <IcAlert /> },
  { key: "pavement",   label: "Pavement (PCI)",       group: "Risk & validation", file: "pavement.geojson",           on: false, icon: <IcRoad /> },
  { key: "basins",     label: "Catch basins",         group: "Drainage assets",   file: "merged_catch_basins.geojson", on: true,  icon: <IcDrop /> },
  { key: "storm_mains",label: "Storm mains",          group: "City stormwater net", file: "city_storm_mains.geojson", on: true,  icon: <IcPipe /> },
  { key: "laterals",   label: "CB laterals",          group: "City stormwater net", file: "city_laterals.geojson",    on: false, icon: <IcBranch /> },
  { key: "inlets",     label: "Storm inlets",         group: "City stormwater net", file: "city_inlets.geojson",      on: false, icon: <IcDot /> },
  { key: "outfalls",   label: "Outfalls",             group: "City stormwater net", file: "city_outfalls.geojson",    on: true,  icon: <IcOut /> },
  { key: "manholes",   label: "SW manholes",          group: "City stormwater net", file: "city_manholes.geojson",    on: false, icon: <IcDisc /> },
];
const GROUPS = ["Risk & validation", "Drainage assets", "City stormwater net"];

function Capture({ onMap }) { const m = useMap(); useEffect(() => onMap(m), [m, onMap]); return null; }
function CountUp({ value, dur = 1100, className }) {
  const reduce = useReducedMotion(); const [n, setN] = useState(reduce ? value : 0);
  useEffect(() => {
    if (reduce || value == null) { setN(value); return; }
    let raf, s; const tick = (t) => { if (!s) s = t; const p = Math.min((t - s) / dur, 1);
      setN(Math.round(value * (1 - Math.pow(1 - p, 3)))); if (p < 1) raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick); return () => cancelAnimationFrame(raf);
  }, [value, reduce, dur]); return <span className={className}>{n}</span>;
}
function Toggle({ icon, label, on, onClick }) {
  return (
    <div className="toggle" role="switch" aria-checked={on} tabIndex={0}
      onClick={onClick} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onClick()}>
      <span className="ico" style={{ color: "var(--accent)" }}>{icon}</span>
      <span className="lab">{label}</span>
      <span className={`sw ${on ? "on" : ""}`}><span className="knob" /></span>
    </div>);
}

export default function RainRiskMap() {
  const reduce = useReducedMotion();
  const [data, setData] = useState({});
  const [map, setMap] = useState(null);
  const [show, setShow] = useState(Object.fromEntries(LAYERS.map((l) => [l.key, l.on])));

  const requested = useRef(new Set());
  const ensure = (key, file) => {
    if (requested.current.has(key)) return;
    requested.current.add(key);
    fetch(`/data/${file}`).then((r) => r.json()).then((j) => setData((d) => ({ ...d, [key]: j }))).catch(() => {});
  };
  useEffect(() => {
    LAYERS.filter((l) => l.on).forEach((l) => ensure(l.key, l.file));
    ensure("boundary", "city_boundary.geojson");
    fetch("/data/validation.json").then((r) => r.json()).then((v) => setData((d) => ({ ...d, validation: v }))).catch(() => {});
  }, []);
  const toggle = (l) => { if (!show[l.key]) ensure(l.key, l.file); setShow((s) => ({ ...s, [l.key]: !s[l.key] })); };

  // fit to city boundary once
  useEffect(() => {
    if (map && data.boundary?.features?.length) {
      try {
        const ring = data.boundary.features[0].geometry.coordinates.flat(2);
        const lats = ring.filter((_, i) => i % 2 === 1), lons = ring.filter((_, i) => i % 2 === 0);
        map.fitBounds([[Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]], { padding: [20, 20] });
      } catch {}
    }
  }, [map, data.boundary]);

  const top10 = useMemo(() => {
    if (!data.ranking) return [];
    return [...data.ranking.features].sort((a, b) => b.properties.priority - a.properties.priority).slice(0, 10)
      .map((f) => { const r = f.geometry.coordinates[0];
        return { ...f.properties, lat: r.reduce((s, c) => s + c[1], 0) / r.length, lon: r.reduce((s, c) => s + c[0], 0) / r.length }; });
  }, [data.ranking]);

  const cm = (ll, st) => L.circleMarker(ll, st);
  const v = data.validation;
  const fade = (delay = 0) => reduce ? {} : { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] } };

  return (
    <>
      <MapContainer center={CENTER} zoom={13} zoomControl={false} preferCanvas>
        <Capture onMap={setMap} />
        <ZoomControl position="bottomright" />
        <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a> · drainage: City of Somerville · infra: Cyvl · 311: Somerville'
          subdomains="abcd" maxZoom={20} />

        {data.boundary && <GeoJSON data={data.boundary} interactive={false}
          style={{ color: "#7fd1ff", weight: 1.5, fill: false, dashArray: "4 4", opacity: 0.6 }} />}

        {show.complaints && data.complaints && (
          <GeoJSON data={data.complaints}
            style={(f) => ({ color: compColor(f.properties.complaints), weight: 0.6, fillColor: compColor(f.properties.complaints), fillOpacity: Math.min(0.12 + f.properties.complaints / 50, 0.5) })}
            onEachFeature={(f, l) => { const p = f.properties; l.bindPopup(miniPopup("311 flooding complaints", compColor(p.complaints), `<span class="mono">${p.complaints}</span> total · catch basin <span class="mono">${p.catch_basin || 0}</span> · sewer <span class="mono">${p.sewer || 0}</span> · flooding <span class="mono">${p.flooding || 0}</span>`)); }} />)}

        {show.ranking && data.ranking && (
          <GeoJSON data={data.ranking}
            style={(f) => ({ color: prioColor(f.properties.priority), weight: 0.4, fillColor: prioColor(f.properties.priority), fillOpacity: 0.4 })}
            onEachFeature={(f, l) => { const p = f.properties; l.bindPopup(rankingPopupHTML(p, data.ranking.features.length), { maxWidth: 300, minWidth: 230 }); }} />)}

        {show.pavement && data.pavement && (
          <GeoJSON data={data.pavement} style={(f) => ({ color: pciColor(f.properties.condition_score), weight: 2.5 })}
            onEachFeature={(f, l) => l.bindPopup(miniPopup("Pavement (PCI)", pciColor(f.properties.condition_score), `PCI <span class="mono">${f.properties.condition_score ?? "n/a"}</span> · ${f.properties.condition_label ?? "n/a"}`))} />)}

        {show.storm_mains && data.storm_mains && (
          <GeoJSON data={data.storm_mains} style={{ color: "#60a5fa", weight: 1.6, opacity: 0.7 }}
            onEachFeature={(f, l) => l.bindPopup(miniPopup("Storm gravity main", "#60a5fa", "City stormwater network"))} />)}
        {show.laterals && data.laterals && (
          <GeoJSON data={data.laterals} style={{ color: "#93c5fd", weight: 1, opacity: 0.6, dashArray: "3 3" }} />)}

        {show.inlets && data.inlets && (
          <GeoJSON data={data.inlets} pointToLayer={(f, ll) => cm(ll, { radius: 2.4, color: "#2dd4bf", weight: 0, fillColor: "#2dd4bf", fillOpacity: 0.7 })} />)}
        {show.manholes && data.manholes && (
          <GeoJSON data={data.manholes} pointToLayer={(f, ll) => cm(ll, { radius: 3, color: "#9fb3c8", weight: 0.5, fillColor: "#6c7d8f", fillOpacity: 0.75 })} />)}
        {show.outfalls && data.outfalls && (
          <GeoJSON data={data.outfalls} pointToLayer={(f, ll) => cm(ll, { radius: 6, color: "#fff", weight: 1.5, fillColor: "#f43f5e", fillOpacity: 0.9 })}
            onEachFeature={(f, l) => l.bindPopup(miniPopup("Storm discharge / outfall", "#f43f5e", "City stormwater network"))} />)}

        {show.basins && data.basins && (
          <GeoJSON data={data.basins}
            pointToLayer={(f, ll) => f.properties.source === "cyvl"
              ? cm(ll, { radius: 5.5, color: "#fde047", weight: 2, fillColor: "#38bdf8", fillOpacity: 0.95 })
              : cm(ll, { radius: 3.5, color: "#38bdf8", weight: 0.6, fillColor: "#1d4ed8", fillOpacity: 0.65 })}
            onEachFeature={(f, l) => l.bindPopup(f.properties.source === "cyvl"
              ? miniPopup("Catch basin", "#38bdf8", `<span class="mono">Cyvl</span> · verified`)
              : miniPopup("Catch basin", "#1d4ed8", "City GIS"))} />)}
      </MapContainer>

      <motion.header className="appbar glass" {...fade(0)}>
        <span className="brand-dot"><IcWaves style={{ color: "#06121f" }} /></span>
        <div><h1><span className="wordmark">FlowState</span><span className="badge">Somerville</span></h1>
          <p className="sub">Elevation-aware stormwater ponding intelligence — Cyvl + City network on LiDAR terrain, validated against 311</p></div>
        <span className="spacer" /><span className="pill"><span className="live" /> LIVE</span>
      </motion.header>

      <div className="rail">
        <motion.section className="card glass" {...fade(0.08)}>
          <h2>311 cross-check</h2>
          {v ? (<>
            <div className="kpi-grid">
              <div className="kpi"><div className="n amber"><CountUp value={v.footprint_complaints} /></div><div className="l">flooding/drainage 311 complaints citywide</div></div>
              <div className="kpi"><div className="n"><CountUp value={v.blocks_with_complaints} /></div><div className="l">census blocks with complaints</div></div>
            </div>
            <div className="cat-row">
              <div className="chip"><b><CountUp value={v.by_category?.catch_basin || 0} /></b>catch basin</div>
              <div className="chip"><b><CountUp value={v.by_category?.sewer || 0} /></b>sewer</div>
              <div className="chip"><b><CountUp value={v.by_category?.flooding || 0} /></b>flooding</div>
            </div>
            <p className="subtle">Honest read: 311 complaints are population-driven (residential), while the model flags
              physical low + under-drained spots. Citywide they <b>align</b>: the ranking is positively correlated with
              logged complaints (Spearman ρ={v.spearman_rho}), and {v.top10_validated} of the top 10 model cells fall in
              blocks with flooding complaints. So 311 partly corroborates the ranking, which also surfaces physically
              risky, under-reported areas. Source: Somerville 311 → 2020 census blocks.</p>
          </>) : <p className="subtle">Loading validation…</p>}
        </motion.section>

        <motion.section className="card glass" style={{ minHeight: 0, display: "flex", flexDirection: "column" }} {...fade(0.16)}>
          <h2>Top 10 risk locations (citywide)</h2>
          <div className="list">
            {top10.map((r, i) => (
              <motion.div key={r.rank} className="row" tabIndex={0} role="button"
                onClick={() => map && map.flyTo([r.lat, r.lon], 18, { duration: reduce ? 0 : 1.1 })}
                onKeyDown={(e) => e.key === "Enter" && map && map.flyTo([r.lat, r.lon], 18)}
                {...(reduce ? {} : { initial: { opacity: 0, x: -12 }, animate: { opacity: 1, x: 0 }, transition: { delay: 0.2 + i * 0.04 } })}>
                <span className="rank-badge" style={{ background: prioColor(r.priority) }}>{i + 1}</span>
                <span className="info"><b>priority {r.priority}</b><br />ponding {r.ponding_ft} ft · basins {r.basins}{r.mean_pci != null ? ` · PCI ${Math.round(r.mean_pci)}` : ""}</span>
              </motion.div>))}
            {!data.ranking && <p className="subtle">Loading…</p>}
          </div>
        </motion.section>
      </div>

      <motion.aside className="layers glass" {...fade(0.12)}>
        {GROUPS.map((g) => (
          <div key={g}>
            <h2 style={{ margin: "4px 4px 6px", fontSize: 10.5, letterSpacing: ".6px", textTransform: "uppercase", color: "var(--muted)" }}>{g}</h2>
            {LAYERS.filter((l) => l.group === g).map((l) => (
              <Toggle key={l.key} icon={l.icon} label={l.label} on={show[l.key]} onClick={() => toggle(l)} />
            ))}
          </div>))}
      </motion.aside>

      <motion.div className="legend glass" {...fade(0.2)}>
        <h3>Ponding-risk priority</h3>
        <div className="lr"><span className="swatch" style={{ background: "#f87171" }} />≥ 75 highest</div>
        <div className="lr"><span className="swatch" style={{ background: "#fb923c" }} />60–75 high</div>
        <div className="lr"><span className="swatch" style={{ background: "#fbbf24" }} />40–60 moderate</div>
        <div className="lr"><span className="swatch" style={{ background: "#34d399" }} />&lt; 40 lower</div>
        <h3 style={{ marginTop: 9 }}>Drainage</h3>
        <div className="lr"><span className="dot" style={{ background: "#38bdf8", boxShadow: "0 0 0 2px #fde047" }} />Cyvl basin (verified)</div>
        <div className="lr"><span className="dot" style={{ background: "#1d4ed8" }} />City basin</div>
        <div className="lr"><span className="line" style={{ background: "#60a5fa" }} />Storm main · <span className="dot" style={{ background: "#f43f5e", width: 9, height: 9 }} />outfall</div>
        <div className="lr"><span className="swatch" style={{ background: "#f59e0b", opacity: .6 }} />311 complaints (block)</div>
      </motion.div>
    </>
  );
}
