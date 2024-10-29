from flask import Flask, render_template, request, abort, redirect, url_for, flash, session, jsonify
from functools import wraps
import scrap
import requests
from datetime import datetime, timedelta
from collections import defaultdict, OrderedDict
from apscheduler.schedulers.background import BackgroundScheduler
from database import Session, Anime, Episode, Favorite, get_episode_ratings, get_user_rating
import os
import re
from sqlalchemy import desc
from utils import clean_title, extract_episode_number, format_date
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
from difflib import SequenceMatcher
import flask
from flask import session as flask_session
from api import AnimeScheduleAPI
import logging

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'votre_clé_secrète_par_défaut')

# Initialisation de l'API
anime_api = AnimeScheduleAPI()

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
    session = Session()
    try:
        api_data = get_anime_schedule_data()
        episodes_added = 0
        
        for anime_data in api_data:
            try:
                # Traiter l'anime
                anime = process_anime_data(anime_data, session)
                if not anime:
                    continue
                    
                # Créer l'épisode
                episode = create_episode(anime, anime_data, session)
                if episode:
                    episodes_added += 1
                    print(f"Nouvel épisode ajouté: {episode.title}")
                    
            except Exception as e:
                print(f"Erreur lors du traitement: {e}")
                continue
                
        session.commit()
        print(f"Initialisation terminée : {episodes_added} épisodes ajoutés")
        
    except Exception as e:
        print(f"Erreur lors de l'initialisation: {e}")
        session.rollback()
    finally:
        session.close()

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
            .options(joinedload(Episode.anime))\
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

def get_anime_info_from_api(title):
    """Récupère les informations d'un anime depuis l'API AnimeSchedule"""
    try:
        url = "https://animeschedule.net/api/v3/anime"
        response = requests.get(url)
        
        if response.status_code == 200:
            animes = response.json()  # C'est déjà une liste, pas besoin de ['data']
            
            # Trouver l'anime le plus similaire
            best_match = None
            best_ratio = 0
            clean_search = clean_title(title).lower()
            
            for anime in animes:
                # Vérifier les différents titres possibles
                titles_to_check = [
                    anime.get('title', ''),
                    anime.get('english', ''),
                    anime.get('romaji', '')
                ]
                
                for anime_title in titles_to_check:
                    if not anime_title:
                        continue
                    ratio = SequenceMatcher(None, clean_search, 
                                          anime_title.lower()).ratio()
                    if ratio > best_ratio and ratio > 0.8:
                        best_ratio = ratio
                        best_match = anime
                        break
            
            return best_match
            
    except Exception as e:
        print(f"Erreur API AnimeSchedule: {e}")
        
    return None

def extract_episode_info(episode_title, anime_api_info):
    """Extrait le numéro d'épisode en utilisant l'API comme référence"""
    try:
        # D'abord essayer l'extraction classique
        import re
        match = re.search(r'[-–]\s*(?:Episode)?\s*(\d+(?:\.\d+)?)', episode_title, re.IGNORECASE)
        if match:
            return float(match.group(1))
            
        # Si pas de match, chercher juste un nombre
        numbers = re.findall(r'\d+(?:\.\d+)?', episode_title)
        if numbers:
            return float(numbers[-1])  # Prendre le dernier nombre trouvé
            
    except Exception as e:
        print(f"Erreur extraction épisode: {e}")
    
    return 9999  # Valeur par défaut pour le tri

def get_anime_with_episodes(anime_id):
    """Récupère un anime avec tous ses épisodes triés"""
    session = Session()
    try:
        anime = session.query(Anime)\
            .options(joinedload(Anime.episodes))\
            .filter_by(id=anime_id)\
            .first()
            
        if anime and anime.episodes:
            # Récupérer les infos de l'API avec cache
            api_info = anime_api.get_anime_info(anime.title)
            
            # Trier les épisodes
            anime.episodes.sort(
                key=lambda x: extract_episode_info(x.title, api_info)
            )
            
        return anime
    except Exception as e:
        logging.error(f"Erreur lors de la récupération de l'anime {anime_id}: {e}")
        return None
    finally:
        session.close()

