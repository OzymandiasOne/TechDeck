# TechDeck Build Script - Enhanced with verification
# Builds executable, verifies assets, and creates installer

param(
    [switch]$SkipInstaller,
    [switch]$SkipVerification
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TechDeck Build Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get version from constants.py
$constantsPath = "techdeck\core\constants.py"
if (-not (Test-Path $constantsPath)) {
    Write-Host "ERROR: Could not find $constantsPath" -ForegroundColor Red
    exit 1
}

$versionLine = Get-Content $constantsPath | Select-String 'APP_VERSION = "(.*)"'
if ($versionLine) {
    $version = $versionLine.Matches.Groups[1].Value
    Write-Host "Building TechDeck v$version" -ForegroundColor Green
} else {
    Write-Host "ERROR: Could not read version from constants.py" -ForegroundColor Red
    exit 1
}

# Step 1: Clean previous builds
Write-Host "`n[1/6] Cleaning previous builds..." -ForegroundColor Yellow
if (Test-Path "build") { 
    Remove-Item -Recurse -Force "build" 
    Write-Host "  ✓ Cleaned build directory" -ForegroundColor Green
}
if (Test-Path "dist") { 
    Remove-Item -Recurse -Force "dist" 
    Write-Host "  ✓ Cleaned dist directory" -ForegroundColor Green
}

# Step 2: Verify source files exist
Write-Host "`n[2/6] Verifying source files..." -ForegroundColor Yellow
$requiredFiles = @(
    "TechDeck.spec",
    "techdeck\__main__.py",
    "assets\icons\dark\chevron-down.svg",
    "assets\icons\light\chevron-down.svg",
    "assets\TechDeck.ico",
    "plugins"
)

$missingFiles = @()
foreach ($file in $requiredFiles) {
    if (-not (Test-Path $file)) {
        $missingFiles += $file
        Write-Host "  ✗ Missing: $file" -ForegroundColor Red
    }
}

if ($missingFiles.Count -gt 0) {
    Write-Host "`nERROR: Missing required source files!" -ForegroundColor Red
    Write-Host "Please ensure all required files exist before building." -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ All required source files present" -ForegroundColor Green

# Step 3: Run PyInstaller
Write-Host "`n[3/6] Running PyInstaller..." -ForegroundColor Yellow
Write-Host "  This may take 2-5 minutes..." -ForegroundColor Gray

# Fixed: Proper error handling for PyInstaller
$pyinstallerOutput = pyinstaller TechDeck.spec --clean 2>&1
$pyinstallerExitCode = $LASTEXITCODE

if ($pyinstallerExitCode -ne 0) {
    Write-Host "  ✗ PyInstaller failed" -ForegroundColor Red
    Write-Host "`nPyInstaller output:" -ForegroundColor Yellow
    Write-Host $pyinstallerOutput
    exit 1
}
Write-Host "  ✓ PyInstaller completed successfully" -ForegroundColor Green

# Step 4: Verify build output
Write-Host "`n[4/6] Verifying build output..." -ForegroundColor Yellow

$exePath = "dist\TechDeck\TechDeck.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "  ✗ Executable not found at $exePath" -ForegroundColor Red
    exit 1
}

$exeSize = [math]::Round((Get-Item $exePath).Length / 1MB, 2)
Write-Host "  ✓ Executable created: $exeSize MB" -ForegroundColor Green

# Verify critical assets were copied
$criticalAssets = @(
    "dist\TechDeck\_internal\assets\icons\dark\chevron-down.svg",
    "dist\TechDeck\_internal\assets\icons\light\chevron-down.svg",
    "dist\TechDeck\_internal\assets\TechDeck.ico",
    "dist\TechDeck\_internal\plugins"
)

$missingAssets = @()
foreach ($asset in $criticalAssets) {
    if (-not (Test-Path $asset)) {
        $missingAssets += $asset
        Write-Host "  ✗ Missing asset: $asset" -ForegroundColor Red
    }
}

if ($missingAssets.Count -gt 0) {
    Write-Host "`n  ERROR: Build is missing required assets!" -ForegroundColor Red
    Write-Host "  This build will NOT work properly." -ForegroundColor Red
    Write-Host "`n  Possible fixes:" -ForegroundColor Yellow
    Write-Host "    1. Check TechDeck.spec includes: ('assets', 'assets')" -ForegroundColor Yellow
    Write-Host "    2. Check TechDeck.spec includes: ('plugins', 'plugins')" -ForegroundColor Yellow
    Write-Host "    3. Verify source assets exist in project root" -ForegroundColor Yellow
    exit 1
}

Write-Host "  ✓ All critical assets included" -ForegroundColor Green

# Count total assets
$assetCount = (Get-ChildItem -Path "dist\TechDeck\_internal\assets" -Recurse -File).Count
Write-Host "  ✓ Total assets bundled: $assetCount files" -ForegroundColor Green

# Step 5: Build Inno Setup installer
if (-not $SkipInstaller) {
    Write-Host "`n[5/6] Building Inno Setup installer..." -ForegroundColor Yellow
    
    $isccPaths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )
    
    $iscc = $null
    foreach ($path in $isccPaths) {
        if (Test-Path $path) {
            $iscc = $path
            break
        }
    }
    
    if ($iscc) {
        $innoOutput = & $iscc "TechDeck-Setup.iss" 2>&1
        if ($LASTEXITCODE -eq 0) {
            $installerPath = "installer_output\TechDeck-$version-Setup.exe"
            if (Test-Path $installerPath) {
                $installerSize = [math]::Round((Get-Item $installerPath).Length / 1MB, 2)
                Write-Host "  ✓ Installer created: $installerSize MB" -ForegroundColor Green
            } else {
                Write-Host "  ✗ Installer not found at expected path" -ForegroundColor Red
            }
        } else {
            Write-Host "  ✗ Inno Setup compilation failed" -ForegroundColor Red
            Write-Host "`nInno Setup output:" -ForegroundColor Yellow
            Write-Host $innoOutput
        }
    } else {
        Write-Host "  ⚠ Inno Setup not found - skipping installer" -ForegroundColor Yellow
    }
} else {
    Write-Host "`n[5/6] Skipping installer build" -ForegroundColor Gray
}

# Step 6: Summary
Write-Host "`n[6/6] Build Summary" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Version: v$version" -ForegroundColor Green
Write-Host "  Executable: $exePath ($exeSize MB)" -ForegroundColor Green
Write-Host "  Assets: $assetCount files" -ForegroundColor Green

if (-not $SkipInstaller -and (Test-Path "installer_output\TechDeck-$version-Setup.exe")) {
    $installerPath = "installer_output\TechDeck-$version-Setup.exe"
    $installerSize = [math]::Round((Get-Item $installerPath).Length / 1MB, 2)
    Write-Host "  Installer: $installerPath ($installerSize MB)" -ForegroundColor Green
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Next steps
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Test: .\dist\TechDeck\TechDeck.exe" -ForegroundColor White
Write-Host "  2. Commit: git add . && git commit -m 'v$version'" -ForegroundColor White
Write-Host "  3. Release: Create GitHub release v$version" -ForegroundColor White
Write-Host "  4. Update: manifest.json to version $version" -ForegroundColor White
Write-Host ""
