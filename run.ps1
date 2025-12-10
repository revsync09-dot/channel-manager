# Helper script to install requirements and run app.py (Windows PowerShell)
# Usage: ./run.ps1

# If a virtual environment doesn't exist, create one and install requirements
if (!(Test-Path -Path "./.venv")) {
    python -m venv .venv
    Write-Host "Created virtual environment in ./.venv"
}

# Load environment variables from .env (copy from sample if missing)
if (!(Test-Path -Path "./.env")) {
    if (Test-Path -Path "./.env.example") {
        Copy-Item -Path ./.env.example -Destination ./.env -Force
        Write-Host "Copied .env.example to .env. Edit .env with your credentials."
    } else {
        Write-Host "No .env or .env.example found. Please create a .env file and add your credentials."
        exit 1
    }
}

# Activate virtual environment
. ./.venv/Scripts/Activate.ps1

# Install requirements if a requirements file exists
if (Test-Path -Path "./requirements.txt") {
    python -m pip install -r requirements.txt
}

# Run the app launcher
python app.py
