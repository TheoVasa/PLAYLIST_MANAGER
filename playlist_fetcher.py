import musicbrainzngs
import requests
import base64
import time
import json
from excel_reader import ExcelReader

# === CONFIGURATION ===
# spotify credentials
# json file with your Spotify API credentials
SPOTIFY_CREDENTIALS_FILE = "credentials/spotify_credentials.json"
# Load Spotify credentials from JSON file
with open(SPOTIFY_CREDENTIALS_FILE, 'r') as file:
    credentials = json.load(file)
CLIENT_ID = credentials['client_id']
CLIENT_SECRET= credentials['client_secret']
titres = []  # liste des titres récupérés
EXCEL_FILE = "Programmation_template.xlsx"  # Remplace par le nom de ton fichier
EXCEL_READER = ExcelReader(EXCEL_FILE)
PRESENT_TITLES = EXCEL_READER.read_dataframe("TITRES")  # lire les titres déjà présents dans l'Excel

musicbrainzngs.set_useragent("RadioPlaylistBuilder", "1.0", "email@exemple.com")


def get_spotify_token():
    """Obtient un token d'accès Spotify via Client Credentials Flow."""
    auth_str = f"{CLIENT_ID}:{CLIENT_SECRET}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials"}
    r = requests.post("https://accounts.spotify.com/api/token", headers=headers, data=data)
    r.raise_for_status()
    return r.json()["access_token"]

def search_playlists(query, token, limit=5, offset=0):
    """Recherche des playlists sur Spotify."""
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "q": query,
        "type": "playlist",
        "limit": limit,
        "offset": offset
    }
    response = requests.get("https://api.spotify.com/v1/search", headers=headers, params=params)

    if response.status_code != 200:
        print("Erreur lors de la recherche :", response.json())
        return []

    data = response.json()
    playlists = data.get("playlists", {}).get("items", [])
    return playlists

def get_playlist_tracks(playlist_id, token):
    """Récupère les titres d'une playlist Spotify."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print("Erreur lors de la récupération des titres :", response.json())
        return []

    tracks_data = response.json().get("items", [])
    track_infos = []

    for item in tracks_data:
        track = item.get("track")
        if not track:
            continue
        title = track.get("name", "Sans titre")
        artists = track.get("artists", [])
        artist_names = [artist.get("name", "Artiste inconnu") for artist in artists]
        track_infos.append((title, artist_names))

    return track_infos

def get_spotify_popularity(artist, title, token):
    """Recherche la popularité d'un titre sur Spotify."""
    query = f"track:{title} artist:{artist}"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": query, "type": "track", "limit": 1}
    r = requests.get("https://api.spotify.com/v1/search", headers=headers, params=params)
    if r.status_code != 200:
        return 0
    results = r.json()
    items = results.get("tracks", {}).get("items", [])
    if items:
        return items[0].get("popularity", 0)
    return 0

# Fonction pour trier les titres par popularité spotify
def sort_by_popularity(tracks):
    """
    Trie la liste de tuples (artiste, titre, popularité) par popularité décroissante.
    """
    return sorted(tracks, key=lambda x: x[2], reverse=True)

# récupère n titres populaires par genre en utilisant les playlists Spotify
def get_tracks_by_genre(genre, n=100, token=None):
    if token is None: print("Token Spotify manquant.")
    fetched_tracks = []
    needed_tracks = n*2 # pour récupérer plus de titres et pouvoir trier par popularité
    offset = 0
    limit = 1
    print(f"Recherche de {n} titres populaires pour le genre '{genre}'...")
    while len(fetched_tracks) < needed_tracks:
        playlists = search_playlists(genre, token, limit, offset)
        if not playlists:
            print(f"Aucune playlist trouvée pour le genre '{genre}'.")
            return []

        for pl in playlists:
            if not pl:
                continue
            tracks = get_playlist_tracks(pl['id'], token)
            for title, artists in tracks:
                # sanitize nom artiste et titre 
                for i in range(len(artists)):
                    artists[i] = str(artists[i]).replace("/", "_").replace("\\", "_")
                    if artists[i] is None: artists[i] = "Artiste inconnu"
                title = str(title).replace("/", "_").replace("\\", "_")
                if title is None: title = "Titre inconnu"
                
                if isinstance(artists, list): artist = ", ".join(artists)
                else: artist = artists
                # récupérer popularité Spotify
                popularity = get_spotify_popularity(artist, title, token)
                fetched_tracks.append((artist, title, popularity))
                time.sleep(0.1)  # pour éviter le throttling
        # incrémenter l'offset pour la prochaine requête
        offset += limit
        # enlever les doublons
        fetched_tracks = list(set(fetched_tracks))
        # enlever les titres déjà présents dans l'Excel
        fetched_tracks = [track for track in fetched_tracks if (track[0], track[1]) not in zip(PRESENT_TITLES['ARTISTE'], PRESENT_TITLES['TITRE'])]
    # Trier par popularité décroissante
    fetched_tracks = sort_by_popularity(fetched_tracks)
    # retourner les n premiers titres
    return fetched_tracks[:n]

# Exécution principale
if __name__ == "__main__":
    # ==== INTERAGIR AVEC L'UTILISATEUR ====
    print("=========================================================================================")
    print("Bienvenue dans le générateur de playlist !                                              |")
    print("Ce programme va récupérer des titres populaires sur Spotify par genre.                  |")
    print("                                                                                        |")
    print(f"Le fichier {EXCEL_FILE} sera mis à jour avec les titres récupérés.                       |")
    print("Appuyez sur Ctrl+C pour arrêter le programme                                            |")
    print("=========================================================================================")
    genre = input("--> Veuillez entrer le mot clé de recherche pour spotify (par exemple, 'Rap FR') : ")
    n = input("--> Veuillez entrer le nombre de titres à récupérer (par exemple, 150) : ")
    while not n.isdigit() or int(n) <= 0:
        n = input("---> Veuillez entrer un nombre valide pour le nombre de titres : ")
    n = int(n)  # convertir en entier

    playlist_name = input("--> Veuillez entrer le nom de la playlist pour l'Excel (par exemple, 'Hip-hop/Rap FR') : ")
    while not playlist_name.strip() in EXCEL_READER.get_playlist_names():
        print(f"Le nom de la playlist '{playlist_name}' n'existe pas dans le fichier Excel.")
        print("Voici les playlists existantes :")
        for name in EXCEL_READER.get_playlist_names():
            print(f"- {name}")
        playlist_name = input("---> Veuillez entrer un nom de playlist valide : ")
    print("------------------------------------------------------------------------------------------")
    token = get_spotify_token()
    tracks = get_tracks_by_genre(genre, n, token)
    
    if not tracks:
        print("Aucun titre trouvé.")
    else:
        print(f"{len(tracks)} titres trouvés pour le genre '{genre}':")
        for artist, title, popularity in tracks:
            print(f"{artist} - {title} (Popularité: {popularity})")
            # ajouter les titres à l'Excel
        valid = input("Voulez-vous ajouter ces titres à l'Excel ? (oui/non) : ").strip().lower()
        if valid in ['oui', 'o']:
            for artist, title, popularity in tracks:
                # ajouter les titres à l'Excel
                EXCEL_READER.append_row("TITRES", {"PLAYLIST": playlist_name, "ARTISTE": artist, "TITRE": title, "LIEN": ""})
            print(f"{len(tracks)} titres ajoutés à la playlist '{playlist_name}' dans l'Excel.")
            EXCEL_READER.save()
        else:
            print("Aucun titre ajouté à l'Excel. Essayez d'autres genres ou mots-clés de recherche.")