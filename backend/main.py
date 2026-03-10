from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import logging
from typing import Optional
from datetime import date, datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Pollen Season Calculator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GDD_BASE_TEMP = 50.0
GDD_START     = 200
GDD_PEAK      = 500
GDD_END       = 900


class ZipRequest(BaseModel):
    zip_code: str


class PhaseResult(BaseModel):
    date: Optional[str]
    gdd_threshold: int
    is_estimated: bool
    confidence_days: Optional[int]


class DataFreshness(BaseModel):
    historical_through: str
    forecast_through: str
    normals_period: str
    calculated_at: str


class PollenSeasonResult(BaseModel):
    zip_code: str
    city: str
    state: str
    year: int
    season_start: PhaseResult
    season_peak: PhaseResult
    season_end: PhaseResult
    current_gdd: float
    current_status: str
    status_label: str
    data_freshness: DataFreshness


class HistoricalResult(BaseModel):
    year: int
    season_start: PhaseResult
    season_peak: PhaseResult
    season_end: PhaseResult
    final_gdd: float


def calc_gdd(tmax: float, tmin: float) -> float:
    return max(0.0, ((tmax + tmin) / 2) - GDD_BASE_TEMP)


async def get_location(zip_code: str) -> dict:
    url = "https://nominatim.openstreetmap.org/search"
    params = {"postalcode": zip_code, "country": "US", "format": "json", "limit": 1}
    headers = {"User-Agent": "PollenSeasonCalculator/2.0"}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params, headers=headers)
        data = resp.json()
    if not data:
        raise HTTPException(status_code=404, detail=f"ZIP code {zip_code} not found")
    item = data[0]
    parts = item.get("display_name", "").split(",")
    return {
        "lat": float(item["lat"]),
        "lon": float(item["lon"]),
        "city": parts[0].strip() if parts else zip_code,
        "state": parts[2].strip() if len(parts) > 2 else "",
    }


async def get_historical_temps(lat: float, lon: float, start: str, end: str) -> list[dict]:
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start, "end_date": end,
        "daily": "temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit",
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        data = resp.json()
    if "daily" not in data:
        logger.error(f"Historical API error: {data}")
        raise HTTPException(status_code=502, detail="Could not fetch historical temperature data")
    result = []
    for d, tmax, tmin in zip(
        data["daily"]["time"],
        data["daily"]["temperature_2m_max"],
        data["daily"]["temperature_2m_min"]
    ):
        if tmax is not None and tmin is not None:
            result.append({"date": d, "tmax": tmax, "tmin": tmin, "source": "observed"})
    return result


async def get_forecast_temps(lat: float, lon: float) -> list[dict]:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit",
        "timezone": "auto",
        "forecast_days": 7,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        data = resp.json()
    if "daily" not in data:
        logger.warning("Forecast API returned no daily data")
        return []
    result = []
    for d, tmax, tmin in zip(
        data["daily"]["time"],
        data["daily"]["temperature_2m_max"],
        data["daily"]["temperature_2m_min"]
    ):
        if tmax is not None and tmin is not None:
            result.append({"date": d, "tmax": tmax, "tmin": tmin, "source": "forecast"})
    return result


async def get_climate_normals(lat: float, lon: float) -> dict:
    """
    Fetch 1991-2020 ERA5 reanalysis and average by MM-DD.
    Falls back to empty dict — caller must handle gracefully.
    """
    url = "https://climate-api.open-meteo.com/v1/climate"
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": "1991-01-01",
        "end_date": "2020-12-31",
        "daily": "temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit",
        "models": "ERA5",
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url, params=params)
            data = resp.json()
        if "daily" not in data:
            logger.warning(f"Climate normals API returned no daily data: {data}")
            return {}
        day_totals: dict[str, list] = {}
        for d, tmax, tmin in zip(
            data["daily"]["time"],
            data["daily"]["temperature_2m_max"],
            data["daily"]["temperature_2m_min"]
        ):
            if tmax is None or tmin is None:
                continue
            mmdd = d[5:]
            if mmdd not in day_totals:
                day_totals[mmdd] = []
            day_totals[mmdd].append((tmax, tmin))
        normals = {
            mmdd: {
                "tmax": sum(v[0] for v in vals) / len(vals),
                "tmin": sum(v[1] for v in vals) / len(vals),
            }
            for mmdd, vals in day_totals.items()
        }
        logger.info(f"Loaded {len(normals)} climate normal day-of-year entries")
        return normals
    except Exception as e:
        logger.error(f"Climate normals fetch failed: {e}")
        return {}


