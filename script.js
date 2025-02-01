const clientId = "864887e0189b4e2a85987af3b17e022f";
const redirectUri = "https://whakamua.github.io/spotify-song-game/callback.html";
const authEndpoint = "https://accounts.spotify.com/authorize";
const scopes = ["user-top-read", "user-read-recently-played"];

document.getElementById("login").addEventListener("click", () => {
    window.location.href = `${authEndpoint}?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=${scopes.join("%20")}&response_type=token`;
});

// Extract access token from URL
const getToken = () => {
    const hash = window.location.hash.substring(1).split("&").reduce((acc, item) => {
        let [key, value] = item.split("=");
        acc[key] = decodeURIComponent(value);
        return acc;
    }, {});
    return hash.access_token;
};

// Fetch user's top songs
const fetchTopSongs = async (token) => {
    const response = await fetch("https://api.spotify.com/v1/me/top/tracks?limit=10", {
        headers: { Authorization: `Bearer ${token}` }
    });
    return response.json();
};

// Generate a quiz question
const generateQuiz = async () => {
    const token = getToken();
    if (!token) return;

    const data = await fetchTopSongs(token);
    if (!data.items) return;

    const song = data.items[Math.floor(Math.random() * data.items.length)];
    const question = `Who listened to "${song.name}" the most in 2024?`;
    
    document.getElementById("question").textContent = question;
    document.getElementById("game").style.display = "block";
};

if (window.location.hash) {
    generateQuiz();
}
