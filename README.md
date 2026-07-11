# 🛰 SatTrack — Satellite Tracking & Communication Window Analyzer

A real-time satellite tracking and communication prediction system built in Python. Fetches live orbital data from the N2YO API, computes RF parameters (Doppler shift, Free Space Path Loss, link budget), predicts communication windows, and visualizes everything through both a console interface and an interactive web dashboard.

---

## ✨ Features

- **Live satellite tracking** — real-time position updates every 5 seconds
- **RF engineering calculations** — Doppler shift, FSPL, slant range, link budget
- **Communication window predictions** — AOS/LOS times, maximum elevation, pass duration
- **Interactive web dashboard** — live map, elevation profile, Doppler & FSPL history charts
- **Dynamic satellite switching** — enter any NORAD ID to track a different satellite
- **Console mode** — terminal dashboard with ground-track and radar plots
- **Reverse geocoding** — human-readable location names for satellite positions

---

## 📋 Prerequisites

- **Python 3.9 or higher**
- **pip** (Python package manager)
- **Internet connection** (for N2YO API calls)
- **N2YO API key** (free — register at [n2yo.com](https://www.n2yo.com/login/register.php))
- **GeoNames username** (free — register at [geonames.org](http://www.geonames.org/login))

---

## 🚀 Installation

### 1. Clone or extract the project
```bash
cd satellite_tracker-feature-web-dashboard
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure your `.env` file
Create a file named `.env` in the project root with the following content:

```env
# N2YO API Configuration
N2YO_API_KEY=your_actual_key_here

# Ground Station Coordinates (default: Bangalore, India)
GROUND_LAT=12.9716
GROUND_LON=77.5946
GROUND_ALT=920

# Carrier frequency in MHz (145.800 = ISS radio)
CARRIER_FREQ_MHZ=145.800

# Position batch size (seconds per API call)
POSITION_SECONDS=300

# GeoNames username for reverse geocoding
GEONAMES_USERNAME=your_geonames_username

# Optional — RF link budget parameters
TX_POWER_DBM=30.0
TX_ANTENNA_GAIN_DBI=2.15
RX_ANTENNA_GAIN_DBI=6.0
RX_SENSITIVITY_DBM=-120.0
```

> **Note:** The default tracked satellite is the International Space Station (NORAD 25544). You can change it at runtime via the dashboard — no need to set it in `.env`.

---

## ▶ Running the Project

### Option 1 — Web Dashboard (recommended)

```bash
python web/app.py
```

Then open your browser at **[http://localhost:5000](http://localhost:5000)**

**What you'll see:**
- Interactive Leaflet map with satellite position and ground track
- RF Link Quality card (Doppler, FSPL, slant range, shifted frequency)
- Link Budget card (received power, link margin, feasibility)
- Orbital State card (azimuth, elevation, velocity)
- Communication Window card (next pass timing)
- Elevation profile chart
- Doppler shift history chart
- FSPL history chart
- Satellite Selector to switch tracked satellites at runtime

Press `Ctrl+C` in the terminal to stop the server.

---

### Option 2 — Console Mode

```bash
python main.py
```

**What you'll see:**
- Terminal dashboard with live satellite telemetry
- Ground-track world map saved to `assets/ground_track.png`
- Sky radar plot saved to `assets/radar.png`
- Continuous updates every 5 seconds

Press `Ctrl+C` to stop.

---

## 🎯 Quick Start

For the fastest setup:

```bash
# 1. Install
pip install -r requirements.txt

# 2. Copy the .env template and edit it
cp .env.example .env
# (edit .env with your N2YO API key)

# 3. Run the web dashboard
python web/app.py

# 4. Open http://localhost:5000
```

---

## 🛰 Switching Satellites

Common NORAD IDs to try:

| Satellite | NORAD ID |
|---|---|
| International Space Station (ISS) | 25544 |
| Hubble Space Telescope | 20580 |
| Chinese Space Station (CSS) | 48274 |
| NOAA-18 | 28654 |
| NOAA-19 | 33591 |
| NOAA-20 | 43226 |

Enter the NORAD ID in the **Satellite Selector** panel on the dashboard, or use one of the quick preset buttons.

Find more satellite IDs at [n2yo.com](https://n2yo.com) or [celestrak.org](https://celestrak.org).

---

## 📁 Project Structure

```
satellite_tracker-feature-web-dashboard/
├── config.py                # Central configuration
├── main.py                  # Console entry point
├── requirements.txt         # Python dependencies
├── .env                     # Your secrets (create this)
├── assets/                  # Generated plots (ground track, radar)
├── modules/
│   ├── collector.py         # N2YO API client
│   ├── processor.py         # RF math engine (Doppler, FSPL, link budget)
│   ├── models.py            # Dataclasses
│   └── visualizer.py        # Matplotlib plots + console dashboard
├── utils/
│   ├── geocoder.py          # Reverse geocoding
│   ├── logger.py            # Logging setup
│   ├── time_utils.py        # Timezone helpers
│   └── validators.py        # Configuration validation
├── web/
│   ├── app.py               # Flask backend
│   └── templates/
│       └── index.html       # Web dashboard UI
└── tests/
    └── test_processor.py    # Unit tests
```

---

## 🧪 Running Tests

```bash
python -m pytest tests/
```

---

## ⚙ Configuration Details

| Setting | Default | Purpose |
|---|---|---|
| `N2YO_API_KEY` | — | Required for API access |
| `GROUND_LAT` | 12.9716 | Your latitude (decimal degrees) |
| `GROUND_LON` | 77.5946 | Your longitude (decimal degrees) |
| `GROUND_ALT` | 920 | Your altitude (metres) |
| `CARRIER_FREQ_MHZ` | 145.800 | Radio carrier frequency |
| `POSITION_SECONDS` | 300 | Positions fetched per API call |
| `TX_POWER_DBM` | 30.0 | Satellite transmit power |
| `RX_SENSITIVITY_DBM` | -120.0 | Your receiver sensitivity |

---

## 🐛 Troubleshooting

**"N2YO_API_KEY is not set"**
Add your API key to the `.env` file. Get one free at [n2yo.com](https://www.n2yo.com/login/register.php).

**"N2YO rate limit reached"**
Free tier allows 1000 calls/hour. Wait an hour or reduce polling frequency.

**"Link Insufficient" for close satellites**
The default TX power (30 dBm) and antenna gains are conservative. Adjust `TX_POWER_DBM`, `TX_ANTENNA_GAIN_DBI`, and `RX_ANTENNA_GAIN_DBI` in `.env` to match your actual hardware.

**Dashboard shows "No Signal" but Link Budget is Feasible**
This is normal — it means the satellite is below your horizon right now, but your gear is capable of receiving it when it rises. Wait for the next pass shown in the Communication Window card.

**Port 5000 already in use**
Edit the last line of `web/app.py` and change `port=5000` to another port like `5001`.

---

## 📊 Understanding the Dashboard

### RF Link Quality
Shows if the satellite is physically receivable *right now*:
- **Excellent / Good / Marginal** — satellite is above horizon
- **No Signal** — satellite is below horizon (blocked by Earth)

### Link Budget
Pure power math — shows if your equipment could theoretically close a link:
- **Link Feasible** — received power is above receiver sensitivity
- **Link Insufficient** — signal too weak to decode

### Doppler Shift
- **Positive (+Hz, green)** — satellite approaching (blue-shift)
- **Negative (−Hz, red)** — satellite receding (red-shift)
- **Zero** — closest approach point

### FSPL (Free Space Path Loss)
Signal loss due to distance and frequency:
- **Below 140 dB (blue)** — manageable
- **140–160 dB (yellow)** — marginal
- **Above 160 dB (red)** — high loss (typical for GEO satellites)

---

## 📚 Tech Stack

- **Python 3.9+**
- **Flask** — web backend
- **Leaflet.js** — interactive map
- **Matplotlib** — console plots
- **N2YO REST API** — satellite orbital data
- **GeoNames API** — reverse geocoding
- **python-dotenv** — environment configuration

---

## 📄 License

Educational project developed at RV College of Engineering.

---



---

## 🔗 Useful Links

- [N2YO API Documentation](https://www.n2yo.com/api/)
- [GeoNames](http://www.geonames.org/)
- [CelesTrak — Satellite Catalogs](https://celestrak.org/)
- [Leaflet.js](https://leafletjs.com/)
- [Flask Documentation](https://flask.palletsprojects.com/)
