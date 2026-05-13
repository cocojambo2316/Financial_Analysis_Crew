# Financial Analysis Crew — Run & Deploy Guide

Overview
--------
Financial Analysis Crew is a Streamlit application that runs three analysis agents (risk, technical/quant, news) and displays charts and summaries for selected tickers.

This README explains how to run the project locally and how to deploy to Streamlit Cloud.

Requirements
------------
- Python 3.10–3.11 (3.11 recommended)
- Git
- Internet access (yfinance downloads, Vertex AI calls)

Install dependencies
--------------------
1. Clone the repository and change into the project folder:

```bash
git clone https://github.com/cocojambo2316/Financial_Analysis_Crew.git
cd Financial_Analysis_Crew
```

2. Create and activate a virtual environment:

Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

macOS / Linux:
```bash
python -m venv venv
source venv/bin/activate
```

3. Install Python dependencies:

```bash
pip install -r requirements.txt
```

Local configuration (Vertex AI)
------------------------------
If you want the agents to use Vertex AI generative models, obtain a service-account JSON key with the required roles and set the environment variable:

Windows (PowerShell):
```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = 'C:\path\to\service-account.json'
```

Or store the path in a `.env` file and load it locally.

Database initialization
-----------------------
The app uses `data/risk_database.duckdb`. The DB is not committed. On first run populate it:

```bash
python src/pipeline/extract.py
# or
python main.py --run-extract
```

Run the app locally
-------------------

```bash
streamlit run src/ui/app.py
```

If the agents fail to import because of missing credentials or package issues, the UI shows warnings and logs.

Deploy to Streamlit Cloud
-------------------------
1. Push your repository to GitHub (ensure secrets and keys are not committed):

```bash
git add README.md
git commit -m "chore: add README"
git push origin main
```

2. On Streamlit Cloud, create a new app and connect the repo `cocojambo2316/Financial_Analysis_Crew`.

3. In app settings, choose **Python 3.11** runtime (recommended for compatibility with dependencies).

4. Add the following secrets under Settings → Secrets:
- `gcp_service_account` — paste the service-account JSON (multiline). Your app can write this to a file at runtime and set `GOOGLE_APPLICATION_CREDENTIALS`.
- `gcp_project` — (optional) `gen-lang-client-0036853021`.

5. Set the app's main file to `app.py` in the repository root (we include a small wrapper that runs `src/ui/app.py`).

Security notes
--------------
- Never commit `keys/`, `.env`, or `venv/` to the repository.
- Use Streamlit Secrets or environment variables in production.

Quick git commands
------------------
```bash
git add -A
git commit -m "chore: update README"
git push origin main
```

Troubleshooting
---------------
- If you encounter `pydantic`/`chromadb` errors in the cloud, set Python to 3.11 and pin `pydantic==1.10.12` in `requirements.txt`.
- If the Streamlit app reports missing Vertex credentials, add the service-account JSON to Streamlit Secrets.

Need help?
-----------
If you want, I can also:
- add a root `app.py` wrapper that launches `src/ui/app.py` (for Streamlit Cloud),
- add logic to write `gcp_service_account` secret to a temp file at runtime,
- or pin dependency versions in `requirements.txt`.
