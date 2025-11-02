from . import mongo # Import the mongo instance from __init__.py

def create_user_indexes():
    """Creates unique indexes on username and email fields if they don't exist."""
    try:
        if not hasattr(mongo, 'db') or mongo.db is None:
            return
        mongo.db.users.create_index("username", unique=True)
        mongo.db.users.create_index("email", unique=True)
        print("User indexes created successfully (or already exist).")
    except Exception as e:
        # Don't crash the app if index creation fails
        print(f"Warning: Error creating user indexes (might already exist or DB unavailable): {e}")

