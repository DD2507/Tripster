from flask import Flask, request, jsonify
from flask_cors import CORS
from data import (
    # MOCK_HOTELS, MOCK_RESTAURANTS, # Can remove mocks if API is primary
    select_hotel, # Keep if using local hotel data as fallback/complement
    estimate_minimum_budget,
)
from ml import cluster_attractions_by_location, select_daily_attractions
from apis import (
    google_geocode_place,
    find_attractions_api,          # Use the refined attraction finder
    find_restaurants_in_budget_api, # Use the new restaurant finder
    google_hotels_search,          # Keep using this for hotels
)
import os
import sqlite3
import json
import math # For rounding up meals cost

# Initialize Flask App
app = Flask(__name__)
CORS(app)

# --- SQLite Setup (as before) ---
DB_PATH = os.path.join(os.path.dirname(__file__), 'tripster.db')

def ensure_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS itineraries (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.commit()
    finally:
        conn.close()

ensure_db()

def save_itinerary(payload: dict) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO itineraries (payload) VALUES (?)", (json.dumps(payload),))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()

def load_itinerary(itinerary_id: int) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT payload FROM itineraries WHERE id = ?", (itinerary_id,))
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row[0])
    finally:
        conn.close()

# --- Routes ---

@app.route('/', methods=['GET'])
def root():
    return jsonify({"message": "Tripster API running", "endpoints": ["/health", "/plan-trip", "/itinerary/<id>"]})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

@app.route('/itinerary/<int:itinerary_id>', methods=['GET'])
def get_itinerary(itinerary_id: int):
    data = load_itinerary(itinerary_id)
    if not data:
        return jsonify({"error": "not_found"}), 404
    return jsonify(data)

