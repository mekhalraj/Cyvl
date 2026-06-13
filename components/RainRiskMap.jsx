"use client";
import { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, GeoJSON, ZoomControl, useMap } from "react-leaflet";
import { motion, useReducedMotion } from "framer-motion";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const CENTER = [42.39444, -71.08228];
const prioColor = (p) => (p >= 75 ? "#f87171" : p >= 60 ? "#fb923c" : p >= 40 ? "#fbbf24" : "#34d399");
const pciColor = (v) =>
  v == null ? "#7f8c99" : v >= 70 ? "#34d399" : v >= 55 ? "#fbbf24" : v >= 40 ? "#fb923c" : "#f87171";
const compColor = (c) => (c >= 10 ? "#f59e0b" : c >= 5 ? "#fbbf24" : "#fcd34d");

/* ---- inline SVG icons (24x24 stroke) ---- */
const I = (d, fill) => (p) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill={fill ? "currentColor" : "none"}
    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}>{d}</svg>
);
const IcGrid = I(<><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /></>);
const IcRoad = I(<><path d="M4 19 8 5" /><path d="M20 19 16 5" /><path d="M12 6v2M12 11v2M12 16v2" /></>);
const IcDrop = I(<path d="M12 2.5S5 10 5 14a7 7 0 0 0 14 0c0-4-7-11.5-7-11.5Z" />);
const IcDisc = I(<><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /></>);
const IcAlert = I(<><path d="M12 9v4" /><path d="M12 17h.01" /><path d="M10.3 3.9 2 18a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /></>);
const IcWave = I(<><path d="M3 8c2-2 4-2 6 0s4 2 6 0 4-2 6 0" /><path d="M3 15c2-2 4-2 6 0s4 2 6 0 4-2 6 0" /></>);
const IcBolt = I(<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" />, true);

function Capture({ onMap }) { const m = useMap(); useEffect(() => onMap(m), [m, onMap]); return null; }

function CountUp({ value, dur = 1100, className }) {
  const reduce = useReducedMotion();
  const [n, setN] = useState(reduce ? value : 0);
  useEffect(() => {
    if (reduce || value == null) { setN(value); return; }
    let raf, start;
    const tick = (t) => {
      if (!start) start = t;
      const p = Math.min((t - start) / dur, 1);
      setN(Math.round(value * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, reduce, dur]);
  return <span className={className}>{n}</span>;
}

function Toggle({ icon, label, on, onClick }) {
  return (
    <div className="toggle" role="switch" aria-checked={on} tabIndex={0}
      onClick={onClick} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onClick()}>
      <span className="ico" style={{ color: "var(--accent)" }}>{icon}</span>
      <span className="lab">{label}</span>
      <span className={`sw ${on ? "on" : ""}`}><span className="knob" /></span>
    </div>
  );
}

async function getJSON(p, fb) { try { const r = await fetch(p); if (!r.ok) throw 0; return await r.json(); } catch { return fb; } }

export default function RainRiskMap() {
  const reduce = useReducedMotion();
  const [data, setData] = useState(null);
  const [map, setMap] = useState(null);
  const [show, setShow] = useState({
    complaints: true, ranking: true, pavement: true, basins: true, manholes: false, contours: false,
  });
  const toggle = (k) => setShow((s) => ({ ...s, [k]: !s[k] }));

  useEffect(() => {
    const empty = { type: "FeatureCollection", features: [] };
    Promise.all([
      getJSON("/data/ranking.geojson", empty), getJSON("/data/pavement.geojson", empty),
      getJSON("/data/catch_basin.geojson", empty), getJSON("/data/manhole.geojson", empty),
      getJSON("/data/contours.geojson", empty), getJSON("/data/complaints_blocks.geojson", empty),
      getJSON("/data/validation.json", null),
    ]).then(([ranking, pavement, catch_basin, manhole, contours, complaints, validation]) =>
      setData({ ranking, pavement, catch_basin, manhole, contours, complaints, validation }));
  }, []);

  const top10 = useMemo(() => {
    if (!data) return [];
    return [...data.ranking.features].sort((a, b) => b.properties.priority - a.properties.priority).slice(0, 10)
      .map((f) => {
        const r = f.geometry.coordinates[0];
        const lon = r.reduce((s, c) => s + c[0], 0) / r.length;
        const lat = r.reduce((s, c) => s + c[1], 0) / r.length;
        return { ...f.properties, lat, lon };
      });
  }, [data]);

  const cm = (latlng, st) => L.circleMarker(latlng, st);
  const photoPopup = (label) => (f, layer) => {
    const p = f.properties;
    let h = `<b>${label} <span class="mono">${p.feature_id ?? ""}</span></b>`;
    if (p.condition) h += `<br>condition: ${p.condition}`;
    if (p.image_url) h += `<br><img src="${p.image_url}" loading="lazy" alt="Cyvl street photo of asset"/>`;
    layer.bindPopup(h, { maxWidth: 260 });
  };

  const fade = (delay = 0) =>
    reduce ? {} : { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] } };
  const v = data?.validation;

  return (
    <>
      <MapContainer center={CENTER} zoom={16} zoomControl={false} preferCanvas>
        <Capture onMap={setMap} />
        <ZoomControl position="bottomright" />
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a> · infra: Cyvl · terrain: LiDAR · 311: City of Somerville'
          subdomains="abcd" maxZoom={20} />

        {data && show.complaints && (
          <GeoJSON data={data.complaints}
            style={(f) => ({ color: compColor(f.properties.complaints), weight: 0.8, fillColor: compColor(f.properties.complaints),
              fillOpacity: Math.min(0.15 + f.properties.complaints / 40, 0.5) })}
            onEachFeature={(f, l) => {
              const p = f.properties;
              l.bindPopup(`<b>311 flooding complaints: <span class="mono">${p.complaints}</span></b>`
                + `<br>catch basin ${p.catch_basin || 0} · sewer ${p.sewer || 0} · flooding ${p.flooding || 0}`
                + `<br><small class="mono">block ${String(p.geoid).slice(-7)}</small>`);
            }} />
        )}
        {data && show.contours && (
          <GeoJSON data={data.contours} style={{ color: "#b08968", weight: 0.7, opacity: 0.45 }} />
        )}
        {data && show.ranking && (
          <GeoJSON data={data.ranking}
            style={(f) => ({ color: prioColor(f.properties.priority), weight: 1,
              fillColor: prioColor(f.properties.priority), fillOpacity: 0.42 })}
            onEachFeature={(f, l) => {
              const p = f.properties;
              l.bindPopup(`<b>Priority <span class="mono">${p.priority}</span></b> (rank ${p.rank})`
                + `<br>ponding ${p.ponding_m} m · basins ${p.basins} · manholes ${p.manholes}`
                + (p.mean_pci != null ? `<br>mean PCI ${Math.round(p.mean_pci)}` : "")
                + `<br><small class="mono">pond ${p.s_pond} · deficit ${p.s_basin_deficit} · pav ${p.s_pci}</small>`);
            }} />
        )}
        {data && show.pavement && (
          <GeoJSON data={data.pavement}
            style={(f) => ({ color: pciColor(f.properties.condition_score), weight: 3 })}
            onEachFeature={(f, l) => l.bindPopup(
              `<b>Pavement</b><br>PCI <span class="mono">${f.properties.condition_score ?? "n/a"}</span> (${f.properties.condition_label ?? "n/a"})`)} />
        )}
        {data && show.manholes && (
          <GeoJSON data={data.manhole}
            pointToLayer={(f, ll) => cm(ll, { radius: 4, color: "#9fb3c8", weight: 1, fillColor: "#6c7d8f", fillOpacity: 0.8 })}
            onEachFeature={photoPopup("Manhole")} />
        )}
        {data && show.basins && (
          <GeoJSON data={data.catch_basin}
            pointToLayer={(f, ll) => cm(ll, { radius: 5, color: "#38bdf8", weight: 1, fillColor: "#38bdf8", fillOpacity: 0.85 })}
            onEachFeature={photoPopup("Catch basin")} />
        )}
      </MapContainer>

      {/* ---- header ---- */}
      <motion.header className="appbar glass" {...fade(0)}>
        <span className="brand-dot"><IcBolt style={{ color: "#06121f" }} /></span>
        <div>
          <h1>Somerville Rain-Risk</h1>
          <p className="sub">Cyvl infrastructure × LiDAR terrain — ponding-risk screen, East Somerville / Inner Belt</p>
        </div>
        <span className="spacer" />
        <span className="pill"><span className="live" /> LIVE</span>
      </motion.header>

      {/* ---- left rail: validation + top-10 ---- */}
      <div className="rail">
        <motion.section className="card glass" {...fade(0.08)}>
          <h2>311 Validation</h2>
          {v ? (
            <>
              <div className="kpi-grid">
                <div className="kpi"><div className="n amber"><CountUp value={v.footprint_complaints} /></div>
                  <div className="l">flooding/drainage 311 complaints in footprint</div></div>
                <div className="kpi"><div className="n"><CountUp value={v.top10_validated} />/10</div>
                  <div className="l">top-10 risk cells in blocks with complaints</div></div>
              </div>
              <div className="cat-row">
                <div className="chip"><b><CountUp value={v.by_category?.catch_basin || 0} /></b>catch basin</div>
                <div className="chip"><b><CountUp value={v.by_category?.sewer || 0} /></b>sewer</div>
                <div className="chip"><b><CountUp value={v.by_category?.flooding || 0} /></b>flooding</div>
              </div>
              <p className="subtle">
                Rank-order corr. ρ={v.spearman_rho} (block-level, n.s.) — complaints confirm the footprint
                as a real flooding hotspot; census-block resolution is too coarse to validate 50 m cell ordering.
                Source: City of Somerville 311, resolved to 2020 census blocks.
              </p>
            </>
          ) : <p className="subtle">Loading validation…</p>}
        </motion.section>

        <motion.section className="card glass" style={{ minHeight: 0, display: "flex", flexDirection: "column" }} {...fade(0.16)}>
          <h2>Top 10 risk locations</h2>
          <div className="list">
            {top10.map((r, i) => (
              <motion.div key={r.rank} className="row" tabIndex={0} role="button"
                onClick={() => map && map.flyTo([r.lat, r.lon], 18, { duration: reduce ? 0 : 1.1 })}
                onKeyDown={(e) => (e.key === "Enter") && map && map.flyTo([r.lat, r.lon], 18)}
                {...(reduce ? {} : { initial: { opacity: 0, x: -12 }, animate: { opacity: 1, x: 0 }, transition: { delay: 0.2 + i * 0.04 } })}>
                <span className="rank-badge" style={{ background: prioColor(r.priority) }}>{i + 1}</span>
                <span className="info"><b>priority {r.priority}</b><br />
                  ponding {r.ponding_m} m · basins {r.basins} · mh {r.manholes}
                  {r.mean_pci != null ? ` · PCI ${Math.round(r.mean_pci)}` : ""}</span>
              </motion.div>
            ))}
            {!data && <p className="subtle">Loading…</p>}
          </div>
        </motion.section>
      </div>

      {/* ---- layer panel ---- */}
      <motion.aside className="layers glass" {...fade(0.12)}>
        <h2 style={{ margin: "2px 4px 8px", fontSize: 11, letterSpacing: ".7px", textTransform: "uppercase", color: "var(--muted)" }}>Layers</h2>
        <Toggle icon={<IcAlert />} label="311 complaints" on={show.complaints} onClick={() => toggle("complaints")} />
        <Toggle icon={<IcGrid />} label="Ponding risk" on={show.ranking} onClick={() => toggle("ranking")} />
        <Toggle icon={<IcRoad />} label="Pavement (PCI)" on={show.pavement} onClick={() => toggle("pavement")} />
        <Toggle icon={<IcDrop />} label="Catch basins" on={show.basins} onClick={() => toggle("basins")} />
        <Toggle icon={<IcDisc />} label="Manholes" on={show.manholes} onClick={() => toggle("manholes")} />
        <Toggle icon={<IcWave />} label="Contours" on={show.contours} onClick={() => toggle("contours")} />
      </motion.aside>

      {/* ---- legend ---- */}
      <motion.div className="legend glass" {...fade(0.2)}>
        <h3>Ponding-risk priority</h3>
        <div className="lr"><span className="swatch" style={{ background: "#f87171" }} />≥ 75 highest</div>
        <div className="lr"><span className="swatch" style={{ background: "#fb923c" }} />60–75</div>
        <div className="lr"><span className="swatch" style={{ background: "#fbbf24" }} />40–60</div>
        <div className="lr"><span className="swatch" style={{ background: "#34d399" }} />&lt; 40</div>
        <h3 style={{ marginTop: 10 }}>Overlays</h3>
        <div className="lr"><span className="swatch" style={{ background: "#f59e0b", opacity: .6 }} />311 complaints (block)</div>
        <div className="lr"><span className="dot" style={{ background: "#38bdf8" }} />Catch basin</div>
        <div className="lr"><span className="line" style={{ background: "#34d399" }} />Pavement (good→poor)</div>
      </motion.div>
    </>
  );
}
