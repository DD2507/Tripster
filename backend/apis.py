from dotenv import load_dotenv
load_dotenv(override=True)

import os
import requests
import time # Import time for potential retries or delays if needed

# --- API Keys Configuration ---
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyDDXHMBEVEj6zIXZ8azNX4xncuyzrhOyCI")
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY") or GOOGLE_MAPS_API_KEY

# --- API Base URLs ---
GOOGLE_PLACES_BASE = "https://maps.googleapis.com/maps/api/place"
GOOGLE_GEOCODING_BASE = "https://maps.googleapis.com/maps/api/geocode"
GOOGLE_PLACES_NEW_BASE = "https://places.googleapis.com/v1"

# --- Helper Functions ---

def _make_request(url, params=None, json_body=None, headers=None, method="GET", timeout=15):
    """General function to make API requests with error handling."""
    try:
        if method == "GET":
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        elif method == "POST":
            resp = requests.post(url, json=json_body, headers=headers, timeout=timeout)
        else:
            return {"status": "error", "reason": "invalid_method"}

        # Handle rate limiting specifically if possible (429 status code)
        if resp.status_code == 429:
            print("[API Warning] Rate limit likely exceeded. Consider adding delays.")
            # Optionally add a retry mechanism here with time.sleep()
            return {"status": "error", "reason": f"HTTP_{resp.status_code}", "error_message": "Rate limit likely exceeded"}

        # For non-200 responses from Places API (New) or general errors
        if resp.status_code != 200:
            error_data = {}
            try:
                error_data = resp.json()
            except requests.exceptions.JSONDecodeError:
                pass # Body might not be JSON
            error_msg = error_data.get("error", {}).get("message", resp.reason)
            print(f"[API Error] Request Failed: HTTP_{resp.status_code} - {error_msg} URL: {resp.url}")
            return {"status": "error", "reason": f"HTTP_{resp.status_code}", "error_message": error_msg}

        # For Legacy API status checks (OK needed)
        is_legacy_api = GOOGLE_PLACES_BASE in url or GOOGLE_GEOCODING_BASE in url
        data = resp.json()

        if is_legacy_api and data.get("status") not in ["OK", "ZERO_RESULTS"]:
             print(f"[API Error] Legacy API Status Not OK: {data.get('status')} - {data.get('error_message', '')} URL: {resp.url}")
             return {"status": "error", "reason": data.get("status"), "error_message": data.get("error_message", "Legacy API status not OK")}

        return {"status": "ok", "data": data}

    except requests.exceptions.Timeout:
        print(f"[API Error] Request Timeout: {method} {url}")
        return {"status": "error", "reason": "timeout"}
    except requests.exceptions.RequestException as e:
        print(f"[API Error] Request Exception: {e}")
        return {"status": "error", "reason": str(e)}
    except Exception as e:
        print(f"[API Error] Unexpected Exception: {e}")
        return {"status": "error", "reason": f"unexpected: {str(e)}"}

# --- Geocoding ---
def google_geocode_place(place_name: str):
    """Geocode a place name to coordinates using Google Maps API."""
    if not GOOGLE_MAPS_API_KEY:
        return {"status": "disabled", "reason": "missing_api_key"}
    
    url = f"{GOOGLE_GEOCODING_BASE}/json"
    params = {"address": place_name, "key": GOOGLE_MAPS_API_KEY}
    result = _make_request(url, params=params, method="GET", timeout=12)
    
    if result["status"] == "ok":
        data = result["data"]
        if data.get("status") == "ZERO_RESULTS" or not data.get("results"):
            return {"status": "not_found", "reason": "ZERO_RESULTS"}
        
        first_result = data["results"][0]
        location = first_result["geometry"]["location"]
        return {
            "status": "ok",
            "lat": location["lat"],
            "lng": location["lng"],
            "name": first_result.get("formatted_address"),
            "place_id": first_result.get("place_id")
        }
    
    # Return error if Google API fails
    return result

# --- Legacy Places API Wrappers (Nearby, Text Search, Details) ---
def google_places_nearby(lat: float, lng: float, radius_m: int = 5000, place_type: str = "tourist_attraction", keyword: str | None = None):
    """Fetch nearby places using Google Places API (Legacy)."""
    if not GOOGLE_PLACES_API_KEY:
        return {"status": "disabled", "reason": "missing_api_key", "items": []}

    url = f"{GOOGLE_PLACES_BASE}/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius": radius_m,
        "type": place_type,
        "key": GOOGLE_PLACES_API_KEY
    }
    if keyword:
        params["keyword"] = keyword

    result = _make_request(url, params=params, method="GET")
    if result["status"] != "ok":
         # Add items key for consistency on error
        result["items"] = []
        return result 

    return {"status": "ok", "items": result["data"].get("results", [])}