@app.route('/plan-trip', methods=['POST']) # Only POST makes sense here
def plan_trip():
    """Receives trip details, fetches data, generates plan, saves, and returns it."""
    
    trip_details = request.get_json()
    if not trip_details:
        return jsonify({"error": "invalid_request", "message": "Missing JSON body"}), 400
        
    print("✅ Received Trip Details:", trip_details)

    # --- Extract Input Parameters ---
    destination = trip_details.get('destination')
    days = int(trip_details.get('days', 3))
    budget = float(trip_details.get('budget', 0))
    people = int(trip_details.get('people', 1))
    # hotel_area = str(trip_details.get('hotelArea', 'any')) # Consider using later for hotel filtering
    veg_only = bool(trip_details.get('vegOnly', False))
    meals_per_day = int(trip_details.get('mealsPerDay', 2)) # Default to 2 (e.g., Lunch, Dinner)

    if not destination or days <= 0 or budget <= 0 or people <= 0:
         return jsonify({"error": "invalid_input", "message": "Missing or invalid destination, days, budget, or people."}), 400

    # --- Initialize Itinerary Structure ---
    itinerary = {
        "title": f"Your Awesome {days}-Day Trip to {destination.title()}",
        "budget_summary": { # Allocate budget (simple split, can be refined)
            "total_budget": budget,
            "accommodation": budget * 0.40,
            "food": budget * 0.25,
            "activities": budget * 0.20,
            "transport": budget * 0.15,
        },
        "minimum_budget": None,
        "disclaimer": "Estimates only. Actual costs vary by season, choice and availability.",
        "hotel": None,
        "daily_plan": [],
        "transport_advice": None,
        "activities_fee_estimated": 0, # Initialize
        "itinerary_id": None,
        "share_url": None
    }

    # --- Minimum Budget Check ---
    itinerary["minimum_budget"] = estimate_minimum_budget(days, people)
    try:
        total_min = float(itinerary["minimum_budget"]["total_min"])
        if budget < total_min:
            return jsonify({
                "error": "budget_too_low",
                "message": f"Minimum estimated budget is ₹{int(total_min):,} for {days} days and {people} people.",
                "minimum_budget": itinerary["minimum_budget"],
                "title": itinerary["title"],
            }), 422
    except (TypeError, ValueError, KeyError):
        print("[Warning] Could not parse minimum budget estimate.")
        pass # Continue even if min budget check fails

    # --- Geocode Destination ---
    geo_lat, geo_lng = None, None
    geo = google_geocode_place(destination)
    if geo and geo.get("status") == "ok":
        geo_lat, geo_lng = float(geo["lat"]), float(geo["lng"])
        print(f"Geocoded {destination} to ({geo_lat}, {geo_lng})")
    else:
        print(f"[Warning] Geocoding failed for {destination}: {geo.get('reason')}")
        # Could potentially return an error here if geocoding is essential
        # return jsonify({"error": "geocoding_failed", "message": f"Could not find location: {destination}"}), 400

    # --- Fetch Attractions ---
    attractions_for_city_raw = []
    if geo_lat and geo_lng:
        attractions_result = find_attractions_api(destination, geo_lat, geo_lng)
        if attractions_result.get("status") == "ok":
            attractions_for_city_raw = attractions_result.get("items", [])
    else:
        print("[Warning] Skipping attraction search due to missing coordinates.")

    # --- Map Attractions for ML ---
    attractions_for_ml = []
    if attractions_for_city_raw:
         mapped = []
         for place in attractions_for_city_raw:
             name = place.get("name", "Point of Interest")
             location = place.get("geometry", {}).get("location", {})
             lat_i, lng_i = location.get("lat"), location.get("lng")
             if lat_i is None or lng_i is None: continue

             # Estimate fee based on price_level if available (usually not for attractions)
             # More reliable fee estimation would need specific API calls or heuristics
             est_fee = 0 # Default free

             # Estimate duration based on place type
             types = place.get("types", [])
             duration = 2.0 # default
             if any(t in ["museum", "art_gallery", "zoo", "aquarium"] for t in types): duration = 2.5
             elif any(t in ["park", "amusement_park"] for t in types): duration = 3.0
             elif "shopping_mall" in types: duration = 1.5

             mapped.append({
                 "name": name,
                 "lat": float(lat_i), "lng": float(lng_i),
                 "est_fee": float(est_fee),
                 "duration_hours": float(duration),
                 "category": types[0] if types else "tourist_attraction",
                 "rating": place.get("rating") # Pass rating along
             })
         attractions_for_ml = mapped
    else:
         print("[Warning] No attractions found or geocoding failed; ML will use defaults if any.")


    # --- ML: Cluster and Select Daily Attractions ---
    clusters = cluster_attractions_by_location(days, attractions=attractions_for_ml)
    activities_days, activities_fees_total = select_daily_attractions(
        clusters=clusters,
        activities_budget_total=itinerary["budget_summary"]["activities"],
        num_days=days,
    )
    itinerary["activities_fee_estimated"] = round(activities_fees_total)

    # --- Hotel Search & Selection ---
    selected_hotel_details = None
    accommodation_budget_total = itinerary["budget_summary"]["accommodation"]
    budget_per_night = accommodation_budget_total / max(1, days)

    try:
        if geo_lat and geo_lng: # Use coords if available
            hotels_result = google_hotels_search(destination, lat=geo_lat, lng=geo_lng)
        else:
             hotels_result = google_hotels_search(destination) # Fallback to query only

        if hotels_result.get("status") == "ok" and hotels_result.get("items"):
            best_hotel_match = None
            min_price_diff = float('inf')

            potential_hotels = hotels_result.get("items", [])
            print(f"Found {len(potential_hotels)} potential hotels via API.")

            for hotel_place in potential_hotels[:15]: # Check top 15 results
                try:
                    name = hotel_place.get("name", "Hotel")
                    rating = float(hotel_place.get("rating", 3.0) or 3.0) # Ensure float, default 3.0
                    price_level = hotel_place.get("price_level") # Integer 0-4 or None

                    # Estimate price based on Google's price_level (Adjust this heuristic!)
                    estimated_per_night = 2500 # Base estimate
                    if price_level == 0: estimated_per_night = 1500 # Free (unlikely for hotel) -> budget
                    elif price_level == 1: estimated_per_night = 3000 # Inexpensive
                    elif price_level == 2: estimated_per_night = 5000 # Moderate
                    elif price_level == 3: estimated_per_night = 8000 # Expensive
                    elif price_level == 4: estimated_per_night = 12000 # Very Expensive

                    # Prioritize hotels within budget, then by rating
                    if estimated_per_night <= budget_per_night:
                         if best_hotel_match is None or rating > best_hotel_match["rating"]:
                            best_hotel_match = hotel_place
                            best_hotel_match["estimated_per_night"] = estimated_per_night # Store estimate
                    # Consider hotels slightly above budget if no in-budget found yet
                    elif best_hotel_match is None:
                        price_diff = estimated_per_night - budget_per_night
                        if price_diff < min_price_diff:
                            min_price_diff = price_diff
                            best_hotel_match = hotel_place # Tentative slightly over budget option
                            best_hotel_match["estimated_per_night"] = estimated_per_night

                except Exception as e:
                    print(f"[Warning] Error processing hotel '{hotel_place.get('name')}': {e}")
                    continue

            if best_hotel_match:
                 print(f"Selected hotel: {best_hotel_match['name']} (Rating: {best_hotel_match.get('rating')}, Est. Price/Night: {best_hotel_match['estimated_per_night']})")
                 address = best_hotel_match.get("formatted_address", destination)
                 area = address.split(",")[-2].strip() if "," in address and len(address.split(",")) > 1 else destination

                 selected_hotel_details = {
                     "name": best_hotel_match["name"],
                     "area": area,
                     "rating": best_hotel_match.get("rating"),
                     "price_per_night": best_hotel_match["estimated_per_night"],
                     "nights": days,
                     "estimated_total": best_hotel_match["estimated_per_night"] * max(1, days),
                 }
            else:
                 print("[Warning] No suitable hotel found via API within budget.")

    except Exception as e:
        print(f"[Error] Hotel search failed: {e}")

    # Fallback to local data if API fails or finds nothing suitable
    if not selected_hotel_details:
         print("Falling back to local hotel selection.")
         local_hotel = select_hotel(budget_per_night) # Assuming select_hotel uses local data
         if local_hotel:
             selected_hotel_details = {
                 "name": local_hotel["name"] + " (Local Suggestion)",
                 "area": local_hotel["area"], "rating": local_hotel["rating"],
                 "price_per_night": local_hotel["price_per_night"], "nights": days,
                 "estimated_total": local_hotel["price_per_night"] * max(1, days),
             }

    itinerary["hotel"] = selected_hotel_details


    # --- Fetch Top Restaurants (based on budget and location) ---
    fetched_restaurants = []
    
    # ******** THIS IS THE FIX *********
    max_price_level = 1 # Default: Inexpensive (FIX for UnboundLocalError)
    # **********************************

    # Use hotel location if available, else destination center
    search_lat = geo_lat
    search_lng = geo_lng
    if selected_hotel_details:
         # Try geocoding hotel address for better restaurant locality (optional optimization)
         hotel_geo = google_geocode_place(f"{selected_hotel_details['name']}, {selected_hotel_details['area']}")
         if hotel_geo and hotel_geo.get("status") == "ok":
             search_lat, search_lng = float(hotel_geo["lat"]), float(hotel_geo["lng"])
             print(f"Using hotel location ({search_lat},{search_lng}) for restaurant search.")
         else:
             print("Could not geocode hotel, using destination center for restaurants.")


    if search_lat and search_lng:
         food_budget_per_day = itinerary["budget_summary"]["food"] / max(1, days)
         avg_meal_cost_target = food_budget_per_day / max(1, meals_per_day) / max(1, people)

         # This block now overwrites the default max_price_level = 1
         if avg_meal_cost_target > 1500: max_price_level = 4 # Very Expensive
         elif avg_meal_cost_target > 700: max_price_level = 3 # Expensive
         elif avg_meal_cost_target > 300: max_price_level = 2 # Moderate
         # Note: The default of 1 (Inexpensive) is already set

         print(f"Target meal cost: {avg_meal_cost_target:.0f} -> Max Price Level: {max_price_level}")

         restaurants_result = find_restaurants_in_budget_api(
             lat=search_lat, lng=search_lng,
             radius_m=3000, # Search within 3km of center/hotel
             min_rating=4.0, # Minimum 4-star rating
             max_price_level=max_price_level,
             veg_only=veg_only
         )
         if restaurants_result.get("status") == "ok":
             fetched_restaurants = restaurants_result.get("items", [])
             print(f"Found {len(fetched_restaurants)} suitable restaurants via API.")
         else:
             print(f"[Warning] Restaurant API search failed: {restaurants_result.get('reason')}")
    else:
        print("[Warning] Skipping restaurant search due to missing coordinates.")


    # --- Generate Daily Plan ---
    used_restaurant_indices = set() # Track used restaurants

    for day_index in range(days):
        day_num = day_index + 1

        # --- Select Activities for the Day ---
        day_activities = []
        selected_attractions_today = activities_days[day_index] if day_index < len(activities_days) else []

        time_slot = 9 # Start activities at 9 AM
        for attraction in selected_attractions_today:
             hour = time_slot % 24
             am_pm = "AM" if hour < 12 else "PM"
             display_hour = hour if hour <= 12 else hour - 12
             if display_hour == 0: display_hour = 12

             day_activities.append({
                 "time": f"{display_hour}:00 {am_pm}",
                 "description": attraction["name"],
                 "type": "activity",
                 "est_fee": attraction.get("est_fee", 0),
                 "rating": attraction.get("rating") # Include rating if available
             })
             time_slot += math.ceil(attraction.get("duration_hours", 2)) # Use ceil to avoid fractional hours

        if not day_activities: # Fallback if no activities selected
             day_activities.append({"time": "10:00 AM", "description": f"Explore local area near hotel", "type": "sightseeing"})

        # --- Select Restaurants for the Day ---
        day_restaurants_suggestions = []
        meals_cost_estimate_day = 0
        available_restaurants = [r for i, r in enumerate(fetched_restaurants) if i not in used_restaurant_indices]

        for meal_index in range(meals_per_day):
             selected_rest_details = None
             if available_restaurants:
                 selected_rest = available_restaurants.pop(0)
                 original_index = fetched_restaurants.index(selected_rest)
                 used_restaurant_indices.add(original_index)
                 selected_rest_details = selected_rest
             
             # Determine meal type
             meal_type = "Meal"
             if meals_per_day == 1: meal_type = "Meal"
             elif meals_per_day == 2: meal_type = "Lunch" if meal_index == 0 else "Dinner"
             elif meals_per_day >= 3:
                 if meal_index == 0: meal_type = "Breakfast"
                 elif meal_index == 1: meal_type = "Lunch"
                 else: meal_type = "Dinner" # Handles 3rd meal and beyond

             # Estimate cost per person (Refined Heuristic)
             # This line caused the error; it's now safe because max_price_level has a default
             price_lvl = selected_rest_details.get('price_level') if selected_rest_details and selected_rest_details.get('price_level') is not None else max_price_level
             est_cost_person = 150 # Base for free/unknown/fallback
             if price_lvl == 1: est_cost_person = 350
             elif price_lvl == 2: est_cost_person = 700
             elif price_lvl == 3: est_cost_person = 1200
             elif price_lvl == 4: est_cost_person = 2000

             # Add suggestion to list
             if selected_rest_details:
                  day_restaurants_suggestions.append({
                      "name": selected_rest_details["name"],
                      "rating": selected_rest_details.get("rating"),
                      "type": meal_type,
                      "est_cost_person": est_cost_person,
                      "price_level": price_lvl
                  })
             else: # Fallback
                  day_restaurants_suggestions.append({
                      "name": f"Local {meal_type} Place (Budget)",
                      "rating": None, "type": meal_type,
                      "est_cost_person": est_cost_person, "price_level": price_lvl if price_lvl <=4 else None
                  })
             meals_cost_estimate_day += (est_cost_person * people)

        # Append day's plan
        plan = {
            "day": day_num,
            "activities": day_activities,
            "restaurants": day_restaurants_suggestions,
            "food_cost_estimated": math.ceil(meals_cost_estimate_day), # Round up cost
        }
        itinerary["daily_plan"].append(plan)


    # --- Transport Suggestion (same heuristic as before) ---
    try:
        transport_total = itinerary["budget_summary"]["transport"]
        per_day = max(0.0, transport_total / max(1, days))
        suggestion = { # Default
            "mode": "public-transit/auto", "per_day_estimate": round(per_day),
            "airport_transfer_estimate": 800,
            "notes": "Use metro/bus and short auto rides; ride-hailing for late hours.",
        }
        if per_day >= 1500: suggestion.update({"mode": "cab/ride-hailing primary", "airport_transfer_estimate": 1200, "notes": "Prefer ride-hailing (4–5 short trips). Consider 1-day car rental if needed."})
        elif per_day >= 800: suggestion.update({"mode": "mixed: transit + ride-hailing", "airport_transfer_estimate": 1000, "notes": "Transit for long hops; 2–3 cab rides/day for convenience."})
        elif per_day <= 300: suggestion.update({"mode": "mostly transit", "airport_transfer_estimate": 600, "notes": "Stick to buses/metro; walk between nearby sights."})
        itinerary["transport_advice"] = suggestion
    except Exception as e:
        print(f"[Error] Failed to generate transport advice: {e}")
        itinerary["transport_advice"] = {"notes": "Transport estimation failed."}


    # --- Save and Return Itinerary ---
    try:
        itinerary_id = save_itinerary(itinerary)
        itinerary["itinerary_id"] = itinerary_id
        # Use request.host_url to build the share URL dynamically
        base_url = request.host_url.rstrip('/')
        itinerary["share_url"] = f"{base_url}/itinerary/{itinerary_id}" # More robust URL generation
        print(f"✅ Itinerary generated and saved with ID: {itinerary_id}")
    except Exception as e:
         print(f"[Error] Failed to save itinerary: {e}")
         # Continue without saving if DB fails, but log error

    return jsonify(itinerary)


# --- Run Flask App ---
if __name__ == '__main__':
    # Ensure debug is False in production!
    app.run(debug=True, port=5000)