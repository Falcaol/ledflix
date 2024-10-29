import requests
from difflib import SequenceMatcher
import logging
from cache import APICache
from typing import Optional, Dict, Any

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AnimeScheduleAPI:
    def __init__(self):
        self.base_url = "https://animeschedule.net/api/v3"
        self.cache = APICache(cache_file="anime_cache.json")
        
    def _make_request(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Effectue une requête à l'API avec gestion des erreurs"""
        try:
            url = f"{self.base_url}/{endpoint}"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.error("Timeout lors de la requête à l'API")
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de la requête à l'API: {e}")
        except ValueError as e:
            logger.error(f"Erreur de parsing JSON: {e}")
        return None

    def get_anime_info(self, title: str) -> Optional[Dict[str, Any]]:
        """Récupère les informations d'un anime avec cache"""
        # Vérifier le cache
        cache_key = f"anime_{title.lower()}"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            logger.info(f"Utilisation du cache pour {title}")
            return cached_data

        # Faire la requête API
        data = self._make_request("anime")
        if not data:
            return None

        # Trouver le meilleur match
        best_match = None
        best_ratio = 0
        clean_search = self._clean_title(title).lower()

        try:
            for anime in data:
                if not isinstance(anime, dict) or 'name' not in anime:
                    continue
                
                ratio = SequenceMatcher(None, clean_search, 
                                      anime['name'].lower()).ratio()
                if ratio > best_ratio and ratio > 0.8:
                    best_ratio = ratio
                    best_match = anime

            # Mettre en cache si un match est trouvé
            if best_match:
                self.cache.set(cache_key, best_match)
                logger.info(f"Anime trouvé et mis en cache: {title}")
            else:
                logger.warning(f"Aucun match trouvé pour: {title}")

            return best_match

        except Exception as e:
            logger.error(f"Erreur lors du traitement des données: {e}")
            return None

    @staticmethod
    def _clean_title(title: str) -> str:
        """Nettoie un titre pour la comparaison"""
        import re
        # Supprimer les parenthèses et leur contenu
        title = re.sub(r'\([^)]*\)', '', title)
        # Supprimer les caractères spéciaux
        title = re.sub(r'[^\w\s]', '', title)
        # Normaliser les espaces
        return ' '.join(title.split()) 