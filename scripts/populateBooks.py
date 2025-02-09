import sys
import os
import json
from datetime import datetime
from time import sleep
from sqlalchemy.exc import SQLAlchemyError

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app, db, Book  # Import your Flask app and models

# Helper function to wait for the database to be available
def wait_for_db():
    """Wait for the database to be available"""
    from sqlalchemy import text
    for _ in range(30):  # Wait for up to 30 seconds
        try:
            # Execute a simple query to check if the database is available
            db.session.execute(text('SELECT 1'))
            print("Database is available!")
            return True
        except SQLAlchemyError as e:
            print(f"Waiting for database... ({e})")
            sleep(1)  # Wait 1 second before trying again
    print("Database is not available after 30 seconds.")
    return False

# Function to load books from a JSON file
def load_books_from_json(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # List to store Book objects
        books = []
        for item in data:
            # Extract and process data from the JSON item
            book = Book(
                title=item.get("Title"),
                author=item.get("Author"),
                description=item.get("Description"),
                language=item.get("Language"),
                genre=item.get("Category"),  # Map Category to genre
                publication_date=datetime.strptime("2000-01-01", "%Y-%m-%d").date(),  # Default date if not available
            )
            books.append(book)
        
        return books
    except json.JSONDecodeError as e:
        print(f"Error loading JSON file: {e}")
        return []
    except Exception as e:
        print(f"Error processing the JSON file: {e}")
        return []

# Wait for the database to be ready
with app.app_context():
    if wait_for_db():
        # Load books from the JSON file
        file_path = 'gutenberg_books_processed.json'  # Replace with the actual path to your JSON file
        books = load_books_from_json(file_path)
        
        if books:
            try:
                # Add books to the database
                db.session.add_all(books)
                db.session.commit()  # Explicitly commit the transaction
                print(f"{len(books)} books added successfully!")
            except SQLAlchemyError as e:
                print(f"An error occurred while adding books: {e}")
                db.session.rollback()  # Rollback in case of error
        else:
            print("No books were loaded from the JSON file.")