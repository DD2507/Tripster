Project layout (backend)

- app/                       Python package exposing the Flask app instance
- run.py                     Local entrypoint to run the server
- static_catalog.json        Curated offline data (destinations, attractions, hotels, restaurants)
- data.py                    Local data utilities and catalog helpers
- ml.py                      Clustering and selection logic for itinerary
- apis.py                    (Optional) API helpers; currently not used after offline mode switch
- requirements.txt           Backend Python dependencies
- .env                       Environment variables (not committed)
- tripster.db                SQLite database (generated at runtime)

Environment (.env)

# GEOAPIFY_API_KEY removed - using Google APIs only
OPENWEATHERMAP_API_KEY=      # optional
# Leave Google keys blank to avoid usage
GOOGLE_MAPS_API_KEY=
GOOGLE_PLACES_API_KEY=

Run locally

Windows PowerShell

python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py

Notes

- The app now uses the static catalog by default for center, attractions, hotels, and restaurants.
- Extend backend/static_catalog.json to cover more destinations.
- The existing /plan-trip, /itinerary/<id>, /health endpoints remain the same.
