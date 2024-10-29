import requests
from bs4 import BeautifulSoup
import time
from difflib import SequenceMatcher
from database import add_episode, get_all_episodes

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
    latest_episodes = soup.find_all('div', class_='col-sm-3 col-xs-12', limit=10)

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
