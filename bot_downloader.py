
import os
import json
import pandas as pd
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from yt_dlp import YoutubeDL
from tqdm import tqdm
import warnings
import re
from excel_reader import ExcelReader
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# Google Drive
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from googleapiclient.discovery import build

def authenticate_service_account(service_account_file, scopes):
    """ Fonction pour authentifier le compte de service Google Drive.
    """
    creds = service_account.Credentials.from_service_account_file(
        service_account_file,
        scopes=scopes
    )
    return build('drive', 'v3', credentials=creds)

def upload_to_shared_drive(file_path, drive_service, folder_id):
    """ Fonction pour uploader un fichier dans un dossier partagé sur Google Drive.
    """
    file_name = os.path.basename(file_path)
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, mimetype='audio/mpeg')
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id',
        supportsAllDrives=True
    ).execute()
    return file.get('id')

def get_or_create_drive_folder(service, folder_name, parent_id=None, drive_id=None):
    """
    Récupère ou crée un dossier (compatible Drive partagé).
    """
    # Échapper les apostrophes dans le nom
    safe_name = folder_name.replace("'", "\\'")

    # Construire la requête
    query = f"mimeType='application/vnd.google-apps.folder' and name='{safe_name}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    list_kwargs = {
        "q": query,
        "spaces": "drive",
        "fields": "files(id, name, parents)",
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
    }

    # Si on sait qu'on est dans un Drive partagé, précisons le corpus
    if drive_id:
        list_kwargs["corpora"] = "drive"
        list_kwargs["driveId"] = drive_id
    else:
        # À défaut, chercher partout
        list_kwargs["corpora"] = "allDrives"

    results = service.files().list(**list_kwargs).execute()
    folders = results.get('files', [])

    if folders:
        return folders[0]['id']

    metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
    }
    if parent_id:
        metadata['parents'] = [parent_id]

    folder = service.files().create(
        body=metadata,
        fields='id',
        supportsAllDrives=True
    ).execute()
    return folder.get('id')

def download_and_upload_to_drive(excel_reader, tracks_df, sheet_name, service_account_file, scopes, parent_folder_id, cache_root):
    """
    Fonction principale pour télécharger les morceaux depuis YouTube et les uploader sur Google Drive.
    """
    # Authentification Google Drive
    drive_service = authenticate_service_account(service_account_file, scopes)
    # === TÉLÉCHARGEMENT DES MORCEAUX ===
    # Créer le dossier racine de téléchargement cache
    os.makedirs(cache_root, exist_ok=True)
    # Barre de progression
    for idx, row in tqdm(tracks_df.iterrows(), total=len(tracks_df), desc="Téléchargement des morceaux"):
        playlist = row['PLAYLIST']  # Nom de la playlist
        artiste_raw = str(row['ARTISTE'])  # Nom de l'artiste
        titre =  str(row['TITRE'])  # Titre de la chanson
        album = str(row['ALBUM'])  # Nom de l'album
        date = row['SORTIE']  # Date de sortie
        youtube_url = row['LIEN']  # URL YouTube

        # Extraction des artistes
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
        main_artist = artist_names_raw[0] if artist_names_raw else ""
        # Créer le nom du fichier
        filename = f"{artiste_raw} - {titre}.mp3".replace("/", "_").replace("\\", "_")
        # éviter les noms de fichiers trop longs
        if len(filename) > 100:
            filename = f"{main_artist} - {titre}.mp3".replace("/", "_").replace("\\", "_")
        if len(filename) > 100:
            filename = f"{titre}.mp3".replace("/", "_").replace("\\", "_")
        if len(filename) > 100:
            filename = filename[:95] + "(...).mp3"
        
        # Créer le dossier de la playlist
        #sanitize le nom de la playlist
        playlist = playlist.replace("/", "_").replace("\\", "_")
        playlist_folder = os.path.join(cache_root, playlist)
        os.makedirs(playlist_folder, exist_ok=True)

        output_path = os.path.join(playlist_folder, filename)

        # Configuration de yt-dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'cookiesfrombrowser': ('firefox',),  # Utiliser les cookies de Firefox
            'outtmpl': output_path.replace(".mp3", ".%(ext)s"),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,           # Supprime tous les logs standards
            'no_warnings': True,      # Supprime les warnings
        }

        # Téléchargement et upload vers Google Drive
        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([youtube_url])
                # rajoute les metadonnée présentent sur l'excel dans le fichier mp3 (titre, artiste, album, date, explicit)
                audio = MP3(output_path, ID3=EasyID3)
                audio['title'] = titre
                audio['artist'] = artiste_raw
                audio['album'] = album if pd.notna(album) else "Inconnu"
                audio['date'] = str(date) if pd.notna(date) else "Inconnu"
                audio.save()
                # Crée ou récupère le dossier de la playlist dans le dossier racine
                drive_playlist_folder_id = get_or_create_drive_folder(drive_service, playlist, parent_id=parent_folder_id)
                # Upload vers Google Drive
                # Upload le fichier dans le bon dossier
                upload_to_shared_drive(output_path, drive_service, drive_playlist_folder_id)
                print(f"Uploadé : {filename} (ID Drive : {drive_playlist_folder_id})")
                # Supprimer le fichier local après l'upload
                os.remove(output_path)
                print(f"Supprimé localement : {filename}")
                # mettre à jour la valeur de la colonne 'TELECHARGEMENT' dans l'Excel
                excel_reader.update_row(sheet_name, idx, {
                    'TELECHARGE': 'VRAI',  # Marquer comme téléchargé
                })
                excel_reader.save()  # Enregistrer les modifications dans l'Excel
        except Exception as e:
            print(f"\nErreur lors du téléchargement de {titre} ({youtube_url}) : {e}")
    return


