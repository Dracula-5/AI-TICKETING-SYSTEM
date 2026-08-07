#!/usr/bin/env powershell
<#
AI Ticketing System - Startup Script
Simple startup for local development
#>

Write-Host "`n" -ForegroundColor Green
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║         AI TICKETING SYSTEM - STARTUP SCRIPT                 ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

$projectRoot = "c:\Users\dheer\OneDrive\Desktop\PROJECT1"
$backendDir = "$projectRoot\ai-ticketing-system\backend"
$frontendDir = "$projectRoot\ai-ticketing-system\frontend"

# Colors
$success = "Green"
$info = "Cyan"
$warning = "Yellow"

Write-Host "📁 Project Root: $projectRoot" -ForegroundColor $info
Write-Host ""

# Backend Setup
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor $info
Write-Host "BACKEND SETUP" -ForegroundColor $info
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor $info

Set-Location $backendDir

if (-not (Test-Path "venv")) {
    Write-Host "📦 Creating Python virtual environment..." -ForegroundColor $warning
    python -m venv venv
    Write-Host "✓ Virtual environment created" -ForegroundColor $success
} else {
    Write-Host "✓ Virtual environment already exists" -ForegroundColor $success
}

Write-Host "📥 Installing backend dependencies..." -ForegroundColor $warning
& ".\venv\Scripts\python.exe" -m pip install -q -r requirements.txt
Write-Host "✓ Dependencies installed" -ForegroundColor $success

# Frontend Setup
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor $info
Write-Host "FRONTEND SETUP" -ForegroundColor $info
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor $info

Set-Location $frontendDir

if (-not (Test-Path "node_modules")) {
    Write-Host "📦 Installing npm packages..." -ForegroundColor $warning
    npm install --silent 2>&1 | Out-Null
    Write-Host "✓ npm packages installed" -ForegroundColor $success
} else {
    Write-Host "✓ npm packages already installed" -ForegroundColor $success
}

# Start Services
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor $info
Write-Host "STARTING SERVICES" -ForegroundColor $info
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor $info
Write-Host ""

Write-Host "🚀 Starting Backend (Port 8000)..." -ForegroundColor $success
Start-Process powershell -ArgumentList @"
    Set-Location "$backendDir"
    & ".\venv\Scripts\activate.ps1"
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"@

Write-Host "🚀 Starting Frontend (Port 3000)..." -ForegroundColor $success
Start-Process powershell -ArgumentList @"
    Set-Location "$frontendDir"
    npm start
"@

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor $success
Write-Host "✓ SERVICES STARTING" -ForegroundColor $success
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor $success
Write-Host ""
Write-Host "📍 Frontend:  http://localhost:3000" -ForegroundColor $info
Write-Host "📍 Backend:   http://localhost:8000" -ForegroundColor $info
Write-Host "📍 API Docs:  http://localhost:8000/docs" -ForegroundColor $info
Write-Host ""
Write-Host "🔐 Demo Login:" -ForegroundColor $warning
Write-Host "   Email: admin@hospital.com" -ForegroundColor $info
Write-Host "   Password: admin123" -ForegroundColor $info
Write-Host ""
Write-Host "📖 Documentation:" -ForegroundColor $warning
Write-Host "   Theory:  THEORY.md  (architecture & design)" -ForegroundColor $info
Write-Host "   Usage:   USAGE.md   (setup & deployment)" -ForegroundColor $info
Write-Host ""
