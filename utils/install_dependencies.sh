#!/usr/bin/env bash
# install_dependencies.sh
#
# Usage
#   ./install_dependencies.sh
#
# What it does
#   1. Installs required system dependencies like **unzip**, **Maven**
#      and Java SDK 8 / 11 / 17 if they are missing (Ubuntu/Debian‑based
#      systems only; other distros print a hint).
# ------------------------------------------------------------------------------

maybe_sudo() {
  # Only use sudo if the binary exists and we're not root
  if command -v sudo >/dev/null 2>&1 && [[ $EUID -ne 0 ]]; then
    sudo "$@"
  else
    "$@"
  fi
}

# ------------------------------------------------------------------------------
# Ensure 'bash' is present (attempt to install if missing)
ensure_bash() {
  if ! command -v bash >/dev/null 2>&1; then
    printf "▶ 'bash' not found. Attempting to install…\n"
    if command -v apt-get >/dev/null 2>&1; then
      maybe_sudo apt-get update -y && maybe_sudo apt-get install -y bash
    elif command -v dnf >/dev/null 2>&1; then
      maybe_sudo dnf install -y bash
    elif command -v pacman >/dev/null 2>&1; then
      maybe_sudo pacman -Sy --noconfirm bash
    elif command -v brew >/dev/null 2>&1; then
      maybe_sudo brew install bash
    else
      printf "❌  Could not detect package manager. Please install 'bash' manually.\n" >&2
      exit 1
    fi
  fi
}

# ------------------------------------------------------------------------------
# Ensure 'curl' is present (attempt to install if missing)
ensure_curl() {
  if ! command -v curl >/dev/null 2>&1; then
    printf "▶ 'curl' not found. Attempting to install…\n"
    if command -v apt-get >/dev/null 2>&1; then
      maybe_sudo apt-get update -y && maybe_sudo apt-get install -y curl
    elif command -v dnf >/dev/null 2>&1; then
      maybe_sudo dnf install -y curl
    elif command -v pacman >/dev/null 2>&1; then
      maybe_sudo pacman -Sy --noconfirm curl
    elif command -v brew >/dev/null 2>&1; then
      maybe_sudo brew install curl
    else
      printf "❌  Could not detect package manager. Please install 'curl' manually.\n" >&2
      exit 1
    fi
  fi
}

# ------------------------------------------------------------------------------
# Ensure 'git' is present (attempt to install if missing)
ensure_git() {
  if ! command -v git >/dev/null 2>&1; then
    printf "▶ 'git' not found. Attempting to install…\n"
    if command -v apt-get >/dev/null 2>&1; then
      maybe_sudo apt-get update -y && maybe_sudo apt-get install -y git
    elif command -v dnf >/dev/null 2>&1; then
      maybe_sudo dnf install -y git
    elif command -v pacman >/dev/null 2>&1; then
      maybe_sudo pacman -Sy --noconfirm git
    elif command -v brew >/dev/null 2>&1; then
      maybe_sudo brew install git
    else
      printf "❌  Could not detect package manager. Please install 'git' manually.\n" >&2
      exit 1
    fi
  fi
}

# ------------------------------------------------------------------------------
# Ensure 'unzip' is present (attempt to install if missing)
ensure_unzip() {
  if ! command -v unzip >/dev/null 2>&1; then
    printf "▶ 'unzip' not found. Attempting to install…\n"
    if command -v apt-get >/dev/null 2>&1; then
      maybe_sudo apt-get update -y && maybe_sudo apt-get install -y unzip
    elif command -v dnf >/dev/null 2>&1; then
      maybe_sudo dnf install -y unzip
    elif command -v pacman >/dev/null 2>&1; then
      maybe_sudo pacman -Sy --noconfirm unzip
    elif command -v brew >/dev/null 2>&1; then
      maybe_sudo brew install unzip
    else
      printf "❌  Could not detect package manager. Please install 'unzip' manually.\n" >&2
      exit 1
    fi
  fi
  # Mark all directories safe for Git
  git config --global --add safe.directory '*'
}

