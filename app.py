from flask import Flask, render_template, request, abort, redirect, url_for, flash, session, jsonify
from functools import wraps
import scrap
import requests
from datetime import datetime
from collections import defaultdict, OrderedDict
from apscheduler.schedulers.background import BackgroundScheduler
from database import Session, Anime, Episode
import os
import re
from sqlalchemy import desc
from utils import clean_title, extract_episode_number, format_date

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'votre_clé_secrète_par_défaut')

# Définir le décorateur login_required avant de l'utiliser
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Créer un scheduler pour la mise à jour automatique
scheduler = BackgroundScheduler()
scheduler.add_job(func=scrap.update_episodes, trigger="interval", minutes=15)
scheduler.start()

# Ajouter cette fonction pour initialiser les données
def initialize_data():
    print("Initialisation des données...")
    try:
        count = scrap.update_episodes()
        print(f"Initialisation terminée : {count} épisodes ajoutés")
    except Exception as e:
        print(f"Erreur lors de l'initialisation : {e}")

# Appeler la fonction d'initialisation au démarrage
initialize_data()

def get_weekly_anime():
    url = "https://animeschedule.net/api/v3/timetables/sub"
    headers = {
        "Authorization": "Bearer r4hbdBLy5GHD4vo4XqDBkpR2ddtsYh"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        animes = response.json()
        weekly_schedule = defaultdict(list)
        
        # Dictionnaire de traduction des jours
        days_translation = {
            'Monday': 'Lundi',
            'Tuesday': 'Mardi',
            'Wednesday': 'Mercredi',
            'Thursday': 'Jeudi',
            'Friday': 'Vendredi',
            'Saturday': 'Samedi',
            'Sunday': 'Dimanche'
        }
        
        # Obtenir le jour actuel
        today = datetime.now().strftime('%A')
        
        # Ordre des jours de la semaine en anglais
        days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        # Réorganiser l'ordre pour commencer par aujourd'hui
        today_index = days_order.index(today)
        days_order = days_order[today_index:] + days_order[:today_index]
        
        # Remplir le planning
        for anime in animes:
            episode_date = datetime.strptime(anime['episodeDate'], '%Y-%m-%dT%H:%M:%SZ')
            day_name = episode_date.strftime('%A')
            
            image_url = f"https://img.animeschedule.net/production/assets/public/img/{anime['imageVersionRoute']}"
            
            anime_info = {
                'title': anime['title'],
                'image': image_url,
                'time': episode_date.strftime('%H:%M')
            }
            weekly_schedule[day_name].append(anime_info)
        
        # Créer un dictionnaire ordonné avec les jours traduits
        ordered_schedule = OrderedDict()
        for day in days_order:
            if day in weekly_schedule:
                ordered_schedule[days_translation[day]] = weekly_schedule[day]
            
        return ordered_schedule
    return None

def get_latest_episodes(page=1, per_page=9):
    """Récupère les derniers épisodes avec les informations de leur anime"""
    session = Session()
    try:
        # Calculer l'offset pour la pagination
        offset = (page - 1) * per_page
        
        # Récupérer les épisodes avec leurs animes associés
        episodes = session.query(Episode)\
            .join(Anime)\
            .order_by(desc(Episode.created_at))\
            .offset(offset)\
            .limit(per_page)\
            .all()
        
        # Compter le nombre total d'épisodes pour la pagination
        total_episodes = session.query(Episode).count()
        total_pages = (total_episodes + per_page - 1) // per_page
        
        return {
            'episodes': episodes,
            'current_page': page,
            'total_pages': total_pages,
            'total_episodes': total_episodes
        }
    finally:
        session.close()

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    episodes_data = get_latest_episodes(page=page)
    
    return render_template('index.html',
                         episodes=episodes_data['episodes'],
                         current_page=episodes_data['current_page'],
                         total_pages=episodes_data['total_pages'])

def get_anime_with_episodes(anime_id):
    """Récupère un anime avec tous ses épisodes triés"""
    session = Session()
    try:
        anime = session.query(Anime)\
            .filter_by(id=anime_id)\
            .first()
            
        if anime:
            # Trier les épisodes par numéro
            anime.episodes.sort(key=lambda x: float(episode_number_filter(x) or 0))
            
            # Ajouter l'information si l'anime est en favoris
            if 'user_id' in session:
                anime.is_favorite = is_favorite(session['user_id'], anime.id)
                
        return anime
    finally:
        session.close()

@app.route('/watch/<int:episode_id>')
def watch_episode(episode_id):
    episodes_data = scrap.get_latest_episodes()
    if episode_id >= len(episodes_data['episodes']):
        abort(404)
    episode = episodes_data['episodes'][episode_id]
    
    # Récupérer la progression si l'utilisateur est connecté
    progress = 0
    user_rating = 0
    if 'user_id' in session:
        progress = database.get_watch_progress(session['user_id'], episode_id)
        user_rating = database.get_user_rating(session['user_id'], episode_id)
    
    ratings = database.get_episode_ratings(episode_id)
    
    return render_template('watch.html', 
                         episode=episode, 
                         progress=progress,
                         ratings=ratings,
                         user_rating=user_rating)

@app.route('/save-progress', methods=['POST'])
@login_required
def save_progress():
    data = request.get_json()
    episode_id = data.get('episode_id')
    timestamp = data.get('timestamp')
    
    if episode_id is not None and timestamp is not None:
        success = database.save_watch_progress(
            session['user_id'], episode_id, timestamp)
        return {'success': success}
    return {'success': False}, 400

@app.route('/calendar')
def calendar():
    weekly_anime = get_weekly_anime()
    search_query = request.args.get('q', '').strip()
    
    if search_query and weekly_anime:
        # Filtrer les animes qui correspondent à la recherche
        filtered_schedule = OrderedDict()
        for day, animes in weekly_anime.items():
            matching_animes = [
                anime for anime in animes 
                if search_query.lower() in anime['title'].lower()
            ]
            if matching_animes:
                filtered_schedule[day] = matching_animes
        weekly_anime = filtered_schedule if filtered_schedule else weekly_anime

    return render_template('calendar.html', 
                         schedule=weekly_anime,
                         search_query=search_query)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if database.get_user_by_username(username):
            flash('Ce nom d\'utilisateur existe déjà', 'danger')
            return redirect(url_for('register'))
        
        user = database.create_user(username, email, password)
        if user:
            flash('Inscription réussie ! Vous pouvez maintenant vous connecter', 'success')
            return redirect(url_for('login'))
        
        flash('Erreur lors de l\'inscription', 'danger')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = database.get_user_by_username(username)
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
            
        flash('Nom d\'utilisateur ou mot de passe incorrect', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    favorites = database.get_user_favorites(session['user_id'])
    return render_template('profile.html', favorites=favorites)

@app.route('/favorite/<int:anime_id>', methods=['POST'])
@login_required
def toggle_favorite(anime_id):
    if database.is_favorite(session['user_id'], anime_id):
        database.remove_from_favorites(session['user_id'], anime_id)
        return {'status': 'removed'}
    else:
        database.add_to_favorites(session['user_id'], anime_id)
        return {'status': 'added'}

@app.route('/animes')
def animes():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('q', '').strip()
    
    if search_query:
        animes_data = database.search_animes(search_query, page=page)
    else:
        animes_data = database.get_all_animes(page=page)
    
    if 'user_id' in session:
        for anime in animes_data['animes']:
            anime['is_favorite'] = database.is_favorite(session['user_id'], anime['id'])
    
    return render_template('animes.html', 
                         animes=animes_data['animes'],
                         current_page=animes_data['current_page'],
                         total_pages=animes_data['total_pages'],
                         search_query=search_query)

@app.route('/anime/<int:anime_id>')
def anime_details(anime_id):
    anime = get_anime_with_episodes(anime_id)
    if anime is None:
        abort(404)
        
    return render_template('anime_details.html',
                         anime=anime,
                         is_favorite=getattr(anime, 'is_favorite', False))

@app.route('/force-update')
def force_update():
    count = scrap.update_episodes()
    return f"Mise à jour effectuée : {count} nouveaux épisodes ajoutés"

@app.route('/rate/<int:episode_id>', methods=['POST'])
@login_required
def rate_episode(episode_id):
    data = request.get_json()
    rating = data.get('rating')
    
    if rating is not None:
        success = database.save_rating(session['user_id'], episode_id, rating)
        if success:
            ratings = database.get_episode_ratings(episode_id)
            return jsonify(ratings)
    
    return {'error': 'Invalid rating'}, 400

@app.route('/chat/messages')
def get_messages():
    messages = database.get_chat_messages()
    return jsonify(messages)

@app.route('/chat/send', methods=['POST'])
@login_required
def send_message():
    data = request.get_json()
    message = data.get('message', '').strip()
    
    if message:
        if database.save_chat_message(session['user_id'], message):
            return jsonify({
                'success': True,
                'username': session['username'],
                'message': message,
                'time': datetime.now().strftime('%H:%M')
            })
    
    return jsonify({'success': False}), 400

@app.route('/health')
def health_check():
    return jsonify({"status": "ok"}), 200

@app.template_filter('episode_number')
def episode_number_filter(episode):
    """Extrait le numéro d'épisode du titre"""
    import re
    match = re.search(r'[-–]\s*(?:Episode)?\s*(\d+(?:\.\d+)?)', episode.title, re.IGNORECASE)
    return match.group(1) if match else "?"

@app.template_filter('format_date')
def format_date_filter(date):
    """Formate une date en français"""
    if isinstance(date, datetime):
        return date.strftime('%d/%m/%Y à %H:%M')
    return date

@app.context_processor
def utility_processor():
    """Ajoute des fonctions utiles disponibles dans tous les templates"""
    def episode_count(anime):
        return len(anime.episodes) if anime.episodes else 0
        
    def latest_episode(anime):
        if not anime.episodes:
            return None
        return max(anime.episodes, key=lambda x: float(episode_number_filter(x) or 0))
        
    def get_user_rating(episode_id):
        if 'user_id' not in session:
            return 0
        db_session = Session()
        try:
            rating = db_session.query(Rating)\
                .filter_by(user_id=session['user_id'], episode_id=episode_id)\
                .first()
            return rating.rating if rating else 0
        finally:
            db_session.close()
            
    return dict(
        episode_count=episode_count,
        latest_episode=latest_episode,
        format_date=format_date_filter,
        get_user_rating=get_user_rating,
        is_favorite=is_favorite
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
