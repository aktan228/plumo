# Local PostgreSQL 16 without Docker or installation (Windows).
#
#   .\scripts\local-db.ps1 start    # downloads once, creates plumo/plumo, starts on :5432
#   .\scripts\local-db.ps1 stop
#   .\scripts\local-db.ps1 status
#   .\scripts\local-db.ps1 reset    # wipes local data
#
# Binaries go to .tools\pgsql, data to .pgdata. Both are git-ignored.
# Same connection string as docker compose: postgresql+asyncpg://plumo:plumo@localhost:5432/plumo

param([ValidateSet("start", "stop", "status", "reset")][string]$Action = "start")

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $Root ".tools"
$Bin = Join-Path $Tools "pgsql\bin"
$Data = Join-Path $Root ".pgdata"
$Log = Join-Path $Tools "postgres.log"
$Url = "https://get.enterprisedb.com/postgresql/postgresql-16.4-1-windows-x64-binaries.zip"

function Ensure-Binaries {
    if (Test-Path (Join-Path $Bin "pg_ctl.exe")) { return }
    New-Item -ItemType Directory -Force $Tools | Out-Null
    $zip = Join-Path $Tools "pg16.zip"
    Write-Host "Downloading PostgreSQL 16 binaries (~340 MB)..."
    Invoke-WebRequest -Uri $Url -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $Tools -Force
    Remove-Item $zip
}

function Ensure-Cluster {
    if (Test-Path (Join-Path $Data "PG_VERSION")) { return }
    $pw = Join-Path $Tools "pwfile.txt"
    Set-Content -Path $pw -Value "plumo" -Encoding ascii -NoNewline
    & (Join-Path $Bin "initdb.exe") -D $Data -U plumo --pwfile=$pw -E UTF8 --locale=C -A scram-sha-256 | Out-Null
    Remove-Item $pw
}

function Is-Running {
    & (Join-Path $Bin "pg_ctl.exe") status -D $Data *> $null
    return $LASTEXITCODE -eq 0
}

switch ($Action) {
    "start" {
        Ensure-Binaries
        Ensure-Cluster
        if (-not (Is-Running)) {
            # Start-Process: a direct call hangs, the server inherits the console pipes.
            $ctl = Join-Path $Bin "pg_ctl.exe"
            Start-Process -FilePath $ctl -ArgumentList @("start", "-D", "`"$Data`"", "-l", "`"$Log`"", "-o", "`"-p 5432`"") -WindowStyle Hidden
            for ($i = 0; $i -lt 30; $i++) {
                & (Join-Path $Bin "pg_isready.exe") -h localhost -p 5432 *> $null
                if ($LASTEXITCODE -eq 0) { break }
                Start-Sleep -Milliseconds 500
            }
        }
        $env:PGPASSWORD = "plumo"
        $exists = & (Join-Path $Bin "psql.exe") -h localhost -U plumo -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='plumo'"
        if ($exists -ne "1") {
            & (Join-Path $Bin "createdb.exe") -h localhost -U plumo plumo
        }
        Write-Host "PostgreSQL is up: postgresql+asyncpg://plumo:plumo@localhost:5432/plumo"
    }
    "stop" {
        if (Is-Running) { & (Join-Path $Bin "pg_ctl.exe") stop -D $Data -m fast | Out-Null }
        Write-Host "PostgreSQL stopped"
    }
    "status" {
        if (Is-Running) { Write-Host "running" } else { Write-Host "stopped" }
    }
    "reset" {
        if (Is-Running) { & (Join-Path $Bin "pg_ctl.exe") stop -D $Data -m fast | Out-Null }
        if (Test-Path $Data) { Remove-Item -Recurse -Force $Data }
        Write-Host "Local data removed. Run 'start' to create a fresh database."
    }
}