# ------------------------------------------------------------------------------
# Ensure 'mvn' (Apache Maven) is present (attempt to install if missing)
ensure_maven() {
  if ! command -v mvn >/dev/null 2>&1; then
    printf "▶ 'mvn' not found. Attempting to install…\n"
    # Install Maven 3.6.3 manually
    mkdir -p /opt
    curl -fsSL https://archive.apache.org/dist/maven/maven-3/3.6.3/binaries/apache-maven-3.6.3-bin.tar.gz | tar -xz -C /opt
    maybe_sudo ln -s /opt/apache-maven-3.6.3 /opt/maven
    maybe_sudo ln -s /opt/maven/bin/mvn /usr/bin/mvn
  fi
}

# ------------------------------------------------------------------------------
# Ensure 'pip3' is present (attempt to install if missing)
ensure_pip() {
  if ! command -v pip3 >/dev/null 2>&1; then
    printf "▶ 'pip3' not found. Attempting to install…\n"
    if command -v apt-get >/dev/null 2>&1; then
      maybe_sudo apt-get update -y && maybe_sudo apt-get install -y python3-pip
    elif command -v dnf >/dev/null 2>&1; then
      maybe_sudo dnf install -y python3-pip
    elif command -v pacman >/dev/null 2>&1; then
      maybe_sudo pacman -Sy --noconfirm python-pip
    elif command -v brew >/dev/null 2>&1; then
      maybe_sudo brew install python
    else
      printf "❌  Could not detect package manager. Please install 'pip3' manually.\n" >&2
      exit 1
    fi
  fi
}

# ------------------------------------------------------------------------------
# Ensure Java SDKs (8, 11, 17) are present
ensure_java() {
  if command -v javac >/dev/null 2>&1; then
    # Check for specific versions; install missing ones
    MISSING=()
    for v in 8 11 17; do
      if ! update-java-alternatives -l 2>/dev/null | grep -q "java-${v}-openjdk"; then
        MISSING+=("openjdk-${v}-jdk")
      fi
    done
    if (( ${#MISSING[@]} )); then
      printf "▶ Installing missing JDKs: %s\n" "${MISSING[*]}"
      maybe_sudo apt-get update -y && maybe_sudo apt-get install -y "${MISSING[@]}"
    fi
  elif command -v apt-get >/dev/null 2>&1; then
    maybe_sudo apt-get update -y && maybe_sudo apt-get install -y openjdk-8-jdk openjdk-11-jdk openjdk-17-jdk
  elif command -v dnf >/dev/null 2>&1; then
    maybe_sudo dnf install -y java-1.8.0-openjdk-devel java-11-openjdk-devel java-17-openjdk-devel
  elif command -v pacman >/dev/null 2>&1; then
    maybe_sudo pacman -Sy --noconfirm jdk8-openjdk jdk11-openjdk jdk17-openjdk
  elif command -v brew >/dev/null 2>&1; then
    maybe_sudo brew install openjdk@8 openjdk@11 openjdk@17
  else
    printf "❌  Could not detect package manager to install JDKs.\n" >&2
    exit 1
  fi
}

# ------------------------------------------------------------------------------
# Ensure 'pandas' Python package is present
ensure_pandas() {
  if command -v python3 >/dev/null 2>&1; then
    if ! python3 - <<<'import pandas' >/dev/null 2>&1; then
      printf "▶ Installing missing Python dependency: pandas\n"
      maybe_sudo python3 -m pip install --upgrade pip
      maybe_sudo python3 -m pip install pandas
    fi
  fi
}

# ------------------------------------------------------------------------------
ensure_bash
ensure_curl
ensure_git
ensure_unzip
ensure_maven
ensure_java
ensure_pip
ensure_pandas
