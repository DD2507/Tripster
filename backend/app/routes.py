from flask import Blueprint, request, jsonify
from . import mongo, bcrypt # Import shared extensions
from pymongo.errors import DuplicateKeyError
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from bson import ObjectId
from .services import generate_itinerary_service # Import our service function

# --- Authentication Blueprint ---
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/signup', methods=['POST'])
def signup():
    """Registers a new user."""
    if not hasattr(mongo, 'db') or mongo.db is None:
        return jsonify({"success": False, "message": "Authentication disabled. MongoDB not configured."}), 503
    
    data = request.get_json()

    if not data or not data.get('username') or not data.get('email') or not data.get('password'):
        return jsonify({"success": False, "message": "Missing username, email, or password"}), 400

    username = data['username']
    email = data['email']
    password = data['password']

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

    try:
        user_id = mongo.db.users.insert_one({
            'username': username,
            'email': email,
            'password': hashed_password
        }).inserted_id
        print(f"User created with ID: {user_id}")
        return jsonify({"success": True, "message": "User registered successfully!"}), 201

    except DuplicateKeyError as e:
        error_field = "Unknown field"
        if 'username' in str(e):
             error_field = "Username"
        elif 'email' in str(e):
             error_field = "Email"
        return jsonify({"success": False, "message": f"{error_field} is already taken!"}), 400

    except Exception as e:
        print(f"Error during signup: {e}")
        return jsonify({"success": False, "message": "An error occurred during registration."}), 500

@auth_bp.route('/signin', methods=['POST'])
def signin():
    """Authenticates a user and returns a JWT."""
    if not hasattr(mongo, 'db') or mongo.db is None:
        return jsonify({"success": False, "message": "Authentication disabled. MongoDB not configured."}), 503
    
    data = request.get_json()

    if not data or not data.get('username') or not data.get('password'):
        return jsonify({"success": False, "message": "Missing username or password"}), 400

    username = data['username']
    password = data['password']

    user = mongo.db.users.find_one({'username': username})

    if user and bcrypt.check_password_hash(user['password'], password):
        user_id_str = str(user['_id'])
        access_token = create_access_token(identity=user_id_str)
        return jsonify({"success": True, "accessToken": access_token}), 200
    else:
        return jsonify({"success": False, "message": "Invalid username or password"}), 401

# --- Itinerary Blueprint ---
itinerary_bp = Blueprint('itinerary', __name__)

@itinerary_bp.route('/generate', methods=['POST'])
@jwt_required() # Protect this route
def generate_plan():
    """Generates a travel itinerary, requires JWT authentication."""
    if not hasattr(mongo, 'db') or mongo.db is None:
        return jsonify({"success": False, "message": "Authentication disabled. MongoDB not configured."}), 503
    
    # Get user ID from the JWT token
    current_user_id = get_jwt_identity()
    user = mongo.db.users.find_one({'_id': ObjectId(current_user_id)})

    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    request_data = request.get_json()
    if not request_data:
        return jsonify({"success": False, "message": "Missing JSON body"}), 400
    
    destination = request_data.get('destination') or request_data.get('destination')
    days = request_data.get('numberOfDays') or request_data.get('days')
    budget = request_data.get('budget')
    people = request_data.get('people', 1)
    
    if not destination or not days or budget is None:
        return jsonify({"success": False, "message": "Missing destination, days/numberOfDays, or budget"}), 400

    normalized_request = {
        'destination': destination,
        'days': int(days),
        'numberOfDays': int(days),
        'budget': float(budget),
        'people': int(people),
        'vegOnly': request_data.get('vegOnly', False),
        'mealsPerDay': request_data.get('mealsPerDay', 2),
        'preferences': request_data.get('preferences', []),
        'startDate': request_data.get('startDate'),
        'originCity': request_data.get('originCity', 'Delhi'),
    }

    result = generate_itinerary_service(normalized_request, user['username'])

    if "error" in result:
        return jsonify({"success": False, "message": result["error"]}), 500
    else:
        return jsonify({"success": True, **result}), 200

@itinerary_bp.route('/generate-public', methods=['POST'])
def generate_plan_public():
    """Generates a travel itinerary without authentication (for backward compatibility)."""
    request_data = request.get_json()
    if not request_data:
        return jsonify({"error": "invalid_request", "message": "Missing JSON body"}), 400
    
    # Normalize request data
    destination = request_data.get('destination')
    days = request_data.get('days') or request_data.get('numberOfDays')
    budget = request_data.get('budget')
    people = request_data.get('people', 1)
    
    if not destination or not days or budget is None:
        return jsonify({"error": "invalid_input", "message": "Missing destination, days, or budget"}), 400

    normalized_request = {
        'destination': destination,
        'days': int(days),
        'numberOfDays': int(days),
        'budget': float(budget),
        'people': int(people),
        'vegOnly': request_data.get('vegOnly', False),
        'mealsPerDay': request_data.get('mealsPerDay', 2),
        'preferences': request_data.get('preferences', []),
    }

    result = generate_itinerary_service(normalized_request, "guest")

    if "error" in result:
        return jsonify(result), 500 if result.get("error") != "budget_too_low" else 422
    else:
        return jsonify(result), 200

# Add backward compatibility route for /plan-trip (register in __init__.py)
plan_trip_bp = Blueprint('legacy', __name__)

@plan_trip_bp.route('/plan-trip', methods=['POST'])
def plan_trip_legacy():
    """Legacy endpoint for backward compatibility with existing frontend."""
    request_data = request.get_json()
    if not request_data:
        return jsonify({"error": "invalid_request", "message": "Missing JSON body"}), 400
    
    destination = request_data.get('destination')
    days = request_data.get('days')
    budget = request_data.get('budget')
    people = request_data.get('people', 1)
    
    if not destination or not days or budget is None:
        return jsonify({"error": "invalid_input", "message": "Missing destination, days, or budget"}), 400

    normalized_request = {
        'destination': destination,
        'days': int(days),
        'budget': float(budget),
        'people': int(people),
        'vegOnly': request_data.get('vegOnly', False),
        'mealsPerDay': request_data.get('mealsPerDay', 2),
    }

    result = generate_itinerary_service(normalized_request, "guest")
    
    if "error" in result:
        return jsonify(result), 500 if result.get("error") != "budget_too_low" else 422
    
    # Save to SQLite for backward compatibility (if needed)
    try:
        import sqlite3
        import json as json_module
        import os
        DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tripster.db')
        # Ensure table exists
        conn = sqlite3.connect(DB_PATH)
        conn.execute("CREATE TABLE IF NOT EXISTS itineraries (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.commit()
        cur = conn.cursor()
        cur.execute("INSERT INTO itineraries (payload) VALUES (?)", (json_module.dumps(result),))
        conn.commit()
        itinerary_id = cur.lastrowid
        conn.close()
        result["itinerary_id"] = itinerary_id
        result["share_url"] = f"{request.host_url.rstrip('/')}/itinerary/{itinerary_id}"
    except Exception as e:
        print(f"[Warning] Could not save to SQLite: {e}")
    
    return jsonify(result), 200

@plan_trip_bp.route('/itinerary/<int:itinerary_id>', methods=['GET'])
def get_itinerary_legacy(itinerary_id):
    """Legacy endpoint to get saved itinerary."""
    try:
        import sqlite3
        import json as json_module
        import os
        DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tripster.db')
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT payload FROM itineraries WHERE id = ?", (itinerary_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "not_found"}), 404
        return jsonify(json_module.loads(row[0]))
    except Exception as e:
        print(f"[Error] Failed to load itinerary: {e}")
        return jsonify({"error": "database_error"}), 500

