from functools import lru_cache
import time
import json
import os

class APICache:
    def __init__(self, cache_file="api_cache.json", expire_time=3600):
        self.cache_file = cache_file
        self.expire_time = expire_time
        self.cache = self._load_cache()

    def _load_cache(self):
        """Charge le cache depuis le fichier"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    # Nettoyer les entrées expirées
                    now = time.time()
                    data = {k: v for k, v in data.items() 
                           if v['timestamp'] + self.expire_time > now}
                    return data
        except Exception as e:
            print(f"Erreur de chargement du cache: {e}")
        return {}

    def _save_cache(self):
        """Sauvegarde le cache dans le fichier"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f)
        except Exception as e:
            print(f"Erreur de sauvegarde du cache: {e}")

    def get(self, key):
        """Récupère une valeur du cache"""
        if key in self.cache:
            data = self.cache[key]
            if data['timestamp'] + self.expire_time > time.time():
                return data['value']
            del self.cache[key]
        return None

    def set(self, key, value):
        """Ajoute une valeur au cache"""
        self.cache[key] = {
            'value': value,
            'timestamp': time.time()
        }
        self._save_cache() 