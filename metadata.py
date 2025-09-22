import pandas as pd
import re
from excel_reader import ExcelReader
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from tqdm import tqdm
import time
import warnings
import random
import json
from functools import lru_cache
from typing import Optional, Dict, Tuple
import os

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

class SpotifyMetadataFetcher:
    def __init__(self, excel_reader, sheet_name, client_id=None, client_secret=None):
        self.excel_reader = excel_reader
        self.sheet_name = sheet_name
        self.request_count = 0
        self.last_request_time = time.time()
        self.track_cache = {}
        
        # Configuration Spotify
        if client_id and client_secret:
            self.client_id = client_id
            self.client_secret = client_secret
        else:
            # Récupérer depuis les variables d'environnement
            self.client_id = os.getenv('SPOTIFY_CLIENT_ID')
            self.client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        
        if not self.client_id or not self.client_secret:
            raise ValueError("Les credentials Spotify doivent être fournis (client_id, client_secret) ou définis dans les variables d'environnement")
        
        # Initialiser le client Spotify
        try:
            client_credentials_manager = SpotifyClientCredentials(
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            self.sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
            print("✓ Connexion à Spotify API réussie")
        except Exception as e:
            raise Exception(f"Erreur lors de l'initialisation de Spotify API: {e}")
    
    def sanitize_string(self, s):
        """Nettoyer une chaîne de caractères pour la recherche."""
        if not s:
            return ""
        # Supprimer les caractères spéciaux mais garder les espaces
        s = re.sub(r'[^\w\s\-]', '', s)
        return s.strip()
    
    def normalize_artist_name(self, artist_name):
        """Normaliser le nom d'artiste pour la recherche."""
        if not artist_name:
            return ""
        
        # Supprimer ce qui est entre parenthèses
        artist_name = re.sub(r'\(.*?\)', '', artist_name)
        
        # Remplacer les différentes mentions de feat., ft., avec, et, & par une virgule
        separators = [r"\s+feat\.?\s+", r"\s+ft\.?\s+", r"\s+avec\s+", r"\s+et\s+", r"\s*&\s*"]
        for sep in separators:
            artist_name = re.sub(sep, ',', artist_name, flags=re.IGNORECASE)
        
        # Remplacer les points-virgules par des virgules
        artist_name = re.sub(r'\s*;\s*', ',', artist_name)
        
        return artist_name.strip()
    
    def normalize_title(self, title):
        """Normaliser le titre pour la recherche."""
        if not title:
            return ""
        
        # Supprimer les feat/ft du titre
        pattern = r'[\(\[\-]?\s*(feat|ft|with|avec|et)\b.*$'
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)
        
        return self.sanitize_string(title)
    
    def rate_limit(self):
        """Gestion du rate limiting pour respecter les limites Spotify."""
        self.request_count += 1
        
        # Pause progressive basée sur le nombre de requêtes
        if self.request_count % 20 == 0:
            delay = random.uniform(1, 2)
            time.sleep(delay)
        elif self.request_count % 100 == 0:
            print("Pause longue pour respecter les limites de l'API...")
            time.sleep(random.uniform(5, 10))
        else:
            # Délai minimum entre requêtes
            time.sleep(random.uniform(0.1, 0.3))
    
    @lru_cache(maxsize=1000)
    def search_spotify_track(self, artist_name: str, title: str) -> Optional[Dict]:
        """
        Rechercher une piste sur Spotify avec mise en cache.
        """
        cache_key = f"{artist_name}_{title}"
        if cache_key in self.track_cache:
            return self.track_cache[cache_key]
        
        self.rate_limit()
        
        try:
            # Essayer différentes variantes de requête
            queries = [
                f'artist:"{artist_name}" track:"{title}"',  # Recherche exacte
                f'{artist_name} {title}',  # Recherche simple
                f'"{title}" {artist_name}'  # Titre en premier
            ]
            
            for query in queries:
                results = self.sp.search(q=query, type='track', limit=10, market='FR')
                tracks = results['tracks']['items']
                
                if tracks:
                    # Trouver la meilleure correspondance
                    best_match = self.find_best_match(tracks, artist_name, title)
                    if best_match:
                        self.track_cache[cache_key] = best_match
                        return best_match
            
            return None
            
        except Exception as e:
            print(f"Erreur lors de la recherche Spotify pour '{artist_name} - {title}': {e}")
            return None
    
    def find_best_match(self, tracks, target_artist, target_title):
        """
        Trouver la meilleure correspondance parmi les résultats Spotify.
        """
        target_artist_clean = self.sanitize_string(target_artist).lower()
        target_title_clean = self.sanitize_string(target_title).lower()
        
        best_score = 0
        best_track = None
        
        for track in tracks:
            # Vérifier les artistes
            artist_names = [artist['name'] for artist in track['artists']]
            artist_match = any(
                target_artist_clean in self.sanitize_string(name).lower() 
                or self.sanitize_string(name).lower() in target_artist_clean
                for name in artist_names
            )
            
            # Vérifier le titre
            track_title_clean = self.sanitize_string(track['name']).lower()
            title_match = (
                target_title_clean in track_title_clean 
                or track_title_clean in target_title_clean
            )
            
            # Calculer le score
            score = 0
            if artist_match and title_match:
                score = 3
            elif artist_match:
                score = 2
            elif title_match:
                score = 1
            
            if score > best_score:
                best_score = score
                best_track = track
        
        return best_track if best_score >= 2 else None
    
    def extract_metadata(self, track: Dict, audio_features: Optional[Dict] = None) -> Dict:
        """
        Extraire les métadonnées d'une piste Spotify.
        """
        metadata = {
            'ALBUM': track['album']['name'],
            'SORTIE': track['album']['release_date'],
            'POPULARITE': track['popularity'],
            'EXPLICITE': track['explicit']
        }
  
        return metadata
    
    def process_track(self, row_data: Tuple[int, pd.Series]) -> Dict:
        """
        Traiter une piste individuellement.
        """
        idx, row = row_data
        
        try:
            # Normaliser les données d'entrée
            artiste_raw = str(row['ARTISTE'])
            titre_raw = str(row['TITRE'])
            
            artiste_normalized = self.normalize_artist_name(artiste_raw)
            titre_normalized = self.normalize_title(titre_raw)
            
            # Prendre le premier artiste pour la recherche
            main_artist = artiste_normalized.split(',')[0].strip() if ',' in artiste_normalized else artiste_normalized
            
            # Rechercher sur Spotify
            track = self.search_spotify_track(main_artist, titre_normalized)
            
            if track:
                
                # Extraire les métadonnées
                metadata = self.extract_metadata(track)
                
                result = {
                    'idx': idx,
                    **metadata
                }
            else:
                result = {
                    'idx': idx,
                    'ALBUM': 'NaN',
                    'SORTIE': 'NaN',
                    'POPULARITE': 'NaN',
                    'EXPLICITE': 'NaN'
                }
            
            return result
            
        except Exception as e:
            print(f"Erreur lors du traitement de la ligne {idx}: {e}")
            return {
                'idx': idx,
                'ALBUM': 'NaN',
                'SORTIE': 'NaN',
                'POPULARITE': 'NaN',
                'EXPLICITE': 'NaN'
            }
    
    def process(self, tracks: pd.DataFrame):
        """
        Traiter les pistes avec gestion des erreurs et sauvegarde périodique.
        """
        total = len(tracks)
        
        with tqdm(total=total, desc="Récupération des métadonnées Spotify") as pbar:
            for idx, row in tracks.iterrows():
                result = self.process_track((idx, row))
                
                # Préparer les données pour la mise à jour
                update_data = {k: v for k, v in result.items() if k != 'idx'}
                
                # Mise à jour immédiate dans Excel
                self.excel_reader.update_row(
                    self.sheet_name, 
                    result['idx'],
                    update_data
                )
                
                # Sauvegarde périodique
                if (pbar.n + 1) % 10 == 0:
                    self.excel_reader.save()
                
                pbar.update(1)
                
                # Gestion des erreurs d'API
                if result.get('STATUT') == 'ERREUR':
                    print(f"Erreur détectée ligne {idx}, pause...")
                    time.sleep(random.uniform(2, 5))
        
        # Sauvegarde finale
        self.excel_reader.save()
        print("Sauvegarde finale effectuée")


