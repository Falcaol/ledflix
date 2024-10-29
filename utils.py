import re
from difflib import SequenceMatcher
import requests
from datetime import datetime

ANIME_SCHEDULE_TOKEN = "r4hbdBLy5GHD4vo4XqDBkpR2ddtsYh"

def get_anime_schedule_data():
    """Récupère les données de l'API AnimeSchedule"""
    try:
        url = "https://animeschedule.net/api/v3/timetables/dub"
        headers = {
            "Authorization": f"Bearer {ANIME_SCHEDULE_TOKEN}"
        }
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Erreur API: status code {response.status_code}")
            return []
            
    except Exception as e:
        print(f"Erreur lors de la récupération des données: {e}")
        return []

def clean_title(title):
    """Nettoie un titre pour la comparaison"""
    # Enlève les numéros d'épisode, VOSTFR, VF, etc.
    title = re.sub(r'\s*(?:–|-|:)?\s*(?:Episode|Ep\.?)?\s*\d+(?:\.\d+)?\s*(?:VOSTFR|VF)?$', '', title, flags=re.IGNORECASE)
    # Enlève les numéros de saison
    title = re.sub(r'\s*(?:Saison|Season|S)\s*\d+', '', title, flags=re.IGNORECASE)
    # Enlève la ponctuation et les espaces multiples
    title = re.sub(r'[^\w\s]', ' ', title)
    title = ' '.join(title.split())
    return title.lower()

def match_anime_title(mavanimes_title, api_data):
    """Trouve la correspondance entre un titre de mavanimes et les données de l'API"""
    best_match = None
    best_ratio = 0
    clean_mav_title = clean_title(mavanimes_title)
    
    for anime in api_data:
        titles_to_check = [
            anime.get('title', ''),
            anime.get('english', ''),
            anime.get('romaji', '')
        ]
        
        for api_title in titles_to_check:
            if not api_title:
                continue
                
            clean_api_title = clean_title(api_title)
            
            if clean_mav_title == clean_api_title:
                return anime
            
            if clean_mav_title in clean_api_title or clean_api_title in clean_mav_title:
                ratio = len(min(clean_mav_title, clean_api_title)) / len(max(clean_mav_title, clean_api_title))
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = anime
            
            ratio = SequenceMatcher(None, clean_mav_title, clean_api_title).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = anime

    return best_match if best_ratio > 0.8 else None 