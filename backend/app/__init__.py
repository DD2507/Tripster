import os
from flask import Flask, jsonify
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables from .env file FIRST
load_dotenv()

# Initialize extensions (optional - MongoDB is optional)
mongo = PyMongo()
bcrypt = Bcrypt()
jwt = JWTManager()
cors = CORS()

def create_app():
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__)

    # --- Configuration ---
    # Load secret keys for JWT and Flask session management from .env
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "default-flask-secret-key-change-me")
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "default-jwt-secret-key-change-me")

    # MongoDB connection string (optional)
    mongo_uri = os.getenv("MONGO_URI")
    if mongo_uri:
        app.config["MONGO_URI"] = mongo_uri
        print("[Info] MongoDB URI found. Auth features enabled.")
    else:
        print("[Info] MONGO_URI not set. Running in SQLite-only mode (auth features disabled).")
        app.config["MONGO_URI"] = "mongodb://localhost:27017/tripster"  # Dummy for init

    # JWT expiration time
    from datetime import timedelta
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)

    # --- Initialize Extensions with App ---
    if mongo_uri and mongo_uri != "mongodb://localhost:27017/tripster":
        try:
            mongo.init_app(app)
            bcrypt.init_app(app)
            jwt.init_app(app)
            print("[Info] MongoDB, Bcrypt, and JWT initialized successfully.")
        except Exception as e:
            print(f"[Warning] Failed to initialize MongoDB: {e}. Running in SQLite-only mode.")
            mongo_uri = None
    
    # Always initialize Bcrypt and JWT (needed even without MongoDB)
    if not hasattr(bcrypt, '_app'):
        bcrypt.init_app(app)
    if not hasattr(jwt, '_app'):
        jwt.init_app(app)
    
    cors.init_app(app, origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:5500", "http://127.0.0.1:5500", "http://localhost:3000", "http://127.0.0.1:3000"])

    # --- JWT Error Handlers ---
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({"success": False, "message": "Token has expired. Please log in again."}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({"success": False, "message": "Invalid token. Please log in again."}), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({"success": False, "message": "Authorization token is required. Please log in."}), 401

    # --- Register Blueprints (API Routes) ---
    # Import the blueprints defined in routes.py
    from .routes import auth_bp, itinerary_bp, plan_trip_bp

    # Register the blueprints with the app and specify URL prefixes
    app.register_blueprint(auth_bp, url_prefix='/api/auth') # Auth routes will be under /api/auth/...
    app.register_blueprint(itinerary_bp, url_prefix='/api/itinerary') # Itinerary routes under /api/itinerary/...
    app.register_blueprint(plan_trip_bp) # Legacy routes without prefix for backward compatibility

    # --- Legacy routes for backward compatibility ---
    @app.route('/', methods=['GET'])
    def root():
        endpoints = ["/health", "/plan-trip", "/itinerary/<id>", "/api/itinerary/generate-public"]
        if mongo_uri and mongo_uri != "mongodb://localhost:27017/tripster":
            endpoints.extend(["/api/auth/signup", "/api/auth/signin", "/api/itinerary/generate"])
        return jsonify({"message": "Tripster API running", "endpoints": endpoints})

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({"status": "ok"})

    # --- Application Context ---
    with app.app_context():
        if mongo_uri and mongo_uri != "mongodb://localhost:27017/tripster":
            try:
                from .models import create_user_indexes
                create_user_indexes()
                print("Flask App created, MongoDB connected, and DB indexes checked/created.")
            except Exception as e:
                print(f"[Warning] MongoDB initialization failed: {e}. Auth features disabled.")
        else:
            print("Flask App created (SQLite-only mode, auth disabled).")

    # Return the configured Flask app instance
    return app
