from sqlalchemy import create_engine, Column, String, JSON, DateTime, Integer, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, scoped_session
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
from dotenv import load_dotenv
import re
from sqlalchemy import or_
from sqlalchemy import func

load_dotenv()

Base = declarative_base()

class Anime(Base):
    __tablename__ = 'animes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, unique=True)
    image = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    episodes = relationship('Episode', back_populates='anime')

class Episode(Base):
    __tablename__ = 'episodes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, unique=True)
    link = Column(String)
    video_links = Column(String)
    image = Column(String)
    crunchyroll = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    anime_id = Column(Integer, ForeignKey('animes.id'))
    anime = relationship('Anime', back_populates='episodes')

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(128))
    created_at = Column(DateTime, default=datetime.utcnow)
    favorites = relationship('Favorite', back_populates='user')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Favorite(Base):
    __tablename__ = 'favorites'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    anime_id = Column(Integer, ForeignKey('animes.id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship('User', back_populates='favorites')
    anime = relationship('Anime')

class WatchProgress(Base):
    __tablename__ = 'watch_progress'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    episode_id = Column(Integer, ForeignKey('episodes.id'))
    timestamp = Column(Integer, default=0)  # Position en secondes
    last_watched = Column(DateTime, default=datetime.utcnow)
    
    user = relationship('User')
    episode = relationship('Episode')

class Rating(Base):
    __tablename__ = 'ratings'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    episode_id = Column(Integer, ForeignKey('episodes.id'))
    rating = Column(Float)  # Pour permettre les demi-étoiles
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship('User')
    episode = relationship('Episode')

class ChatMessage(Base):
    __tablename__ = 'chat_messages'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    message = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship('User')

# Configuration de la base de données
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///anime.db')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)

# Créer une session thread-safe
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

def extract_anime_title(episode_title):
    """Extrait et nettoie le titre de l'anime depuis le titre de l'épisode"""
    import re
    
    # Dictionnaire de correspondance entre les titres anglais et japonais
    translations = {
        'after school hanako kun': ['Houkago Shounen Hanako-kun', 'Toilet-Bound Hanako-kun'],
        'ron kamonohashi\'s forbidden deductions': ['Kamonohashi Ron no Kindan Suiri', 'Ron Kamonohashi: Forbidden Deductions'],
        'seirei gensouki spirit chronicles': ['Seirei Gensouki', 'Spirit Chronicles'],
        'a terrified teacher at ghoul school': ['Youkai Gakkou no Sensei Hajimemashita', 'A Terrified Teacher at Ghoul School'],
        'i\'ll become a villainess': ['Rekishi ni Nokoru Akujo ni Naru zo', 'I\'ll Become a Villainess That Will Go Down in History'],
        'tying the knot with an amagami sister': ['Amagami-san Chi no Enmusubi', 'The Amagami Household'],
        'tasuketsu fate of the majority': ['Tasuuketsu', 'TASUKETSU']
    }
    
    # Nettoyage de base
    title = re.sub(r'(?:episode|ep|e)\s*\d+.*', '', episode_title, flags=re.IGNORECASE)
    title = re.sub(r'vostfr|vf', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*-\s*', ' ', title)  # Nettoie les tirets
    title = re.sub(r'\s+', ' ', title)  # Normalise les espaces
    title = title.strip().lower()  # Convertit en minuscules pour la comparaison
    
    # Enlever les numéros de saison
    title = re.sub(r'\s*\d(?:nd|rd|th)?\s*season\s*', '', title)
    title = re.sub(r'\s+\d+$', '', title)
    
    # Vérifier les correspondances dans le dictionnaire
    for eng, titles in translations.items():
        if eng in title:
            # Utiliser le premier titre (japonais) comme référence
            title = titles[0]
            break
    
    print(f"Titre original: {episode_title}")
    print(f"Titre nettoyé: {title}")
    
    return title

def add_episode(episode_data):
    session = Session()
    try:
        existing_episode = session.query(Episode).filter_by(title=episode_data['title']).first()
        if not existing_episode:
            # Extraire et nettoyer le titre de l'anime
            anime_title = extract_anime_title(episode_data['title'])
            
            # Chercher l'anime existant avec le titre nettoyé
            anime = session.query(Anime).filter(
                or_(
                    Anime.title.ilike(anime_title),
                    Anime.title.ilike(episode_data.get('api_title', ''))  # Utiliser aussi le titre de l'API
                )
            ).first()
            
            if not anime:
                # Créer un nouvel anime avec le titre de l'API si disponible
                anime = Anime(
                    title=episode_data.get('api_title', anime_title),  # Préférer le titre de l'API
                    image=episode_data['image']
                )
                session.add(anime)
                session.flush()
            
            # Créer le nouvel épisode
            new_episode = Episode(
                title=episode_data['title'],
                link=episode_data['link'],
                video_links=json.dumps(episode_data['video_links']),
                image=episode_data['image'],
                crunchyroll=episode_data.get('crunchyroll'),
                anime_id=anime.id
            )
            session.add(new_episode)
            session.commit()
            print(f"Nouvel épisode ajouté: {episode_data['title']}")
            return True
        return False
    except Exception as e:
        print(f"Erreur lors de l'ajout de l'épisode: {e}")
        session.rollback()
        return False
    finally:
        session.close()

def get_all_episodes(page=1, per_page=9):
    session = Session()
    try:
        # Calculer le total et le nombre de pages
        total = session.query(Episode).count()
        total_pages = (total + per_page - 1) // per_page
        
        # Calculer l'offset pour la pagination
        offset = (page - 1) * per_page
        
        # Récupérer les épisodes dans l'ordre décroissant de création
        episodes = session.query(Episode)\
            .order_by(Episode.created_at.desc())\
            .offset(offset)\
            .limit(per_page)\
            .all()
        
        # Convertir les épisodes en dictionnaire
        episodes_list = [
            {
                'title': episode.title,
                'link': episode.link,
                'video_links': json.loads(episode.video_links),
                'image': episode.image,
                'crunchyroll': episode.crunchyroll
            }
            for episode in episodes
        ]
        
        return {
            'episodes': episodes_list,
            'total_pages': total_pages,
            'current_page': page
        }
    finally:
        session.close()

def get_all_animes(page=1, per_page=12):
    session = Session()
    try:
        offset = (page - 1) * per_page
        total = session.query(Anime).count()
        
        # Sous-requête pour compter les épisodes de manière plus précise
        episode_count = session.query(
            Episode.anime_id,
            func.count(Episode.id).label('episode_count')
        ).group_by(Episode.anime_id).subquery()
        
        # Requête principale avec tri
        animes = session.query(Anime, func.coalesce(episode_count.c.episode_count, 0).label('ep_count'))\
            .outerjoin(episode_count, Anime.id == episode_count.c.anime_id)\
            .order_by(
                # Trier d'abord par présence d'épisodes
                func.coalesce(episode_count.c.episode_count, 0).desc(),
                # Puis par titre
                Anime.title
            )\
            .offset(offset)\
            .limit(per_page)\
            .all()
            
        total_pages = (total + per_page - 1) // per_page
        
        animes_list = [
            {
                'id': anime[0].id,
                'title': anime[0].title,
                'image': anime[0].image,
                'episode_count': anime[1]  # Utiliser le compte exact d'épisodes
            }
            for anime in animes
        ]
        
        return {
            'animes': animes_list,
            'total_pages': total_pages,
            'current_page': page
        }
    finally:
        session.close()

def get_anime_episodes(anime_id):
    session = Session()
    try:
        anime = session.query(Anime).get(anime_id)
        if not anime:
            return None
            
        episodes = session.query(Episode)\
            .filter_by(anime_id=anime_id)\
            .order_by(Episode.created_at.desc())\
            .all()
            
        return {
            'anime': {
                'id': anime.id,
                'title': anime.title,
                'image': anime.image
            },
            'episodes': [
                {
                    'title': episode.title,
                    'link': episode.link,
                    'video_links': json.loads(episode.video_links),
                    'image': episode.image,
                    'crunchyroll': episode.crunchyroll
                }
                for episode in episodes
            ]
        }
    finally:
        session.close()

def search_animes(query, page=1, per_page=12):
    session = Session()
    try:
        # Recherche avec un filtre LIKE pour le titre
        search = f"%{query}%"
        total = session.query(Anime).filter(Anime.title.ilike(search)).count()
        
        animes = session.query(Anime)\
            .filter(Anime.title.ilike(search))\
            .order_by(Anime.title)\
            .offset((page - 1) * per_page)\
            .limit(per_page)\
            .all()
            
        total_pages = (total + per_page - 1) // per_page
        
        animes_list = [
            {
                'id': anime.id,
                'title': anime.title,
                'image': anime.image,
                'episode_count': len(anime.episodes)
            }
            for anime in animes
        ]
        
        return {
            'animes': animes_list,
            'total_pages': total_pages,
            'current_page': page,
            'total_results': total
        }
    finally:
        session.close()

def create_user(username, email, password):
    session = Session()
    try:
        user = User(username=username, email=email)
        user.set_password(password)
        session.add(user)
        session.commit()
        return user
    except Exception as e:
        print(f"Erreur lors de la création de l'utilisateur: {e}")
        session.rollback()
        return None
    finally:
        session.close()

def get_user_by_username(username):
    session = Session()
    try:
        return session.query(User).filter_by(username=username).first()
    finally:
        session.close()

def add_to_favorites(user_id, anime_id):
    session = Session()
    try:
        existing = session.query(Favorite).filter_by(
            user_id=user_id, anime_id=anime_id).first()
        if not existing:
            favorite = Favorite(user_id=user_id, anime_id=anime_id)
            session.add(favorite)
            session.commit()
            return True
        return False
    finally:
        session.close()

def remove_from_favorites(user_id, anime_id):
    session = Session()
    try:
        favorite = session.query(Favorite).filter_by(
            user_id=user_id, anime_id=anime_id).first()
        if favorite:
            session.delete(favorite)
            session.commit()
            return True
        return False
    finally:
        session.close()

def get_user_favorites(user_id):
    session = Session()
    try:
        favorites = session.query(Favorite).filter_by(user_id=user_id).all()
        return [
            {
                'id': fav.anime.id,
                'title': fav.anime.title,
                'image': fav.anime.image,
                'episode_count': len(fav.anime.episodes)
            }
            for fav in favorites
        ]
    finally:
        session.close()

def is_favorite(user_id, anime_id):
    session = Session()
    try:
        return session.query(Favorite).filter_by(
            user_id=user_id, anime_id=anime_id).first() is not None
    finally:
        session.close()

def save_watch_progress(user_id, episode_id, timestamp):
    session = Session()
    try:
        progress = session.query(WatchProgress).filter_by(
            user_id=user_id, episode_id=episode_id).first()
        
        if progress:
            progress.timestamp = timestamp
            progress.last_watched = datetime.utcnow()
        else:
            progress = WatchProgress(
                user_id=user_id,
                episode_id=episode_id,
                timestamp=timestamp
            )
            session.add(progress)
        
        session.commit()
        return True
    except Exception as e:
        print(f"Erreur lors de la sauvegarde de la progression: {e}")
        session.rollback()
        return False
    finally:
        session.close()

def get_watch_progress(user_id, episode_id):
    session = Session()
    try:
        progress = session.query(WatchProgress).filter_by(
            user_id=user_id, episode_id=episode_id).first()
        return progress.timestamp if progress else 0
    finally:
        session.close()

def save_rating(user_id, episode_id, rating):
    session = Session()
    try:
        existing_rating = session.query(Rating).filter_by(
            user_id=user_id, episode_id=episode_id).first()
        
        if existing_rating:
            existing_rating.rating = rating
        else:
            new_rating = Rating(
                user_id=user_id,
                episode_id=episode_id,
                rating=rating
            )
            session.add(new_rating)
        
        session.commit()
        return True
    except Exception as e:
        print(f"Erreur lors de la sauvegarde de la note: {e}")
        session.rollback()
        return False
    finally:
        session.close()

def get_episode_ratings(episode_id):
    session = Session()
    try:
        ratings = session.query(Rating).filter_by(episode_id=episode_id).all()
        if not ratings:
            return {'average': 0, 'count': 0, 'user_rating': 0}
            
        total = sum(r.rating for r in ratings)
        average = total / len(ratings)
        
        return {
            'average': round(average * 2) / 2,  # Arrondir à la demi-étoile la plus proche
            'count': len(ratings)
        }
    finally:
        session.close()

def get_user_rating(user_id, episode_id):
    session = Session()
    try:
        rating = session.query(Rating).filter_by(
            user_id=user_id, episode_id=episode_id).first()
        return rating.rating if rating else 0
    finally:
        session.close()

def save_chat_message(user_id, message):
    session = Session()
    try:
        chat_message = ChatMessage(
            user_id=user_id,
            message=message
        )
        session.add(chat_message)
        session.commit()
        return True
    except Exception as e:
        print(f"Erreur lors de l'enregistrement du message: {e}")
        session.rollback()
        return False
    finally:
        session.close()

def get_chat_messages(limit=50):
    session = Session()
    try:
        messages = session.query(ChatMessage)\
            .join(User)\
            .order_by(ChatMessage.created_at.desc())\
            .limit(limit)\
            .all()
            
        return [
            {
                'id': msg.id,
                'username': msg.user.username,
                'message': msg.message,
                'created_at': msg.created_at.strftime('%H:%M')
            }
            for msg in messages
        ][::-1]  # Inverser pour avoir les plus anciens en premier
    finally:
        session.close()

def get_episodes_by_anime_title(title):
    """Récupère les épisodes correspondant à un titre d'anime"""
    session = Session()
    try:
        # D'abord, trouver l'anime correspondant
        anime = session.query(Anime).filter(Anime.title.ilike(title)).first()
        
        if anime:
            # Si l'anime est trouvé, retourner tous ses épisodes
            episodes = session.query(Episode)\
                .filter_by(anime_id=anime.id)\
                .order_by(Episode.created_at.desc())\
                .all()
            
            print(f"Recherche pour '{title}'")
            print(f"Anime trouvé: {anime.title}")
            print(f"Épisodes trouvés: {[ep.title for ep in episodes]}")
            
            return episodes
        
        # Si l'anime n'est pas trouvé, essayer avec des variations du titre
        variations = [
            title,
            title.replace('Season', '').strip(),
            re.sub(r'\s+\d+$', '', title),
            title.split(' Season ')[0] if ' Season ' in title else title
        ]
        
        # Chercher avec toutes les variations
        conditions = [Anime.title.ilike(f"%{v}%") for v in variations]
        anime = session.query(Anime).filter(or_(*conditions)).first()
        
        if anime:
            episodes = session.query(Episode)\
                .filter_by(anime_id=anime.id)\
                .order_by(Episode.created_at.desc())\
                .all()
            return episodes
            
        print(f"Aucun anime trouvé pour '{title}'")
        return []
    finally:
        session.close()
