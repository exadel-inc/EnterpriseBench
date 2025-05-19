#!/usr/bin/env bash
# prepare_dataverse.sh
#
# Usage
#   ./prepare_dataverse.sh dataverse_files.zip      # if you have the archive
#   ./prepare_dataverse.sh dataverse_files          # if it is already unzipped
#
# What it does
#   1. Unzips the root archive (if a .zip is provided).
#   2. For every immediate sub-folder (AuthoringToolKit, CompreFace, …):
#        • Renames the single *.csv → pr_states.csv
#        • Unpacks patches_neg-*.zip → patches_neg/   (folder)
#        • Unpacks patches_pos-*.zip → patches_pos/   (folder)
#        • Unpacks the main repo zip (the one **without** “-mock”) → project_repo/
#

# Prerequisites: Bash ≥ 4 and “unzip” installed.
# ------------------------------------------------------------------------------
maybe_sudo() {
  if [[ $EUID -ne 0 ]]; then
    sudo "$@"
  else
    "$@"
  fi
}

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

ensure_unzip
ensure_maven
# ------------------------------------------------------------------------------
# ---------------------------------------------------------------------------
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
ensure_java
# ---------------------------------------------------------------------------

# ──────────────────────────────────────────────────────────────────────────────
# Optional auto‑download of the dataset archive
# Dataverse “original” format downloads the whole dataset as a single ZIP archive
DATAVERSE_URL="https://dataverse.harvard.edu/api/access/dataset/:persistentId/?persistentId=doi:10.7910/DVN/S4WOTJ&format=original"
DOWNLOAD_ZIP="dataverse_files.zip"

if [[ ! -f $DOWNLOAD_ZIP ]]; then
  printf "▶ Downloading dataverse archive to %s (this may take a while…)\n" "$DOWNLOAD_ZIP"
  TMP_FILE="${DOWNLOAD_ZIP}.part"
  # Follow redirects, fail on HTTP errors, show progress, and retry on transient issues
  if ! curl --location --fail --progress-bar --retry 3 --retry-delay 5 \
            --output "$TMP_FILE" "$DATAVERSE_URL"; then
    echo "❌  Download failed. Please check your Internet connection or download the file manually:"
    echo "    $DATAVERSE_URL"
    exit 1
  fi
  mv -f "$TMP_FILE" "$DOWNLOAD_ZIP"
fi
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail
shopt -s nullglob              # empty globs expand to nothing, not themselves

usage() { printf "Usage: %s [dataverse_files.zip | dataverse_files_dir]\n" "$0"; exit 1; }

if (( $# )); then
  INPUT=$1
else
  INPUT=$DOWNLOAD_ZIP          # default to the freshly downloaded archive
fi

if [[ $INPUT == *.zip ]]; then
  if ! unzip -t "$INPUT" >/dev/null 2>&1; then
    echo "❌ Invalid or corrupted zip file: $INPUT" >&2
    exit 1
  fi
fi

# 1. Unzip the top‑level archive only if the target directory is missing or empty
if [[ $INPUT == *.zip ]]; then
  ROOT_DIR=${INPUT%.zip}       # strip trailing “.zip”
  if [[ -d $ROOT_DIR && $(ls -A "$ROOT_DIR" 2>/dev/null) ]]; then
    printf "▶ %s already exists – skipping all extraction & rename steps.\n" "$ROOT_DIR"
    exit 0
  else
    printf "▶ Unzipping %s to %s/\n" "$INPUT" "$ROOT_DIR"
    rm -rf "$ROOT_DIR"
    mkdir -p "$ROOT_DIR"
    unzip -q "$INPUT" -d "$ROOT_DIR"
  fi
elif [[ -d $INPUT ]]; then
  ROOT_DIR=$INPUT
  if [[ $(ls -A "$ROOT_DIR" 2>/dev/null) ]]; then
    printf "▶ %s already exists – skipping all extraction & rename steps.\n" "$ROOT_DIR"
    exit 0
  fi
else
  printf "❌  %s is neither a directory nor a .zip file\n" "$INPUT" >&2
  exit 1
fi

# 2-4. Walk each project directory and apply the transformations
for PROJECT_DIR in "$ROOT_DIR"/*/; do
  [[ ! -d $PROJECT_DIR ]] && continue
  printf "\n◆ Processing %s\n" "${PROJECT_DIR%/}"
  pushd "$PROJECT_DIR" >/dev/null

  # Symlink the system JDK directory (/usr/lib/jvm) as "jvm" for this project
  if [[ -d /usr/lib/jvm ]]; then
    maybe_sudo ln -sfn /usr/lib/jvm jvm
  fi

  # 2. Rename *.csv → pr_states.csv
  for CSV in *.csv; do
    [[ $CSV == pr_states.csv ]] && continue   # already done
    printf "  • Renaming %s → pr_states.csv\n" "$CSV"
    mv -f -- "$CSV" pr_states.csv
  done

  # 3. Unpack and rename patch archives
  for KIND in neg pos; do
    for ZIP in patches_"$KIND"-*.zip; do
      TARGET=patches_"$KIND"                 # desired folder name
      printf "  • Unzipping %s → %s/\n" "$ZIP" "$TARGET"
      rm -rf "$TARGET"
      mkdir -p "$TARGET"
      unzip -q "$ZIP" -d "$TARGET"
      rm -rf "$TARGET"/__MACOSX               # drop macOS metadata dirs
      find "$TARGET" -name '._*' -type f -delete   # remove AppleDouble resource‑fork files

      # ── Flatten one superfluous level (e.g., patches_neg/patches_neg‑EAK/*) ──
      if [[ $(find "$TARGET" -mindepth 1 -maxdepth 1 -type d | wc -l) -eq 1 ]] && \
         [[ $(find "$TARGET" -mindepth 1 -maxdepth 1 -type f | wc -l) -eq 0 ]]; then
        SUBDIR=$(find "$TARGET" -mindepth 1 -maxdepth 1 -type d)
        shopt -s dotglob
        mv "$SUBDIR"/* "$TARGET"/
        rmdir "$SUBDIR"
        shopt -u dotglob
      fi
    done
  done

  # 4. Unzip main project repo (skip *-mock.zip and patch archives)
  for ZIP in *.zip; do
    [[ $ZIP == *-mock.zip ]] && continue
    [[ $ZIP == patches_* ]]   && continue
    printf "  • Unzipping %s → project_repo/\n" "$ZIP"
    rm -rf project_repo
    mkdir -p project_repo
    unzip -q "$ZIP" -d project_repo
    rm -rf project_repo/__MACOSX               # remove macOS cruft
    find project_repo -name '._*' -type f -delete       # remove AppleDouble resource‑fork files

    # ── Flatten one unnecessary top‑level directory ──
    if [[ $(find project_repo -mindepth 1 -maxdepth 1 -type d | wc -l) -eq 1 ]] && \
       [[ $(find project_repo -mindepth 1 -maxdepth 1 -type f | wc -l) -eq 0 ]]; then
      SUBDIR=$(find project_repo -mindepth 1 -maxdepth 1 -type d)
      shopt -s dotglob
      mv "$SUBDIR"/* project_repo/
      rmdir "$SUBDIR"
      shopt -u dotglob
    fi
  done

  popd >/dev/null
done

printf "\n✅ All done. Updated content lives in “%s/”.\n" "$ROOT_DIR"