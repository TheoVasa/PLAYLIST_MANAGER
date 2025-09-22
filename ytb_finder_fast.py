import pandas as pd
import re
from excel_reader import ExcelReader
from youtubesearchpython import VideosSearch, ChannelsSearch, Video
from tqdm import tqdm
import time
import warnings
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import requests
import traceback
from typing import Optional, Dict, Tuple

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# Configuration pour éviter les erreurs 403
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

class YouTubeSearcher:
    def __init__(self, excel_reader, sheet_name):
        self.excel_reader = excel_reader
        self.sheet_name = sheet_name
        self.artist_channel_cache = {}
        self.request_count = 0
        self.last_request_time = time.time()
        
    def sanitize_string(self, s):
        """Nettoyer une chaîne de caractères."""
        if not s:
            return ""
        # Supprimer ce qu'il y a entre les parenthèse
        #s = re.sub(r'\(.*?\)', '', s)  
        #s = re.sub(r'[^\w\s]', '', s)
        s = s.replace(' ', '')
        return s.strip().lower()
    
    @lru_cache(maxsize=500)
    def get_ytb_artist_channel_name(self, artist_name):
        """
        Obtenir le nom de la chaîne YouTube de l'artiste avec mise en cache.
        Utilise l'API YouTube Search sans yt-dlp pour éviter les erreurs SABR.
        """
        if artist_name in self.artist_channel_cache:
            return self.artist_channel_cache[artist_name]
        
        try:
            query = f"{artist_name} official channel"
            search = ChannelsSearch(query, limit=1)
            channels = search.result()['result']
            
            if channels:
                channel_name = self.sanitize_string(channels[0].get('title', ''))
                self.artist_channel_cache[artist_name] = channel_name
                return channel_name
        except Exception as e:
            print(f"Erreur lors de la recherche de chaîne pour {artist_name}:")
            traceback.print_exc()
        
        return None
    
    def rate_limit(self):
        """Gestion du rate limiting pour éviter les erreurs 403."""
        self.request_count += 1
        
        # Pause progressive basée sur le nombre de requêtes
        if self.request_count % 10 == 0:
            delay = random.uniform(2, 4)
            time.sleep(delay)
        elif self.request_count % 50 == 0:
            print("Pause longue pour éviter le rate limiting...")
            time.sleep(random.uniform(10, 15))
        else:
            # Délai minimum entre requêtes
            time.sleep(random.uniform(0.5, 1.5))
    
    def search_video_lightweight(self, query: str, limit: int = 3) -> Optional[Dict]:
        """
        Recherche légère de vidéos sans utiliser yt-dlp.
        Retourne uniquement les métadonnées de base.
        """
        self.rate_limit()
        
        try:
            search = VideosSearch(query, limit=limit)
            results = search.result()['result']
            
            if results:
                # Retourner les informations de base sans extraction yt-dlp
                videos_info = []
                for video in results:
                    info = {
                        'url': video.get('link', ''),
                        'title': video.get('title', ''),
                        'channel': video.get('channel', {}).get('name', ''),
                        'duration': video.get('duration', ''),
                        'view_count': video.get('viewCount', {}).get('text', ''),
                        'published_time': video.get('publishedTime', '')
                    }
                    videos_info.append(info)
                return videos_info
            return None
            
        except Exception as e:
            print(f"Erreur lors de la recherche:")
            traceback.print_exc()
            return None
    
    def calculate_confidence_score(self, video_info: Dict, titre: str, 
                                  artist_names: list, artist_channel_name: str) -> Tuple[int, str]:
        """
        Calculer le score de confiance sans utiliser yt-dlp.
        """
        video_title = self.sanitize_string(video_info.get('title', ''))
        video_channel = self.sanitize_string(video_info.get('channel', ''))
        
        # Vérifications
        title_match = titre in video_title

        #récupère la description complète de la vidéo
        url = video_info.get('url', '')
        try: 
            desc = Video.getInfo(url).get("description") 
        except Exception as e:
            print(f"Erreur lors de la récupération de la description pour {url}: {e}")
            desc = ""

        # Vérification si c'est une vidéo auto-générée (basée sur le pattern du titre)
        is_auto_generated = any(pattern in desc for pattern in 
                              ['- Topic', 'Auto-generated', 'Provided to YouTube'])

        # Vérifications de la chaîne
        channel_exact_match = artist_channel_name and artist_channel_name == video_channel
        channel_contains_artist = any(self.sanitize_string(a) in video_channel for a in artist_names)
        
        # Attribution des scores
        if is_auto_generated:
            if title_match and channel_exact_match:
                return 4
            elif title_match and channel_contains_artist:
                return 3
        else:
            if title_match and channel_exact_match:
                return 2
            elif title_match and channel_contains_artist:
                return 1
        
        return 0
    
    def process_track(self, row_data: Tuple[int, pd.Series]) -> Dict:
        """
        Traiter une piste individuellement.
        """
        idx, row = row_data
        
        try:
            # Extraction des artistes
            artiste_raw = str(row['ARTISTE'])
            # suppression de ce qu'il y a entre parenthèses
            artiste_raw = re.sub(r'\(.*?\)', '', artiste_raw)
            # remplacer les différentes mentions de feat., ft., avec, et, & par une virgule
            separators = [r"\s+feat\.?\s+", r"\s+ft\.?\s+", r"\s+avec\s+", r"\s+et\s+", r"\s*&\s*"]
            for sep in separators: artiste_raw = re.sub(sep, ',', artiste_raw, flags=re.IGNORECASE)
            # On remplace les points virgules par une seule virgule
            artiste_raw = re.sub(r'\s*;\s*', ',', artiste_raw)
            # On supprime les espaces en début et fin de chaîne
            artiste_raw = artiste_raw.strip()
            # On récupère le nom des artistes
            artist_names_raw = artiste_raw.split(',') if ',' in artiste_raw else [artiste_raw]
            artist_names = [self.sanitize_string(name) for name in artist_names_raw]
            main_artist = artist_names[0] if artist_names else ""
            
            # Extraction du titre
            titre_raw = str(row['TITRE'])
            pattern = r'[\(\[\-]?\s*(feat|ft|with|avec|et)\b.*$'
            titre = re.sub(pattern, '', titre_raw, flags=re.IGNORECASE)
            titre = self.sanitize_string(titre)
            
            # Obtenir le nom de la chaîne de l'artiste (avec cache)
            artist_channel_name = self.get_ytb_artist_channel_name(main_artist)
            
            # Recherche 1: Vidéos auto-générées
            query_auto = f"{' '.join(artist_names_raw)}  {titre_raw} "
            videos_auto = self.search_video_lightweight(query_auto, limit=3)
            
            best_score = 0
            best_url = None
            
            if videos_auto:
                for video in videos_auto:
                    score = self.calculate_confidence_score(
                        video, titre, artist_names, artist_channel_name
                    )
                    if score > best_score:
                        best_score = score
                        best_url = video['url']
            
            # Si pas de bon résultat, recherche normale
            if best_score < 3:
                query_normal = f"{' '.join(artist_names_raw)} {titre_raw} audio"
                videos_normal = self.search_video_lightweight(query_normal, limit=1)
                
                if videos_normal:
                    for video in videos_normal:
                        score = self.calculate_confidence_score(
                            video, titre, artist_names, artist_channel_name
                        )
                        if score > best_score:
                            best_score = score
                            best_url = video['url']
            
            # Résultat final
            if best_url:
                return {
                    'idx': idx,
                    'CONFIANCE': best_score,
                    'LIEN': best_url,
                    'TELECHARGE': 'FAUX'
                }
            else:
                return {
                    'idx': idx,
                    'CONFIANCE': 'NaN',
                    'LIEN': 'NaN',
                    'TELECHARGE': 'FAUX'
                }
                
        except Exception as e:
            print(f"Erreur lors du traitement de la ligne {idx}:")
            traceback.print_exc()
            return {
                'idx': idx,
                'CONFIANCE': 'NaN',
                'LIEN': 'Erreur',
                'TELECHARGE': 'FAUX'
            }
    
    def process(self, tracks: pd.DataFrame, max_workers: int = 3):
        """
        Traiter les pistes avec gestion des erreurs 403.
        """
        results = []
        total = len(tracks)
        
        # Diviser le travail en lots pour mieux gérer le rate limiting
        batch_size = 10
        batches = [tracks.iloc[i:i+batch_size] for i in range(0, len(tracks), batch_size)]
        
        with tqdm(total=total, desc="Recherche des URLs") as pbar:
            for batch_num, batch in enumerate(batches):
                # Pause entre les lots
                if batch_num > 0:
                    time.sleep(random.uniform(3, 5))
                
                # Traitement séquentiel dans chaque lot pour éviter trop de requêtes simultanées
                for idx, row in batch.iterrows():
                    result = self.process_track((idx, row))
                    
                    # Mise à jour immédiate dans Excel
                    self.excel_reader.update_row(
                        self.sheet_name, 
                        result['idx'],
                        {
                            'CONFIANCE': result['CONFIANCE'],
                            'LIEN': result['LIEN'],
                            'TELECHARGEMENT': 'FAUX'
                        }
                    )
                    
                    # Sauvegarde périodique
                    if (pbar.n + 1) % 5 == 0:
                        self.excel_reader.save()
                    
                    pbar.update(1)
                    
                    # Gestion des erreurs 403
                    if 'Erreur' in str(result.get('LIEN', '')):
                        print("Erreur détectée, pause prolongée...")
                        time.sleep(random.uniform(30, 60))
        
        # Sauvegarde finale
        self.excel_reader.save()
        return results


