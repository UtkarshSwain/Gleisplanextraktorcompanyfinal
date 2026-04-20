# PowerShell script to run API tests
# Run this with: .\run_tests.ps1

Write-Host "Activating virtual environment..." -ForegroundColor Green
& "D:\MAsterarbeitprototypv1\project1\.venv2\Scripts\Activate.ps1"

Write-Host "`nInstalling test dependencies..." -ForegroundColor Green
pip install pytest httpx fastapi

Write-Host "`nRunning tests..." -ForegroundColor Green
python -m pytest tests/test_api.py -v --tb=short

Write-Host "`nTests complete!" -ForegroundColor Green
