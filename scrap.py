import requests
from bs4 import BeautifulSoup
import time
from difflib import SequenceMatcher
from database import add_episode, get_all_episodes
import re

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

def get_anime_info(title):
    """Récupère les informations de l'anime depuis l'API AnimeSchedule"""
    url = "https://animeschedule.net/api/v3/timetables/sub"
    headers = {
        "Authorization": "Bearer r4hbdBLy5GHD4vo4XqDBkpR2ddtsYh"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            animes = response.json()
            
            # Nettoyer le titre de recherche
            search_title = clean_title(title)
            # Extraire le nom de l'anime (sans le numéro d'épisode)
            anime_name = re.sub(r'\s*(?:Episode|EP|E)\s*\d+.*$', '', search_title, flags=re.IGNORECASE)
            
            best_match = None
            highest_similarity = 0
            
            for anime in animes:
                titles_to_check = [
                    anime.get('title', ''),
                    anime.get('english', ''),
                    anime.get('native', ''),
                    anime.get('romaji', '')
                ]
                
                for api_title in titles_to_check:
                    if not api_title:
                        continue
                    
                    api_title_clean = clean_title(api_title)
                    similarity = similar(anime_name, api_title_clean)
                    
                    if similarity > highest_similarity and similarity > 0.6:
                        highest_similarity = similarity
                        best_match = {
                            'title': anime.get('title'),
                            'english': anime.get('english'),
                            'romaji': anime.get('romaji'),
                            'crunchyroll': f"https://{anime['streams']['crunchyroll']}" if 'streams' in anime and 'crunchyroll' in anime['streams'] else None,
                            'episode_number': anime.get('episodeNumber'),
                            'next_episode': anime.get('nextEpisodeDate'),
                            'image': anime.get('image'),
                            'similarity': similarity
                        }
            
            return best_match
            
    except Exception as e:
        print(f"Erreur lors de la recherche sur AnimeSchedule: {e}")
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
    
    latest_episodes = soup.find_all('div', class_='col-sm-3 col-xs-12', limit=10)
    latest_episodes = list(reversed(latest_episodes))

    new_episodes_count = 0
    for episode in latest_episodes:
        title = episode.find('p').get_text()
        link = episode.find('a')['href']
        image_url = episode.find('img')['src']
        
        # Récupérer les informations depuis AnimeSchedule
        anime_info = get_anime_info(title)
        
        if anime_info:
            print(f"Correspondance trouvée pour {title}")
            print(f"Similarité: {anime_info['similarity']:.2f}")
            print(f"Titre API: {anime_info['title']}")
            
            # Extraire le numéro d'épisode du titre de mavanimes
            episode_number = None
            episode_match = re.search(r'(?:Episode|EP|E)\s*(\d+)', title, re.IGNORECASE)
            if episode_match:
                episode_number = int(episode_match.group(1))
            
            # Vérifier si le numéro d'épisode correspond
            if episode_number and anime_info['episode_number']:
                if abs(episode_number - anime_info['episode_number']) <= 1:
                    print(f"Numéro d'épisode correspondant: {episode_number}")
                else:
                    print(f"Attention: Différence de numéro d'épisode - MAvanimes: {episode_number}, API: {anime_info['episode_number']}")
        
        # Récupérer le contenu de la page de l'épisode
        episode_response = requests.get(link)
        episode_content = episode_response.text
        episode_soup = BeautifulSoup(episode_content, 'html.parser')
        
        video_iframes = episode_soup.find_all('iframe')
        video_links = [iframe['src'] for iframe in video_iframes]
        
        episode_data = {
            'title': title,
            'link': link,
            'video_links': video_links,
            'image': image_url,
            'crunchyroll': anime_info['crunchyroll'] if anime_info else None
        }
        
        if add_episode(episode_data):
            new_episodes_count += 1
            print(f"Nouvel épisode ajouté: {title}")

    return new_episodes_count

def get_latest_episodes(page=1):
    """Fonction pour récupérer les derniers épisodes depuis la base de données"""
    return get_all_episodes(page=page, per_page=9)  # 9 épisodes par page
