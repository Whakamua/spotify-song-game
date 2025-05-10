# Spotify Song Game 🎵

A lightweight Flask web-app you can run locally to play a quick game with friends: **Who listened most recently?**

Each participant logs into their personal Spotify account on the landing page.  The app stores their *recently played* tracks and then challenges the group to guess who listened to a given song most recently.

> ⚠️  **Disclaimer**: The public Spotify Web-API only returns up to 50 of a user's most recently played tracks.  Building a *full* "all-time" timeline is therefore impossible without each user requesting an extended data export from Spotify.  For the purpose of this demo we use the standard 50-track endpoint.

---

## 1. Prerequisites

1. **Python 3.9+** installed and available in your shell.
2. A **Spotify Developer** account — create one for free at <https://developer.spotify.com/>.

---

## 2. Register a Spotify App

1. Sign-in to the  _Spotify Developer Dashboard_.
2.  Click **"Create an App"**.  Give it any name (e.g. _Spotify Song Game_) and description.
3.  Inside the app settings add **Redirect URI**:

    ```
    http://127.0.0.1:5000/callback
    ```
4.  Note the following credentials – you will need them in the next step:
   * **Client ID**
   * **Client Secret**

> **Heads-up (2025 change)** – Spotify no longer allows the hostname `localhost` in redirect URIs. Use the loopback IP literal `127.0.0.1` (IPv4) or `[::1]` (IPv6). See their developer blog for details.

---

## 3. Configure local environment

Create a file named `.env` in the project root **(same folder as `app.py`)** containing:

```env
# -----------------------------------------------------------------------------
# ⚠️  Paste *your* Spotify credentials below.  DO NOT commit this file to Git. ⚠️
# -----------------------------------------------------------------------------
SPOTIFY_CLIENT_ID="YOUR_CLIENT_ID_HERE"
SPOTIFY_CLIENT_SECRET="YOUR_CLIENT_SECRET_HERE"
# The redirect URI must match what you configured on the Developer Dashboard
SPOTIFY_REDIRECT_URI="http://127.0.0.1:5000/callback"

# Optional: a secret key used by Flask for session cookies
# (if omitted a random key is generated each time which is fine for local use)
# FLASK_SECRET_KEY="choose-anything-random-here"
```

> Replace `YOUR_CLIENT_ID_HERE` and `YOUR_CLIENT_SECRET_HERE` with the values from the Developer Dashboard.

---

## 4. Install dependencies

We recommend using a virtual environment (e.g. **`venv`** or **`conda`**).  Then run:

```bash
pip install -r requirements.txt
```

---

## 5. Run the app locally

```bash
python app.py
```

Open your browser at **<http://127.0.0.1:5000>** (or the same address you registered above).

> The terminal shows Flask's debug log – handy while experimenting.

---

## 6. How to play

1. Each player, on their own device or the same screen, clicks **"Login with Spotify"** and approves the requested scopes.
2. The landing page lists everyone who joined.
3. When you're ready (even if it's just you), click **"Start Game"**.
4. The app randomly selects a song from the collected recent-playback timelines and asks:
   > Who has most recently listened to *Song X*?
5. Reveal the answer or hit **"Next Question"** to keep playing.

---

## 7. Customisation hints  🛠️

* **Development mode user limit** – While your Spotify app is in *development* mode, only users explicitly added in the **Users** tab of the developer dashboard (max 25) can log in. If someone sees a *403 Forbidden* error, add their Spotify account e-mail there or switch the app to production (requires review).
* **Track limit** – change the `limit` parameter in `fetch_recently_played()` inside `app.py` to fetch fewer/more songs (≤50).
* **Persistent storage** – right now everything lives in RAM.  Swap the `players` dict for a small database (e.g. SQLite) if you want to keep data between restarts.
* **Frontend tweaks** – HTML lives in `templates/`; simple CSS overrides in `static/style.css`.

---

## 8. Project structure

```
.
├── app.py               # Flask backend & routes
├── templates/
│   ├── index.html       # Lobby page
│   └── game.html        # Game page
├── static/
│   └── style.css        # Tiny custom CSS
├── requirements.txt     # Python deps
└── README.md            # You are here ✅
```

Enjoy!  Feedback & pull requests welcome. 🙌 

{"access_token": "BQDm4UcgqOP2YwF_XD_8Q5qQLDq3vbO8HVmlQ081bnvLTQwU5S0MuB9qT74pncv5wbC20YELMg-1dVPFnuACN61QsCzF-MzpesuFGE8e5X-nCVpbWKF0-1gN2x3dMVE3riSblYa1Ek93OpsK3X1ZIlZk2kzyQF8OTB9i2rGz03LIDjUyBXOWpTBMwTashIV8dajresSoNsu_2E6_SbmFatK7wiPNsOyokA", "token_type": "Bearer", "expires_in": 3600, "refresh_token": "AQAZpY-IfucIMPxrRKUVYwuKQuAqhmJ-eQjI5z8x9h28-hV-5YzWcSXsHLVa_rkuQvLe4mV6iiIOFw2D_ib9ORT6ZqKA9rW9G6VNvC65vOkKRNLpOzdhIlPJKOOLpzi1qRY", "scope": "user-read-recently-played user-read-email", "expires_at": 1746897164}