def google_places_text_search(query: str, location: str | None = None, radius_m: int = 10000):
    """Search for places using Google Places Text Search API (Legacy)."""
    if not GOOGLE_PLACES_API_KEY:
        return {"status": "disabled", "reason": "missing_api_key", "items": []}

    url = f"{GOOGLE_PLACES_BASE}/textsearch/json"
    params = {"query": query, "key": GOOGLE_PLACES_API_KEY}
    if location:
        params["location"] = location # Expects "lat,lng" string
        params["radius"] = radius_m

    result = _make_request(url, params=params, method="GET")
    if result["status"] != "ok":
         result["items"] = []
         return result

    return {"status": "ok", "items": result["data"].get("results", [])}

def google_places_details(place_id: str):
    """Get detailed information about a place using Google Places Details API (Legacy)."""
    if not GOOGLE_PLACES_API_KEY:
        return {"status": "disabled", "reason": "missing_api_key"}

    url = f"{GOOGLE_PLACES_BASE}/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,rating,price_level,formatted_address,geometry,types,photos,user_ratings_total", # Added user_ratings_total
        "key": GOOGLE_PLACES_API_KEY
    }
    result = _make_request(url, params=params, method="GET", timeout=12)

    if result["status"] != "ok":
        return result # Return error

    # Return result key from data for consistency
    return {"status": "ok", "data": result["data"].get("result", {})}

# --- Places API (New) v1 Wrappers (Nearby, Text Search) ---

def _normalize_new_places_results(places_data: list) -> list:
    """Helper to convert Places API (New) results to a more legacy-like structure."""
    items = []
    for p in places_data:
        name = (p.get("displayName", {}) or {}).get("text")
        loc = (p.get("location", {}) or {})
        # Map new priceLevel enum string to integer
        price_level_map = {
             "PRICE_LEVEL_FREE": 0, "PRICE_LEVEL_INEXPENSIVE": 1, "PRICE_LEVEL_MODERATE": 2,
             "PRICE_LEVEL_EXPENSIVE": 3, "PRICE_LEVEL_VERY_EXPENSIVE": 4
        }
        price_level_str = p.get("priceLevel")
        price_level_int = price_level_map.get(price_level_str) if price_level_str else None

        if not name or not loc.get("latitude") or not loc.get("longitude"):
             continue # Skip if essential info is missing

        item = {
            "name": name,
            "geometry": {"location": {"lat": loc.get("latitude"), "lng": loc.get("longitude")}},
            "types": p.get("types", []),
            "rating": p.get("rating"),
            "user_ratings_total": p.get("userRatingCount"), # Map userRatingCount
            "price_level": price_level_int,
            "price_level_str": price_level_str, # Keep original string
            "formatted_address": p.get("formattedAddress"), # Added address
            "place_id": p.get("id", "").replace("places/","") # Added cleaned place ID
        }
        items.append(item)
    return items

def gplaces_new_nearby(lat: float, lng: float, radius_m: int = 8000, included_types: list | None = None, rank_preference: str = "POPULARITY", max_results: int = 20):
    """Search nearby using Google Places (New) API."""
    if not GOOGLE_PLACES_API_KEY:
        return {"status": "disabled", "reason": "missing_api_key", "items": []}
    
    url = f"{GOOGLE_PLACES_NEW_BASE}/places:searchNearby"
    headers = {
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.types,places.rating,places.userRatingCount,places.priceLevel"
    }
    body = {
        "maxResultCount": min(max_results, 20),
        "rankPreference": rank_preference,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius_m
            }
        }
    }
    if included_types:
        body["includedTypes"] = included_types
    if rank_preference == "DISTANCE" and not included_types:
        print("[API Warning] RankPreference.DISTANCE requires includedTypes. Using POPULARITY.")
        body["rankPreference"] = "POPULARITY"
    result = _make_request(url, json_body=body, headers=headers, method="POST")
    if result["status"] == "ok":
        normalized_items = _normalize_new_places_results(result["data"].get("places", []))
        return {"status": "ok", "items": normalized_items}
    # Return error if Google API fails
    result["items"] = []
    return result

def gplaces_new_text_search(query: str, lat: float | None = None, lng: float | None = None, radius_m: int = 12000, included_type: str | None = None, rank_preference: str = "RELEVANCE", max_results: int = 20):
    """Search using text query with Google Places (New) API."""
    if not GOOGLE_PLACES_API_KEY:
        return {"status": "disabled", "reason": "missing_api_key", "items": []}
    
    url = f"{GOOGLE_PLACES_NEW_BASE}/places:searchText"
    headers = {
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.types,places.rating,places.userRatingCount,places.priceLevel"
    }
    body = {
        "textQuery": query,
        "maxResultCount": min(max_results, 20),
        "rankPreference": rank_preference
    }
    if lat is not None and lng is not None:
        body["locationBias"] = {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_m}}
        if rank_preference == "DISTANCE" and "locationBias" not in body:
            print("[API Warning] RankPreference.DISTANCE requires locationBias/Restriction. Using RELEVANCE.")
            body["rankPreference"] = "RELEVANCE"
    if included_type:
        body["includedType"] = included_type
    result = _make_request(url, json_body=body, headers=headers, method="POST")
    if result["status"] == "ok":
        normalized_items = _normalize_new_places_results(result["data"].get("places", []))
        return {"status": "ok", "items": normalized_items}
    # Return error if Google API fails
    result["items"] = []
    return result


