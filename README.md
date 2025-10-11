# strava-oauth

## Overview
...existing code...

## Project Structure
...existing code...

## Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd strava-oauth
   ```

2. **Set up Google Cloud Project:**
   ```bash
   # Set the project ID
   gcloud config set project whaly-customer-strava-aggregator

   # Set up permissions for Cloud Build
   gcloud projects add-iam-policy-binding wly-customer-strava-aggregator \
       --member="serviceAccount:1087017681131@cloudbuild.gserviceaccount.com" \
       --role="roles/run.admin"

   gcloud projects add-iam-policy-binding wly-customer-strava-aggregator \
       --member="serviceAccount:1087017681131@cloudbuild.gserviceaccount.com" \
       --role="roles/iam.serviceAccountUser"
   ```

3. **Set up environment variables:**
   ```bash
   export PROJECT_ID=wly-customer-strava-aggregator
   export PROJECT_NUMBER=1087017681131
   ```
   Also ensure you have these Strava-specific variables:
   - `STRAVA_CLIENT_ID`
   - `STRAVA_CLIENT_SECRET`
   - `PORT` (optional, defaults to 8080)

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Deployment
Deploy to Cloud Run using Cloud Build:

```bash
# Manual deployment
gcloud builds submit --project=whaly-customer-strava-aggregator

# Check deployment status
gcloud run services list --platform managed --project=whaly-customer-strava-aggregator --region=europe-west1
```

## Usage
...existing code...

## License
...existing code...