def build_simple_normals_fallback(lat: float) -> dict:
    """
    If the climate API fails, generate approximate sinusoidal normals
    based on latitude. Rougher but always works.
    Tmax peaks in July (~day 196), troughs in January.
    """
    import math
    normals = {}
    # Approximate annual mean and amplitude based on latitude
    mean_temp = max(20.0, 85.0 - abs(lat - 25) * 1.2)
    amplitude = max(15.0, abs(lat - 25) * 1.5)

    ref = date(2000, 1, 1)
    for day_num in range(366):
        d = ref + timedelta(days=day_num)
        if d.month == 2 and d.day == 29:
            continue
        mmdd = d.strftime("%m-%d")
        # Peak around day 196 (July 15)
        angle = 2 * math.pi * (day_num - 196) / 365
        avg = mean_temp + amplitude * math.cos(angle)
        normals[mmdd] = {"tmax": avg + 8, "tmin": avg - 8}
    return normals


def project_thresholds(
    current_gdd: float,
    from_date_str: str,
    normals: dict,
    year: int,
    thresholds: list[int],
) -> dict[int, dict]:
    """Walk forward from from_date using normals to estimate threshold crossing dates."""
    results = {}
    gdd = current_gdd
    d = datetime.strptime(from_date_str, "%Y-%m-%d").date() + timedelta(days=1)
    year_end = date(year, 12, 31)
    remaining = [t for t in thresholds if t > current_gdd]

    if not remaining:
        return results

    while d <= year_end and remaining:
        mmdd = d.strftime("%m-%d")
        norm = normals.get(mmdd)
        if norm:
            gdd += calc_gdd(norm["tmax"], norm["tmin"])
        crossed = [t for t in remaining if gdd >= t]
        for t in crossed:
            days_from_feb = max(1, (d - date(year, 2, 1)).days)
            confidence = max(3, int(days_from_feb * 0.05))
            results[t] = {"date": d.isoformat(), "confidence_days": confidence}
            remaining.remove(t)
        d += timedelta(days=1)

    # If still not found by year end, extend into next year
    if remaining:
        logger.warning(f"Thresholds {remaining} not reached by year end — extending projection")
        d = date(year, 12, 31) + timedelta(days=1)
        extend_end = date(year + 1, 8, 1)
        while d <= extend_end and remaining:
            mmdd = d.strftime("%m-%d")
            norm = normals.get(mmdd)
            if norm:
                gdd += calc_gdd(norm["tmax"], norm["tmin"])
            crossed = [t for t in remaining if gdd >= t]
            for t in crossed:
                results[t] = {"date": d.isoformat(), "confidence_days": 14}
                remaining.remove(t)
            d += timedelta(days=1)

    return results


def accumulate_season(daily_temps: list[dict]) -> dict:
    """Accumulate GDD from a full year's temps and find threshold crossings."""
    cumulative = 0.0
    phase_dates = {}
    last_date = None
    for entry in daily_temps:
        if entry["date"][5:7] == "01":
            continue
        cumulative += calc_gdd(entry["tmax"], entry["tmin"])
        last_date = entry["date"]
        for threshold in [GDD_START, GDD_PEAK, GDD_END]:
            if threshold not in phase_dates and cumulative >= threshold:
                phase_dates[threshold] = {
                    "date": entry["date"],
                    "is_estimated": entry.get("source") == "forecast",
                }
    return {"phase_dates": phase_dates, "final_gdd": cumulative, "last_date": last_date}


def determine_status(current_gdd: float, start_crossed: bool, peak_crossed: bool, end_crossed: bool):
    if end_crossed:
        return "ended", "Season Ended"
    if peak_crossed:
        return "winding_down", "Winding Down"
    if start_crossed:
        pct = (current_gdd - GDD_START) / (GDD_PEAK - GDD_START)
        if pct > 0.75:
            return "peak", "Near Peak"
        return "active", "Active Season"
    return "pre_season", "Pre-Season"


def fmt_date(d: str) -> str:
    return datetime.strptime(d, "%Y-%m-%d").strftime("%B %d, %Y")


