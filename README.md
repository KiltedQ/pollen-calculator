# 🌿 Pollen Season Calculator

A containerized web application that predicts pollen season **start, peak, and end dates** for any US ZIP code using **Growing Degree Day (GDD)** temperature math.

## How It Works

Plants don't track calendar dates — they track accumulated heat. This app uses the **Growing Degree Day** model:

```
GDD per day = max(0, ((T_max + T_min) / 2) - 50°F)
```

GDD accumulates starting February 1st each year. Pollen season phases are triggered at:

| Phase        | GDD Threshold |
|--------------|---------------|
| Season Start | 200 GDD       |
| Peak Season  | 500 GDD       |
| Season End   | 900 GDD       |

Temperature data is sourced from [Open-Meteo](https://open-meteo.com/) (free, no API key required).
Location lookup uses [Nominatim/OpenStreetMap](https://nominatim.org/) (free, no API key required).

---

## Stack

| Layer     | Technology        |
|-----------|-------------------|
| Frontend  | React + Vite      |
| Backend   | FastAPI (Python)  |
| Container | Docker Compose    |
| Web server| Nginx             |

---

## Quick Start

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) and Docker Compose installed

### Run

```bash
git clone <your-repo>
cd pollen-calculator
docker compose up --build
```

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### Stop

```bash
docker compose down
```

---

## Development (without Docker)

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server runs at http://localhost:5173 and proxies API calls to port 8000.

---

## API

### `POST /api/pollen-season`

**Request:**
```json
{ "zip_code": "90210" }
```

**Response:**
```json
{
  "zip_code": "90210",
  "city": "Beverly Hills",
  "state": "California",
  "year": 2024,
  "season_start": "February 14, 2024",
  "season_peak": "March 28, 2024",
  "season_end": "May 22, 2024",
  "gdd_start": 200,
  "gdd_peak": 500,
  "gdd_end": 900,
  "method": "Growing Degree Days (GDD), base 50°F",
  "current_gdd": 734.2,
  "current_date": "2024-07-15"
}
```

---

## Notes

- The app uses the **current year** if we're past April; otherwise it uses the **previous year** to ensure full temperature data is available.
- The 50°F base temperature is a commonly used standard for general vegetation phenology.
- GDD thresholds are based on published phenological research for temperate North American climates.
