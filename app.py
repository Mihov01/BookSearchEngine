from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://myuser:mypassword@db:5432/mydatabase'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the database and migrations
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # Use hashing for production!
    preferences = db.Column(db.JSON, default={})  # Ensure preferences defaults to an empty dict
# Book model
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    language = db.Column(db.String(50), nullable=True)
    genre = db.Column(db.String(100), nullable=True)
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

# Routes remain the same
@app.route('/')
def home():
    return redirect(url_for('dashboard'))

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

        # Get recommended books based on user preferences or search history
        recommended_books = get_recommended_books(user)

        return render_template('dashboard.html', recommended_books=recommended_books, username=user.username)
    return redirect(url_for('login'))

def get_recommended_books(user):
    # Example function to fetch books based on user preferences
    if user.preferences and 'favorite_genres' in user.preferences:
        genres = user.preferences['favorite_genres']
        recommended_books = Book.query.filter(Book.genre.in_(genres)).all()
    else:
        # Fetch a few random books if no preferences are set
        recommended_books = Book.query.limit(5).all()
    return recommended_books

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/categories')
def categories():
    # Get all unique genres for the category list
    categories = [genre[0] for genre in Book.query.with_entities(Book.genre).distinct()]
    return render_template('categories.html', categories=categories)

@app.route('/categories/<category>')
def category_books(category):
    # Get books for the selected category
    books = Book.query.filter_by(genre=category).all()
    return render_template('category_books.html', books=books, category=category)
@app.route('/favorites')
def favorites():
    if 'username' in session:
        user_id = session.get('user_id')
        favorite_books = Favorite.query.filter_by(user_id=user_id).join(Book, Favorite.book_id == Book.id).all()
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
    app.run(debug=True)