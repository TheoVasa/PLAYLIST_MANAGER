# Playlist Manager

A comprehensive Python-based system for managing music playlists using Spotify API, YouTube search, and Google Drive integration. The system uses an Excel file as a database to track songs, fetch metadata, find YouTube links, and automatically download and upload tracks to Google Drive.

## Features

- **Playlist Generation**: Fetch popular tracks by genre from Spotify
- **Metadata Enrichment**: Automatically retrieve song metadata (album, release date, popularity, explicit content)  
- **YouTube Link Discovery**: Find corresponding YouTube videos for tracks
- **Automated Download & Upload**: Download tracks from YouTube and upload to Google Drive
- **Excel Database**: Manage everything through a structured Excel file

## Prerequisites

- Python 3.7+
- Firefox browser (for cookie extraction in downloads) (can be changed)
- FFmpeg (for audio processing)

## Installation

1. Clone the repository
2. Install dependencies (here using pip):
```bash
pip install -r requirements.txt
```

## Setup

### 1. Excel File Setup

The system uses `Programmation_template.xlsx` with two main sheets:

#### Sheet 1: "TITRES" (Tracks)
Contains columns:
- `PLAYLIST`: Name of the playlist
- `ARTISTE`: Artist name(s)
- `TITRE`: Song title
- `ALBUM`: Album name (auto-filled)
- `SORTIE`: Release date (auto-filled)
- `LIEN`: YouTube URL (auto-filled)
- `CONFIANCE`: Confidence score for YouTube match (auto-filled)
- `TELECHARGE`: Download status (auto-filled)
- `POPULARITE`: Spotify popularity score (auto-filled)
- `EXPLICITE`: Whether song contains explicit content (auto-filled)

#### Sheet 2: "NOM PLAYLISTS" 
Contains a single column `Playlists` with all available playlist names.

### 2. Spotify API Credentials

1. Go to [Spotify for Developers](https://developer.spotify.com/)
2. Log in and create a new app
3. Note your `Client ID` and `Client Secret`
4. Create `credentials/spotify_credentials.json`:

```json
{
  "type": "spotify_credentials",
  "client_id": "YOUR_SPOTIFY_CLIENT_ID",
  "client_secret": "YOUR_SPOTIFY_CLIENT_SECRET"
}
```

### 3. Google Drive API Setup

#### Step 1: Create a Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Drive API

#### Step 2: Create Service Account
1. Go to "IAM & Admin" > "Service Accounts"
2. Click "Create Service Account"
3. Fill in the details and click "Create"
4. Skip role assignment and click "Done"

#### Step 3: Generate Credentials
1. Click on your service account
2. Go to "Keys" tab
3. Click "Add Key" > "Create New Key"
4. Select "JSON" format
5. Download the file and rename it to `service_account.json`
6. Place it in `credentials/service_account.json`

#### Step 4: Share Drive Folder
1. Create a folder in Google Drive where you want to upload music, it needs to be in a **shared drive**.
2. Share this folder with your service account email (found in the JSON file as `client_email`)
3. Give it "Editor" permissions

### 4. Directory Structure

```
project/
├── credentials/
│   ├── spotify_credentials.json
│   └── service_account.json
├── cache/                          # Temporary download folder
├── Programmation_template.xlsx     # Main database
├── bot_downloader.py              # Download & upload to Drive
├── excel_reader.py                # Excel manipulation utilities
├── metadata.py                    # Spotify metadata fetcher
├── playlist_fetcher.py            # Generate playlists from Spotify
├── ytb_finder_fast.py            # Find YouTube links
└── requirements.txt
```

## Usage

### 1. Generate Playlist (`playlist_fetcher.py`)

Fetch popular tracks from Spotify by genre:

```bash
python playlist_fetcher.py
```

The script will:
- Ask for a search keyword (e.g., "Rap FR", "Pop Rock")
- Ask for number of tracks to fetch
- Ask for playlist name (must exist in Excel)
- Add tracks to your Excel file

### 2. Enrich with Metadata (`metadata.py`)

Fetch additional metadata from Spotify:

```bash
python metadata.py
```

This will:
- Add album names, release dates, popularity scores
- Mark explicit content
- Only process tracks missing metadata

### 3. Find YouTube Links (`ytb_finder_fast.py`)

Search for corresponding YouTube videos:

```bash
python ytb_finder_fast.py
```

Features:
- Prioritizes official channels and auto-generated content
- Assigns confidence scores (0-4)
- Only processes tracks without links
- Optimized rate limiting to avoid YouTube blocks

### 4. Download and Upload (`bot_downloader.py`)

Download tracks and upload to Google Drive:

```bash
python bot_downloader.py
```

The script will:
- Ask for your Google Drive folder link
- Option to process specific playlist or all
- Download tracks from YouTube
- Add metadata to MP3 files
- Upload to Google Drive organized by playlist
- Mark tracks as downloaded in Excel
- Clean up local files

## Configuration

### Rate Limiting
All scripts include intelligent rate limiting to avoid API blocks:
- Spotify: Progressive delays with longer pauses every 100 requests
- YouTube: Random delays with batch processing
- Google Drive: Built-in retry mechanisms

### File Naming
Downloaded files are automatically sanitized:
- Special characters replaced with underscores
- Long filenames truncated
- Format: `Artist - Title.mp3`

### Error Handling
- Failed downloads are logged and can be retried
- Excel is saved periodically to prevent data loss
- Network errors trigger automatic pauses

## Troubleshooting

### Common Issues

1. **Spotify API Errors**
   - Check your credentials in `credentials/spotify_credentials.json`
   - Ensure your Spotify app has correct settings

2. **Google Drive Upload Fails**
   - Verify service account has access to target folder
   - Check that `service_account.json` is properly formatted
   - Ensure the folder ID in the Drive link is correct

3. **YouTube Search Errors**
   - Script includes automatic retry logic
   - If persistent, try running with longer delays

4. **Excel File Issues**
   - Don't edit Excel file while scripts are running
   - Ensure playlist names match exactly between sheets
   - Check that all required columns exist

### Performance Tips

- Run scripts during off-peak hours for better API performance
- Process playlists in smaller batches if experiencing timeouts
- Keep Excel file closed while scripts are running

## Security Notes

- Keep your credentials files private and never commit them to version control
- The service account only has access to folders you explicitly share
- Spotify credentials only allow reading public data

## License

This project is for educational and personal use. Respect YouTube's terms of service and copyright laws when downloading content.