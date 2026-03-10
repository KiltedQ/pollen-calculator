import { useState } from "react";
import "./index.css";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const STATUS_CONFIG = {
  pre_season:   { emoji: "🌱", color: "var(--blue)" },
  active:       { emoji: "🌿", color: "var(--green)" },
  peak:         { emoji: "🌸", color: "var(--amber)" },
  winding_down: { emoji: "🍃", color: "var(--orange)" },
  ended:        { emoji: "🍂", color: "var(--red-dim)" },
};

function LoadingDots() {
  return (
    <div className="loading-dots">
      <span /><span /><span />
    </div>
  );
}

function StatusBadge({ status, label }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pre_season;
  return (
    <div className="status-badge" style={{ "--badge-color": cfg.color }}>
      <span className="status-emoji">{cfg.emoji}</span>
      <span>{label}</span>
    </div>
  );
}

function PhaseCard({ phase, result, icon, delay }) {
  const isActual   = result?.date && result.date !== "Not reached" && !result.is_estimated;
  const isForecast = result?.date && result.date !== "Not reached" && result.is_estimated;
  const notReached = !result?.date || result.date === "Not reached";

  return (
    <div className="phase-card" style={{ animationDelay: `${delay}ms` }}>
      <div className="phase-icon">{icon}</div>
      <div className="phase-label">{phase}</div>
      <div className="phase-date" style={{ opacity: notReached ? 0.35 : 1 }}>
        {notReached ? "—" : result.date}
      </div>
      <div className="phase-meta">
        {isActual   && <span className="tag actual">● Observed</span>}
        {isForecast && result.confidence_days && <span className="tag estimated">~ ±{result.confidence_days}d est.</span>}
        {isForecast && !result.confidence_days && <span className="tag estimated">~ Projected</span>}
        {notReached && <span className="tag unknown">Unknown</span>}
      </div>
      <div className="phase-gdd">≥ {result?.gdd_threshold} GDD</div>
    </div>
  );
}

function GDDBar({ currentGdd }) {
  const max = 900;
  const currentPct = Math.min(100, (currentGdd / max) * 100);
  const markers = [
    { label: "Start", pct: (200 / max) * 100, cls: "marker-start" },
    { label: "Peak",  pct: (500 / max) * 100, cls: "marker-peak"  },
    { label: "End",   pct: 100,               cls: "marker-end"   },
  ];

  return (
    <div className="gdd-bar-wrap">
      <div className="gdd-bar-header">
        <span className="gdd-bar-title">GDD Progress</span>
        <span className="gdd-current-val">{currentGdd.toLocaleString()} °F·days accumulated</span>
      </div>
      <div className="gdd-bar-track">
        <div className="gdd-bar-fill" style={{ width: `${currentPct}%` }} />
        <div className="gdd-needle" style={{ left: `${currentPct}%` }}>
          <div className="needle-line" />
          <div className="needle-label">Today</div>
        </div>
        {markers.map(m => (
          <div key={m.label} className={`gdd-marker ${m.cls}`} style={{ left: `${m.pct}%` }} />
        ))}
      </div>
      <div className="gdd-bar-ticks">
        {markers.map(m => (
          <span key={m.label} style={{ left: `${m.pct}%` }}>{m.label}</span>
        ))}
      </div>
    </div>
  );
}

function FreshnessPanel({ freshness }) {
  const fmt = (str) => new Date(str + "T12:00:00Z")
    .toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

  return (
    <div className="freshness-panel">
      <div className="freshness-title">Data Sources</div>
      <div className="freshness-rows">
        <div className="freshness-row">
          <span className="freshness-dot observed" />
          <span className="freshness-key">Observed temps through</span>
          <span className="freshness-val">{fmt(freshness.historical_through)}</span>
        </div>
        <div className="freshness-row">
          <span className="freshness-dot forecast" />
          <span className="freshness-key">Forecast through</span>
          <span className="freshness-val">{fmt(freshness.forecast_through)}</span>
        </div>
        <div className="freshness-row">
          <span className="freshness-dot normals" />
          <span className="freshness-key">Projections based on</span>
          <span className="freshness-val">{freshness.normals_period}</span>
        </div>
        <div className="freshness-row dimmed">
          <span className="freshness-dot calc" />
          <span className="freshness-key">Calculated at</span>
          <span className="freshness-val">{freshness.calculated_at}</span>
        </div>
      </div>
    </div>
  );
}

