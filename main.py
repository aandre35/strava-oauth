from flask import Flask, redirect, request, jsonify
import os, requests, time, traceback, json
from google.cloud import storage
from google.api_core import exceptions

app = Flask(__name__)

# --- Configuration ---
try:
    STRAVA_CLIENT_ID = os.environ["STRAVA_CLIENT_ID"]
    STRAVA_CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]
    REDIRECT_URI = os.environ["REDIRECT_URI"]
    GCS_BUCKET_NAME = os.environ["GCS_BUCKET_NAME"]
    GCS_FOLDER_NAME = os.environ["GCS_FOLDER_NAME"]
    # NOUVEAU : Un dossier dédié pour stocker les fichiers de tokens
    GCS_TOKEN_FOLDER = os.environ.get("GCS_TOKEN_FOLDER", "strava_tokens")
except KeyError as e:
    raise RuntimeError(f"Missing environment variable: {e}")

# URL Strava
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_URL = "https://www.strava.com/api/v3"

# Client Google Cloud Storage
storage_client = storage.Client()
bucket = storage_client.bucket(GCS_BUCKET_NAME)


# --- Fonctions utilitaires pour la gestion des tokens dans GCS ---

def save_token_to_gcs(athlete_id, tokens):
    """Sauvegarde les données du token dans un fichier JSON sur GCS."""
    blob_name = f"{GCS_TOKEN_FOLDER}/{athlete_id}.json"
    blob = bucket.blob(blob_name)
    blob.upload_from_string(
        data=json.dumps(tokens, indent=2),
        content_type="application/json"
    )
    print(f"Tokens pour l'athlète {athlete_id} sauvegardés dans {blob_name}")

def read_token_from_gcs(athlete_id):
    """Lit les données du token depuis un fichier JSON sur GCS."""
    blob_name = f"{GCS_TOKEN_FOLDER}/{athlete_id}.json"
    blob = bucket.blob(blob_name)
    if not blob.exists():
        return None
    token_data = json.loads(blob.download_as_string())
    return token_data


# --- Routes de l'application ---

@app.route("/")
def home():
    """
    Page d'accueil. Gère aussi la redirection depuis Strava si le paramètre
    'code' est présent dans l'URL.
    """
    # Si la requête est une redirection de retour de l'OAuth Strava (contient un code)
    if 'code' in request.args:
        # Reconstruit l'URL de redirection vers /exchange_token avec les mêmes paramètres
        query_params = request.query_string.decode('utf-8')
        return redirect(f"/exchange_token?{query_params}")

    # Sinon, affiche la page d'accueil normale
    return "✅ Strava OAuth Cloud Run app is running (GCS Version)"

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

    data = {
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
    }

    try:
        response = requests.post(STRAVA_TOKEN_URL, data=data)
        response.raise_for_status()
        tokens = response.json()
        athlete_id = tokens["athlete"]["id"]

        # Stockage des tokens dans un fichier JSON sur GCS
        save_token_to_gcs(athlete_id, {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "expires_at": tokens["expires_at"]
        })

        return jsonify({"message": f"Tokens pour l'athlète {athlete_id} stockés avec succès dans GCS."})

    except requests.exceptions.RequestException as e:
        return jsonify({"error": "Échec de l'échange du token avec Strava", "details": str(e)}), 502
    except Exception as e:
        return jsonify({"error": "Une erreur interne est survenue", "details": str(e)}), 500


