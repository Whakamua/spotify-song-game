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
SCOPE = "user-read-recently-played user-read-email"

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
    """Fetch a user's most recently played tracks (Spotify's maximum is 50)."""
    return sp.current_user_recently_played(limit=limit)["items"]


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
    """Spotify redirects back here after authorization."""
    code = request.args.get("code")
    error = request.args.get("error")
    if error:
        flash(f"Spotify authorization failed: {error}", "danger")
        return redirect(url_for("index"))

    oauth_state = session.pop("oauth_state", None)  # remove once used
    oauth = create_spotify_oauth(state=oauth_state)
    token_info = oauth.get_access_token(code)
    sp = Spotify(auth=token_info["access_token"])
    try:
        user_profile = sp.current_user()
    except SpotifyException as e:
        # Most common cause in dev mode: the Spotify app is still in
        # *development* status and this user isn't whitelisted.
        if e.http_status == 403:
            flash(
                "Spotify returned 403 – this account is not authorised for the app. "
                "Ask the app owner to add your e-mail in the Users tab on developer.spotify.com.",
                "danger",
            )
            return redirect(url_for("index"))
        # Unknown or unexpected error: re-raise so Flask debug shows full stack.
        raise

    user_id = user_profile["id"]

    # Fetch user's recently played tracks (timeline)
    timeline = fetch_recently_played(sp)

    # Store / update the player record
    players[user_id] = {
        "display_name": user_profile.get("display_name") or user_profile.get("id"),
        "token_info": token_info,
        "timeline": timeline,
    }

    flash(f"{players[user_id]['display_name']} successfully joined!", "success")
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
    """Game page: Ask who listened most recently to a random song from history."""
    # Build a combined list of (track_name, player_id, played_at_ts)
    combined: List[Dict[str, Any]] = []
    for pid, pdata in players.items():
        for item in pdata["timeline"]:
            track = item["track"]
            if track and track.get("name") and track.get("artists"):
                track_name = track["name"]
                # Taking the first artist for simplicity
                artist_name = track["artists"][0]["name"]
                played_at = item["played_at"]  # ISO 8601 string
                ts = datetime.strptime(played_at, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
                track_id = track.get("id")
                combined.append({
                    "track_name": track_name,
                    "artist_name": artist_name,
                    "player_id": pid,
                    "played_ts": ts,
                    "track_id": track_id,
                })

    if not combined:
        flash("Unable to build game – no track history found.", "danger")
        return redirect(url_for("index"))

    # Pick a random track occurrence
    chosen = random.choice(combined)
    song_name = chosen["track_name"]
    artist_name = chosen["artist_name"]
    track_id = chosen.get("track_id")

    # Determine most recent listener for this track across players.
    most_recent = max(
        [c for c in combined if c["track_name"] == song_name and c["artist_name"] == artist_name],
        key=lambda x: x["played_ts"],
    )
    most_recent_player_id = most_recent["player_id"]
    answer_name = players[most_recent_player_id]["display_name"]

    # Prepare player options for UI (simple list of names)
    options = [pdata["display_name"] for pdata in players.values()]

    return render_template(
        "game.html",
        song_name=song_name,
        artist_name=artist_name,
        options=options,
        answer=answer_name,
        track_id=track_id,
    )


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    # Host locally accessible on http://localhost:5000
    # debug=True enables auto-reload on code changes.
    app.run(debug=True) 