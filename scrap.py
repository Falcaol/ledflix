import requests
from bs4 import BeautifulSoup
import time
from difflib import SequenceMatcher
from database import add_episode, get_all_episodes, Anime, Episode, Session
import json

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
    """Fonction pour mettre à jour la base de données avec les nouveaux épisodes"""
    url = "https://www.mavanimes.co"
    response = requests.get(url)

    if response.status_code != 200:
        print("Failed to retrieve the page.")
        return False

    html_content = response.text
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Récupérer tous les épisodes
    latest_episodes = soup.find_all('div', class_='col-sm-3 col-xs-12', limit=10)
    
    # Inverser la liste pour que le plus récent soit traité en premier
    latest_episodes = list(reversed(latest_episodes))

    new_episodes_count = 0
    for episode in latest_episodes:
        title = episode.find('p').get_text()
        link = episode.find('a')['href']
        image_url = episode.find('img')['src']
        
        # Récupérer le contenu de la page de l'épisode
        episode_response = requests.get(link)
        episode_content = episode_response.text
        episode_soup = BeautifulSoup(episode_content, 'html.parser')
        
        video_iframes = episode_soup.find_all('iframe')
        video_links = [iframe['src'] for iframe in video_iframes]
        
        # Rechercher le lien Crunchyroll correspondant
        crunchyroll_link = get_crunchyroll_link(title)
        
        # Préparer les données de l'épisode
        episode_data = {
            'title': title,
            'link': link,
            'video_links': video_links,
            'image': image_url,
            'crunchyroll': crunchyroll_link
        }
        
        # Ajouter l'épisode à la base de données
        if add_episode(episode_data):
            new_episodes_count += 1
            print(f"Nouvel épisode ajouté: {title}")

    return new_episodes_count

def get_latest_episodes(page=1):
    """Fonction pour récupérer les derniers épisodes depuis la base de données"""
    return get_all_episodes(page=page, per_page=9)  # 9 épisodes par page

def get_anime_info_from_api(title):
    """Récupère les informations d'un anime depuis l'API AnimeSchedule"""
    try:
        url = "https://animeschedule.net/api/v3/anime"
        response = requests.get(url)
        if response.status_code == 200:
            animes = response.json()
            # Trouver l'anime le plus similaire
            best_match = None
            best_ratio = 0
            clean_search = clean_title(title).lower()
            
            for anime in animes:
                ratio = SequenceMatcher(None, clean_search, anime['name'].lower()).ratio()
                if ratio > best_ratio and ratio > 0.8:  # Seuil de similarité à 80%
                    best_ratio = ratio
                    best_match = anime
            
            return best_match
    except Exception as e:
        print(f"Erreur API AnimeSchedule: {e}")
    return None

def extract_episode_info(episode_title, anime_api_info):
    """Extrait le numéro d'épisode en utilisant l'API comme référence"""
    if not anime_api_info:
        # Fallback sur l'ancienne méthode si pas d'info API
        return extract_episode_number(episode_title)
    
    try:
        # Nettoyer le titre de l'épisode
        clean_ep_title = clean_title(episode_title).lower()
        
        # Vérifier le format du numéro d'épisode
        import re
        match = re.search(r'[-–]\s*(?:Episode)?\s*(\d+(?:\.\d+)?)', episode_title, re.IGNORECASE)
        if match:
            ep_num = float(match.group(1))
            # Vérifier si ce numéro est cohérent avec l'API
            if 'episodes' in anime_api_info and ep_num <= anime_api_info['episodes']:
                return ep_num
                
        # Si pas de match ou numéro incohérent, chercher dans l'API
        if 'episodes' in anime_api_info:
            for i in range(1, anime_api_info['episodes'] + 1):
                if f"episode {i}" in clean_ep_title:
                    return float(i)
    except Exception as e:
        print(f"Erreur extraction épisode: {e}")
    
    # Fallback sur l'ancienne méthode
    return extract_episode_number(episode_title)

def get_anime_with_episodes(anime_id):
    """Récupère un anime avec tous ses épisodes triés"""
    session = Session()
    try:
        anime = session.query(Anime)\
            .options(joinedload(Episode))\
            .filter_by(id=anime_id)\
            .first()
            
        if anime:
            # Récupérer les infos de l'API
            api_info = get_anime_info_from_api(anime.title)
            
            # Trier les épisodes en utilisant l'API comme référence
            anime.episodes.sort(
                key=lambda x: extract_episode_info(x.title, api_info)
            )
            
            # Ajouter l'information si l'anime est en favoris
            if 'user_id' in session:
                anime.is_favorite = is_favorite(session['user_id'], anime.id)
                
        return anime
    finally:
        session.close()

def add_episode(episode_data):
    session = Session()
    try:
        # Vérifier si l'épisode existe déjà
        existing_episode = session.query(Episode).filter_by(title=episode_data['title']).first()
        if not existing_episode:
            # Extraire le titre de l'anime proprement
            anime_title = clean_title(episode_data['title'])
            
            # Chercher les informations dans l'API
            api_info = get_anime_info_from_api(anime_title)
            if api_info:
                anime_title = api_info['name']  # Utiliser le titre officiel
            
            # Chercher l'anime existant
            anime = session.query(Anime).filter_by(title=anime_title).first()
            if not anime:
                # Créer un nouvel anime
                anime = Anime(
                    title=anime_title,
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
            return True
        return False
    except Exception as e:
        print(f"Erreur lors de l'ajout de l'épisode: {e}")
        session.rollback()
        return False
    finally:
        session.close()
