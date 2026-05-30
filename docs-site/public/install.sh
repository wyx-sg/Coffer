#!/bin/sh
# Coffer one-line installer — POSIX sh
#
# Usage:
#   curl -fsSL --proto '=https' --tlsv1.2 \
#       https://wyx-sg.github.io/Coffer/install.sh | sh
#
# Environment variables:
#   COFFER_INSTALL_DIR   Install directory (default: ~/.coffer/bin)
#   COFFER_VERSION       Release tag to install, e.g. v0.1.0 (default: latest)
#   COFFER_NO_MODIFY_PATH  Set to 1 to skip adding install dir to shell profile
#
# Windows users: use the PowerShell one-liner instead:
#   irm https://wyx-sg.github.io/Coffer/install.ps1 | iex
#
# Full install guide: https://wyx-sg.github.io/Coffer/guide/install

set -eu

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

say() {
    printf 'coffer-install: %s\n' "$*"
}

err() {
    printf 'coffer-install: error: %s\n' "$*" >&2
    exit 1
}

need_cmd() {
    if ! command -v "$1" > /dev/null 2>&1; then
        err "required command not found: '$1' — please install it and try again"
    fi
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

main() {
    # --- check required tools -----------------------------------------------
    need_cmd curl
    need_cmd tar
    need_cmd uname

    if command -v sha256sum > /dev/null 2>&1; then
        SHASUM_CMD="sha256sum"
    elif command -v shasum > /dev/null 2>&1; then
        SHASUM_CMD="shasum -a 256"
    else
        err "neither 'sha256sum' nor 'shasum' found — please install one and try again"
    fi

    # --- detect OS + arch → triple ------------------------------------------
    _os="$(uname -s)"
    _arch="$(uname -m)"

    case "$_os" in
        Darwin)
            case "$_arch" in
                arm64)   triple="aarch64-apple-darwin" ;;
                x86_64)  triple="x86_64-apple-darwin" ;;
                *)       err "unsupported macOS architecture: $_arch" ;;
            esac
            archive_ext="tar.gz"
            ;;
        Linux)
            case "$_arch" in
                x86_64)  triple="x86_64-unknown-linux-gnu" ;;
                *)
                    err "unsupported Linux architecture: $_arch
Linux ARM / aarch64 builds are not yet published. See https://wyx-sg.github.io/Coffer/guide/install for alternatives."
                    ;;
            esac
            archive_ext="tar.gz"
            ;;
        MINGW*|MSYS*|CYGWIN*|Windows*)
            err "Windows detected — use the PowerShell one-liner instead:
  irm https://wyx-sg.github.io/Coffer/install.ps1 | iex"
            ;;
        *)
            err "unsupported OS: $_os
