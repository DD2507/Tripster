"""
Service layer for itinerary generation.
Integrates existing apis.py, data.py, and ml.py functionality.
"""
import sys
import os
import math

# Add parent directory to path to import existing modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data import (
    select_hotel,
    estimate_minimum_budget,
    get_catalog_for_destination,
    get_catalog_center,
    get_catalog_attractions,
    select_catalog_hotel,
    get_catalog_restaurants,
)
from ml import cluster_attractions_by_location, select_daily_attractions
from apis import (
    google_geocode_place,
    find_attractions_api,
    find_restaurants_in_budget_api,
    google_hotels_search,
)

def generate_itinerary_service(request_data: dict, username: str = "guest"):
    """
    Generates a travel itinerary based on request data.
    This is the main service function that coordinates all the data fetching and ML logic.
    """
    print(f"✅ Generating itinerary for user: {username}")
    print(f"Request data: {request_data}")
    
    # Extract input parameters
    destination = request_data.get('destination')
    days = int(request_data.get('days') or request_data.get('numberOfDays', 3))
    budget = float(request_data.get('budget', 0))
    people = int(request_data.get('people', 1))
    veg_only = bool(request_data.get('vegOnly', False))
    meals_per_day = int(request_data.get('mealsPerDay', 2))

    if not destination or days <= 0 or budget <= 0 or people <= 0:
        return {"error": "Missing or invalid destination, days, budget, or people."}

    # Initialize Itinerary Structure
    itinerary = {
        "title": f"Your Awesome {days}-Day Trip to {destination.title()}",
        "budget_summary": {
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
        "activities_fee_estimated": 0,
        "itinerary_id": None,
        "share_url": None
    }

    # Minimum Budget Check
    itinerary["minimum_budget"] = estimate_minimum_budget(days, people)
    try:
        total_min = float(itinerary["minimum_budget"]["total_min"])
        if budget < total_min:
            return {
                "error": "budget_too_low",
                "message": f"Minimum estimated budget is ₹{int(total_min):,} for {days} days and {people} people.",
                "minimum_budget": itinerary["minimum_budget"],
                "title": itinerary["title"],
            }
    except (TypeError, ValueError, KeyError):
        print("[Warning] Could not parse minimum budget estimate.")
        pass

    # Determine Destination Center (Catalog first, then Google Geocoding)
    geo_lat, geo_lng = None, None
    cat = get_catalog_for_destination(destination)
    if cat and get_catalog_center(destination):
        c = get_catalog_center(destination)
        try:
            geo_lat, geo_lng = float(c.get('lat')), float(c.get('lng'))
            print(f"Catalog center for {destination}: ({geo_lat},{geo_lng})")
        except Exception:
            geo_lat, geo_lng = None, None
    if geo_lat is None or geo_lng is None:
        geo = google_geocode_place(destination)
        if geo and geo.get("status") == "ok":
            geo_lat, geo_lng = float(geo["lat"]), float(geo["lng"])
            print(f"Geocoded {destination} to ({geo_lat}, {geo_lng})")
        else:
            print(f"[Warning] Geocoding failed for {destination}: {geo.get('reason') if isinstance(geo, dict) else 'unknown'}")

    # Fetch Attractions (Catalog first, then API)
    attractions_for_city_raw = []
    if cat:
        cat_items = get_catalog_attractions(destination, geo_lat, geo_lng)
        if cat_items:
            attractions_for_city_raw = cat_items
    if not attractions_for_city_raw and geo_lat and geo_lng:
        attractions_result = find_attractions_api(destination, geo_lat, geo_lng)
        if attractions_result.get("status") == "ok":
            attractions_for_city_raw = attractions_result.get("items", [])
    if not attractions_for_city_raw:
        print("[Warning] No attractions found from catalog or API.")

    # Map Attractions for ML
    attractions_for_ml = []
    if attractions_for_city_raw:
         mapped = []
         for place in attractions_for_city_raw:
             name = place.get("name", "Point of Interest")
             location = place.get("geometry", {}).get("location", {})
             lat_i, lng_i = location.get("lat"), location.get("lng")
             if lat_i is None or lng_i is None: continue

             est_fee = 0  # Default free

             # Estimate duration based on place type
             types = place.get("types", [])
             duration = 2.0  # default
             if any(t in ["museum", "art_gallery", "zoo", "aquarium"] for t in types): duration = 2.5
             elif any(t in ["park", "amusement_park"] for t in types): duration = 3.0
             elif "shopping_mall" in types: duration = 1.5

             mapped.append({
                 "name": name,
                 "lat": float(lat_i), "lng": float(lng_i),
                 "est_fee": float(est_fee),
                 "duration_hours": float(duration),
                 "category": types[0] if types else "tourist_attraction",
                 "rating": place.get("rating")
             })
         attractions_for_ml = mapped
    else:
         print("[Warning] No attractions found or geocoding failed; ML will use defaults if any.")

    # ML: Cluster and Select Daily Attractions
    clusters = cluster_attractions_by_location(days, attractions=attractions_for_ml)
    activities_days, activities_fees_total = select_daily_attractions(
        clusters=clusters,
        activities_budget_total=itinerary["budget_summary"]["activities"],
        num_days=days,
    )
    itinerary["activities_fee_estimated"] = round(activities_fees_total)

    # Hotel Search & Selection
    selected_hotel_details = None
    accommodation_budget_total = itinerary["budget_summary"]["accommodation"]
    budget_per_night = accommodation_budget_total / max(1, days)

    try:
        best_hotel_match = select_catalog_hotel(destination, budget_per_night)
        hotels_result = {"status": "skip"}
        if best_hotel_match is None:
            if geo_lat and geo_lng:
                hotels_result = google_hotels_search(destination, lat=geo_lat, lng=geo_lng)
            else:
                hotels_result = google_hotels_search(destination)

        if best_hotel_match is None and hotels_result.get("status") == "ok" and hotels_result.get("items"):
            best_hotel_match = None
            min_price_diff = float('inf')

            potential_hotels = hotels_result.get("items", [])
            print(f"Found {len(potential_hotels)} potential hotels via API.")

            for hotel_place in potential_hotels[:15]:
                try:
                    name = hotel_place.get("name", "Hotel")
                    rating = float(hotel_place.get("rating", 3.0) or 3.0)
                    price_level = hotel_place.get("price_level")

                    estimated_per_night = 2500
                    if price_level == 0: estimated_per_night = 1500
                    elif price_level == 1: estimated_per_night = 3000
                    elif price_level == 2: estimated_per_night = 5000
                    elif price_level == 3: estimated_per_night = 8000
                    elif price_level == 4: estimated_per_night = 12000

                    if estimated_per_night <= budget_per_night:
                        if best_hotel_match is None or rating > best_hotel_match["rating"]:
                            best_hotel_match = hotel_place
                            best_hotel_match["estimated_per_night"] = estimated_per_night
                    elif best_hotel_match is None:
                        price_diff = estimated_per_night - budget_per_night
                        if price_diff < min_price_diff:
                            min_price_diff = price_diff
                            best_hotel_match = hotel_place
                            best_hotel_match["estimated_per_night"] = estimated_per_night

                except Exception as e:
                    print(f"[Warning] Error processing hotel '{hotel_place.get('name')}': {e}")
                    continue

        if best_hotel_match:
            print(f"Selected hotel: {best_hotel_match['name']} (Rating: {best_hotel_match.get('rating')}, Est. Price/Night: {best_hotel_match.get('estimated_per_night', best_hotel_match.get('price_per_night'))})")
            address = best_hotel_match.get("formatted_address", destination)
            area = address.split(",")[-2].strip() if "," in address and len(address.split(",")) > 1 else destination

            selected_hotel_details = {
                "name": best_hotel_match["name"],
                "area": area,
                "rating": best_hotel_match.get("rating"),
                "price_per_night": best_hotel_match.get("estimated_per_night", best_hotel_match.get("price_per_night", 0)),
                "nights": days,
                "estimated_total": best_hotel_match.get("estimated_per_night", best_hotel_match.get("price_per_night", 0)) * max(1, days),
            }
        else:
            print("[Warning] No suitable hotel found in catalog or API within budget.")
    except Exception as e:
        print(f"[Error] Hotel selection failed: {e}")

    # Fallback to local data if API fails or finds nothing suitable
    if not selected_hotel_details:
         print("Falling back to local hotel selection.")
         local_hotel = select_hotel(budget_per_night)
         if local_hotel:
             selected_hotel_details = {
                 "name": local_hotel["name"] + " (Local Suggestion)",
                 "area": local_hotel["area"], "rating": local_hotel["rating"],
                 "price_per_night": local_hotel["price_per_night"], "nights": days,
                 "estimated_total": local_hotel["price_per_night"] * max(1, days),
             }

    itinerary["hotel"] = selected_hotel_details

    # Fetch Top Restaurants (based on budget and location)
    fetched_restaurants = []
    max_price_level = 1  # Default: Inexpensive

    # Use hotel location if available, else destination center
    search_lat = geo_lat
    search_lng = geo_lng
    if selected_hotel_details:
         is_local_hotel = isinstance(selected_hotel_details.get('name'), str) and 'Local Suggestion' in selected_hotel_details.get('name')
         if not is_local_hotel:
             hotel_geo = google_geocode_place(f"{selected_hotel_details['name']}, {selected_hotel_details['area']}")
             if hotel_geo and hotel_geo.get("status") == "ok":
                 search_lat, search_lng = float(hotel_geo["lat"]), float(hotel_geo["lng"])
                 print(f"Using hotel location ({search_lat},{search_lng}) for restaurant search.")
             else:
                 print("Could not geocode hotel, using destination center for restaurants.")
         else:
             print("Hotel is a local suggestion; using destination center for restaurants.")

    if search_lat and search_lng:
         food_budget_per_day = itinerary["budget_summary"]["food"] / max(1, days)
         avg_meal_cost_target = food_budget_per_day / max(1, meals_per_day) / max(1, people)

         if avg_meal_cost_target > 1500: max_price_level = 4
         elif avg_meal_cost_target > 700: max_price_level = 3
         elif avg_meal_cost_target > 300: max_price_level = 2

         print(f"Target meal cost: {avg_meal_cost_target:.0f} -> Max Price Level: {max_price_level}")

         # Catalog restaurants first, then API
         fetched_restaurants = get_catalog_restaurants(destination, veg_only=veg_only) or []
         if not fetched_restaurants:
             restaurants_result = find_restaurants_in_budget_api(
                 lat=search_lat, lng=search_lng,
                 radius_m=3000,
                 min_rating=4.0,
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

    # Generate Daily Plan
    used_restaurant_indices = set()

    for day_index in range(days):
        day_num = day_index + 1

        # Select Activities for the Day
        day_activities = []
        selected_attractions_today = activities_days[day_index] if day_index < len(activities_days) else []

        time_slot = 9  # Start activities at 9 AM
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
                 "rating": attraction.get("rating")
             })
             time_slot += math.ceil(attraction.get("duration_hours", 2))

        if not day_activities:
             day_activities.append({"time": "10:00 AM", "description": f"Explore local area near hotel", "type": "sightseeing"})

        # Select Restaurants for the Day
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
                 else: meal_type = "Dinner"

             price_lvl = selected_rest_details.get('price_level') if selected_rest_details and selected_rest_details.get('price_level') is not None else max_price_level
             est_cost_person = 150
             if price_lvl == 1: est_cost_person = 350
             elif price_lvl == 2: est_cost_person = 700
             elif price_lvl == 3: est_cost_person = 1200
             elif price_lvl == 4: est_cost_person = 2000

             if selected_rest_details:
                  day_restaurants_suggestions.append({
                      "name": selected_rest_details["name"],
                      "rating": selected_rest_details.get("rating"),
                      "type": meal_type,
                      "est_cost_person": est_cost_person,
                      "price_level": price_lvl
                  })
             else:
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
            "food_cost_estimated": math.ceil(meals_cost_estimate_day),
        }
        itinerary["daily_plan"].append(plan)

    # Transport Suggestion
    try:
        transport_total = itinerary["budget_summary"]["transport"]
        per_day = max(0.0, transport_total / max(1, days))
        airport_est = 800

        mode = "public transit + short autos"
        notes = "Use metro/bus for most hops. Take autos/ride-hailing for the last mile or late hours."
        if per_day >= 1500:
            mode = "ride-hailing/cabs as primary"
            airport_est = 1200
            notes = "Plan 4–5 cab rides per day. Consider a 1‑day car rental if doing far‑spread sights."
        elif per_day >= 800:
            mode = "mixed: transit + 2–3 cab rides/day"
            airport_est = 1000
            notes = "Transit for long hops; cabs for convenience or evenings."
        elif per_day <= 300:
            mode = "mostly transit + walking"
            airport_est = 600
            notes = "Stick to buses/metro and walk between nearby sights."

        if people >= 4 and per_day >= 800:
            mode = "group: cab/6‑seater or day rental"
            notes = "For 4+ people, shared cabs/day rental often cheaper than multiple singles."

        itinerary["transport_advice"] = {
            "mode": mode,
            "per_day_estimate": round(per_day),
            "airport_transfer_estimate": airport_est,
            "notes": notes,
        }
    except Exception as e:
        print(f"[Error] Failed to generate transport advice: {e}")
        itinerary["transport_advice"] = {"notes": "Transport estimation failed."}

    return itinerary

