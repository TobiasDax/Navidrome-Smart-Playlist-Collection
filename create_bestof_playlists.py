"""
Creates "04 - Best of - YEAR" playlists in Navidrome from Maloja scrobble data.
Outputs a missing_tracks_YYYYMMDD.md report for tracks not found on the server.

Run: python create_bestof_playlists.py
"""

import getpass
import json
import re
import urllib.parse
import urllib.request
from datetime import date
from difflib import SequenceMatcher

TOP_N = 50
YEARS = [2007, 2010, 2011, 2013, 2014, 2015, 2017, 2018, 2019, 2020, 2021, 2022, 2024]


def load_dotenv():
    """Load .env from the script's directory into os.environ (does not override existing vars)."""
    import os
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def prompt_config():
    """
    Reads config from .env file or environment variables, otherwise prompts interactively.

    .env / environment variables:
      MALOJA_URL        Maloja base URL (default: http://localhost:42010)
      NAVIDROME_URL     Navidrome base URL (default: http://localhost:4533)
      NAVIDROME_USER    Navidrome username
      NAVIDROME_PASS    Navidrome password
      BESTOF_YEARS      Comma-separated years to process (default: all missing years)
    """
    load_dotenv()
    import os

    env_maloja = os.environ.get("MALOJA_URL")
    env_nd_url = os.environ.get("NAVIDROME_URL")
    env_nd_user = os.environ.get("NAVIDROME_USER")
    env_nd_pass = os.environ.get("NAVIDROME_PASS")
    env_years = os.environ.get("BESTOF_YEARS")

    if all([env_maloja, env_nd_url, env_nd_user, env_nd_pass]):
        maloja_url = env_maloja.rstrip("/")
        nd_url = env_nd_url.rstrip("/")
        nd_user = env_nd_user
        nd_pass = env_nd_pass
        if env_years:
            try:
                years = [int(y.strip()) for y in env_years.split(",")]
            except ValueError:
                years = YEARS
        else:
            years = YEARS
        print(f"=== Best of Year Playlist Creator ===")
        print(f"Using environment variables (Maloja: {maloja_url}, Navidrome: {nd_url})\n")
        return maloja_url, nd_url, nd_user, nd_pass, years

    print("=== Best of Year Playlist Creator ===")
    print("Enter connection details (press Enter to accept defaults):\n")

    maloja_url = input("Maloja URL [http://localhost:42010]: ").strip()
    if not maloja_url:
        maloja_url = "http://localhost:42010"
    maloja_url = maloja_url.rstrip("/")

    nd_url = input("Navidrome URL [http://localhost:4533]: ").strip()
    if not nd_url:
        nd_url = "http://localhost:4533"
    nd_url = nd_url.rstrip("/")

    nd_user = input("Navidrome username: ").strip()
    nd_pass = getpass.getpass("Navidrome password: ")

    years_input = input(f"Years to process [{','.join(str(y) for y in YEARS)}]: ").strip()
    if years_input:
        try:
            years = [int(y.strip()) for y in years_input.split(",")]
        except ValueError:
            print("Invalid year format, using defaults.")
            years = YEARS
    else:
        years = YEARS

    print()
    return maloja_url, nd_url, nd_user, nd_pass, years


def get(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read())


def nd_url_builder(base, endpoint, auth, **params):
    p = {**auth, **params}
    return f"{base}/rest/{endpoint}?" + urllib.parse.urlencode(p)


