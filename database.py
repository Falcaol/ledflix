from sqlalchemy import create_engine, Column, String, JSON, DateTime, Integer, ForeignKey, Float, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, scoped_session
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
from dotenv import load_dotenv
import re
from sqlalchemy import or_

load_dotenv()

Base = declarative_base()

# Table d'association pour la relation many-to-many entre Anime et Genre
anime_genres = Table('anime_genres', Base.metadata,
    Column('anime_id', Integer, ForeignKey('animes.id'), primary_key=True),
    Column('genre_id', Integer, ForeignKey('genres.id'), primary_key=True)
)

class Genre(Base):
    __tablename__ = 'genres'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)

class Anime(Base):
    __tablename__ = 'animes'
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, unique=True)
    image = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    episodes = relationship('Episode', back_populates='anime')
    genres = relationship('Genre', secondary=anime_genres)

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
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)
Session = scoped_session(sessionmaker(bind=engine))

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
        'tying the knot with an amagami sister': [
            'Amagami-san Chi no Enmusubi',
            'The Amagami Household'
        ],
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
        # Vérifier si l'épisode existe déjà
        existing_episode = session.query(Episode).filter_by(title=episode_data['title']).first()
        if not existing_episode:
            # Extraire et nettoyer le titre de l'anime
            anime_title = extract_anime_title(episode_data['title'])
            
            # Chercher l'anime existant avec le titre API
            anime = session.query(Anime).filter(
                or_(
                    Anime.title == episode_data.get('api_title'),
                    Anime.title.ilike(f"%{anime_title}%")
                )
            ).first()
            
            if not anime:
                # Si l'anime n'existe pas, le créer
                anime = Anime(
                    title=episode_data.get('api_title', anime_title),
                    image=episode_data['image']
                )
                session.add(anime)
                session.flush()
                print(f"Nouvel anime créé: {anime.title}")
            
            # S'assurer que le lien est valide
            if not episode_data.get('link'):
                print(f"Erreur: lien manquant pour l'épisode {episode_data['title']}")
                return False
                
            # Créer le nouvel épisode avec tous les liens
            new_episode = Episode(
                title=episode_data['title'],
                link=episode_data['link'],  # Lien direct vers la page de l'épisode
                video_links=json.dumps(episode_data.get('video_links', [])),
                image=episode_data['image'],
                crunchyroll=episode_data.get('crunchyroll'),
                anime_id=anime.id
            )
            session.add(new_episode)
            
            # Gérer les genres
            if 'genres' in episode_data:
                for genre_name in episode_data['genres']:
                    # Chercher ou créer le genre
                    genre = session.query(Genre).filter_by(name=genre_name).first()
                    if not genre:
                        genre = Genre(name=genre_name)
                        session.add(genre)
                        session.flush()
                    
                    # Ajouter le genre à l'anime s'il n'existe pas déjà
                    if genre not in anime.genres:
                        anime.genres.append(genre)
            
            session.commit()
            print(f"Nouvel épisode ajouté: {episode_data['title']} pour l'anime {anime.title} (ID: {anime.id})")
            print(f"Lien de l'épisode: {episode_data['link']}")
            return True
        
        print(f"L'épisode existe déjà: {episode_data['title']}")
        return False
    except Exception as e:
        print(f"Erreur lors de l'ajout de l'épisode: {e}")
        session.rollback()
        return False
    finally:
        session.close()