function PreviousYearPanel({ prev }) {
  const phases = [
    { label: "Season Start", result: prev.season_start, icon: "🌿" },
    { label: "Peak Season",  result: prev.season_peak,  icon: "🌸" },
    { label: "Season End",   result: prev.season_end,   icon: "🍂" },
  ];

  return (
    <div className="prev-year-panel">
      <div className="prev-year-header">
        <span className="prev-year-title">{prev.year} — Previous Season</span>
        <span className="prev-year-gdd">{prev.final_gdd.toLocaleString()} total GDD</span>
      </div>
      <div className="prev-year-grid">
        {phases.map(({ label, result, icon }) => {
          const hasDate = result?.date && result.date !== "Not reached";
          return (
            <div className="prev-phase" key={label}>
              <span className="prev-phase-icon">{icon}</span>
              <span className="prev-phase-label">{label}</span>
              <span className="prev-phase-date" style={{ opacity: hasDate ? 1 : 0.35 }}>
                {hasDate ? result.date : "—"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function App() {
  const [zip, setZip] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (zip.length !== 5) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const resp = await fetch(`${API_BASE}/api/pollen-season`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ zip_code: zip }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Something went wrong");
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <div className="grain" />

      <header>
        <div className="header-pollen">
          {["✿","❋","✾","✤","❊"].map((s, i) => (
            <span key={i} className="spore" style={{ animationDelay: `${i * 0.7}s` }}>{s}</span>
          ))}
        </div>
        <h1>
          <span className="title-line">Pollen</span>
          <span className="title-line accent">Season</span>
          <span className="title-line">Calculator</span>
        </h1>
        <p className="subtitle">Temperature-driven phenology via Growing Degree Days</p>
      </header>

      <main>
        <form className="search-form" onSubmit={handleSubmit}>
          <div className="input-wrap">
            <input
              type="text"
              className="zip-input"
              placeholder="Enter ZIP code"
              value={zip}
              onChange={e => setZip(e.target.value.replace(/\D/g, "").slice(0, 5))}
              maxLength={5}
              inputMode="numeric"
              autoFocus
            />
            <button type="submit" className="submit-btn" disabled={zip.length !== 5 || loading}>
              {loading ? <LoadingDots /> : "Calculate"}
            </button>
          </div>
        </form>

        {error && (
          <div className="error-card"><span>⚠</span> {error}</div>
        )}

        {result && (
          <div className="results">
            <div className="location-header">
              <div className="location-left">
                <span className="location-name">
                  {result.city}{result.state ? `, ${result.state}` : ""}
                </span>
                <span className="location-year">{result.year} Season</span>
              </div>
              <StatusBadge status={result.current_status} label={result.status_label} />
            </div>

            <div className="phases-grid">
              <PhaseCard phase="Season Start" result={result.season_start} icon="🌿" delay={0} />
              <PhaseCard phase="Peak Season"  result={result.season_peak}  icon="🌸" delay={100} />
              <PhaseCard phase="Season End"   result={result.season_end}   icon="🍂" delay={200} />
            </div>

            <GDDBar currentGdd={result.current_gdd} />
            <FreshnessPanel freshness={result.data_freshness} />

            {result.previous_year && (
              <PreviousYearPanel prev={result.previous_year} />
            )}
          </div>
        )}

        {!result && !loading && !error && (
          <div className="explainer">
            <h2>How it works</h2>
            <div className="explainer-steps">
              <div className="step">
                <div className="step-num">01</div>
                <div className="step-text">Observed daily high/low temps are pulled from the Open-Meteo archive, updated daily with a ~2 day lag.</div>
              </div>
              <div className="step">
                <div className="step-num">02</div>
                <div className="step-text">A 7-day forecast extends the curve forward. Beyond that, 1991–2020 climate normals project remaining thresholds.</div>
              </div>
              <div className="step">
                <div className="step-num">03</div>
                <div className="step-text">GDD accumulates above 50°F from Feb 1. Observed dates are exact; projected dates show a confidence range.</div>
              </div>
            </div>
          </div>
        )}
      </main>

      <footer>
        <p>Growing Degree Day phenology · Weather via Open-Meteo · No API key required</p>
      </footer>
    </div>
  );
}
