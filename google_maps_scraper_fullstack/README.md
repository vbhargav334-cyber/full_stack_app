# Google Maps Scraper Full Stack App

Full local app with:
- Flask backend API
- Playwright scraper engine (no API key)
- Web UI for running jobs and exporting data
- Bulk CSV/Excel upload mode
- Retry, delay, and anti-block controls
- Competitor radius analysis
- Lead scoring and prioritization
- Auto-save checkpoints during running jobs
- Resume from checkpoint uploads
- Change tracking vs previous runs
- Client-side lead filter panel
- Deduped output + data quality flags
- Area clustering + competitor gap scoring
- Outreach + CRM exports
- Schedule mode for recurring jobs
- Social links + public emails from website (optional)

## What it collects
- Name
- Category
- Rating
- Review count
- Open now status
- Business status
- Price level
- Address
- Phone
- Website
- Services
- Amenities
- Payment options
- Latest review freshness hint
- Owner response availability hint
- Photos count hint
- Menu / order / booking links (when detectable)
- Public emails from website pages (optional)
- Social links (Facebook, Instagram, Twitter/X, LinkedIn, YouTube, TikTok)
- Plus code
- Located in
- Hours
- Description
- Latitude/Longitude (from URL when available)
- CID (when available)
- Google Maps URL
- Competitor count within radius
- Nearest/top competitor hints
- Lead score, lead priority, lead reason
- Opportunity score and competitor gap
- Data quality flags + cluster metadata

## Setup (Windows PowerShell)

```powershell
cd "c:\Users\Bhargav\Documents\google_maps_scraper_fullstack"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

Open in browser:

`http://127.0.0.1:8000`

## API Endpoints
- `POST /api/jobs` start a scrape job
- `POST /api/jobs/bulk-upload` start bulk scrape from uploaded CSV/XLSX
- `POST /api/jobs/resume-upload` resume from checkpoint CSV/XLSX
- `GET /api/jobs/<job_id>` job status/progress
- `GET /api/jobs/<job_id>/results` job rows
- `GET /api/jobs/<job_id>/checkpoint.csv` download latest checkpoint
- `GET /api/jobs/<job_id>/export.csv` download CSV
- `GET /api/jobs/<job_id>/export.xlsx` download XLSX
- `GET /api/jobs/<job_id>/export.outreach.csv` download outreach list
- `GET /api/jobs/<job_id>/export.crm.csv?provider=hubspot|zoho|salesforce`
- `GET /api/jobs/<job_id>/clusters` cluster summary
- `GET /api/schedules` list schedules
- `POST /api/schedules` create schedule
- `POST /api/schedules/<schedule_id>/run-now` run schedule now
- `DELETE /api/schedules/<schedule_id>` delete schedule

## Bulk File Format
- Required column: `keyword` (or `query`)
- Optional columns: `location`, `max_results`
- If optional columns are missing, UI defaults are used.

Example CSV:

```csv
keyword,location,max_results
dentists,Hyderabad,20
gyms,Bangalore,15
hotels,Chennai,10
```

## Anti-Block Controls
- `max_retries`: retry full query when blocked/failed
- `min_delay` / `max_delay`: random per-page delay window
- Browser rotates user-agent and uses backoff between retries

## Market Intelligence Controls
- `Competitor Radius (km)`: radius used to compute nearby same-category competitors
- `Checkpoint Every (rows)`: auto-saves progress in `checkpoints/<job_id>_checkpoint.csv`
- `Dedup Results`: removes duplicates using `place_id/feature_id/url`
- `Scrape Social Links + Emails`: pulls public links/emails from the business website
- `Website Pages to Scan`: homepage + extra contact/about pages (1-5)

## Change Tracking
- Stores last seen business metrics in `history/latest_master.csv`
- Adds fields in output:
  - `change_flag` (`New` / `Yes` / `No`)
  - `rating_change`
  - `review_count_change`
  - `status_changed`

## Exports
- Outreach CSV: high/medium priority leads with a simple pitch
- CRM CSV: HubSpot, Zoho, or Salesforce formats

## Notes
- This scrapes only details that are publicly visible in the Google Maps UI.
- Field availability varies by place.
- Large-volume runs can be blocked or slowed by Google.

## Build Windows EXE

Use one-click builder:

```bat
build_exe.bat
```

Output:
- `dist\GoogleMapsScraperApp\GoogleMapsScraperApp.exe`

The EXE starts a local server and opens the app in your browser.

If an older EXE shows `Executable doesn't exist ... .local-browsers`, rebuild with latest `build_exe.bat`.
The script now installs Chromium into project-local Playwright folder and bundles it into the EXE.
