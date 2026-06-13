"use client";
import { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, GeoJSON, LayersControl, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const CENTER = [42.39444, -71.08228];

const pciColor = (v) =>
  v == null ? "#7f8c99" : v >= 70 ? "#2ecc71" : v >= 55 ? "#f1c40f" : v >= 40 ? "#e67e22" : "#e74c3c";
const prioColor = (p) =>
  p >= 75 ? "#e74c3c" : p >= 60 ? "#e67e22" : p >= 40 ? "#f1c40f" : "#2ecc71";

function Capture({ onMap }) {
  const map = useMap();
  useEffect(() => onMap(map), [map, onMap]);
  return null;
}

async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path);
  return r.json();
}

export default function RainRiskMap() {
  const [data, setData] = useState(null);
  const [map, setMap] = useState(null);

  useEffect(() => {
    Promise.all(
      ["catch_basin", "manhole", "pavement", "ranking", "contours"].map((n) =>
        getJSON(`/data/${n}.geojson`).catch(() => ({ type: "FeatureCollection", features: [] }))
      )
    ).then(([catch_basin, manhole, pavement, ranking, contours]) =>
      setData({ catch_basin, manhole, pavement, ranking, contours })
    );
  }, []);

  const top10 = useMemo(() => {
    if (!data) return [];
    return [...data.ranking.features]
      .sort((a, b) => b.properties.priority - a.properties.priority)
      .slice(0, 10)
      .map((f) => {
        const ring = f.geometry.coordinates[0];
        const lon = ring.reduce((s, c) => s + c[0], 0) / ring.length;
        const lat = ring.reduce((s, c) => s + c[1], 0) / ring.length;
        return { ...f.properties, lat, lon };
      });
  }, [data]);

  const pointLayer = (latlng, style) => L.circleMarker(latlng, style);

  const basinPopup = (label) => (feat, layer) => {
    const p = feat.properties;
    let html = `<b>${label} ${p.feature_id ?? ""}</b>`;
    if (p.condition) html += `<br>condition: ${p.condition}`;
    if (p.image_url) html += `<br><img src="${p.image_url}" loading="lazy" alt="Cyvl photo"/>`;
    layer.bindPopup(html, { maxWidth: 260 });
  };

  return (
    <>
      <aside className="sidebar">
        <h2>Top 10 risk locations</h2>
        {top10.map((r) => (
          <div key={r.rank} className="rankrow" onClick={() => map && map.flyTo([r.lat, r.lon], 18)}>
            <span className="num" style={{ background: prioColor(r.priority) }}>
              {top10.indexOf(r) + 1}
            </span>
            <span className="meta">
              <b>priority {r.priority}</b>
              <br />
              ponding {r.ponding_m} m · basins {r.basins} · mh {r.manholes}
              {r.mean_pci != null ? ` · PCI ${Math.round(r.mean_pci)}` : ""}
            </span>
          </div>
        ))}
        {!data && <div style={{ color: "#8aa0b6", fontSize: 12 }}>Loading…</div>}
      </aside>

      <div className="mapwrap">
        <MapContainer center={CENTER} zoom={16} preferCanvas>
          <Capture onMap={setMap} />
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a> · infra: Cyvl · terrain: LiDAR'
            subdomains="abcd"
            maxZoom={20}
          />
          {data && (
            <LayersControl position="topright">
              <LayersControl.Overlay checked name="Ponding-risk ranking">
                <GeoJSON
                  data={data.ranking}
                  style={(f) => ({
                    color: prioColor(f.properties.priority),
                    weight: 1,
                    fillColor: prioColor(f.properties.priority),
                    fillOpacity: 0.42,
                  })}
                  onEachFeature={(f, layer) => {
                    const p = f.properties;
                    layer.bindPopup(
                      `<b>Priority ${p.priority}</b> (rank ${p.rank})<br>` +
                        `ponding ${p.ponding_m} m<br>basins ${p.basins} · manholes ${p.manholes}` +
                        (p.mean_pci != null ? `<br>mean PCI ${Math.round(p.mean_pci)}` : "") +
                        `<br><small>pond ${p.s_pond} · drainage-deficit ${p.s_basin_deficit} · pavement ${p.s_pci}</small>`
                    );
                  }}
                />
              </LayersControl.Overlay>

              <LayersControl.Overlay checked name="Pavement (PCI)">
                <GeoJSON
                  data={data.pavement}
                  style={(f) => ({ color: pciColor(f.properties.condition_score), weight: 3 })}
                  onEachFeature={(f, layer) => {
                    const p = f.properties;
                    layer.bindPopup(`<b>Pavement</b><br>PCI ${p.condition_score ?? "n/a"} (${p.condition_label ?? "n/a"})`);
                  }}
                />
              </LayersControl.Overlay>

              <LayersControl.Overlay checked name="Catch basins">
                <GeoJSON
                  data={data.catch_basin}
                  pointToLayer={(f, ll) =>
                    pointLayer(ll, { radius: 5, color: "#00d2ff", weight: 1, fillColor: "#00d2ff", fillOpacity: 0.85 })
                  }
                  onEachFeature={basinPopup("Catch basin")}
                />
              </LayersControl.Overlay>

              <LayersControl.Overlay checked name="Manholes">
                <GeoJSON
                  data={data.manhole}
                  pointToLayer={(f, ll) =>
                    pointLayer(ll, { radius: 4, color: "#9fb3c8", weight: 1, fillColor: "#6c7d8f", fillOpacity: 0.8 })
                  }
                  onEachFeature={basinPopup("Manhole")}
                />
              </LayersControl.Overlay>

              <LayersControl.Overlay name="Terrain contours (2 m)">
                <GeoJSON data={data.contours} style={{ color: "#b08968", weight: 0.7, opacity: 0.5 }} />
              </LayersControl.Overlay>
            </LayersControl>
          )}
        </MapContainer>

        <div className="legend">
          <h3>Ponding-risk priority</h3>
          <div className="row"><span className="sw" style={{ background: "#e74c3c" }} />≥ 75 (highest)</div>
          <div className="row"><span className="sw" style={{ background: "#e67e22" }} />60 – 75</div>
          <div className="row"><span className="sw" style={{ background: "#f1c40f" }} />40 – 60</div>
          <div className="row"><span className="sw" style={{ background: "#2ecc71" }} />&lt; 40</div>
          <h3 style={{ marginTop: 10 }}>Assets</h3>
          <div className="row"><span className="dot" style={{ background: "#00d2ff" }} />Catch basin</div>
          <div className="row"><span className="dot" style={{ background: "#6c7d8f" }} />Manhole</div>
          <div className="row"><span className="sw" style={{ height: 3, background: "#2ecc71" }} />Pavement (green=good PCI)</div>
        </div>
      </div>
    </>
  );
}