# Exécution principale
if __name__ == "__main__":
    EXCEL_FILE = "Programmation_template.xlsx"
    EXCEL_READER = ExcelReader(EXCEL_FILE)
    SHEET_NAME = "TITRES"
    
    # Charger le fichier Excel
    df = EXCEL_READER.read_dataframe(SHEET_NAME)

    # json file with your Spotify API credentials
    SPOTIFY_CREDENTIALS_FILE = "credentials/spotify_credentials.json"
    # Load Spotify credentials from JSON file
    with open(SPOTIFY_CREDENTIALS_FILE, 'r') as file:
        credentials = json.load(file)
    CLIENT_ID = credentials['client_id']
    CLIENT_SECRET= credentials['client_secret']
    
    # Filtrer uniquement les lignes où les métadonnées Spotify ne sont pas encore récupérées
    # On peut filtrer sur une colonne existante ou traiter toutes les lignes
    df_to_process = df[df['ALBUM'].isna() | df['SORTIE'].isna() | df['EXPLICITE'].isna() | df['POPULARITE'].isna()]
    
    print("=" * 90)
    print("Bienvenue dans le récupérateur de métadonnées Spotify!")
    print("Ce programme va enrichir votre fichier Excel avec les métadonnées Spotify.")
    print(f"Nombre de titres à traiter: {len(df_to_process)}")
    print(f"Le fichier {EXCEL_FILE} sera mis à jour avec les métadonnées trouvées.")
    print("Métadonnées récupérées:")
    print("  - Album")
    print("  - Date de sortie")
    print("  - Explicite")
    print("  - Popularité")
    print("Appuyez sur Ctrl+C pour arrêter le programme")
    print("=" * 90)
    
    try:
        # Initialiser le récupérateur (les credentials peuvent être dans les variables d'environnement)
        fetcher = SpotifyMetadataFetcher(EXCEL_READER, SHEET_NAME, client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
        
        # Traiter les pistes
        fetcher.process(df_to_process)
        
        print("\n-> Les métadonnées ont été écrites dans le tableau Excel.")
        print(f"-> Nombre total de requêtes effectuées: {fetcher.request_count}")
        
    except Exception as e:
        print(f"Erreur lors de l'initialisation: {e}")
        print("Vérifiez que vos credentials Spotify sont correctement configurés.")