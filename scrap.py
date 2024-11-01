import requests
from bs4 import BeautifulSoup
import time
from difflib import SequenceMatcher
from database import add_episode, get_all_episodes
import re
import urllib3
import warnings
from datetime import datetime

# Désactiver les avertissements SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

def similar(a, b):
    # Fonction pour calculer la similarité entre deux chaînes okok
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def clean_title(title):
    """Nettoie le titre pour une meilleure comparaison"""
    # Enlever les numéros d'épisode et les suffixes communs
    title = re.sub(r'(?:episode|ep|e)\s*\d+.*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'(?:vostfr|vf|vo|oav|ova)', '', title, flags=re.IGNORECASE)
    
    # Enlever les numéros de saison
    title = re.sub(r'(?:saison|season|s)\s*\d+', '', title, flags=re.IGNORECASE)
    
    # Enlever l'année entre parenthèses
    title = re.sub(r'\(\d{4}\)', '', title)
    
    # Enlever les caractères spéciaux et les espaces multiples
    title = re.sub(r'[^\w\s-]', ' ', title)
    title = re.sub(r'\s+', ' ', title)
    
    return title.strip().lower()

def get_anime_info(title, link, video_links, image_url):
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
            print(f"[DEBUG] Titre original: {title}")
            print(f"[DEBUG] Titre nettoyé: {search_title}")
            
            best_match = None
            highest_similarity = 0
            
            for anime in animes:
                # Récupérer tous les titres possibles de l'anime
                titles_to_check = [
                    anime.get('title', ''),
                    anime.get('english', ''),
                    anime.get('romaji', ''),
                    anime.get('native', '')
                ]
                
                # Nettoyer chaque titre pour la comparaison
                clean_titles = [clean_title(t) for t in titles_to_check if t]
                
                for api_title in clean_titles:
                    # Vérifier si l'un contient l'autre
                    if search_title in api_title or api_title in search_title:
                        similarity = 0.9  # Boost de similarité si contenu
                    else:
                        similarity = similar(search_title, api_title)
                    
                    print(f"[DEBUG] Comparaison {search_title} avec {api_title}: {similarity}")
                    
                    if similarity > highest_similarity:
                        highest_similarity = similarity
                        best_match = anime
                        print(f"[DEBUG] Nouveau meilleur match: {api_title} ({similarity})")
            
            if best_match and highest_similarity > 0.6:
                # Faire un deuxième appel API pour obtenir les détails complets
                anime_details_url = f"https://animeschedule.net/api/v3/anime/{best_match['route']}"
                details_response = requests.get(anime_details_url, headers=headers)
                
                if details_response.status_code == 200:
                    anime_details = details_response.json()
                    genres = [genre['name'] for genre in anime_details.get('genres', [])]
                    
                    return {
                        'title': title,
                        'link': link,
                        'video_links': video_links,
                        'image': image_url,
                        'crunchyroll': f"https://{best_match['streams'].get('crunchyroll', '')}" if 'streams' in best_match and 'crunchyroll' in best_match['streams'] else None,
                        'api_title': best_match['title'],
                        'genres': genres
                    }
            else:
                print(f"[DEBUG] Pas de correspondance trouvée pour {title}")
                # Créer un groupe local avec le titre de base
                base_title = re.sub(r'\s*(?:episode|ep|e)?\s*\d+.*', '', search_title, flags=re.IGNORECASE)
                return {
                    'title': title,
                    'link': link,
                    'video_links': video_links,
                    'image': image_url,
                    'api_title': base_title,
                    'genres': []
                }
                
    except Exception as e:
        print(f"[ERROR] Erreur lors de la recherche sur AnimeSchedule: {e}")
        return None

def get_anime_details(anime, title, link, video_links, image_url):
    """Récupère les détails complets d'un anime depuis l'API"""
    headers = {
        "Authorization": "Bearer r4hbdBLy5GHD4vo4XqDBkpR2ddtsYh"
    }
    
    try:
        # Faire un appel API pour obtenir les détails complets
        anime_details_url = f"https://animeschedule.net/api/v3/anime/{anime['route']}"
        details_response = requests.get(anime_details_url, headers=headers)
        
        if details_response.status_code == 200:
            anime_details = details_response.json()
            genres = [genre['name'] for genre in anime_details.get('genres', [])]
            
            return {
                'title': title,
                'link': link,
                'video_links': video_links,
                'image': image_url,
                'crunchyroll': f"https://{anime['streams'].get('crunchyroll', '')}" if 'streams' in anime and 'crunchyroll' in anime['streams'] else None,
                'api_title': anime['title'],
                'genres': genres
            }
    except Exception as e:
        print(f"[ERROR] Erreur lors de la récupération des détails: {e}")
    
    # En cas d'erreur, retourner les infos de base
    return {
        'title': title,
        'link': link,
        'video_links': video_links,
        'image': image_url,
        'api_title': anime['title'],
        'genres': []
    }

def update_episodes():
    """Fonction pour mettre à jour la base de données avec les nouveaux épisodes"""
    episodes_needed = 20  # Réduire le nombre d'épisodes
    page = 1
    max_pages = 3  # Réduire le nombre de pages
    all_episodes = []

    # Utiliser une seule session requests pour toutes les requêtes
    session = requests.Session()
    session.verify = False
    
    # Ajouter un cache pour les réponses API
    api_cache = {}

    while len(all_episodes) < episodes_needed and page <= max_pages:
        url = f"https://www.mavanimes.co/page/{page}/"  # Ajout du slash final
        try:
            print(f"[DEBUG] Scraping page {page}")
            time.sleep(1)
            
            session = requests.Session()
            session.verify = False
            response = session.get(url, timeout=10)
            
            if response.status_code != 200:
                print(f"[ERROR] Failed to retrieve page {page}: {response.status_code}")
                break

            soup = BeautifulSoup(response.text, 'html.parser')
            page_episodes = soup.find_all('div', class_='col-sm-3 col-xs-12')
            
            if not page_episodes:
                print(f"[DEBUG] Aucun épisode trouvé sur la page {page}")
                break
            
            print(f"[DEBUG] {len(page_episodes)} épisodes trouvés sur la page {page}")
            
            for episode in page_episodes:
                if len(all_episodes) >= episodes_needed:
                    break
                    
                try:
                    title = episode.find('p').get_text().strip()
                    link = episode.find('a')['href'].strip()
                    image_url = episode.find('img')['src'].strip()
                    
                    print(f"\n[DEBUG] Traitement de l'épisode: {title}")
                    
                    # Récupérer le contenu de la page de l'épisode
                    episode_response = session.get(link, timeout=10)
                    episode_soup = BeautifulSoup(episode_response.text, 'html.parser')
                    
                    video_iframes = episode_soup.find_all('iframe')
                    video_links = [iframe['src'].strip() for iframe in video_iframes]
                    
                    # Récupérer les informations de l'API
                    anime_info = get_anime_info(title, link, video_links, image_url)
                    
                    if anime_info:
                        all_episodes.append({
                            'title': title,
                            'link': link,
                            'image_url': image_url,
                            'video_links': video_links,
                            'api_info': anime_info
                        })
                        print(f"[DEBUG] Épisode ajouté: {title}")
                    else:
                        print(f"[DEBUG] Pas d'info API trouvée pour: {title}")
                    
                except Exception as e:
                    print(f"[ERROR] Erreur lors du traitement de l'épisode: {e}")
                    continue
                    
                time.sleep(0.5)  # Pause entre chaque épisode
            
            page += 1
            time.sleep(2)  # Pause entre les pages
            
        except Exception as e:
            print(f"[ERROR] Erreur lors du scraping de la page {page}: {e}")
            break

    print(f"[INFO] {len(all_episodes)} épisodes collectés au total")

    # Traiter les épisodes collectés dans l'ordre inverse
    new_episodes_count = 0
    for episode_data in reversed(all_episodes):
        try:
            if add_episode(episode_data['api_info']):
                new_episodes_count += 1
                print(f"[INFO] Nouvel épisode ajouté: {episode_data['title']}")
        except Exception as e:
            print(f"[ERROR] Erreur lors de l'ajout de l'épisode: {e}")
            continue

    print(f"[INFO] Scraping terminé. {new_episodes_count} nouveaux épisodes ajoutés.")
    return new_episodes_count

def get_latest_episodes(page=1):
    """Fonction pour récupérer les derniers épisodes depuis la base de données"""
    episodes = get_all_episodes(page=page, per_page=12)
    
    # Trier les épisodes par date de création décroissante
    if 'episodes' in episodes:
        try:
            episodes['episodes'] = sorted(
                episodes['episodes'],
                key=lambda x: x.get('id', 0),  # Utiliser l'ID comme critère de tri
                reverse=True  # Pour avoir les plus récents en premier
            )
            print(f"[DEBUG] Episodes triés: {[ep['id'] for ep in episodes['episodes']]}")
        except Exception as e:
            print(f"[ERROR] Erreur lors du tri des épisodes: {e}")
    
    return episodes
