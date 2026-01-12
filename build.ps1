# TechDeck Build Script
# Packages TechDeck into a distributable executable using PyInstaller

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TechDeck Build Script v0.7.4" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Clean previous builds
Write-Host "[1/5] Cleaning previous builds..." -ForegroundColor Yellow
if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }
if (Test-Path "TechDeck.spec") { Remove-Item "TechDeck.spec" -Force }
Write-Host "      Clean complete!" -ForegroundColor Green
Write-Host ""

# Step 2: Check for icon
Write-Host "[2/5] Checking for application icon..." -ForegroundColor Yellow
$iconPath = "techdeck\ui\assets\icon.ico"
if (Test-Path $iconPath) {
    Write-Host "      Icon found: $iconPath" -ForegroundColor Green
} else {
    Write-Host "      Warning: No icon found at $iconPath" -ForegroundColor Yellow
    Write-Host "      Application will use default icon" -ForegroundColor Yellow
}
Write-Host ""

# Step 3: Build with PyInstaller
Write-Host "[3/5] Building TechDeck with PyInstaller..." -ForegroundColor Yellow
Write-Host "      This may take 2-5 minutes..." -ForegroundColor Gray

$pyinstallerArgs = @(
    "--name=TechDeck",
    "--windowed",
    "--onedir",
    "--clean",
    "--noconfirm"
)

# Add icon if it exists
if (Test-Path $iconPath) {
    $pyinstallerArgs += "--icon=$iconPath"
}

# Add data files
$pyinstallerArgs += @(
    "--add-data=plugins;plugins",
    "--hidden-import=PySide6.QtCore",
    "--hidden-import=PySide6.QtGui",
    "--hidden-import=PySide6.QtWidgets",
    "--hidden-import=openpyxl",
    "--hidden-import=pandas",
    "--hidden-import=fitz",
    "--hidden-import=pypdf",
    "--hidden-import=packaging",
    "--hidden-import=requests"
)

# Check if assets exist and add them
if (Test-Path "techdeck\ui\assets") {
    $pyinstallerArgs += "--add-data=techdeck\ui\assets;techdeck\ui\assets"
}
if (Test-Path "techdeck\ui\themes") {
    $pyinstallerArgs += "--add-data=techdeck\ui\themes;techdeck\ui\themes"
}

# Add entry point
$pyinstallerArgs += "techdeck\__main__.py"

# Run PyInstaller
& pyinstaller $pyinstallerArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: PyInstaller failed!" -ForegroundColor Red
    Write-Host "Check the output above for errors." -ForegroundColor Red
    exit 1
}

Write-Host "      Build complete!" -ForegroundColor Green
Write-Host ""

# Step 4: Verify build
Write-Host "[4/5] Verifying build output..." -ForegroundColor Yellow
$exePath = "dist\TechDeck\TechDeck.exe"
if (Test-Path $exePath) {
    $exeSize = (Get-Item $exePath).Length / 1MB
    Write-Host "      Executable created: $exePath" -ForegroundColor Green
    Write-Host "      Size: $([math]::Round($exeSize, 2)) MB" -ForegroundColor Green
    
    # Check for plugins
    if (Test-Path "dist\TechDeck\plugins") {
        $pluginCount = (Get-ChildItem "dist\TechDeck\plugins" -Directory).Count
        Write-Host "      Bundled plugins: $pluginCount" -ForegroundColor Green
    } else {
        Write-Host "      WARNING: No plugins folder in build!" -ForegroundColor Yellow
    }
} else {
    Write-Host "      ERROR: Executable not found!" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 5: Create distribution package
Write-Host "[5/5] Creating distribution package..." -ForegroundColor Yellow
$version = "0.7.4"
$zipName = "TechDeck_v$version.zip"
$zipPath = "dist\$zipName"

# Remove old zip if exists
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

# Create zip
Compress-Archive -Path "dist\TechDeck\*" -DestinationPath $zipPath -CompressionLevel Optimal
$zipSize = (Get-Item $zipPath).Length / 1MB
Write-Host "      Package created: $zipPath" -ForegroundColor Green
Write-Host "      Size: $([math]::Round($zipSize, 2)) MB" -ForegroundColor Green
Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Output locations:" -ForegroundColor White
Write-Host "  Executable:  dist\TechDeck\TechDeck.exe" -ForegroundColor White
Write-Host "  Package:     dist\$zipName" -ForegroundColor White
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Test the executable: dist\TechDeck\TechDeck.exe" -ForegroundColor Gray
Write-Host "  2. Upload $zipName to GitHub Release v0.7.4" -ForegroundColor Gray
Write-Host "  3. Update manifest.json with download URL" -ForegroundColor Gray
Write-Host ""
