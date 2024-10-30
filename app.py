from flask import Flask, render_template, request, abort, redirect, url_for, flash, session, jsonify
from functools import wraps
import scrap
import requests
from datetime import datetime
from collections import defaultdict, OrderedDict
from apscheduler.schedulers.background import BackgroundScheduler
import database
import os
from flask_socketio import SocketIO, emit
from database import add_episode, get_all_episodes, get_episode_by_id

app = Flask(__name__)
socketio = SocketIO(app)
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

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    episodes_data = scrap.get_latest_episodes(page=page)
    return render_template('index.html', 
                         episodes=episodes_data['episodes'],
                         current_page=episodes_data['current_page'],
                         total_pages=episodes_data['total_pages'])

@app.route('/watch/<int:episode_id>')
def watch_episode(episode_id):
    print(f"Tentative d'affichage de l'épisode avec ID: {episode_id}")  # Log pour déboguer
    episode = get_episode_by_id(episode_id)
    if not episode:
        return "Episode not found", 404
    
    # Log pour vérifier l'ID de l'épisode
    print(f"Affichage de l'épisode ID: {episode_id}, Titre: {episode['title']}")
    
    # Récupérer les évaluations de l'épisode
    ratings = database.get_episode_ratings(episode_id)
    
    return render_template('watch.html', episode=episode, ratings=ratings)

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
    search_query = request.args.get('search', '').strip()
    
    # Récupérer les animes du calendrier
    weekly_schedule = get_weekly_anime()
    processed_animes = []
    
    # Traiter chaque anime du calendrier
    for day, day_animes in weekly_schedule.items():
        for anime in day_animes:
            # Si une recherche est active, filtrer les résultats
            if search_query and search_query.lower() not in anime['title'].lower():
                continue
                
            # Récupérer les épisodes
            episodes = database.get_episodes_by_anime_title(anime['title'])
            
            # Créer un dictionnaire pour chaque anime
            anime_dict = {
                'title': anime['title'],
                'image': anime['image'],
                'next_episode': anime['time'],
                'episodes': episodes,
                'episode_count': len(episodes)  # Ajouter le compte d'épisodes
            }
            processed_animes.append(anime_dict)
    
    # Trier les animes : ceux avec des épisodes en premier
    processed_animes.sort(key=lambda x: (-x['episode_count'], x['title']))
    
    # Récupérer les favoris si l'utilisateur est connecté
    favorites = set()
    if 'user_id' in session:
        favorites = database.get_user_favorites(session['user_id'])
    
    return render_template('animes.html', 
                         weekly_anime=processed_animes,
                         favorites=favorites)

@app.route('/anime/<int:anime_id>')
def anime_details(anime_id):
    anime_data = database.get_anime_episodes(anime_id)
    if anime_data is None:
        abort(404)
    return render_template('anime_details.html', 
                         anime=anime_data['anime'],
                         episodes=anime_data['episodes'])

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

# Ajoutez ces fonctions pour gérer les événements Socket.IO
@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {session.get("username", "Anonymous")}')
    emit('message', {
        'username': 'Système',
        'message': f'{session.get("username", "Anonymous")} a rejoint le chat',
        'time': datetime.now().strftime('%H:%M')
    }, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Client disconnected: {session.get("username", "Anonymous")}')
    emit('message', {
        'username': 'Système',
        'message': f'{session.get("username", "Anonymous")} a quitté le chat',
        'time': datetime.now().strftime('%H:%M')
    }, broadcast=True)

@socketio.on('message')
def handle_message(data):
    if 'user_id' not in session:
        return
    
    message = {
        'username': session['username'],
        'message': data['message'],
        'time': datetime.now().strftime('%H:%M')
    }
    emit('message', message, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)