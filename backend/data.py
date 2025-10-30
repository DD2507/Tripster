# Centralized mock data and helper functions (INR-based)

MOCK_HOTELS = [
    {"name": "City Comfort Inn", "price_per_night": 3600, "rating": 4.2, "area": "city center"},
    {"name": "Budget Stay Suites", "price_per_night": 2400, "rating": 3.9, "area": "suburbs"},
    {"name": "Seaside View Hotel", "price_per_night": 5600, "rating": 4.5, "area": "beachfront"},
    {"name": "Backpacker Lodge", "price_per_night": 1600, "rating": 3.5, "area": "old town"},
    {"name": "Business Plaza Hotel", "price_per_night": 4400, "rating": 4.1, "area": "downtown"},
]

MOCK_RESTAURANTS = [
    {"name": "Spice Route", "avg_cost_per_person": 800, "rating": 4.3, "type": "indian"},
    {"name": "Coastal Catch", "avg_cost_per_person": 1200, "rating": 4.5, "type": "seafood"},
    {"name": "Veggie Bowl", "avg_cost_per_person": 640, "rating": 4.1, "type": "vegetarian"},
    {"name": "Budget Bites", "avg_cost_per_person": 480, "rating": 3.8, "type": "fast-casual"},
    {"name": "Rooftop Diner", "avg_cost_per_person": 1440, "rating": 4.4, "type": "continental"},
    {"name": "Local Tiffins", "avg_cost_per_person": 400, "rating": 3.9, "type": "breakfast"},
]

def select_hotel(budget_per_night: float, preferred_area: str | None = None):
    preferred_area = (preferred_area or '').lower()
    within_budget = [h for h in MOCK_HOTELS if h["price_per_night"] <= budget_per_night]
    
    if within_budget:
        # If a preferred area is specified, try to find a match in that area
        if preferred_area and preferred_area != 'any':
            area_subset = [h for h in within_budget if h["area"].lower() == preferred_area]
            if area_subset:
                # Return best-rated (then cheapest) in that area
                return sorted(area_subset, key=lambda h: (h["rating"], -h["price_per_night"]), reverse=True)[0]
        
        # If no area preference or no match in preferred area, return best-rated in budget
        return sorted(within_budget, key=lambda h: (h["rating"], -h["price_per_night"]), reverse=True)[0]

    # If *nothing* is in budget, return None (or you could return the cheapest overall)
    # return sorted(MOCK_HOTELS, key=lambda h: h["price_per_night"])[0] # This would book the cheapest regardless of budget
    return None # This is safer, your app.py will handle it

def select_meals(budget_per_day: float, people: int, meals_per_day: int = 2, veg_only: bool = False):
    per_meal_cap = max(1.0, budget_per_day / max(1, meals_per_day)) / max(1, people)
    candidates = sorted(MOCK_RESTAURANTS, key=lambda r: r["rating"], reverse=True)
    
    if veg_only:
        veg_options = [r for r in candidates if r.get("type") == "vegetarian"]
        # Only use veg options if they exist, otherwise fall back to all candidates
        if veg_options:
            candidates = veg_options

    picks = []
    total_cost = 0.0
    
    # First pass: try to pick best-rated items under the per-meal cap
    for r in candidates:
        if len(picks) >= meals_per_day:
            break
        cost_this_meal = r["avg_cost_per_person"] * max(1, people)
        if r["avg_cost_per_person"] <= per_meal_cap:
            picks.append({
                "name": r["name"],
                "type": r["type"],
                "rating": r["rating"],
                "estimated_cost": cost_this_meal,
            })
            total_cost += cost_this_meal

    # Second pass: if we still need meals, fill with the cheapest available
    if len(picks) < meals_per_day:
        by_cost = sorted(MOCK_RESTAURANTS, key=lambda r: r["avg_cost_per_person"])
        if veg_only: # Re-filter for veg if needed
             veg_by_cost = [r for r in by_cost if r.get("type") == "vegetarian"]
             if veg_by_cost:
                 by_cost = veg_by_cost

        for r in by_cost:
            if len(picks) >= meals_per_day:
                break
            # Avoid adding the same restaurant twice
            if r["name"] not in [p["name"] for p in picks]:
                cost_this_meal = r["avg_cost_per_person"] * max(1, people)
                # Check if adding this meal keeps us within the *total* daily budget
                if (total_cost + cost_this_meal) <= budget_per_day:
                    picks.append({
                        "name": r["name"],
                        "type": r["type"],
                        "rating": r["rating"],
                        "estimated_cost": cost_this_meal,
                    })
                    total_cost += cost_this_meal
                    
    return picks, total_cost

def estimate_minimum_budget(days: int, people: int) -> dict:
    nights = max(1, days)
    cheapest_hotel = sorted(MOCK_HOTELS, key=lambda h: h["price_per_night"])[0]
    hotel_cost = cheapest_hotel["price_per_night"] * nights
    
    cheapest_two = sorted(MOCK_RESTAURANTS, key=lambda r: r["avg_cost_per_person"])[:2]
    per_day_meals = sum(r["avg_cost_per_person"] for r in cheapest_two) * max(1, people)
    food_cost = per_day_meals * nights
    
    transport_buffer = 400 * nights
    activities_buffer = 300 * nights
    
    total_min = hotel_cost + food_cost + transport_buffer + activities_buffer
    
    return {
        "hotel_min": hotel_cost,
        "food_min": food_cost,
        "transport_min": transport_buffer,
        "activities_min": activities_buffer,
        "total_min": total_min,
        "assumptions": {
            "hotel_used": cheapest_hotel["name"],
            "meals_per_day": 2,
            "people": people,
        }
    }