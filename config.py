import os

class Config:
    # Use a secure secret key for session management
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a_very_secret_and_hard_to_guess_key_for_carbon_app'

    # Database configuration
    # Using SQLite for simplicity in this example
    SQLALCHEMY_DATABASE_URI = 'sqlite:///database.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
