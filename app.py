import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy.dialects.postgresql import ARRAY
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from datetime import datetime
import pandas as pd
import json
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://myuser:mypassword@db:5432/mydatabase'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the database and migrations
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Elasticsearch configuration
ELASTICSEARCH_URL = os.getenv('ELASTICSEARCH_URL', 'http://elasticsearch:9200')
es = Elasticsearch([ELASTICSEARCH_URL])
index_name = "books"

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # Use hashing for production!
    preferences = db.Column(db.JSON, default={})  # Ensure preferences defaults to an empty dict

# Book model
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(1000), nullable=False)
    author = db.Column(db.String(1000), nullable=False)
    description = db.Column(db.Text, nullable=True)
    language = db.Column(db.String(500), nullable=True)
    genre = db.Column(ARRAY(db.String), nullable=True)  # Store genres as an array
    publication_date = db.Column(db.Date, nullable=True)
    isbn = db.Column(db.String(20), nullable=True)
    cover_image_url = db.Column(db.String(200), nullable=True)

    def __repr__(self):
        return f'<Book {self.title}>'

# Favorite model
class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    added_date = db.Column(db.DateTime, default=db.func.current_timestamp())

# Search History model
class SearchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    search_query = db.Column(db.String(500), nullable=False)
    search_date = db.Column(db.DateTime, default=db.func.current_timestamp())
    filters = db.Column(db.JSON, nullable=True)  # Store filters in JSON format

# Popular Searches model
class PopularSearch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    search_query = db.Column(db.String(500), unique=True, nullable=False)
    frequency = db.Column(db.Integer, default=1)

# Load synonyms from CSV
def load_synonyms_from_csv(csv_file_path):
    if not os.path.exists(csv_file_path):
        raise FileNotFoundError(f"CSV file not found: {csv_file_path}")

    df = pd.read_csv(csv_file_path)
    df.columns = df.columns.str.lower()

    if "lemma" not in df.columns or "synonyms" not in df.columns:
        raise ValueError("CSV file must have 'lemma' and 'synonyms' columns.")

    return [f"{row['lemma']} => {row['synonyms']}" for _, row in df.iterrows()]

# Function to get user recommendations based on search hist

def log_search(query):
    user_id = session.get('user_id')
    new_search = SearchHistory(search_query=query, user_id=user_id)
    db.session.add(new_search)
    db.session.commit()
    es.indices.refresh(index="search_logs")  # ✅ Force refresh

def popular_searches(hours_interval=None):
    from datetime import datetime, timedelta

    time_filter = {"match_all": {}}
    if hours_interval:
        start_time = (datetime.utcnow() - timedelta(hours=hours_interval)).isoformat()
        time_filter = {"range": {"timestamp": {"gte": start_time}}}

    query = {
        "query": time_filter,
        "aggs": {
            "popular_terms": {
                "terms": {
                    "field": "query",  # Changed from "query.keyword" to "query"
                    "size": 5
                }
            }
        }
    }

    response = es.search(index="search_logs", body=query)
    print("Popular Search Response:", response, flush=True)

    return [bucket["key"] for bucket in response.get("aggregations", {}).get("popular_terms", {}).get("buckets", [])]

# Update synonym filter in Elasticsearch
def update_synonym_filter(csv_file_path):
    synonyms = load_synonyms_from_csv(csv_file_path)

    if es.indices.exists(index='books'):
        es.indices.close(index='books')

        es.indices.put_settings(
            index='books',
            body={
                "settings": {
                    "analysis": {
                        "filter": {
                            "synonym_filter": {
                                "type": "synonym",
                                "synonyms": synonyms
                            }
                        },
                        "analyzer": {
                            "synonym_analyzer": {
                                "tokenizer": "standard",
                                "filter": ["lowercase", "synonym_filter"]
                            }
                        }
                    }
                }
            }
        )
        es.indices.open(index='books')
        print("Synonym filter updated successfully.")
    else:
        print("Index 'books' does not exist.")

# Elasticsearch Indexing for Books
def create_or_update_es_index():
    if not es.indices.exists(index='books'):
        es.indices.create(index='books', ignore=400)

    # Update synonyms
    update_synonym_filter('synonyms.csv')

    books = Book.query.all()
    actions = [
        {
            "_index": "books",
            "_id": book.id,
            "_source": {
                "title": book.title,
                "author": book.author,
                "description": book.description,
                "language": book.language,
                "genre": book.genre,
                "publication_date": book.publication_date,
                "isbn": book.isbn,
                "cover_image_url": book.cover_image_url,
            }
        }
        for book in books
    ]
    bulk(es, actions)
    es.indices.refresh(index='books')  # Ensure the index is refreshed after updates

def populate_elasticsearch_from_json():
    import json

    with open('gutenberg_books_processed.json', 'r') as file:
        books = json.load(file)

    actions = []
    for book in books:
        if 'title' in book:  # Ensure the record has a title
            actions.append({
                "_index": "books",
                "_id": book['title'],  # Use the title as the unique identifier
                "_source": {
                    "title": book.get('title', ''),
                    "author": book.get('author', ''),
                    "description": book.get('description', ''),
                    "language": book.get('language', ''),
                    "genre": book.get('genre', []),
                    "publication_date": book.get('publication_date', ''),
                    "isbn": book.get('isbn', ''),
                    "cover_image_url": book.get('cover_image_url', ''),
                }
            })

    bulk(es, actions)

# Search function using Elasticsearch
def search_books(query):
    log_search(query) 
    response = es.search(
        index="books",
        body={
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["title^3", "description^2", "author", "genre"],
                                "fuzziness": "AUTO",
                                "analyzer": "synonym_analyzer"
                            }
                        }
                    ]
                }
            }
        }
    )
    return response['hits']['hits']