def normalize(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def similarity(a, b):
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def artists_match(maloja_artists, nd_artist):
    nd_norm = normalize(nd_artist)
    for a in maloja_artists:
        if similarity(a, nd_artist) >= 0.8:
            return True
        a_norm = normalize(a)
        if a_norm and (a_norm in nd_norm or nd_norm in a_norm):
            return True
    return False


def find_in_navidrome(nd_base, auth, title, artists):
    for query in [title, f"{title} {artists[0]}"]:
        url = nd_url_builder(nd_base, "search3", auth, query=query, songCount=15, artistCount=0, albumCount=0)
        try:
            data = get(url)
        except Exception as e:
            print(f"    Search error for '{query}': {e}")
            continue

        songs = data.get("subsonic-response", {}).get("searchResult3", {}).get("song", [])
        if not songs:
            continue

        best_score = 0
        best_song = None
        for song in songs:
            t_sim = similarity(title, song.get("title", ""))
            if t_sim < 0.8:
                continue
            if not artists_match(artists, song.get("artist", "")):
                continue
            if t_sim > best_score:
                best_score = t_sim
                best_song = song

        if best_song:
            return best_song

    return None


def get_existing_playlists(nd_base, auth):
    url = nd_url_builder(nd_base, "getPlaylists", auth)
    data = get(url)
    playlists = data.get("subsonic-response", {}).get("playlists", {}).get("playlist", [])
    return {p["name"]: p["id"] for p in playlists}


def create_playlist(nd_base, auth, name):
    url = nd_url_builder(nd_base, "createPlaylist", auth, name=name)
    data = get(url)
    return data.get("subsonic-response", {}).get("playlist", {}).get("id")


def get_playlist_tracks(nd_base, auth, playlist_id):
    url = nd_url_builder(nd_base, "getPlaylist", auth, id=playlist_id)
    data = get(url)
    songs = data.get("subsonic-response", {}).get("playlist", {}).get("entry", [])
    return {s["id"] for s in songs}


def add_songs_to_playlist(nd_base, auth, playlist_id, song_ids):
    base = f"{nd_base}/rest/updatePlaylist?"
    params = urllib.parse.urlencode(auth)
    params += f"&playlistId={playlist_id}"
    for sid in song_ids:
        params += f"&songIdToAdd={sid}"
    get(base + params)


def main():
    maloja_base, nd_base, nd_user, nd_pass, years = prompt_config()

    maloja_api = f"{maloja_base}/apis/mlj_1"
    auth = {"u": nd_user, "p": nd_pass, "v": "1.16.1", "c": "bestof-creator", "f": "json"}

    print("Fetching existing Navidrome playlists...")
    existing = get_existing_playlists(nd_base, auth)

    all_missing = {}

    for year in years:
        playlist_name = f"04 - Best of - {year}"
        print(f"\n{'='*60}")
        print(f"Processing {year}...")

        url = f"{maloja_api}/charts/tracks?from={year}&to={year}"
        try:
            data = get(url)
        except Exception as e:
            print(f"  Maloja error: {e}")
            continue

        tracks = data.get("list", [])[:TOP_N]
        print(f"  Got {len(tracks)} tracks from Maloja")

        found_ids = []
        missing = []

        for entry in tracks:
            rank = entry["rank"]
            scrobbles = entry["scrobbles"]
            track = entry["track"]
            title = track["title"]
            artists = track["artists"]
            artist_str = ", ".join(artists)

            print(f"  [{rank:2d}] {artist_str} - {title} ({scrobbles} plays)", end=" ")

            song = find_in_navidrome(nd_base, auth, title, artists)
            if song:
                found_ids.append(song["id"])
                print(f"-> found (id={song['id']})")
            else:
                missing.append({"rank": rank, "artists": artists, "title": title, "scrobbles": scrobbles})
                print("-> MISSING")

        if playlist_name in existing:
            pid = existing[playlist_name]
            current_ids = get_playlist_tracks(nd_base, auth, pid)
            new_ids = [sid for sid in found_ids if sid not in current_ids]
            if new_ids:
                print(f"\n  Updating '{playlist_name}': adding {len(new_ids)} new track(s)...")
                add_songs_to_playlist(nd_base, auth, pid, new_ids)
                print(f"  Done.")
            else:
                print(f"\n  '{playlist_name}' is already up to date.")
        elif found_ids:
            print(f"\n  Creating playlist '{playlist_name}' with {len(found_ids)} tracks...")
            pid = create_playlist(nd_base, auth, playlist_name)
            if pid:
                add_songs_to_playlist(nd_base, auth, pid, found_ids)
                print(f"  Done. Playlist ID: {pid}")
            else:
                print("  ERROR: Failed to create playlist.")
        else:
            print(f"\n  No tracks found for {year}, skipping playlist creation.")

        if missing:
            all_missing[year] = missing
            print(f"  {len(missing)} tracks not found on server.")

    report_path = f"missing_tracks_{date.today().strftime('%Y%m%d')}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Missing Tracks Report — {date.today()}\n\n")
        f.write("Tracks from Maloja top charts not found in Navidrome library.\n\n")
        for year, tracks in sorted(all_missing.items()):
            f.write(f"## {year} ({len(tracks)} missing)\n\n")
            f.write("| Rank | Artist(s) | Title | Plays |\n")
            f.write("|------|-----------|-------|-------|\n")
            for t in tracks:
                artists = ", ".join(t["artists"])
                f.write(f"| {t['rank']} | {artists} | {t['title']} | {t['scrobbles']} |\n")
            f.write("\n")

    print(f"\n{'='*60}")
    print(f"Report written to: {report_path}")
    total_missing = sum(len(v) for v in all_missing.values())
    print(f"Total missing tracks across all years: {total_missing}")


if __name__ == "__main__":
    main()