if __name__ == "__main__":
    # === CONFIGURATION ===
    EXCEL_FILE = "Programmation_template.xlsx"  # Remplace par le nom du fichier
    DOWNLOAD_ROOT = "cache"    # Dossier racine des téléchargements
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    SERVICE_ACCOUNT_FILE = "credentials/service_account.json"  # Fichier de compte de service
    with open(SERVICE_ACCOUNT_FILE, 'r') as file:
        CLIENT_EMAIL = json.load(file)['client_email']  # Email du compte de service
    SHEET_NAME = "TITRES"  # Nom de la feuille dans le fichier Excel
    EXCEL_READER = ExcelReader(EXCEL_FILE)
    
    print("==================================================================================================")
    print("Bienvenue dans l'uploader de playlist dans google drive !                                        |")
    print("Ce programme va uploader automatiquement les titres de titres.xlsx dans un dossier Google Drive. |")
    print("                                                                                                 |")
    print("-> Il va seulement uploader les titres avec la valeur VRAI dans la colonne TELECHARGEMENTS       |")
    print("                                                                                                 |")
    print("-> vérifier que le compte de service ait bien accès au dossier partagé (en édition)              |")
    print(f"--> mail du compte de service : {CLIENT_EMAIL}      |")
    print("                                                                                                 |")
    print("-> Il a besoin d'un fichier JSON avec des credentials d'un compte de service valide sous:        |")
    print(f"--> {SERVICE_ACCOUNT_FILE}                                                             |")
    print("                                                                                                 |")
    print("Appuyez sur Ctrl+C pour arrêter le programme                                                     |")
    print("==================================================================================================")
    df = EXCEL_READER.read_dataframe(SHEET_NAME)
    df = df[df['TELECHARGE'] == False]
    print(f"Il y a {len(df)} titres à uploader dans l'Excel '{EXCEL_FILE}' (feuille '{SHEET_NAME}')")
    
    # demander à l'utilisateur de donner le lien du dossier partagé dans Google Drive
    shared_folder_link = input("--> Veuillez entrer le lien du dossier partagé dans Google Drive : ")
    # check si le lien est valide
    while not shared_folder_link.startswith("https://drive.google.com/drive/folders/"):
        shared_folder_link = input("Lien invalide. Veuillez entrer un lien valide : ")
    # extraire l'ID du dossier partagé
    PARENT_FOLDER_ID = shared_folder_link.split("/")[-1].split("?")[0]  # Prend la dernière partie du lien avant le '?'
    print(f"ID du dossier partagé : {PARENT_FOLDER_ID}")
    # demander à l'utilisateur si il veut uploader une playlist spécifique ou toutes les playlists
    print("Voulez-vous uploader une playlist spécifique ou toutes les playlists ?")
    print("1 - Uploader une playlist spécifique")
    print("2 - Uploader toutes les playlists")
    choice = input("Entrez 1 ou 2 : ")
    if choice == "1":
        playlist_name = input("Entrez le nom exact de la playlist à uploader (ex: 'Jazz') : ")
        # vérifier que la playlist existe dans l'Excel
        available_playlists = EXCEL_READER.get_playlist_names()
        if playlist_name not in available_playlists:
            print(f"La playlist '{playlist_name}' n'existe pas dans l'Excel. Les playlists disponibles sont : {available_playlists}")
            exit()
        # filtrer l'Excel pour ne garder que les titres de la playlist spécifiée
        df = df[df['PLAYLIST'] == playlist_name]
        print(f"Uploader uniquement la playlist : {playlist_name} ({len(df)} titres)")
    elif choice == "2":
        print("Uploader toutes les playlists.")
    else:
        print("Choix invalide. Uploader toutes les playlists par défaut.")
    # demander à l'utilisateur de confirmer le début du téléchargement
    confirm = input("Voulez-vous commencer le téléchargement ? (O/N) : ")
    if confirm.lower() != 'o':
        print("Téléchargement annulé.")
        exit()
    # Lancer le téléchargement et l'upload
    download_and_upload_to_drive(EXCEL_READER, df, SHEET_NAME, SERVICE_ACCOUNT_FILE, SCOPES, PARENT_FOLDER_ID, DOWNLOAD_ROOT)
    print("Téléchargement et upload terminés.")
    print("Tous les fichiers ont été uploadés et les entrées Excel mises à jour.")

        


    