@app.before_first_request
def before_first_request():
    """Ensure Elasticsearch index is created and populated."""
    create_or_update_es_index()
    populate_elasticsearch_from_json()
    create_search_logs_index() 

def create_search_logs_index():
    if not es.indices.exists(index="search_logs"):
        es.indices.create(index="search_logs", body={
            "mappings": {
                "properties": {
                    "query": {"type": "keyword"},
                    "timestamp": {"type": "date"}
                }
            }
        })
        print("Created index: search_logs")
    else:
        print("Index 'search_logs' already exists.")


# Routes for handling user actions
def fuzzy_search_books(query):
    log_search(query) 
    response = es.search(
        index="books",
        body={
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["title^3", "description^2", "author", "genre"],
                                "fuzziness": "AUTO",
                                "analyzer": "synonym_analyzer"
                            }
                        },
                        {
                            "fuzzy": {
                                "title": {
                                    "value": query,
                                    "fuzziness": "AUTO",
                                    "prefix_length": 2
                                }
                            }
                        }
                    ]
                }
            }
        }
    )
    return response['hits']['hits']

@app.route('/')
def home():
    return redirect(url_for('dashboard'))

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query', '')
    if query:
        search_results = search_books(query)
        return render_template('search_results.html', query=query, results=search_results)
    return render_template('search_form.html')

@app.route('/book/<int:book_id>')
def book_detail(book_id):
    # Fetch the book details from the database
    book = Book.query.get_or_404(book_id)
    return render_template('book.html', book=book)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:  # Use hashing for production!
            session['username'] = username
            session['user_id'] = user.id
            next_page = request.args.get('next')  # Redirect to the next page (after login)
            return redirect(next_page or url_for('dashboard'))
        else:
            return "Invalid username or password"
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return "User already exists"
        new_user = User(username=username, password=password)  # Use hashing for production!
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/dashboard')
def dashboard():
    if 'username' in session:
        user_id = session['user_id']
        user = User.query.get(user_id)

        recommended_books = get_recommended_books(user)
        popular_terms = popular_searches(hours_interval=24)

        # Debugging: Print popular terms to the console
        print("Popular Searches:", popular_terms)

        return render_template('dashboard.html', recommended_books=recommended_books, username=user.username, popular_searches=popular_terms)
    return redirect(url_for('login'))

def get_recommended_books(user):
    latest_search = SearchHistory.query.order_by(SearchHistory.search_date.desc()).first()
    keyword = latest_search.search_query if latest_search else "Education"

    if isinstance(keyword, str):  # Ensure keyword is a string
        query = {
            "query": {
                "more_like_this": {
                    "fields": ["title", "author", "description"],
                    "like": keyword,
                    "min_term_freq": 1,
                    "max_query_terms": 12
                }
            }
        }
        response = es.search(index=index_name, body=query)
        recommended_books = [{
            "title": hit["_source"].get("title"),
            "author": hit["_source"].get("author"),
            "description": hit["_source"].get("description")
        } for hit in response["hits"]["hits"]]
    else:
        recommended_books = []

    return recommended_books


@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/categories')
def categories():
    # Get all unique genres for the category list (flatten genres into a list)
    genres = db.session.query(Book.genre).distinct().all()
    # Flatten the list and remove duplicates
    unique_genres = set([genre for sublist in genres for genre in sublist[0]])
    return render_template('categories.html', categories=sorted(unique_genres))

@app.route('/categories/<category>')
def category_books(category):
    # Get books for the selected category
    books = Book.query.filter(Book.genre.any(category)).all()  # Filter books by genre in array
    return render_template('category_books.html', books=books, category=category)

@app.route('/favorites')
def favorites():
    if 'username' in session:
        user_id = session.get('user_id')
        favorite_books = (
            db.session.query(Favorite, Book)
            .join(Book, Favorite.book_id == Book.id)
            .filter(Favorite.user_id == user_id)
            .all()
        )

        print(favorite_books)
        return render_template('favorites.html', favorite_books=favorite_books)
    else:
        return redirect(url_for('login', next=request.url))

@app.route('/favorites/add', methods=['POST'])
def add_to_favorites():
    if 'username' in session:
        user_id = session.get('user_id')
        book_id = request.form.get('book_id')  # Assuming the book ID is passed from the form
        favorite = Favorite(user_id=user_id, book_id=book_id)
        db.session.add(favorite)
        db.session.commit()
        return redirect(url_for('favorites'))
    return redirect(url_for('login'))

@app.route('/favorites/remove/<int:favorite_id>', methods=['POST'])
def remove_from_favorites(favorite_id):
    if 'username' in session:
        favorite = Favorite.query.get_or_404(favorite_id)
        if favorite.user_id == session.get('user_id'):
            db.session.delete(favorite)
            db.session.commit()
        return redirect(url_for('favorites'))
    return redirect(url_for('login'))

@app.route('/user')
def user_page():
    if 'username' in session:
        user_id = session['user_id']
        user = User.query.get(user_id)  # Get the user information from the database
        return render_template('user.html', user=user)
    return redirect(url_for('login'))

@app.route('/user/update', methods=['POST'])
def update_preferences():
    if 'username' in session:
        user_id = session['user_id']
        user = User.query.get(user_id)
        
        # Get the new preferences from the form
        favorite_genres = request.form.get('favorite_genres')
        
        # Update the user's preferences in the database
        user.preferences['favorite_genres'] = [genre.strip() for genre in favorite_genres.split(',')]
        db.session.commit()
        
        return redirect(url_for('user_page'))  # Redirect to the user profile page after saving the preferences
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)