@app.route('/watch/<int:episode_id>')
def watch_episode(episode_id):
    session = Session()
    try:
        episode = session.query(Episode)\
            .options(joinedload(Episode.anime))\
            .filter_by(id=episode_id)\
            .first()
            
        if not episode:
            flash('Épisode non trouvé', 'error')
            return redirect(url_for('index'))
            
        # Récupérer les notes
        ratings = get_episode_ratings(episode_id)
        user_rating = None
        
        # Si l'utilisateur est connecté, récupérer sa note
        if 'user_id' in flask.session:
            user_rating = get_user_rating(flask.session['user_id'], episode_id)
            
        return render_template('watch.html',
                             episode=episode,
                             ratings=ratings,
                             user_rating=user_rating)
    finally:
        session.close()

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
    session = Session()
    try:
        # Récupérer les épisodes des 7 prochains jours
        episodes = session.query(Episode)\
            .join(Episode.anime)\
            .filter(Episode.air_date >= datetime.utcnow())\
            .order_by(Episode.air_date)\
            .all()

        # Grouper par jour
        episodes_by_day = {}
        for episode in episodes:
            day = episode.air_date.strftime('%Y-%m-%d')
            if day not in episodes_by_day:
                episodes_by_day[day] = []
            episodes_by_day[day].append(episode)

        return render_template('calendar.html', 
                             episodes_by_day=episodes_by_day)
    finally:
        session.close()

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
    search_query = request.args.get('q', '')
    db_session = Session()
    
    try:
        query = db_session.query(Anime)
        
        if search_query:
            query = query.filter(Anime.title.ilike(f'%{search_query}%'))
        
        total_animes = query.count()
        per_page = 12
        total_pages = (total_animes + per_page - 1) // per_page
        
        animes = query\
            .options(joinedload(Anime.episodes))\
            .order_by(Anime.title)\
            .offset((page - 1) * per_page)\
            .limit(per_page)\
            .all()
            
        if 'user_id' in flask.session:
            user_id = flask.session['user_id']
            for anime in animes:
                anime.is_favorite = is_favorite(user_id, anime.id)
        
        return render_template('animes.html',
                             animes=animes,
                             current_page=page,
                             total_pages=total_pages,
                             search_query=search_query)
    finally:
        db_session.close()

@app.route('/anime/<int:anime_id>')
def anime_details(anime_id):
    session = Session()
    try:
        anime = session.query(Anime)\
            .options(joinedload(Anime.episodes))\
            .filter_by(id=anime_id)\
            .first_or_404()

        # Trier les épisodes par numéro
        episodes = sorted(anime.episodes, key=lambda x: x.number)

        return render_template('anime.html',
                             anime=anime,
                             episodes=episodes)
    finally:
        session.close()

def detect_season(title):
    """Détecte la saison dans le titre d'un épisode"""
    # Chercher "Saison X" ou "Season X"
    season_match = re.search(r'(?:Saison|Season)\s*(\d+)', title, re.IGNORECASE)
    if season_match:
        return int(season_match.group(1))
        
    # Chercher "SX" ou "S0X"
    s_match = re.search(r'S(?:aison)?\s*(\d+)', title, re.IGNORECASE)
    if s_match:
        return int(s_match.group(1))
        
    return 1  # Saison 1 par défaut

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

def is_favorite(user_id, anime_id):
    """Vérifie si un anime est dans les favoris d'un utilisateur"""
    session = Session()
    try:
        return session.query(Favorite)\
            .filter_by(user_id=user_id, anime_id=anime_id)\
            .first() is not None
    finally:
        session.close()

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

ANIME_SCHEDULE_TOKEN = "r4hbdBLy5GHD4vo4XqDBkpR2ddtsYh"

def get_anime_schedule_data():
    """Récupère les données de l'API AnimeSchedule"""
    try:
        url = "https://animeschedule.net/api/v3/timetables/dub"
        headers = {
            "Authorization": f"Bearer {ANIME_SCHEDULE_TOKEN}"
        }
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"Erreur API: status code {response.status_code}")
            return []
            
        return response.json()
        
    except Exception as e:
        print(f"Erreur lors de la récupération des données: {e}")
        return []

def process_anime_data(anime_data, session):
    """Traite les données d'un anime et crée/met à jour l'entrée en base"""
    try:
        # Rechercher l'anime existant
        existing_anime = session.query(Anime).filter(
            (Anime.title == anime_data['title']) |
            (Anime.english_title == anime_data.get('english')) |
            (Anime.romaji_title == anime_data.get('romaji'))
        ).first()
        
        if existing_anime:
            # Mettre à jour les informations
            existing_anime.english_title = anime_data.get('english')
            existing_anime.romaji_title = anime_data.get('romaji')
            existing_anime.image_url = f"https://animeschedule.net/{anime_data.get('imageVersionRoute')}"
            existing_anime.total_episodes = anime_data.get('episodes')
            return existing_anime
            
        # Créer un nouvel anime
        new_anime = Anime(
            title=anime_data['title'],
            english_title=anime_data.get('english'),
            romaji_title=anime_data.get('romaji'),
            image_url=f"https://animeschedule.net/{anime_data.get('imageVersionRoute')}",
            total_episodes=anime_data.get('episodes')
        )
        session.add(new_anime)
        session.flush()  # Pour obtenir l'ID
        return new_anime
        
    except Exception as e:
        print(f"Erreur lors du traitement de l'anime {anime_data.get('title')}: {e}")
        return None

