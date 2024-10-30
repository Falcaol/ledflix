import requests
from bs4 import BeautifulSoup
import time
from difflib import SequenceMatcher
from database import add_episode, get_all_episodes
import re
import urllib3
import warnings

# Désactiver les avertissements SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

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
            # Extraire le nom de l'anime (sans le numéro d'épisode et autres infos)
            anime_name = re.sub(r'\s*(?:Episode|EP|E|VOSTFR|VF|–|-)\s*\d+.*$', '', search_title, flags=re.IGNORECASE)
            anime_name = re.sub(r'\s*\d+\s*$', '', anime_name).strip()
            
            print(f"Recherche pour le titre nettoyé: {anime_name}")
            
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
                    # Vérifier la correspondance exacte d'abord
                    if anime_name.lower() == api_title_clean.lower():
                        highest_similarity = 1.0
                        best_match = anime
                        break
                    
                    # Sinon, vérifier la similarité
                    similarity = similar(anime_name, api_title_clean)
                    if similarity > highest_similarity and similarity > 0.6:
                        highest_similarity = similarity
                        best_match = anime
                
                if highest_similarity == 1.0:
                    break
            
            if best_match:
                print(f"Correspondance trouvée pour {title}")
                print(f"Similarité: {highest_similarity:.2f}")
                print(f"Titre API: {best_match['title']}")
                
                # Créer le dictionnaire avec les paramètres reçus
                episode_data = {
                    'title': title,
                    'link': link,
                    'video_links': video_links,
                    'image': image_url,
                    'crunchyroll': f"https://{best_match['streams']['crunchyroll']}" if 'streams' in best_match and 'crunchyroll' in best_match['streams'] else None,
                    'api_title': best_match['title']
                }
                
                return episode_data
            else:
                print(f"Aucune correspondance trouvée pour: {title}")
            
    except Exception as e:
        print(f"Erreur lors de la recherche sur AnimeSchedule: {e}")
    return None

def update_episodes():
    """Fonction pour mettre à jour la base de données avec les nouveaux épisodes"""
    episodes_needed = 20
    page = 1
    max_pages = 3
    all_episodes = []

    while len(all_episodes) < episodes_needed and page <= max_pages:
        url = f"https://www.mavanimes.co/page/{page}"
        try:
            time.sleep(1)
            
            session = requests.Session()
            session.verify = False
            response = session.get(url, timeout=10)
            
            if response.status_code != 200:
                print(f"Failed to retrieve page {page}.")
                break

            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Trouver les épisodes sur la page
            page_episodes = soup.find_all('div', class_='col-sm-3 col-xs-12')
            
            # Traiter chaque épisode de la page immédiatement
            for episode in page_episodes:
                if len(all_episodes) >= episodes_needed:
                    break
                    
                try:
                    title = episode.find('p').get_text().strip()
                    link = episode.find('a')['href'].strip()
                    image_url = episode.find('img')['src'].strip()
                    
                    print(f"\nTraitement de l'épisode: {title}")
                    print(f"Lien trouvé: {link}")
                    
                    # Récupérer le contenu de la page de l'épisode
                    episode_response = session.get(link, timeout=10)
                    episode_content = episode_response.text
                    episode_soup = BeautifulSoup(episode_content, 'html.parser')
                    
                    video_iframes = episode_soup.find_all('iframe')
                    video_links = [iframe['src'].strip() for iframe in video_iframes]
                    
                    # Récupérer les informations de l'API immédiatement
                    anime_info = get_anime_info(title, link, video_links, image_url)
                    
                    if anime_info:
                        all_episodes.append({
                            'title': title,
                            'link': link,
                            'image_url': image_url,
                            'video_links': video_links,
                            'api_info': anime_info
                        })
                    
                except Exception as e:
                    print(f"Erreur lors du traitement de l'épisode: {e}")
                    continue
                    
                time.sleep(0.5)
            
            if not page_episodes:
                break
                
            page += 1
            
        except Exception as e:
            print(f"Erreur lors du scraping de la page {page}: {e}")
            break

    # Traiter les épisodes collectés dans l'ordre inverse
    new_episodes_count = 0
    for episode_data in reversed(all_episodes):
        try:
            if add_episode(episode_data['api_info']):
                new_episodes_count += 1
                print(f"\nNouvel épisode ajouté: {episode_data['title']}")
                print(f"Lien: {episode_data['link']}")
                print(f"Liens vidéo: {episode_data['video_links']}")
        except Exception as e:
            print(f"Erreur lors de l'ajout de l'épisode: {e}")
            continue

    print(f"\nScraping terminé. {new_episodes_count} nouveaux épisodes ajoutés.")
    return new_episodes_count

def get_latest_episodes(page=1):
    """Fonction pour récupérer les derniers épisodes depuis la base de données"""
    episodes = get_all_episodes(page=page, per_page=12)
    
    # Trier les épisodes par ID décroissant pour avoir les plus récents en premier
    if 'episodes' in episodes:
        episodes['episodes'] = sorted(
            episodes['episodes'],
            key=lambda x: x.get('id', 0),  # Utiliser l'ID au lieu de created_at
            reverse=True
        )
    
    return episodes
