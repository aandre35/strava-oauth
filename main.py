from flask import Flask, redirect, request, jsonify
import os, requests
from google.cloud import firestore  # pour stocker tokens
import traceback
import sys

app = Flask(__name__)

# Variables d'environnement
STRAVA_CLIENT_ID = os.environ["STRAVA_CLIENT_ID"]
STRAVA_CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]
REDIRECT_URI = os.environ["REDIRECT_URI"]
#REDIRECT_URI = "https://strava-oauth-1087017681131.europe-west1.run.app/exchange_token"

# URL Strava
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_URL = "https://www.strava.com/api/v3"

# Firestore client
db = firestore.Client()

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

    # Échange du code contre tokens
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
    athlete_id = tokens["athlete"]["id"]

    # Stockage dans Firestore
    db.collection("strava_tokens").document(str(athlete_id)).set({
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_at": tokens["expires_at"]
    })

    return jsonify({"message": "Tokens stored successfully", "tokens": tokens})

@app.route("/activities/<athlete_id>")
def get_activities(athlete_id):
    
    """Récupère les activités Strava pour un athlète donné"""
    try:
        print(f"[DEBUG] Starting get_activities for athlete {athlete_id}")
        print(f"[DEBUG] Firestore client initialized: {db}")
        
        doc_ref = db.collection("strava_tokens").document(str(athlete_id))
        print(f"[DEBUG] Document reference created: {doc_ref}")
        
        doc = doc_ref.get()
        print(f"[DEBUG] Document retrieved: {doc}")
        print(f"[DEBUG] Document exists: {doc.exists if doc else 'No doc'}")
        
        if not doc.exists:
            print(f"[ERROR] No tokens found for athlete {athlete_id}")
            return jsonify({"error": "Tokens not found"}), 404

    except Exception as e:        
        print(f"[ERROR] Firestore error type: {type(e)}")
        print(f"[ERROR] Firestore error message: {str(e)}")
        print("[ERROR] Full traceback:")
        traceback.print_exc(file=sys.stdout)
        
        # Check if it's a credentials issue
        if "Permission denied" in str(e):
            print("[ERROR] Possible credentials issue - verify service account permissions")
            return jsonify({
                "error": "Database authentication error",
                "details": "Service account permissions issue"
            }), 500
            
        return jsonify({
            "error": "Database connection error",
            "details": str(e)
        }), 500
    token_data = doc.to_dict()

    # Vérifier si le token a expiré
    import time
    if token_data["expires_at"] < time.time():
        # Rafraîchir le token
        data = {
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": token_data["refresh_token"]
        }
        r = requests.post(STRAVA_TOKEN_URL, data=data)
        if r.status_code != 200:
            return jsonify({"error": r.text}), r.status_code

        new_tokens = r.json()
        token_data["access_token"] = new_tokens["access_token"]
        token_data["refresh_token"] = new_tokens["refresh_token"]
        token_data["expires_at"] = new_tokens["expires_at"]

        # Mettre à jour Firestore
        doc_ref.set(token_data)

    # Récupérer les activités
    r = requests.get(
        os.path.join(STRAVA_API_URL, "activities"),
        headers={"Authorization": f"Bearer {token_data['access_token']}"}
    )
    if r.status_code != 200:
        return jsonify({"error": r.text}), r.status_code

    activities = r.json()
    return jsonify(activities)


@app.route("/sync_activities")
def sync_activities():
    """Récupère les nouvelles activités pour tous les athlètes stockés"""
    athletes = db.collection("strava_tokens").stream()
    print(athletes)
    results = {}

    import time

    for doc in athletes:
        athlete_id = doc.id
        token_data = doc.to_dict()

        # Rafraîchir le token si nécessaire
        if token_data["expires_at"] < time.time():
            data = {
                "client_id": STRAVA_CLIENT_ID,
                "client_secret": STRAVA_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": token_data["refresh_token"]
            }
            r = requests.post(STRAVA_TOKEN_URL, data=data)
            if r.status_code != 200:
                results[athlete_id] = {"error": r.text}
                continue
            new_tokens = r.json()
            token_data["access_token"] = new_tokens["access_token"]
            token_data["refresh_token"] = new_tokens["refresh_token"]
            token_data["expires_at"] = new_tokens["expires_at"]
            db.collection("strava_tokens").document(athlete_id).set(token_data)

        # Récupérer les activités
        r = requests.get(
            os.path.join(STRAVA_API_URL, "activities"),
            headers={"Authorization": f"Bearer {token_data['access_token']}"}
        )
        if r.status_code != 200:
            results[athlete_id] = {"error": r.text}
            continue

        activities = r.json()
        # Ici tu peux stocker les activités en base si tu veux
        results[athlete_id] = {"count": len(activities)}

    return jsonify(results)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))