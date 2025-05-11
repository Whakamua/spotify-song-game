import os
import random
from datetime import datetime
from typing import Dict, List, Any

from flask import Flask, redirect, request, url_for, render_template, flash, session
from spotipy import Spotify, SpotifyOAuth
from spotipy.exceptions import SpotifyException
from spotipy.cache_handler import MemoryCacheHandler
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# Load environment variables from .env file IF present. This file is NOT
# committed to source control. See README for instructions.
# -----------------------------------------------------------------------------
load_dotenv()

# ----------------------------------------------------------------------------
# Basic Flask application setup
# ----------------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")

# SECURITY NOTE:  Replace this in production!  For local usage, a random secret
# key is fine.
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))

# Ensure session cookies work cross-domain (if multiple players on same network)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# ----------------------------------------------------------------------------
# Spotify OAuth configuration
# ----------------------------------------------------------------------------
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:5000/callback")

if not CLIENT_ID or not CLIENT_SECRET:
    # We fail early with a helpful message so that first time users know what
    # they still need to configure.
    raise RuntimeError(
        "Missing SPOTIFY_CLIENT_ID and/or SPOTIFY_CLIENT_SECRET. "
        "See README.md for setup instructions."
    )

# The scopes below allow us to read the user's playback history and profile.
SCOPE = "user-read-recently-played user-read-email user-library-read"

def create_spotify_oauth(state: str | None = None) -> SpotifyOAuth:
    """Create a fresh SpotifyOAuth manager each request.

    Passing a unique `state` allows us to validate the callback, preventing the
    potential cross-login bug where one person's flow overwrote the in-memory
    `state` value of another.
    """
    return SpotifyOAuth(
        scope=SCOPE,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        cache_handler=MemoryCacheHandler(),
        show_dialog=True,
        state=state,
    )

# ----------------------------------------------------------------------------
# In-memory storage of logged-in players and their listening history.
# For a production-grade app you would move this to a persistent database.
# Format:
#     players = {
#         spotify_user_id: {
#             "display_name": str,
#             "token_info": dict,  # token_info returned by Spotipy
#             "timeline": List[dict]  # recently played track objects
#         },
#         ...
#     }
# ----------------------------------------------------------------------------
players: Dict[str, Dict[str, Any]] = {}


# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------

def fetch_recently_played(sp: Spotify, limit: int = 50) -> List[dict]:
    """Fetch `limit` most recently played tracks for the current user."""
    try:
        results = sp.current_user_recently_played(limit=limit)
        return results.get("items", [])
    except SpotifyException as e:
        app.logger.error(f"Error fetching recently played for {sp.me()['id']}: {e}")
        return []

def fetch_saved_tracks(sp: Spotify, limit: int = 2000) -> List[Dict[str, Any]]:
    """Fetch saved tracks for the current user, up to a specified limit, returning a list of SavedTrackObjects."""
    saved_tracks_objects: List[Dict[str, Any]] = []
    try:
        offset = 0
        page_limit = 50 
        while True: 
            num_to_fetch = page_limit
            if len(saved_tracks_objects) + page_limit > limit:
                num_to_fetch = limit - len(saved_tracks_objects)
            
            if num_to_fetch <= 0: 
                break

            results = sp.current_user_saved_tracks(limit=num_to_fetch, offset=offset)
            items = results.get("items", []) # items are SavedTrackObjects
            if not items:
                break

            for item in items: # item is a SavedTrackObject
                track_details = item.get("track")
                # Ensure the item has a track, the track has an ID, name, artists, and the item has added_at
                if track_details and track_details.get("id") and \
                   track_details.get("name") and track_details.get("artists") and item.get("added_at"):
                    saved_tracks_objects.append(item) # Append the whole SavedTrackObject
                    if len(saved_tracks_objects) >= limit:
                        break 
            
            if len(saved_tracks_objects) >= limit:
                break

            offset += len(items)
            if len(items) < page_limit:
                break
        return saved_tracks_objects
    except SpotifyException as e:
        app.logger.error(f"Error fetching saved tracks for {sp.me()['id']}: {e}")
        return []


# -----------------------------------------------------------------------------
# Route definitions
# -----------------------------------------------------------------------------

@app.route("/")
def index():
    """Landing page – show login link and already-joined players."""
    return render_template("index.html", players=players.values())


@app.route("/login")
def login():
    """Redirect the user to Spotify's authorization page."""
    oauth = create_spotify_oauth()
    # Generate the authorization URL which also creates a random CSRF `state`.
    auth_url = oauth.get_authorize_url()
    # Persist the generated state in the (signed) browser session so we can
    # validate it when Spotify redirects back.
    session["oauth_state"] = oauth.state
    return redirect(auth_url)


