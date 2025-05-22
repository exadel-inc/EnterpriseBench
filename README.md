# EnterpriseBench

We present **EnterpriseBench**, a new commercially grounded benchmark designed to evaluate the capabilities of AI agents in solving real-world software engineering tasks.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Dataset Preparation](#dataset-preparation)
4. [Running the Benchmark](#running-the-benchmark)
5. [Troubleshooting & FAQ](#troubleshooting--faq)
6. [License](#license)

---

## Overview

Addressing limitations in existing benchmarks, we introduce two versions: one based on SWE-bench methodology, featuring a curated set of high-quality selected tasks, and another employing a test-driven development (TDD) paradigm with 147 selected tasks across 3 repositories. Tasks originate from authentic enterprise Jira tickets and cover diverse issue types including bug fixes, and feature implementations. Visual task elements are transformed into textual descriptions using multimodal models. To improve experimentation efficiency, we propose a novel cost efficient strategy based on early agent-model pair selection using limited repositories. Additionally, we introduce experimental stub projects methodology and data, to assess agent performance in complex pipeline construction, offering a stripped-down project skeleton with matching tickets and tests. The benchmark was tested on state of the art AI coding agents. Our dataset is unique in its exclusive use of proprietary commercial data, preventing answer leakage and ensuring non-contamination of current LLM training sets.

---

## Prerequisites

```bash
# Clone the framework
$ git clone https://github.com/exadel-inc/EnterpriseBench.git
$ cd EnterpriseBench
````

| Tool                           | Version                                                                       | Notes                                                       |
| ------------------------------ |-------------------------------------------------------------------------------| ----------------------------------------------------------- |
| **Ubuntu**                     | 20.04.6 LTS (tested)                                                          | Other OSes are **not yet supported**                        |
| **Java Development Kit (JDK)** | AuthoringToolKit (JDK8)<br />CompreFace (JDK17)<br />DynamicMailboxes (JDK11) | Set `JVM_DIR` to the JDK home if it is **not** on your PATH |
| **Maven**                      | Apache Maven 3.6.3                                                            | Used to build the target repo                               |
| **Python**                     | 3.12                                                                          | Required for the orchestration scripts                      |
| **Git**                        | latest                                                                        | Required for checking out historical commits                |

> 🗂️  **Note:** When working with the **AuthoringToolKit** repository you must force the benchmark to use Java 8 by adding `--java-major 8` to the command line of both `4_run_all_tickets.py` and any direct calls to `3_run_ticket_test.py`.

---

## Dataset Preparation

### Automatic setup (recommended)

> 🗂️  Simply run `utils/install_dependencies.sh` to install required system dependencies
> and `utils/prepare_dataverse.sh` to download the Harvard Dataverse archive if needed, which creates the corrects folder layout and renames/unpacks everything exactly as required.

The `install_dependencies.sh` script will:
1. Ensure **bash**, **curl**, **git**, and **unzip** are installed.
2. Install **Apache Maven 3.6.3** if `mvn` is missing.
3. Install Java SDKs 8, 11, and 17 (on Ubuntu/Debian; other distros print a hint).
4. Ensure **pip3** is available (installing `python3-pip` if missing).
5. Install the **pandas** Python package.

The `prepare_dataverse.sh` script will:
1. Download the Harvard Dataverse archive (DOI [10.7910/DVN/S4WOTJ](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/S4WOTJ)) if `dataverse_files.zip` is not already present.
2. Extract the archive into a clean `dataverse_files/` directory – *unless that folder already exists and is non‑empty, in which case the script skips all extraction & rename work*.
3. Inside every project subfolder it  
   • renames `*.csv` → **`pr_states.csv`**  
   • unpacks `patches_neg*`/`patches_pos*` ZIPs into flat `patches_neg/` and `patches_pos/` folders  
   • unzips the main repo archive into a flat **`project_repo/`** folder  
   • creates a `jvm` symlink pointing to `/usr/lib/jvm` (so the benchmark finds all installed JDKs).

> 🗂️  Re‑running the script is idempotent: it detects an existing `dataverse_files/` directory and exits without touching your data or reinstalling the JDKs.

After the script finishes, point `--project-root` at one of the unpacked project sub‑folders (e.g., `dataverse_files/CompreFace`) and jump straight to the [Running the Benchmark](#running-the-benchmark) section.

### Manual setup

EnterpriseBench expects the following artefacts for **every** benchmark run:

1. **`project_root`** - provide the root directory of the benchmark project by calling the script with the `--project-root` argument in the `4_run_all_tickets.py` script.
2. **`pr_states.csv`** – the mapping between issue/ticket IDs and the commit SHA(s) that resolved them.
3. **`project_repo`** – the full Git history of the benchmark project.
4. **`patches_neg/`** – *negative* git diff patches.
5. **`patches_ai/`** – *AI agent* git diff patches (default; can be overridden via `--ai-patches-dir`).

> 🗂️  Rename / copy your dataset file to **`pr_states.csv`** (e.g. `dataset_CF_anonymized.csv → pr_states.csv`).  The scripts look for that exact filename by default.

The directory layout with necessary files should look like this:

```
project_root/
├── pr_states.csv
├── project_repo/         # cloned target project
├── patches_neg/
│   ├── <ticket1>_non_test.diff
│   └── ...
├── patches_ai/
│   ├── <patch_set1>/
│   │   ├── <ticket1>_non_test.diff
│   │   └── ...
│   └── <patch_set2>/
│       ├── <ticket1>_non_test.diff
│       └── ...
```

---

## Running the Benchmark

```bash
$ python3 4_run_all_tickets.py --project-root dataverse_files/CompreFace
```

### AI patches

The following commands apply your AI‑generated patch sets to each of the three benchmark projects that ship in the Harvard Dataverse archive.  
Adjust the `--ai-patches-dir` argument to point at the directory that contains your `<ticket>_non_test.diff` files. If `--ai-patches-dir` is omitted, the script defaults to the `patches_ai` directory within the project root. The script supports multiple AI patch sets. If the provided AI patch directory contains subfolders, each is treated as a distinct patch set and processed separately.

```bash
$ python3 4_run_all_tickets.py --ai --project-root dataverse_files/CompreFace
```

### Golden patches

Place the golden patches in the `patches_pos/` directory under the project root (e.g., `dataverse_files/CompreFace/patches_pos`).

### Single patch

```bash
$ python3 3_run_ticket_test.py MM-62925 patches_pos/MM-62925_non_test.diff
```

### Measure scores

Results from each run are saved in the `test_results.csv` CSV file and in the `results/` directory. This is a helper script to summarize and display results from benchmark runs.

```bash
$ python3 5_measure_scores.py dataverse_files/CompreFace
```

#### Examples with the public *dataverse_files/* dataset

```bash
# 1) AuthoringToolKit — this repo must be built with Java 8
python3 4_run_all_tickets.py \
  --project-root dataverse_files/AuthoringToolKit \
  --java-major 8 \
  --ai \
  --ai-patches-dir PATCHES_EAK_TDD_DEEPSEEK_mSWE_AGENT_CL2
```

```bash
# 2) CompreFace
python3 4_run_all_tickets.py \
  --project-root dataverse_files/CompreFace \
  --ai \
  --ai-patches-dir PATCHES_CF_classic_GPT_4o_MINI_mSWE_AGENT_CL_1
```

```bash
# 3) DynamicMailboxes
python3 4_run_all_tickets.py \
  --project-root dataverse_files/DynamicMailboxes \
  --ai \
  --ai-patches-dir PATCHES_DMB_classic_GPT_4o_MINI_mSWE_AGENT_CL_1
```

### Command‑line flags

#### 3_run_ticket_test.py

| Flag | Purpose | Default |
|------|---------|---------|
| `TICKET` | PR ticket ID to test (positional) | required |
| `PATCH`  | Optional diff file (`<ticket>_non_test.diff`) | — |
| `--ai` | Skip base + merge stages; run only negative/code stage | off |
| `--project-root PATH` | Root of the benchmark project | script’s folder |
| `--java-major N` | Force Java major version (e.g., 8, 17) | highest JDK found |

#### 4_run_all_tickets.py

| Flag | Purpose                                                                                                                                                 | Default                     |
|------|---------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------|
| `--ai` | Run only the AI‑patch stage (skips base + merge)                                                                                                        | off                         |
| `--ai-patches-dir PATH` | Directory containing `<ticket>_non_test.diff` files. If the flag is omitted, the script defaults to the `patches_ai` directory within the project root. | `patches_ai` project folder |
| `--project-root PATH` | Root of the benchmark project                                                                                                                           | script’s folder             |
| `--java-major N` | Force Java major version (e.g., 8, 17)                                                                                                                  | highest JDK found           |

#### 5_measure_scores.py

| Argument         | Purpose                                                      | Default    |
|------------------|--------------------------------------------------------------|------------|
| `<folder_path>`  | Directory containing CSV files to summarize and display       | required   |
| `-h`, `--help`   | Show the help message                                         | N/A        |

All parameters are documented via `-h/--help`.

---

## Troubleshooting & FAQ

| Symptom                          |  Fix                                                                          |
| -------------------------------- | ----------------------------------------------------------------------------- |
| `java: command not found`        | Check your JDK installation and `JVM_DIR`.                                    |
| Maven can’t resolve dependencies | Make sure the target project builds *without* EnterpriseBench first.          |
| "FileNotFound: pr\_states.csv"   | Confirm you renamed your dataset correctly or pass `--dataset` to the script. |

---

## License

Distributed under the Apache 2.0 license – see `LICENSE` for details.
