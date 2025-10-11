# strava-oauth

## Overview
This project is a Strava OAuth application built using Flask. It allows users to authenticate with Strava, exchange authorization codes for access tokens, and retrieve activities from the Strava API. The application stores tokens in Google Firestore.

## Project Structure
```
strava-oauth
├── src
│   └── main.py          # Main application code
├── Dockerfile           # Dockerfile for building the application image
├── requirements.txt     # Python dependencies
├── cloudbuild.yaml      # Google Cloud Build configuration
└── README.md            # Project documentation
```

## Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd strava-oauth
   ```

2. **Set up environment variables:**
   Ensure you have the following environment variables set:
   - `STRAVA_CLIENT_ID`
   - `STRAVA_CLIENT_SECRET`
   - `PORT` (optional, defaults to 8080)

3. **Install dependencies:**
   You can install the required dependencies using:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application:**
   You can run the application locally using:
   ```bash
   python src/main.py
   ```

## Deployment
This application can be deployed to Google Cloud Run using Google Cloud Build. The `cloudbuild.yaml` file contains the necessary configuration for building and deploying the Docker image.

## Usage
- Navigate to `/` to check if the application is running.
- Use the `/auth` route to initiate the Strava OAuth flow.
- The `/exchange_token` route handles the exchange of the authorization code for access tokens.
- The `/activities/<athlete_id>` route retrieves activities for a specified athlete.

## License
This project is licensed under the MIT License.