Smart Trip Planner (Tripster)

A minimal end-to-end starter for a smart trip planner with a Flask backend and a vanilla HTML/Tailwind frontend.

Prerequisites
- Windows 10/11 (PowerShell)
- Python 3.11 or 3.12 (use the embedded venv inside `backend/venv` or your own)
- Chrome/Edge for the frontend

1) Backend Setup

Open PowerShell and run:

```powershell
cd "C:\Users\Dhrupad\Desktop\Trip planner\backend"
# If you want to use the repo's venv (already present), activate it:
. .\venv\Scripts\Activate.ps1
# If you prefer your own venv, create it instead:
# python -m venv .venv; . .\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Set your Google Places API key (optional for now)
$env:GOOGLE_PLACES_API_KEY = "your-key-here"

# Run the server
python app.py
```

This starts the API at `http://127.0.0.1:5000`.

2) Frontend

Simply open `frontend/index.html` in your browser (double-click or drag into a tab).

The form will POST to `http://127.0.0.1:5000/plan-trip` and render the mock itinerary.

3) Project Structure

- `backend/app.py`: Flask app with a `/plan-trip` endpoint returning a mock itinerary
- `backend/requirements.txt`: Python dependencies
- `frontend/index.html`: Tailwind-based UI with a trip form

Notes
- The API key is read from the environment variable `GOOGLE_PLACES_API_KEY`.
- Next steps: add real data collection (Google Maps, TripAdvisor, Zomato), ML models (KMeans, ranking, knapsack), and persistence (MySQL/MongoDB).

ML features
- Basic KMeans clustering (via `backend/ml.py`) groups attractions by location across days.
- Greedy selector keeps daily attraction fees and time under caps.
- Mock hotels/restaurants live in `backend/data.py`. Replace with API/CSV data to go live.

Project synopsis (expanded)

Objectives
- Collect and unify travel data (attractions, hotels, restaurants, transport) for Indian destinations
- Clean and impute missing values; normalize ratings/cost/time
- Use ML to cluster attractions by geography/time and optimize day-wise plans within a user budget
- Provide a simple web UI and REST API; no bookings, only budget-fit suggestions and guidance

Problem statement
Travelers struggle to convert large lists of attractions into realistic day-wise plans that fit budget, time and preferences. Existing sites list places but rarely provide optimized itineraries with cost visibility. This system generates structured, budget-aware plans with a clear minimum-budget disclaimer.

High-level architecture
- Frontend: static `index.html` + Tailwind + `assets/app.js`
- Backend API: Flask (`app.py`), CORS enabled
- Data layer: mock datasets in `data.py` (replaceable by CSV/API)
- ML layer: `ml.py` (KMeans clustering + greedy budget/time selection)
- Optional external APIs: Google Maps/Places, TripAdvisor, Zomato/Swiggy, Booking providers (future)

Data sources (current and planned)
- Current: curated mock data for hotels/restaurants; sample attractions in `ml.py`
- Planned APIs: `Google Places`, `TripAdvisor`, `Zomato`, `OpenStreetMap` routing (for distance/time)
- Planned CSVs: city-wise attractions with lat/lng, expected fees, durations, seasonal notes

Preprocessing & imputation
- Normalize costs to INR; standardize durations to hours
- Missing fees/durations: median per category/city; optional linear regression with city and category features
- Deduplicate records by name+geo radius, unify rating scales to 1–5

ML components
- Clustering: KMeans groups attractions by proximity into N day-buckets
- Selection: greedy fit under per-day time (default 6h) and per-day activity-fee budget
- Roadmap: preference-aware ranking (weighted scores), knapsack optimizer for activities/food, city-aware priors

Budget model
- Split of total budget: 40% stay, 25% food, 20% activities, 15% transport (tunable)
- Minimum budget estimator: cheapest hotel × nights + two cheapest meals/day × people + daily transport and activity buffers
- Disclaimer: estimates only; vary by season, availability, and choices

API design
- `GET /` → service info
- `GET /health` → `{ status: ok }`
- `POST /plan-trip` → body: `{ destination, days, budget, people, travelerType }`
  - Response: title, `budget_summary`, `minimum_budget`, `hotel`, `daily_plan[]` (activities + restaurants), `activities_fee_estimated`

