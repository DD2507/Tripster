from dotenv import load_dotenv
load_dotenv(override=True)
from app import create_app

# Create the Flask app using the factory function
app = create_app()

if __name__ == "__main__":
    # Runs the Flask development server
    # Debug=True allows auto-reloading on code changes and provides better error messages
    app.run(debug=True, port=5000)
