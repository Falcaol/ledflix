from bs4 import BeautifulSoup
import requests
from database import Session, Anime, Episode
from utils import get_anime_schedule_data, match_anime_title
from datetime import datetime
import re

def get_latest_episodes(page=1, per_page=24):
    """Récupère les derniers épisodes de la base de données"""
    session = Session()
    try:
        offset = (page - 1) * per_page
        episodes = session.query(Episode)\
            .join(Episode.anime)\
            .order_by(Episode.air_date.desc())\
            .offset(offset)\
            .limit(per_page)\
            .all()
            
        total = session.query(Episode).count()
        total_pages = (total + per_page - 1) // per_page
        
        return {
            'episodes': episodes,
            'current_page': page,
            'total_pages': total_pages
        }
    finally:
        session.close()

def update_episodes():
    """Met à jour les épisodes depuis mavanimes et enrichit avec les données de l'API"""
    try:
        # Récupérer les données de l'API
        api_data = get_anime_schedule_data()
        
        # Scraper mavanimes
        url = "https://mavanimes.co/"
        response = requests.get(url)
        if response.status_code != 200:
            print("Erreur lors de l'accès à mavanimes")
            return 0
            
        soup = BeautifulSoup(response.text, 'html.parser')
        episodes_list = soup.find_all('article', class_='episode-card')
        
        count = 0
        session = Session()
        
        for episode_elem in episodes_list:
            try:
                # Extraire les informations de base
                title_elem = episode_elem.find('h2', class_='entry-title')
                if not title_elem:
                    continue
                    
                title = title_elem.text.strip()
                
                # Chercher la correspondance dans l'API
                api_match = match_anime_title(title, api_data)
                
                if api_match:
                    # Créer ou mettre à jour l'anime avec les données enrichies
                    anime = session.query(Anime).filter(
                        (Anime.title == api_match['title']) |
                        (Anime.english_title == api_match.get('english')) |
                        (Anime.romaji_title == api_match.get('romaji'))
                    ).first()
                    
                    if not anime:
                        anime = Anime(
                            title=api_match['title'],
                            english_title=api_match.get('english'),
                            romaji_title=api_match.get('romaji'),
                            image_url=f"https://animeschedule.net/{api_match['imageVersionRoute']}",
                            total_episodes=api_match.get('episodes')
                        )
                        session.add(anime)
                        session.flush()
                    
                    # Extraire le numéro d'épisode
                    episode_match = re.search(r'(?:Episode|Ep\.?)\s*(\d+(?:\.\d+)?)', title, re.IGNORECASE)
                    if episode_match:
                        episode_number = float(episode_match.group(1))
                    else:
                        episode_number = api_match.get('episodeNumber', 0)
                    
                    # Vérifier si l'épisode existe déjà
                    existing_episode = session.query(Episode).filter_by(
                        anime_id=anime.id,
                        number=episode_number
                    ).first()
                    
                    if not existing_episode:
                        # Créer le nouvel épisode
                        air_date = datetime.strptime(api_match['episodeDate'], '%Y-%m-%dT%H:%M:%SZ')
                        episode = Episode(
                            title=title,
                            number=episode_number,
                            anime_id=anime.id,
                            air_date=air_date
                        )
                        session.add(episode)
                        count += 1
                        print(f"Nouvel épisode ajouté: {title}")
                
                else:
                    print(f"Pas de correspondance API pour: {title}")
                    # Créer l'anime et l'épisode avec les données minimales
                    anime_title = re.sub(r'\s*(?:–|-)\s*\d+.*$', '', title)
                    anime = session.query(Anime).filter_by(title=anime_title).first()
                    
                    if not anime:
                        anime = Anime(title=anime_title)
                        session.add(anime)
                        session.flush()
                    
                    episode_match = re.search(r'(\d+(?:\.\d+)?)', title)
                    if episode_match:
                        episode_number = float(episode_match.group(1))
                        existing_episode = session.query(Episode).filter_by(
                            anime_id=anime.id,
                            number=episode_number
                        ).first()
                        
                        if not existing_episode:
                            episode = Episode(
                                title=title,
                                number=episode_number,
                                anime_id=anime.id,
                                air_date=datetime.utcnow()
                            )
                            session.add(episode)
                            count += 1
                    
            except Exception as e:
                print(f"Erreur lors du traitement de l'épisode: {e}")
                continue
        
        session.commit()
        return count
        
    except Exception as e:
        print(f"Erreur lors de la mise à jour: {e}")
        if 'session' in locals():
            session.rollback()
        return 0
    finally:
        if 'session' in locals():
            session.close()
