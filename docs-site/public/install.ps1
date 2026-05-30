# Coffer one-line installer — Windows PowerShell
#
# Usage (run from PowerShell as a regular user):
#   irm https://wyx-sg.github.io/Coffer/install.ps1 | iex
#
# Environment variables:
#   COFFER_INSTALL_DIR   Install directory (default: $env:USERPROFILE\.coffer\bin)
#   COFFER_VERSION       Release tag to install, e.g. v0.1.0 (default: latest)
#   COFFER_NO_MODIFY_PATH  Set to '1' to skip adding install dir to User PATH
#
# macOS / Linux users: use the shell one-liner instead:
#   curl -fsSL --proto '=https' --tlsv1.2 \
#       https://wyx-sg.github.io/Coffer/install.sh | sh
#
# Full install guide: https://wyx-sg.github.io/Coffer/guide/install

$ErrorActionPreference = 'Stop'

# Force TLS 1.2+. Stock Windows PowerShell 5.1 on older systems may negotiate
# a protocol GitHub rejects, aborting the download with an SSL/TLS error
# before we ever reach checksum/extract. Harmless on modern hosts.
try {
    [Net.ServicePointManager]::SecurityProtocol = `
        [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {
    # Older runtimes may not expose the Tls12 enum value; nothing to do.
}

function Write-Step {
    param([string]$Message)
    Write-Host "coffer-install: $Message"
}

function Write-Fatal {
    param([string]$Message)
    Write-Host "coffer-install: error: $Message" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
# Detect architecture
# ---------------------------------------------------------------------------

$arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
if ($arch -ne [System.Runtime.InteropServices.Architecture]::X64) {
    Write-Fatal "Unsupported architecture: $arch. Only x86_64 (64-bit) Windows is supported."
}
$triple = 'x86_64-pc-windows-msvc'

# ---------------------------------------------------------------------------
# Resolve install directory
# ---------------------------------------------------------------------------

$installDir = if ($env:COFFER_INSTALL_DIR) { $env:COFFER_INSTALL_DIR } `
              else { Join-Path $env:USERPROFILE '.coffer\bin' }

if (-not (Test-Path $installDir)) {
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
}

# ---------------------------------------------------------------------------
# Resolve download URL
# ---------------------------------------------------------------------------

$baseRepo = 'https://github.com/wyx-sg/Coffer'
$archiveName = "coffer-cli-${triple}.zip"
$checksumsName = 'SHA256SUMS'

if ($env:COFFER_VERSION) {
    $version = $env:COFFER_VERSION.TrimStart('v')
    $dlBase = "${baseRepo}/releases/download/v${version}"
} else {
    $dlBase = "${baseRepo}/releases/latest/download"
}

$archiveUrl   = "${dlBase}/${archiveName}"
$checksumsUrl = "${dlBase}/${checksumsName}"

Write-Step "installing Coffer CLI to $installDir"
Write-Step "archive:   $archiveUrl"
Write-Step "checksums: $checksumsUrl"

# ---------------------------------------------------------------------------
# Download into a temp directory
# ---------------------------------------------------------------------------

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName())
New-Item -ItemType Directory -Path $tmp -Force | Out-Null

