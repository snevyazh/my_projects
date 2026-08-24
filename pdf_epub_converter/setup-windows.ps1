$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ProjectDir ".venv-windows"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

Set-Location $ProjectDir

if (-not (Test-Path $PythonExe)) {
    Write-Host "Creating the Windows virtual environment..." -ForegroundColor Cyan
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        & py -3 -m venv $VenvDir
    }
    else {
        $Python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $Python) {
            throw "Python 3.12+ was not found. Install it from https://www.python.org/downloads/windows/ and enable 'Add Python to PATH'."
        }
        & python -m venv $VenvDir
    }
}

Write-Host "Installing pdf2epub and the Streamlit interface..." -ForegroundColor Cyan
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -e ".[dev,ui]"

Write-Host "Running tests..." -ForegroundColor Cyan
& $PythonExe -m pytest

Write-Host ""
Write-Host "Windows setup completed." -ForegroundColor Green
Write-Host "Start the interface by double-clicking start-windows.bat"
Write-Host "OCRmyPDF and Tesseract must also be available on PATH for scanned PDFs."