# --- Specific Search Functions (Hotels, Restaurants, Attractions) ---

def google_hotels_search(destination: str, lat: float | None = None, lng: float | None = None):
    """Search for hotels using Google Places API."""
    print(f"Searching hotels in: {destination}")
    query = f"hotels in {destination}"
    return gplaces_new_text_search(query, lat=lat, lng=lng, included_type="lodging")

def find_attractions_api(destination: str, lat: float, lng: float, radius_m: int = 10000, max_results: int = 40):
    """Searches for popular tourist spots using Google Places API."""
    print(f"Searching attractions near ({lat},{lng}) for {destination}")
    # Try Nearby Search first for tourist attractions, ranked by popularity
    nearby_result = gplaces_new_nearby(
        lat=lat, lng=lng, radius_m=radius_m,
        included_types=["tourist_attraction", "park", "museum", "landmark"],
        rank_preference="POPULARITY",
        max_results=max_results
    )
    items = nearby_result.get("items", [])

    # If Nearby Search yields few results, broaden with Text Search
    if len(items) < max_results // 2 :
        print("Nearby search yielded few results, trying Text Search for attractions...")
        text_result = gplaces_new_text_search(
            query=f"things to do in {destination}",
            lat=lat, lng=lng, radius_m=radius_m + 5000, # Slightly larger radius for text search
            rank_preference="RELEVANCE",
            max_results=max_results
        )
        text_items = text_result.get("items", [])
        # Combine and deduplicate results (simple dedupe by name)
        existing_names = {item['name'] for item in items}
        for item in text_items:
            if item['name'] not in existing_names:
                items.append(item)
                existing_names.add(item['name'])

    # Filter out potential non-attractions if needed (e.g., shops results from broad query)
    google_types = [
        "tourist_attraction", "park", "museum", "landmark", "point_of_interest",
        "zoo", "aquarium", "art_gallery", "amusement_park", "natural_feature",
        "place_of_worship", "historic_site"
    ]
    final_items = []
    for item in items:
        types = item.get("types", [])
        # Check if any type matches Google types
        matches = False
        for t in types:
            t_str = str(t).lower()
            if any(gt.lower() in t_str for gt in google_types):
                matches = True
                break
        if matches or not types:  # Include items with no types (they might still be valid)
            final_items.append(item)

    print(f"Found {len(final_items)} potential attractions.")
    return {"status": "ok", "items": final_items[:max_results]} # Return final filtered list


def find_restaurants_in_budget_api(lat: float, lng: float, radius_m: int = 3000, min_rating: float = 4.0, max_price_level: int = 4, veg_only: bool = False, max_results: int = 20):
    """Finds restaurants nearby, filtering by rating and price using Google Places API."""
    print(f"Searching restaurants near ({lat},{lng}), MaxPrice: {max_price_level}, MinRating: {min_rating}, VegOnly: {veg_only}")

    # Use Nearby Search (New) for restaurants
    nearby_result = gplaces_new_nearby(
        lat=lat, lng=lng, radius_m=radius_m,
        included_types=["restaurant"],
        rank_preference="POPULARITY",
        max_results=50
    )

    if nearby_result["status"] != "ok":
        return nearby_result # Return error

    all_restaurants = nearby_result.get("items", [])
    filtered_restaurants = []
    # Check if ratings are available
    has_ratings = any(r.get('rating') is not None for r in all_restaurants)

    for item in all_restaurants:
        rating = item.get("rating", 0.0) or 0.0
        price_level = item.get("price_level") # Integer 0-4 or None
        name = item.get("name", "")

        # Apply filters
        passes_rating = (rating >= min_rating) if has_ratings else True
        # Pass if price_level is None (unknown) or within budget
        passes_price = (price_level is None) or (price_level <= max_price_level)

        # Simple veg check (heuristic)
        is_likely_veg = False
        if veg_only and name:
             veg_keywords = ['veg', 'vegetarian', 'pure veg', 'shakahari', 'plant-based']
             if any(keyword in name.lower() for keyword in veg_keywords):
                 is_likely_veg = True
        passes_veg = (not veg_only) or is_likely_veg

        if passes_rating and passes_price and passes_veg:
            filtered_restaurants.append(item)

    # Sort by rating (descending), then by number of ratings (descending) as tie-breaker
    filtered_restaurants.sort(key=lambda x: (x.get('rating', 0.0) or 0.0, x.get('user_ratings_total', 0) or 0), reverse=True)

    print(f"Found {len(filtered_restaurants)} suitable restaurants after filtering.")
    return {"status": "ok", "items": filtered_restaurants[:max_results]} # Return top N results