@app.route("/callback")
def callback():
    """Handle the redirect from Spotify after user authorization."""
    # Create a fresh OAuth manager for this request to validate the state.
    # It MUST have the same settings as the one used in /login
    oauth = create_spotify_oauth(state=session.get("oauth_state"))

    # Clear the persisted (signed) session state as it's single-use.
    session.pop("oauth_state", None)

    try:
        # Redeem the authorization code from the &code= URL parameter for an
        # access token.
        token_info = oauth.get_access_token(request.args.get("code"))
    except SpotifyException as e:
        app.logger.error(f"Spotify OAuth Error: {e.reason}")
        flash(
            f"Login failed (Spotify error: {e.reason}). Please try again.", "danger"
        )
        return redirect(url_for("index"))

    # Create a Spotify API client with the obtained access token
    sp = Spotify(auth=token_info["access_token"])

    try:
        user_profile = sp.current_user()
        user_id = user_profile["id"]
        display_name = user_profile.get("display_name", user_id)

        # Store or update player data
        players[user_id] = {
            "display_name": display_name,
            "timeline": fetch_recently_played(sp),
            "saved_tracks": fetch_saved_tracks(sp), # Fetch and store saved tracks
            "sp": sp,  # Store the API client for potential future use (e.g. refresh)
        }

        flash(f"Welcome, {display_name}! Game joined.", "success")
    except SpotifyException as e:
        app.logger.error(f"Error fetching user data: {e}")
        flash("Error fetching your Spotify data. Please try again.", "danger")
    return redirect(url_for("index"))


@app.route("/start-game")
def start_game():
    """Transition page once all participants have logged in."""
    if len(players) == 0:
        flash("No players joined yet!", "warning")
        return redirect(url_for("index"))
    return redirect(url_for("game"))


