from bs4 import BeautifulSoup
import requests
from database import Session, Anime, Episode
from utils import get_anime_schedule_data, match_anime_title  # Importez depuis utils
from datetime import datetime
import re