Frontend UX
- Hero form (destination, days, INR budget)
- Result cards: minimum budget banner, budget breakdown, suggested stay, day-wise activities and restaurants, cost hints

Non-functional requirements
- Runs locally without DB; CORS enabled for static file usage
- Extensible: drop-in CSV/API fetchers; replace mock with real data sources
- Privacy: no user auth or PII stored (current scope)

Testing & evaluation
- Unit: budget allocator, minimum-budget estimator, ML clustering selectors
- Scenario tests: budgets below/close to/above minimum; 1–7 day itineraries
- Metrics (initial): activity coverage per day, budget adherence (% over/under), average attraction rating

Risks & mitigations
- Data quality gaps → fallbacks, imputation, city-specific baselines
- API rate limits → local caching, scheduled harvests
- Route realism → integrate travel-time estimates (OSRM/Google Directions) in future

Roadmap (suggested)
1. City-aware datasets and priors (e.g., New Delhi, Goa, Bengaluru)
2. Preference filters (veg-only, cultural, adventure), and time windows
3. Knapsack-based optimizer for activities/food; add travel-time penalty
4. Persist itineraries (SQLite/MySQL) and simple share link
5. Real data integration (Places/TripAdvisor/Zomato) with caching layer

Synopsis alignment

PROJECT TITLE: SMART TRIP PLANNER

OBJECTIVE
- Design and develop a trip planning system that uses AI/ML to collect, clean, link travel data (popular places, hotels, restaurants) and automatically generate personalized itineraries within a user-defined budget.

PROBLEM STATEMENT
- Travelers struggle to balance budget, time, and preferences. Platforms list attractions but do not optimize costs or create structured day-wise plans. An intelligent system should integrate multiple data sources and apply ML models to suggest optimized itineraries.

PROPOSED SYSTEM
- User Interaction: input destination, days, budget, preferences (login planned as future work).
- Data Collection: fetch from APIs/datasets (attractions, hotels, restaurants, transport).
- AI/ML Processing: clean and impute missing data (entry fees, hotel prices); cluster and select.
- Itinerary Generation: customized, day‑wise plan within budget, with minimum‑budget guidance.

METHODOLOGY
- Data Collection: Google Maps/Places, TripAdvisor, Zomato; CSVs for attractions/hotels/restaurants.
- Preprocessing: handle missing values (median/regression), normalize ratings/costs/time.
- Models: KMeans for clustering, ranking/recommendation for picks, greedy/knapsack for budget.
- Generation: assign attractions/hotels/restaurants per day; optimize order/route (future routing).

APPLICATIONS
- Individual travelers planning on limited budgets
- Travel agencies offering automated plans
- Students/young travelers seeking affordable vacations

TOOLS AND TECHNOLOGIES
- Programming Languages: Python (backend), JavaScript (frontend)
- Libraries: Pandas, NumPy, Scikit‑learn (ML models)
- Frameworks: Flask (current), React/Angular (future UI options)
- Database: MySQL / MongoDB (planned; current version is stateless)
- APIs: Google Maps/Places, TripAdvisor, Booking.com, Zomato (planned integrations)

TEAM
- 4NI23CS028 ARUN V — 2023cs_arunv_a@nie.ac.in 
- 4NI23CS052 DHRUPAD S — 2023cs_dhrupadsuresha_a@nie.ac.in
- 4NI23CS044 CHINMAYA PUTTASWAMY — 2023cs_chinmayaputtaswamy_a@nie.ac.in 
- 4NI23CS047 DEEKSHITH KUMAR K — 2023cs_deekshithkumark_a@nie.ac.in

Current status vs. planned
- Implemented: Flask API, INR budget logic, minimum‑budget estimator, hotel/restaurant budget picks, ML clustering selector for attractions, frontend form/UI.
- Planned: user login, persistent DB (MySQL/MongoDB), real API integrations (Places/TripAdvisor/Zomato/Booking), preference filters, routing/time windows, knapsack optimizer, shareable itineraries.