@app.route("/game")
def game():
    """Game page: Ask a question about a song, selected fairly."""
    if 'question_number' not in session:
        session['question_number'] = 0
    session['question_number'] += 1

    options = [pdata["display_name"] for pdata in players.values()]
    question_text = ""
    song_name = "N/A"
    artist_name = "N/A"
    track_id = None
    answer_name = "N/A"
    question_type = ""
    
    # Determine if we attempt to ask a "saved track" question first
    attempt_saved_track_question = (session['question_number'] % 2 == 0)

    if attempt_saved_track_question:
        question_type = "saved_track" # Tentatively set
        question_text = "Who most recently added this song to their saved tracks?"
        
        players_with_saved_tracks = [pid for pid, pdata in players.items() if pdata.get("saved_tracks")]
        
        selected_saved_track_details = None # This will be the 'track' dict part of a SavedTrackObject

        if players_with_saved_tracks:
            source_player_id_for_saved = random.choice(players_with_saved_tracks)
            source_player_data = players[source_player_id_for_saved]
            
            if source_player_data.get("saved_tracks"):
                # chosen_saved_item is a SavedTrackObject (contains 'track' and 'added_at')
                chosen_saved_item = random.choice(source_player_data["saved_tracks"])
                
                # Validate the chosen saved item and its track details
                if chosen_saved_item and chosen_saved_item.get("track") and \
                   chosen_saved_item["track"].get("id") and \
                   chosen_saved_item["track"].get("name") and \
                   chosen_saved_item["track"].get("artists") and \
                   chosen_saved_item.get("added_at"):
                    selected_saved_track_details = chosen_saved_item["track"]
                    track_id = selected_saved_track_details["id"] # Song for the question
                    song_name = selected_saved_track_details["name"]
                    artist_name = selected_saved_track_details["artists"][0]["name"]
                else:
                    flash("Selected saved track has incomplete data. Falling back to recent listener question.", "warning")
                    attempt_saved_track_question = False # Fallback
            else:
                # This case implies player_with_saved_tracks was non-empty, but the chosen player had no tracks.
                # Should be rare if players_with_saved_tracks is derived correctly.
                attempt_saved_track_question = False # Fallback
        else:
            flash("No players have any saved tracks. Asking a recent listener question instead.", "info")
            attempt_saved_track_question = False # Fallback

        # If song selected successfully, find the answer (most recent global saver)
        if attempt_saved_track_question and selected_saved_track_details:
            savers_with_timestamp: List[tuple[datetime, str]] = []
            for pid, pdata in players.items():
                for saved_item_object in pdata.get("saved_tracks", []):
                    # Check if this player saved the *specific chosen song*
                    if saved_item_object.get("track") and saved_item_object["track"].get("id") == track_id:
                        added_at_str = saved_item_object.get("added_at")
                        if added_at_str:
                            dt_added_at = None
                            try:
                                dt_added_at = datetime.strptime(added_at_str, "%Y-%m-%dT%H:%M:%SZ")
                            except ValueError:
                                try:
                                    dt_added_at = datetime.strptime(added_at_str, "%Y-%m-%dT%H:%M:%S.%fZ")
                                except ValueError:
                                    app.logger.warning(f"Could not parse added_at timestamp: {added_at_str} for track {track_id}, player {pid}")
                            if dt_added_at:
                                savers_with_timestamp.append((dt_added_at, pdata["display_name"]))
            
            if savers_with_timestamp:
                most_recent_save = max(savers_with_timestamp, key=lambda x: x[0])
                answer_name = most_recent_save[1]
            else:
                # Song was picked, but no one found to have saved it (or timestamp parse failed for all)
                flash(f"Could not determine who most recently saved '{song_name}'. Falling back.", "warning")
                attempt_saved_track_question = False # Fallback
        elif attempt_saved_track_question and not selected_saved_track_details:
             # Song selection itself failed from saved tracks logic
             attempt_saved_track_question = False # Fallback to ensure it goes to recent listener

    # Fallback to "recent listener" question if initial attempt was for "saved_track" and failed,
    # or if it's the turn for a "recent listener" question anyway.
    if not attempt_saved_track_question:
        question_type = "recent_listener"
        question_text = "Who has most recently listened to:"

        # Prepare combined_recent for global answer checking and potential global song selection
        combined_recent: List[Dict[str, Any]] = []
        for pid_c, pdata_c in players.items():
            for item_c in pdata_c.get("timeline", []):
                track_c = item_c.get("track")
                if track_c and track_c.get("name") and track_c.get("artists") and item_c.get("played_at"):
                    try:
                        ts = datetime.strptime(item_c["played_at"], "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
                        combined_recent.append({
                            "track_name": track_c["name"],
                            "artist_name": track_c["artists"][0]["name"],
                            "player_id": pid_c,
                            "played_ts": ts,
                            "track_id": track_c.get("id"),
                            "full_track_obj": track_c # For easy access to song details
                        })
                    except ValueError:
                        app.logger.warning(f"Could not parse played_at: {item_c['played_at']} for track {track_c.get('id')}")


        selected_recent_track_obj = None # This will be a full track object
        
        # Try to pick a song fairly from a random player's recent history
        players_with_recent_history = [pid for pid, pdata in players.items() if pdata.get("timeline")]
        if players_with_recent_history:
            source_player_id_for_recent = random.choice(players_with_recent_history)
            source_player_timeline = players[source_player_id_for_recent].get("timeline", [])
            if source_player_timeline:
                # chosen_play_item is an item from a player's timeline (has 'track' and 'played_at')
                chosen_play_item = random.choice(source_player_timeline)
                if chosen_play_item and chosen_play_item.get("track") and \
                   chosen_play_item["track"].get("name") and \
                   chosen_play_item["track"].get("artists"):
                    selected_recent_track_obj = chosen_play_item["track"]
        
        # If fair selection failed, try picking from the global combined_recent list
        if not selected_recent_track_obj and combined_recent:
            flash("Fair song selection from recent plays failed or no specific player history available. Picking globally.", "info")
            # random_play_from_combined is an item from combined_recent list
            random_play_from_combined = random.choice(combined_recent)
            selected_recent_track_obj = random_play_from_combined.get("full_track_obj")

        if not selected_recent_track_obj:
            # This means no recent play history anywhere, or issues with all available data
            flash("Critical: Unable to select any song from recent history. No game data available.", "danger")
            return render_template("game.html", question_text="Error: No game data available to ask a question.", 
                                   song_name="", artist_name="", options=options, answer="", track_id=None, question_type="error")

        # We have a selected_recent_track_obj for the question
        song_name = selected_recent_track_obj["name"]
        artist_name = selected_recent_track_obj["artists"][0]["name"]
        track_id = selected_recent_track_obj.get("id") # track_id of the chosen song

        # Now, find who *globally* listened to THIS song most recently from combined_recent
        plays_of_this_chosen_song = [
            play for play in combined_recent if play.get("track_id") == track_id
        ]
        
        if plays_of_this_chosen_song:
            most_recent_play_info = max(plays_of_this_chosen_song, key=lambda x: x["played_ts"])
            answer_name = players[most_recent_play_info["player_id"]]["display_name"]
        else:
            # This implies the selected song (e.g. from a single player's history)
            # was not found in combined_recent, or combined_recent is empty.
            # This should be rare if the song was picked from combined_recent itself.
            # If it was picked from a single player, it might not be in other's limited timeline for combined_recent.
            flash(f"Could not find recent play data for '{song_name}' to determine the answer. Displaying N/A.", "warning")
            answer_name = "N/A (Data consistency issue)"

    return render_template(
        "game.html",
        question_text=question_text, # New variable for the question text
        song_name=song_name,
        artist_name=artist_name,
        options=options,
        answer=answer_name,
        track_id=track_id,
        question_type=question_type # To adjust answer display in template
    )


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    # Host locally accessible on http://localhost:5000
    # debug=True enables auto-reload on code changes.
    app.run(debug=True) 