try {
    Write-Step 'downloading archive...'
    Invoke-WebRequest -Uri $archiveUrl -OutFile (Join-Path $tmp $archiveName) -UseBasicParsing

    Write-Step 'downloading checksums...'
    Invoke-WebRequest -Uri $checksumsUrl -OutFile (Join-Path $tmp $checksumsName) -UseBasicParsing

    # -------------------------------------------------------------------------
    # Verify checksum
    # -------------------------------------------------------------------------

    Write-Step 'verifying checksum...'

    $archivePath    = Join-Path $tmp $archiveName
    $checksumsPath  = Join-Path $tmp $checksumsName

    # Read SHA256SUMS and find the line for our archive.
    # Format: "<hash>  <filename>" or "<hash> *<filename>"
    $checksumLine = Get-Content $checksumsPath |
        Where-Object { $_ -match [regex]::Escape($archiveName) } |
        Select-Object -First 1

    if (-not $checksumLine) {
        Write-Fatal "Archive '$archiveName' not found in SHA256SUMS."
    }

    # Parse the expected hash (first whitespace-delimited token)
    $expectedHash = ($checksumLine -split '\s+')[0].ToUpper()

    $actualHash = (Get-FileHash -Path $archivePath -Algorithm SHA256).Hash.ToUpper()

    if ($actualHash -ne $expectedHash) {
        Write-Fatal "Checksum mismatch!`n  expected: $expectedHash`n  got:      $actualHash`nDownload may be corrupted; please retry."
    }

    Write-Step 'checksum OK'

    # -------------------------------------------------------------------------
    # Extract
    # -------------------------------------------------------------------------

    Write-Step 'extracting...'
    Expand-Archive -Path $archivePath -DestinationPath $tmp -Force

    # -------------------------------------------------------------------------
    # Install binaries
    # -------------------------------------------------------------------------

    $binaries = @('coffer.exe', 'coffer-daemon.exe', 'coffer-mcp-shim.exe')
    foreach ($bin in $binaries) {
        $src = Join-Path $tmp $bin
        if (-not (Test-Path $src)) {
            Write-Fatal "Binary '$bin' not found in archive — the release may be malformed."
        }
        Copy-Item -Path $src -Destination (Join-Path $installDir $bin) -Force
    }

    Write-Step "installed coffer.exe, coffer-daemon.exe, coffer-mcp-shim.exe to $installDir"

} finally {
    # Clean up temp dir regardless of success or failure
    if (Test-Path $tmp) {
        Remove-Item -Path $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------------------
# PATH setup — add install dir to User PATH if not already present
# ---------------------------------------------------------------------------

$userPath = [System.Environment]::GetEnvironmentVariable('PATH', 'User')
$pathEntries = $userPath -split ';' | Where-Object { $_ -ne '' }

# Normalise before comparing so an existing entry that differs only by a
# trailing backslash or an unexpanded %USERPROFILE% token is still detected
# (otherwise a re-run appends a duplicate). PowerShell -ieq is case-insensitive.
$normInstall = $installDir.TrimEnd('\')
$alreadyOnPath = $pathEntries | Where-Object {
    [System.Environment]::ExpandEnvironmentVariables($_).TrimEnd('\') -ieq $normInstall
}

if (-not $alreadyOnPath) {
    if ($env:COFFER_NO_MODIFY_PATH -eq '1') {
        Write-Step ''
        Write-Step 'Add the following directory to your PATH to use Coffer from any terminal:'
        Write-Step "  $installDir"
    } else {
        $newPath = ($pathEntries + $installDir) -join ';'
        [System.Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')
        # Also update the current session's PATH so Coffer is usable immediately
        $env:PATH = "$env:PATH;$installDir"
        Write-Step "added '$installDir' to User PATH"
        Write-Step 'You may need to restart your terminal for PATH changes to take effect in new sessions.'
    }
}

# ---------------------------------------------------------------------------
# Post-install message
# ---------------------------------------------------------------------------

Write-Host ''
Write-Host 'coffer-install: ============================================================'
Write-Host 'coffer-install:  Coffer installed successfully!'
Write-Host 'coffer-install: ============================================================'
Write-Host ''
Write-Host 'coffer-install:   Coffer starts AUTOMATICALLY — you never run a daemon manually.'
Write-Host ''
Write-Host 'coffer-install:   Connect an MCP client:'
Write-Host 'coffer-install:     claude mcp add coffer coffer-mcp-shim'
Write-Host 'coffer-install:   The daemon auto-starts on first use.'
Write-Host ''
Write-Host 'coffer-install:   Manage servers from the terminal:'
Write-Host 'coffer-install:     coffer mcp add ...   (daemon auto-starts)'
Write-Host 'coffer-install:     coffer mcp list'
Write-Host ''
Write-Host 'coffer-install:   Full guide: https://wyx-sg.github.io/Coffer/guide/install'
Write-Host ''
