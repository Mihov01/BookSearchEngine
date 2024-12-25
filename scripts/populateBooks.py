import sys
import os
from datetime import datetime
# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app, db, Book  # Import your Flask app and models



# Helper function to wait for the database to be available
def wait_for_db():
    """Wait for the database to be available"""
    from sqlalchemy import text
    from time import sleep
    for _ in range(30):  # Wait for up to 30 seconds
        try:
            # Explicitly declare the query as a text-based SQL expression
            db.session.execute(text('SELECT 1'))
            print("Database is available!")
            return True
        except Exception as e:
            print(f"Waiting for database... ({e})")
            sleep(1)  # Wait 1 second before trying again
    print("Database is not available after 30 seconds.")
    return False

# Wait for the database to be ready
with app.app_context():
    if wait_for_db():
        # Example books to add
        books = [
            Book(
                title="To Kill a Mockingbird",
                author="Harper Lee",
                description="A novel about racial injustice in the Deep South.",
                language="English",
                genre="Fiction",
                publication_date=datetime.strptime("1960-07-11", "%Y-%m-%d").date()  # Convert string to date
            ),
            Book(
                title="1984",
                author="George Orwell",
                description="A dystopian novel about totalitarianism.",
                language="English",
                genre="Dystopian",
                publication_date=datetime.strptime("1949-06-08", "%Y-%m-%d").date()  # Convert string to date
            ),
            # Add more books as needed
        ]

        try:
            # Add books to the database
            db.session.add_all(books)
            db.session.commit()  # Explicitly commit the transaction
            print("Books added successfully!")
        except Exception as e:
            print(f"An error occurred: {e}")
            db.session.rollback()  # Rollback in case of error