def create_episode(anime, episode_data, session):
    """Crée ou met à jour un épisode"""
    try:
        episode_number = episode_data.get('episodeNumber', 0)
        air_date = datetime.strptime(episode_data['episodeDate'], '%Y-%m-%dT%H:%M:%SZ')
        
        # Vérifier si l'épisode existe déjà
        existing_episode = session.query(Episode).filter_by(
            anime_id=anime.id,
            number=episode_number
        ).first()
        
        if existing_episode:
            # Mettre à jour les informations
            existing_episode.air_date = air_date
            return existing_episode
            
        # Créer le titre de l'épisode
        episode_title = f"{anime.title} – {episode_number:02d} VOSTFR"
        
        # Créer un nouvel épisode
        new_episode = Episode(
            title=episode_title,
            number=episode_number,
            anime_id=anime.id,
            air_date=air_date
        )
        session.add(new_episode)
        return new_episode
        
    except Exception as e:
        print(f"Erreur lors de la création de l'épisode {episode_number}: {e}")
        return None

def match_episode_to_anime(episode_title, anime_data):
    """Trouve l'anime correspondant dans les données de l'API"""
    for anime in anime_data:
        # Vérifier les différents titres possibles
        titles_to_check = [
            anime.get('title', ''),
            anime.get('english', ''),
            anime.get('romaji', '')
        ]
        
        for title in titles_to_check:
            if title and title.lower() in episode_title.lower():
                return anime
                
    return None

def process_new_episode(episode_title):
    """
    Traite un nouvel épisode et le lie à son anime
    """
    session = Session()
    try:
        # Récupérer les données de l'API
        api_data = get_anime_schedule_data()  # La fonction qui fait l'appel API
        if not api_data:
            print(f"Impossible de récupérer les données API pour: {episode_title}")
            return None
            
        # Trouver l'anime correspondant
        anime_data = match_episode_to_anime(episode_title, api_data)
        if not anime_data:
            print(f"Aucun anime trouvé pour: {episode_title}")
            return None
            
        # Chercher si l'anime existe déjà en base
        anime = session.query(Anime).filter(
            or_(
                Anime.title.ilike(anime_data['title']),
                Anime.title.ilike(anime_data.get('english', '')),
                Anime.title.ilike(anime_data.get('romaji', ''))
            )
        ).first()
        
        # Si l'anime n'existe pas, le créer
        if not anime:
            anime = Anime(
                title=anime_data['title'],
                english_title=anime_data.get('english'),
                romaji_title=anime_data.get('romaji'),
                image=f"https://animeschedule.net/{anime_data.get('imageVersionRoute', '')}"
            )
            session.add(anime)
            session.flush()
        
        # Extraire le numéro d'épisode
        episode_number = extract_episode_number(episode_title)
        
        # Créer l'épisode
        episode = Episode(
            title=episode_title,
            number=episode_number,
            anime_id=anime.id
        )
        session.add(episode)
        session.commit()
        
        print(f"Nouvel épisode ajouté: {episode_title}")
        return episode
        
    except Exception as e:
        print(f"Erreur lors du traitement de l'épisode {episode_title}: {e}")
        session.rollback()
        return None
    finally:
        session.close()

def extract_episode_number(title):
    """
    Extrait le numéro d'épisode du titre
    """
    # Chercher d'abord le format "Episode XX" ou "- XX"
    match = re.search(r'(?:Episode|–)\s*(\d+(?:\.\d+)?)', title, re.IGNORECASE)
    if match:
        return float(match.group(1))
        
    # Sinon chercher juste un nombre à la fin
    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:VOSTFR|VF)?$', title)
    if match:
        return float(match.group(1))
        
    return 0  # Valeur par défaut

@app.template_filter('format_date')
def format_date(date):
    """Formate une date pour l'affichage"""
    if isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d')
    return date.strftime('%d/%m/%Y')

@app.template_filter('format_time')
def format_time(date):
    """Formate une heure pour l'affichage"""
    return date.strftime('%H:%M')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