@app.route("/activities/<athlete_id>")
def get_activities(athlete_id):
    """Récupère les activités Strava, les retourne et les stocke dans GCS."""
    try:
        # Lire les tokens depuis GCS
        token_data = read_token_from_gcs(athlete_id)

        if token_data is None:
            return jsonify({"error": f"Tokens non trouvés pour l'athlète {athlete_id}. Veuillez vous ré-authentifier."}), 404

        # Rafraîchir le token si nécessaire
        if token_data["expires_at"] < time.time():
            print(f"Le token pour l'athlète {athlete_id} a expiré. Rafraîchissement...")
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
            # Mettre à jour le fichier de token dans GCS
            save_token_to_gcs(athlete_id, token_data)
            print(f"Token pour l'athlète {athlete_id} rafraîchi et mis à jour dans GCS.")

        # Récupérer les activités avec un token valide
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        activities_url = f"{STRAVA_API_URL}/athlete/activities"
        response = requests.get(activities_url, headers=headers)
        response.raise_for_status()
        
        activities = response.json()

        if activities:
            filename = f"{GCS_FOLDER_NAME}/{athlete_id}/{int(time.time())}.json"
            blob = bucket.blob(filename)
            blob.upload_from_string(
                data=json.dumps(activities, indent=2),
                content_type="application/json"
            )
            print(f"Succès : {len(activities)} activités uploadées vers {filename}")

        return jsonify(activities)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": "Échec de la récupération des données depuis Strava", "details": str(e)}), 502
    except Exception as e:
        print(f"Une erreur est survenue : {e}")
        traceback.print_exc()
        if "PermissionDenied" in str(e) or (hasattr(e, 'code') and e.code == 403):
            return jsonify({
                "error": "Erreur d'authentification avec Storage",
                "details": f"Permission refusée pour le projet. Vérifiez les rôles IAM pour le compte de service Cloud Run (a besoin de 'Créateur des objets de l'espace de stockage')."
            }), 403
            
        return jsonify({"error": "Une erreur interne du serveur est survenue.", "details": str(e)}), 500


@app.route("/sync_activities")
def sync_activities():
    """Récupère les nouvelles activités pour tous les athlètes et les stocke dans GCS."""
    try:
        # Lister tous les fichiers de tokens dans GCS
        blobs = storage_client.list_blobs(bucket, prefix=f"{GCS_TOKEN_FOLDER}/")
        results = {}

        for blob in blobs:
            if not blob.name.endswith(".json"):
                continue
            
            athlete_id = os.path.splitext(os.path.basename(blob.name))[0]
            
            try:
                token_data = json.loads(blob.download_as_string())

                if token_data["expires_at"] < time.time():
                    refresh_data = {
                        "client_id": STRAVA_CLIENT_ID, "client_secret": STRAVA_CLIENT_SECRET,
                        "grant_type": "refresh_token", "refresh_token": token_data["refresh_token"]
                    }
                    r = requests.post(STRAVA_TOKEN_URL, data=refresh_data)
                    if r.status_code != 200:
                        results[athlete_id] = {"error": f"Échec du rafraîchissement du token : {r.text}"}
                        continue
                    new_tokens = r.json()
                    token_data.update(new_tokens)
                    save_token_to_gcs(athlete_id, token_data)

                headers = {"Authorization": f"Bearer {token_data['access_token']}"}
                activities_url = f"{STRAVA_API_URL}/athlete/activities"
                r = requests.get(activities_url, headers=headers)
                
                if r.status_code != 200:
                    results[athlete_id] = {"error": f"Échec de la récupération des activités : {r.text}"}
                    continue
                
                activities = r.json()

                if activities:
                    filename = f"{GCS_FOLDER_NAME}/{athlete_id}/sync_{int(time.time())}.json"
                    activity_blob = bucket.blob(filename)
                    activity_blob.upload_from_string(
                        data=json.dumps(activities, indent=2),
                        content_type="application/json"
                    )
                    results[athlete_id] = {"status": "succès", "activités trouvées": len(activities), "gcs_path": filename}
                else:
                    results[athlete_id] = {"status": "succès", "activités trouvées": 0}
            
            except Exception as e:
                results[athlete_id] = {"error": f"Le traitement a échoué : {str(e)}"}

        return jsonify(results)
    except Exception as e:
        print(f"Une erreur est survenue durant la synchronisation : {e}")
        traceback.print_exc()
        return jsonify({"error": "La synchronisation a échoué", "details": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)

