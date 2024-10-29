import re
from datetime import datetime

def clean_title(title):
    """Nettoie un titre d'anime"""
    title = re.sub(r'[-–]\s*(?:Episode)?\s*\d+(?:\.\d+)?.*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'vostfr|vf', '', title, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', title).strip()

def extract_episode_number(title):
    """Extrait le numéro d'épisode d'un titre"""
    match = re.search(r'[-–]\s*(?:Episode)?\s*(\d+(?:\.\d+)?)', title, re.IGNORECASE)
    return match.group(1) if match else None

def format_date(date):
    """Formate une date en français"""
    if isinstance(date, datetime):
        return date.strftime('%d/%m/%Y à %H:%M')
    return date 