# Exécution principale
if __name__ == "__main__":
    EXCEL_FILE = "Programmation_template.xlsx"
    EXCEL_READER = ExcelReader(EXCEL_FILE)
    SHEET_NAME = "TITRES"
    
    # Charger le fichier Excel
    df = EXCEL_READER.read_dataframe(SHEET_NAME)
    
    # Filtrer uniquement les lignes où la colonne 'LIEN' est vide ou 'Non trouvé'
    df = df[(df['LIEN'].isna()) | (df['LIEN'] == 'Non trouvé')]
    # drop les 400 premières lignes pour les tests

    print("=" * 90)
    print("Bienvenue dans le générateur de liens YouTube optimisé!")
    print("Ce programme va rechercher les liens YouTube pour les titres dans le fichier Excel.")
    print(f"Nombre de titres à traiter: {len(df)}")
    print(f"Le fichier {EXCEL_FILE} sera mis à jour avec les liens trouvés.")
    print("Optimisations appliquées:")
    print("  - Recherche sans yt-dlp pour éviter les erreurs SABR")
    print("  - Rate limiting intelligent pour éviter les erreurs 403")
    print("  - Mise en cache des résultats")
    print("  - Traitement par lots avec pauses")
    print("Appuyez sur Ctrl+C pour arrêter le programme")
    print("=" * 90)
    
    # Initialiser le chercheur
    searcher = YouTubeSearcher(EXCEL_READER, SHEET_NAME)
    
    # Traiter les pistes
    searcher.process(df, max_workers=1)  # Utilisation d'un seul worker pour éviter le rate limiting
    
    print("\n-> Les liens ont été écrits dans le tableau Excel.")
    print(f"-> Nombre total de requêtes effectuées: {searcher.request_count}")
    