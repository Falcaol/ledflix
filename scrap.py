import requests
from bs4 import BeautifulSoup
import time
from difflib import SequenceMatcher
from database import add_episode, get_all_episodes, Session, Anime, Episode
from app import get_anime_schedule_data, match_anime_title
import re
from datetime import datetime

def similar(a, b):
    # Fonction pour calculer la similarité entre deux chaînes
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def clean_title(title):
    # Nettoie le titre pour une meilleure comparaison
    # Enlève les numéros d'épisode, les caractères spéciaux, etc.
    import re
    title = re.sub(r'episode\s*\d+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'vostfr', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title)
    return title.strip()

def get_crunchyroll_link(title):
    url = "https://animeschedule.net/api/v3/timetables/sub"
    headers = {
        "Authorization": "Bearer r4hbdBLy5GHD4vo4XqDBkpR2ddtsYh"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            animes = response.json()
            cleaned_search_title = clean_title(title)
            
            best_match = None
            highest_similarity = 0
            
            for anime in animes:
                # Vérifier les différentes versions du titre
                titles_to_check = [
                    anime.get('title', ''),
                    anime.get('english', ''),
                    anime.get('native', ''),
                    anime.get('romaji', '')
                ]
                
                for api_title in titles_to_check:
                    if not api_title:
                        continue
                    
                    cleaned_api_title = clean_title(api_title)
                    similarity = similar(cleaned_search_title, cleaned_api_title)
                    
                    if similarity > highest_similarity and similarity > 0.6:  # Seuil de similarité de 60%
                        highest_similarity = similarity
                        if 'streams' in anime and 'crunchyroll' in anime['streams']:
                            best_match = f"https://{anime['streams']['crunchyroll']}"
            
            return best_match
    except Exception as e:
        print(f"Erreur lors de la recherche Crunchyroll: {e}")
    return None

def update_episodes():
    """Met à jour les épisodes depuis mavanimes et enrichit avec les données de l'API"""
    try:
        # Récupérer les données de l'API AnimeSchedule
        api_data = get_anime_schedule_data()  # Assurez-vous d'importer cette fonction
        
        # Scraper mavanimes
        url = "https://mavanimes.cc/"
        response = requests.get(url)
        if response.status_code != 200:
            return 0
            
        soup = BeautifulSoup(response.text, 'html.parser')
        episodes_list = soup.find_all('article', class_='episode-card')
        
        count = 0
        session = Session()
        
        for episode_elem in episodes_list:
            try:
                # Extraire les informations de base
                title = episode_elem.find('h2', class_='entry-title').text.strip()
                
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
                    
                    # Extraire le numéro d'épisode du titre mavanimes
                    episode_number = extract_episode_number(title)
                    if not episode_number:
                        episode_number = api_match.get('episodeNumber')
                    
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
                    # Fallback : créer l'épisode avec les données minimales de mavanimes
                    print(f"Pas de correspondance API pour: {title}")
                    # ... votre logique existante pour créer l'épisode ...
                    
            except Exception as e:
                print(f"Erreur lors du traitement de l'épisode {title}: {e}")
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

def extract_episode_number(title):
    """Extrait le numéro d'épisode d'un titre"""
    match = re.search(r'(?:Episode|Ep\.?)\s*(\d+(?:\.\d+)?)', title, re.IGNORECASE)
    if match:
        return float(match.group(1))
    
    # Chercher un nombre à la fin du titre
    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:VOSTFR|VF)?$', title)
    if match:
        return float(match.group(1))
    
    return None

def get_latest_episodes(page=1):
    """Fonction pour récupérer les derniers épisodes depuis la base de données"""
    return get_all_episodes(page=page, per_page=9)  # 9 épisodes par page