def get_all_episodes(page=1, per_page=12):
    session = Session()
    try:
        offset = (page - 1) * per_page
        total = session.query(Episode).count()
        
        # Récupérer les épisodes triés par ID décroissant
        episodes = session.query(Episode)\
            .order_by(Episode.id.desc())\
            .offset(offset)\
            .limit(per_page)\
            .all()
            
        total_pages = (total + per_page - 1) // per_page
        
        episodes_list = [
            {
                'id': episode.id,
                'title': episode.title,
                'link': episode.link,
                'video_links': json.loads(episode.video_links) if episode.video_links else [],
                'image': episode.image,
                'crunchyroll': episode.crunchyroll,
                'anime_id': episode.anime_id
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

def get_all_animes(page=1, per_page=12, genres=None):
    session = Session()
    try:
        offset = (page - 1) * per_page
        
        # Construire la requête de base
        query = session.query(Anime)
        
        # Si des genres sont sélectionnés, filtrer les animes
        if genres and genres[0]:
            query = query.join(AnimeGenre).join(Genre)\
                        .filter(Genre.id.in_(genres))\
                        .distinct()
        
        # Compter le total avant la pagination
        total = query.count()
        
        # Appliquer la pagination
        animes = query.order_by(Anime.created_at.desc())\
                     .offset(offset)\
                     .limit(per_page)\
                     .all()
        
        total_pages = (total + per_page - 1) // per_page
        
        animes_list = [
            {
                'id': anime.id,
                'title': anime.title,
                'image': anime.image,
                'genres': [genre.name for genre in anime.genres]
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
            return {'average': 0, 'count': 0}
            
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
    """Récupre les épisodes correspondant à un titre d'anime"""
    session = Session()
    try:
        # Dictionnaire de correspondance entre les différentes versions des titres
        title_mappings = {
            'Houkago Shounen Hanako-kun': ['After school Hanako kun', 'Toilet-Bound Hanako-kun', 'After school', 'Hanako kun'],
            'Kamonohashi Ron no Kindan Suiri': ['Ron Kamonohashi\'s Forbidden Deductions', 'Ron Kamonohashi', 'Forbidden Deductions'],
            'Seirei Gensouki': ['Spirit Chronicles', 'Seirei Gensouki Spirit Chronicles', 'Spirit Chronicles'],
            'Youkai Gakkou no Sensei Hajimemashita': ['A Terrified Teacher at Ghoul School', 'Terrified Teacher', 'Ghoul School'],
            'Rekishi ni Nokoru Akujo ni Naru zo': ['I\'ll Become a Villainess That Will Go Down in History', 'Villainess', 'History'],
            'Amagami-san Chi no Enmusubi': [
                'Tying the Knot with an Amagami Sister',
                'The Amagami Household',
                'Amagami Sister',
                'Amagami-san',
                'Amagami'
            ],
            'Tasuuketsu': ['TASUKETSU', 'Tasuketsu Fate of the Majority', 'Fate of the Majority'],
            'Wonderful Precure!': ['Wonderful Precure', 'Precure'],
            'Natsume Yuujinchou Shichi': ['Natsume Yuujinchou', 'Natsume'],
            'Raise wa Tanin ga Ii': ['Raise wa Tanin', 'Tanin ga Ii']
        }

        # Nettoyer le titre de recherche
        clean_title = re.sub(r'(?:episode|ep|e)\s*\d+.*', '', title, flags=re.IGNORECASE)
        clean_title = re.sub(r'vostfr|vf', '', clean_title, flags=re.IGNORECASE)
        clean_title = re.sub(r'\s*-\s*', ' ', clean_title)
        clean_title = clean_title.strip().lower()

        # Créer une liste de tous les titres possibles
        possible_titles = [clean_title]
        
        # Ajouter les variations connues
        for main_title, variants in title_mappings.items():
            if any(variant.lower() in clean_title for variant in variants):
                possible_titles.append(main_title.lower())
            if main_title.lower() in clean_title:
                possible_titles.extend(variant.lower() for variant in variants)

        # Créer les conditions de recherche
        conditions = [
            Anime.title.ilike(f"%{t}%") for t in possible_titles
        ]

        # Rechercher l'anime
        anime = session.query(Anime).filter(or_(*conditions)).first()

        if anime:
            episodes = session.query(Episode)\
                .filter_by(anime_id=anime.id)\
                .order_by(Episode.created_at.desc())\
                .all()
            
            print(f"Recherche pour '{title}'")
            print(f"Anime trouvé: {anime.title}")
            print(f"Épisodes trouvés: {[ep.title for ep in episodes]}")
            
            return episodes

        print(f"Aucun anime trouvé pour '{title}'")
        return []
    finally:
        session.close()

def get_episode_by_id(episode_id):
    session = Session()
    try:
        episode = session.query(Episode).get(episode_id)
        if episode:
            # Filtrer les liens vidéo problématiques
            video_links = json.loads(episode.video_links) if episode.video_links else []
            filtered_links = [
                link for link in video_links 
                if not any(domain in link.lower() for domain in [
                    'dailymotion.com',
                    'streamtape.com',  # Lecteur avec beaucoup de pubs
                    'voe.sx',          # Lecteur avec anti-adblock
                    # Ajoutez d'autres domaines problématiques ici
                ])
            ]
            
            return {
                'id': episode.id,
                'title': episode.title,
                'link': episode.link,
                'video_links': filtered_links,
                'image': episode.image,
                'crunchyroll': episode.crunchyroll,
                'anime_id': episode.anime_id
            }
        return None
    finally:
        session.close()

def get_animes_by_genres(genre_ids):
    session = Session()
    try:
        query = session.query(Anime).distinct()
        
        if genre_ids and genre_ids[0]:  # Si des genres sont sélectionnés
            query = query.join(AnimeGenre).join(Genre)\
                        .filter(Genre.id.in_(genre_ids))
        
        animes = query.all()
        
        return [
            {
                'id': anime.id,
                'title': anime.title,
                'image': anime.image,
                'genres': [g.genre.name for g in anime.genres]
            }
            for anime in animes
        ]
    finally:
        session.close()

def get_all_genres():
    session = Session()
    try:
        return session.query(Genre).order_by(Genre.name).all()
    finally:
        session.close()