Only macOS and Linux x86_64 are supported by this script.
See https://wyx-sg.github.io/Coffer/guide/install for alternatives."
            ;;
    esac

    # --- resolve install dir -------------------------------------------------
    install_dir="${COFFER_INSTALL_DIR:-$HOME/.coffer/bin}"
    mkdir -p "$install_dir"

    # --- resolve download URL ------------------------------------------------
    base_repo="https://github.com/wyx-sg/Coffer"
    archive_name="coffer-cli-${triple}.${archive_ext}"
    checksums_name="SHA256SUMS"

    if [ -n "${COFFER_VERSION:-}" ]; then
        # Normalize: strip leading 'v' then re-add it
        _ver="${COFFER_VERSION#v}"
        version="v${_ver}"
        dl_base="${base_repo}/releases/download/${version}"
    else
        dl_base="${base_repo}/releases/latest/download"
    fi

    archive_url="${dl_base}/${archive_name}"
    checksums_url="${dl_base}/${checksums_name}"

    say "installing Coffer CLI to ${install_dir}"
    say "archive:   ${archive_url}"
    say "checksums: ${checksums_url}"

    # --- download into a temp dir -------------------------------------------
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT

    say "downloading archive..."
    curl -fsSL --proto '=https' --tlsv1.2 -o "${tmp}/${archive_name}" "${archive_url}"

    say "downloading checksums..."
    curl -fsSL --proto '=https' --tlsv1.2 -o "${tmp}/${checksums_name}" "${checksums_url}"

    # --- verify checksum -----------------------------------------------------
    say "verifying checksum..."
    # grep the line for our archive, write a single-entry checksums file,
    # then verify from within the temp dir so relative paths resolve correctly
    grep -F "${archive_name}" "${tmp}/${checksums_name}" > "${tmp}/expected.txt" \
        || err "archive '${archive_name}' not found in SHA256SUMS"
    ( cd "$tmp" && $SHASUM_CMD -c expected.txt --status ) \
        || err "checksum mismatch — download may be corrupted; please retry"
    say "checksum OK"

    # --- extract -------------------------------------------------------------
    say "extracting..."
    tar -xzf "${tmp}/${archive_name}" -C "$tmp"

    # --- install -------------------------------------------------------------
    for bin in coffer coffer-daemon coffer-mcp-shim; do
        if [ ! -f "${tmp}/${bin}" ]; then
            err "binary '${bin}' not found in archive — the release may be malformed"
        fi
        cp "${tmp}/${bin}" "${install_dir}/${bin}"
        chmod +x "${install_dir}/${bin}"
    done

    say "installed coffer, coffer-daemon, coffer-mcp-shim to ${install_dir}"

    # --- PATH setup ----------------------------------------------------------
    _on_path=0
    case ":${PATH}:" in
        *":${install_dir}:"*) _on_path=1 ;;
    esac

    if [ "$_on_path" -eq 0 ]; then
        # Detect the shell profile AND the correct path-export syntax up front,
        # so the COFFER_NO_MODIFY_PATH hint matches the user's shell (fish has
        # no `export` and uses `fish_add_path`, not `$PATH`).
        _profile=""
        _path_line="export PATH=\"${install_dir}:\$PATH\""
        _shell_name="$(basename "${SHELL:-}")"

        case "$_shell_name" in
            zsh)
                _profile="${ZDOTDIR:-$HOME}/.zshrc"
                ;;
            bash)
                # On macOS bash uses .bash_profile for login shells;
                # on Linux .bashrc is more common for interactive shells.
                if [ "$(uname -s)" = "Darwin" ]; then
                    _profile="$HOME/.bash_profile"
                else
                    _profile="$HOME/.bashrc"
                fi
                ;;
            fish)
                _fish_config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/fish"
                _profile="$_fish_config_dir/config.fish"
                _path_line="fish_add_path ${install_dir}"
                ;;
            *)
                _profile="$HOME/.profile"
                ;;
        esac

        if [ "${COFFER_NO_MODIFY_PATH:-0}" = "1" ]; then
            say ""
            say "Add the following line to ${_profile} to put Coffer on PATH:"
            say "  ${_path_line}"
        elif [ -f "$_profile" ] && grep -qF "${_path_line}" "$_profile" 2>/dev/null; then
            # Idempotent: a previous run already added the line (the current
            # shell's PATH just hasn't been reloaded yet). Don't duplicate it.
            say "PATH entry already present in ${_profile}"
        else
            [ "$_shell_name" = "fish" ] && mkdir -p "$_fish_config_dir"
            printf '\n# Added by Coffer installer\n%s\n' "${_path_line}" >> "$_profile"
            say "added '${_path_line}' to ${_profile}"
            say "restart your shell or run: source ${_profile}"
        fi
    fi

    # --- post-install message ------------------------------------------------
    say ""
    say "============================================================"
    say " Coffer installed successfully!"
    say "============================================================"
    say ""
    say "  Coffer starts AUTOMATICALLY — you never run a daemon manually."
    say ""
    say "  Connect an MCP client:"
    say "    claude mcp add coffer coffer-mcp-shim"
    say "  The daemon auto-starts on first use."
    say ""
    say "  Manage servers from the terminal:"
    say "    coffer mcp add ...   (daemon auto-starts)"
    say "    coffer mcp list"
    say ""
    say "  Full guide: https://wyx-sg.github.io/Coffer/guide/install"
    say ""
}

main "$@"
