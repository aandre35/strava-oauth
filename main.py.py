from flask import Flask, redirect, request, jsonify
import os, requests

app = Flask(__name__)

STRAVA_CLIENT_ID = os.environ["STRAVA_CLIENT_ID"]
STRAVA_CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]
REDIRECT_URI = os.environ["REDIRECT_URI"]  # ton callback public

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"


@app.route("/")
def home():
    return "✅ Strava OAuth Cloud Run app is running"


@app.route("/auth")
def auth():
    """Redirige l'utilisateur vers la page d'autorisation Strava"""
    scope = "read,activity:read_all"
    url = (
        f"{STRAVA_AUTH_URL}?client_id={STRAVA_CLIENT_ID}"
        f"&response_type=code&redirect_uri={REDIRECT_URI}"
        f"&approval_prompt=auto&scope={scope}"
    )
    return redirect(url)


@app.route("/exchange_token")
def exchange_token():
    """Reçoit le code et échange contre un token Strava"""
    code = request.args.get("code")
    if not code:
        return "Missing code", 400

    data = {
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
    }

    r = requests.post(STRAVA_TOKEN_URL, data=data)
    if r.status_code != 200:
        return jsonify({"error": r.text}), r.status_code

    tokens = r.json()
    # TODO : stocker refresh_token, athlete.id, expires_at dans ta base
    return jsonify(tokens)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