def make_phase_result(threshold: int, phase_dates: dict, projected: dict) -> PhaseResult:
    if threshold in phase_dates:
        info = phase_dates[threshold]
        return PhaseResult(
            date=fmt_date(info["date"]),
            gdd_threshold=threshold,
            is_estimated=info["is_estimated"],
            confidence_days=3 if info["is_estimated"] else None,
        )
    if threshold in projected:
        info = projected[threshold]
        return PhaseResult(
            date=fmt_date(info["date"]),
            gdd_threshold=threshold,
            is_estimated=True,
            confidence_days=info["confidence_days"],
        )
    return PhaseResult(date=None, gdd_threshold=threshold, is_estimated=True, confidence_days=None)


@app.get("/")
def root():
    return {"status": "ok", "service": "Pollen Season Calculator v2"}


@app.post("/api/pollen-season")
async def calculate_pollen_season(req: ZipRequest):
    zip_code = req.zip_code.strip()
    if not zip_code.isdigit() or len(zip_code) != 5:
        raise HTTPException(status_code=400, detail="Please enter a valid 5-digit ZIP code")

    location = await get_location(zip_code)
    lat, lon = location["lat"], location["lon"]
    today = date.today()
    year = today.year
    calculated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # --- Current year ---
    hist_end = (today - timedelta(days=2)).isoformat()
    observed = await get_historical_temps(lat, lon, f"{year}-01-01", hist_end)
    historical_through = observed[-1]["date"] if observed else hist_end

    forecast = await get_forecast_temps(lat, lon)
    observed_dates = {e["date"] for e in observed}
    forecast = [e for e in forecast if e["date"] not in observed_dates]
    forecast_through = forecast[-1]["date"] if forecast else historical_through

    all_temps = sorted(observed + forecast, key=lambda x: x["date"])
    season = accumulate_season(all_temps)
    phase_dates = season["phase_dates"]
    cumulative_gdd = season["final_gdd"]
    last_date = season["last_date"] or hist_end

    # Project remaining thresholds
    remaining = [t for t in [GDD_START, GDD_PEAK, GDD_END] if t not in phase_dates]
    projected = {}
    normals = {}
    if remaining:
        normals = await get_climate_normals(lat, lon)
        if not normals:
            logger.warning("Climate API failed — using sinusoidal fallback normals")
            normals = build_simple_normals_fallback(lat)
        projected = project_thresholds(cumulative_gdd, last_date, normals, year, remaining)
        logger.info(f"Projected thresholds: {projected}")

    status, status_label = determine_status(
        cumulative_gdd,
        GDD_START in phase_dates,
        GDD_PEAK in phase_dates,
        GDD_END in phase_dates,
    )

    # --- Previous year ---
    prev_year = year - 1
    prev_observed = await get_historical_temps(lat, lon, f"{prev_year}-01-01", f"{prev_year}-12-31")
    prev_season = accumulate_season(prev_observed)

    # Previous year is complete so no projection needed; mark blanks as unknown
    prev_phase_dates = prev_season["phase_dates"]

    def make_prev_phase(threshold: int) -> PhaseResult:
        if threshold in prev_phase_dates:
            info = prev_phase_dates[threshold]
            return PhaseResult(
                date=fmt_date(info["date"]),
                gdd_threshold=threshold,
                is_estimated=False,
                confidence_days=None,
            )
        return PhaseResult(date="Not reached", gdd_threshold=threshold, is_estimated=False, confidence_days=None)

    return {
        "zip_code": zip_code,
        "city": location["city"],
        "state": location["state"],
        "year": year,
        "season_start": make_phase_result(GDD_START, phase_dates, projected).model_dump(),
        "season_peak":  make_phase_result(GDD_PEAK,  phase_dates, projected).model_dump(),
        "season_end":   make_phase_result(GDD_END,   phase_dates, projected).model_dump(),
        "current_gdd": round(cumulative_gdd, 1),
        "current_status": status,
        "status_label": status_label,
        "data_freshness": {
            "historical_through": historical_through,
            "forecast_through": forecast_through,
            "normals_period": "1991–2020 Climate Normals (ERA5)",
            "calculated_at": calculated_at,
        },
        "previous_year": {
            "year": prev_year,
            "season_start": make_prev_phase(GDD_START).model_dump(),
            "season_peak":  make_prev_phase(GDD_PEAK).model_dump(),
            "season_end":   make_prev_phase(GDD_END).model_dump(),
            "final_gdd": round(prev_season["final_gdd"], 1),
        },
    }
