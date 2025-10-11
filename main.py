from flask import Flask, redirect, request, jsonify
import os, requests, time, traceback, json
from google.cloud import firestore
from google.cloud import storage

app = Flask(__name__)

# --- Configuration ---
# Il est recommandé de vérifier si les variables d'environnement existent au démarrage
try:
    STRAVA_CLIENT_ID = os.environ["STRAVA_CLIENT_ID"]
    STRAVA_CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]
    REDIRECT_URI = os.environ["REDIRECT_URI"]
    GCS_BUCKET_NAME = os.environ["GCS_BUCKET_NAME"] # NOUVEAU: Nom du bucket de stockage
except KeyError as e:
    raise RuntimeError(f"Missing environment variable: {e}")

# URL Strava
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_URL = "https://www.strava.com/api/v3"

# Clients Google Cloud
db = firestore.Client()
storage_client = storage.Client()
bucket = storage_client.bucket(GCS_BUCKET_NAME)

# --- Routes de l'application ---

@app.route("/")
def home():
    """Page d'accueil simple pour vérifier que l'application est en ligne."""
    return "✅ Strava OAuth Cloud Run app is running"

@app.route("/auth")
def auth():
    """Redirige l'utilisateur vers la page d'autorisation Strava."""
    scope = "read,activity:read_all"
    params = {
        "client_id": STRAVA_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "approval_prompt": "auto",
        "scope": scope,
    }
    auth_url = f"{STRAVA_AUTH_URL}?{requests.compat.urlencode(params)}"
    return redirect(auth_url)

@app.route("/exchange_token")
def exchange_token():
    """Reçoit le code d'autorisation et l'échange contre un access token."""
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "Missing authorization code"}), 400

    # Échange du code contre les tokens
    data = {
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
    }

    try:
        response = requests.post(STRAVA_TOKEN_URL, data=data)
        response.raise_for_status()  # Lève une exception pour les codes d'erreur HTTP (4xx ou 5xx)
        tokens = response.json()
        athlete_id = tokens["athlete"]["id"]

        # Stockage des tokens dans Firestore
        doc_ref = db.collection("strava_tokens").document(str(athlete_id))
        doc_ref.set({
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "expires_at": tokens["expires_at"]
        })

        return jsonify({"message": f"Tokens for athlete {athlete_id} stored successfully."})

    except requests.exceptions.RequestException as e:
        return jsonify({"error": "Failed to exchange token with Strava", "details": str(e)}), 502
    except Exception as e:
        return jsonify({"error": "An internal error occurred", "details": str(e)}), 500

@app.route("/activities/<athlete_id>")
def get_activities(athlete_id):
    """Récupère les activités Strava, les retourne et les stocke dans GCS."""
    try:
        doc_ref = db.collection("strava_tokens").document(str(athlete_id))
        doc = doc_ref.get()

        if not doc.exists:
            return jsonify({"error": f"Tokens not found for athlete {athlete_id}. Please re-authenticate."}), 404

        token_data = doc.to_dict()

        if token_data["expires_at"] < time.time():
            print(f"Token for athlete {athlete_id} has expired. Refreshing...")
            data = {
                "client_id": STRAVA_CLIENT_ID,
                "client_secret": STRAVA_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": token_data["refresh_token"]
            }
            response = requests.post(STRAVA_TOKEN_URL, data=data)
            response.raise_for_status()
            
            new_tokens = response.json()
            token_data.update(new_tokens)
            doc_ref.set(token_data)
            print(f"Token for athlete {athlete_id} refreshed and updated in Firestore.")

        # Récupérer les activités avec un token valide
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        activities_url = f"{STRAVA_API_URL}/athlete/activities"
        response = requests.get(activities_url, headers=headers)
        response.raise_for_status()
        
        activities = response.json()

        # --- NOUVEAU: Stockage dans Google Cloud Storage ---
        if activities:
            # Créer un nom de fichier unique avec un timestamp
            filename = f"activities/{athlete_id}/{int(time.time())}.json"
            blob = bucket.blob(filename)
            
            # Uploader les données en tant que chaîne JSON
            blob.upload_from_string(
                data=json.dumps(activities, indent=2),
                content_type="application/json"
            )
            print(f"Successfully uploaded {len(activities)} activities to {filename}")

        return jsonify(activities)

    except firestore.NotFound:
         return jsonify({"error": f"Document for athlete {athlete_id} not found."}), 404
    except requests.exceptions.RequestException as e:
        return jsonify({"error": "Failed to fetch data from Strava", "details": str(e)}), 502
    except Exception as e:
        print(f"An error occurred: {e}")
        traceback.print_exc()
        if "PermissionDenied" in str(e) or (hasattr(e, 'code') and e.code == 403):
            return jsonify({
                "error": "Database or Storage authentication error",
                "details": f"Permission denied for project '{db.project}'. Check IAM roles for the Cloud Run service account (needs Firestore User and Storage Object Creator roles)."
            }), 403
            
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500


@app.route("/sync_activities")
def sync_activities():
    """Récupère les nouvelles activités pour tous les athlètes et les stocke dans GCS."""
    try:
        athletes_ref = db.collection("strava_tokens")
        athletes = athletes_ref.stream()
        results = {}

        for doc in athletes:
            athlete_id = doc.id
            token_data = doc.to_dict()

            if token_data["expires_at"] < time.time():
                refresh_data = {
                    "client_id": STRAVA_CLIENT_ID, "client_secret": STRAVA_CLIENT_SECRET,
                    "grant_type": "refresh_token", "refresh_token": token_data["refresh_token"]
                }
                r = requests.post(STRAVA_TOKEN_URL, data=refresh_data)
                if r.status_code != 200:
                    results[athlete_id] = {"error": f"Failed to refresh token: {r.text}"}
                    continue
                new_tokens = r.json()
                token_data.update(new_tokens)
                athletes_ref.document(athlete_id).set(token_data)

            headers = {"Authorization": f"Bearer {token_data['access_token']}"}
            activities_url = f"{STRAVA_API_URL}/athlete/activities"
            r = requests.get(activities_url, headers=headers)
            
            if r.status_code != 200:
                results[athlete_id] = {"error": f"Failed to fetch activities: {r.text}"}
                continue
            
            activities = r.json()

            # --- NOUVEAU: Stockage dans Google Cloud Storage ---
            if activities:
                filename = f"activities/{athlete_id}/sync_{int(time.time())}.json"
                blob = bucket.blob(filename)
                blob.upload_from_string(
                    data=json.dumps(activities, indent=2),
                    content_type="application/json"
                )
                results[athlete_id] = {"status": "success", "activities_found": len(activities), "gcs_path": filename}
            else:
                results[athlete_id] = {"status": "success", "activities_found": 0}
        
        return jsonify(results)
    except Exception as e:
        print(f"An error occurred during sync: {e}")
        traceback.print_exc()
        return jsonify({"error": "Sync failed", "details": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)

