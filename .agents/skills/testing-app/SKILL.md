# Testing the Google Maps Scraper App

## Quick Start

```bash
cd google_maps_scraper_fullstack
pip install -r requirements.txt
python app.py
```

The app reads configuration from `google_maps_scraper_fullstack/.env`. Copy `.env.example` to `.env` and modify values as needed.

## Key Endpoints for Verification

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Health check — returns `{"status": "ok"}` |
| `/api/config` | GET | Returns current loaded configuration (Flask settings, file limits, scraper defaults) |
| `/api/jobs` | POST | Create a scraper job — accepts `keyword`, `max_retries`, `min_delay`, `max_delay`, `headless`, etc. |
| `/api/jobs/<id>` | GET | Returns job status and stored params |

## Testing Configuration Loading

1. Modify `.env` with non-default values (e.g., `FLASK_PORT=9000`, `DEFAULT_MAX_RETRIES=5`)
2. Start the app: `python app.py`
3. Verify port: `curl http://127.0.0.1:9000/api/health`
4. Verify all config values: `curl http://127.0.0.1:9000/api/config`
5. Verify job defaults: `curl -X POST http://127.0.0.1:9000/api/jobs -H 'Content-Type: application/json' -d '{"keyword":"test"}'` then check `GET /api/jobs/<id>` for stored params

## Testing Job Parameter Overrides

To verify explicit params override .env defaults:
```bash
curl -X POST http://127.0.0.1:9000/api/jobs \
  -H 'Content-Type: application/json' \
  -d '{"keyword":"test","max_retries":1,"min_delay":0.5,"max_delay":1.0}'
```
Then `GET /api/jobs/<id>` and confirm the params match the explicit values, not `.env` defaults.

## Entry Points

- `python app.py` — Flask dev server (reads FLASK_HOST, FLASK_PORT, FLASK_DEBUG from env)
- `python launcher.py` — Waitress production server (also reads FLASK_HOST, FLASK_PORT from env)

## Known Limitations

- **Playwright browsers**: The scraper requires Playwright Chromium. If not installed, jobs will fail at browser launch. Run `python -m playwright install chromium` to install.
- **No formal test suite**: There are no unit tests. All testing is manual via API calls.
- **No authentication**: API endpoints are unauthenticated. The `/api/config` endpoint exposes configuration values.

## Configurable Environment Variables

| Variable | Default | Description |
|---|---|---|
| FLASK_PORT | 8000 | Port the Flask server listens on |
| FLASK_HOST | 127.0.0.1 | Host the Flask server binds to |
| FLASK_DEBUG | False | Enable Flask debug mode |
| MAX_BULK_FILE_SIZE | 10 | Max bulk upload file size in MB |
| MAX_CHECKPOINT_FILE_SIZE | 50 | Max checkpoint file size in MB |
| DEFAULT_HEADLESS | True | Whether scraper runs headless by default |
| DEFAULT_MAX_RETRIES | 3 | Default scraper retry count |
| DEFAULT_MIN_DELAY | 0.9 | Default minimum delay between scraper requests |
| DEFAULT_MAX_DELAY | 1.8 | Default maximum delay between scraper requests |
