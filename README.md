# EnterpriseBench

We present **EnterpriseBench**, a new commercially grounded benchmark designed to evaluate the capabilities of AI agents in solving real-world software engineering tasks.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Dataset Preparation](#dataset-preparation)
4. [Running the Benchmark](#running-the-benchmark)
5. [Output & Results](#output--results)
6. [Troubleshooting & FAQ](#troubleshooting--faq)
7. [License](#license)

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

**Note:** When working with the **AuthoringToolKit** repository you must force the benchmark to use Java 8 by adding `--java-major 8` to the command line of both `4_run_all_tickets.py` and any direct calls to `3_run_ticket_test.py`.

---

## Dataset Preparation

### Automatic setup (recommended)

> 🗂️  If you’d rather automate these steps, simply run `prepare.sh`.  
The script will download the Harvard Dataverse archive, create the correct folder layout and rename/unpack everything exactly as required.

The script will:

1. Download the Harvard Dataverse archive (DOI [10.7910/DVN/S4WOTJ](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/S4WOTJ)) if it is not already present in the working directory.
2. Extract it into a clean `dataverse_files/` directory.
3. Rename each dataset `*.csv` file to **`pr_states.csv`**.
4. Unpack the `patches_neg*` and `patches_pos*` archives into flat `patches_neg/` and `patches_pos/` folders.
5. Unzip and flatten every project repository archive into a **`project_repo/`** directory.

After the script finishes, point `--project-root` at one of the unpacked project sub‑folders (e.g., `dataverse_files/CompreFace`) and jump straight to the [Running the Benchmark](#running-the-benchmark) section.

### Manual setup

EnterpriseBench expects the following artefacts for **every** benchmark run:

1. **`project_root`** - provide the root directory of the benchmark project by calling the script with the `--project-root` argument in the `4_run_all_tickets.py` script.
2. **`pr_states.csv`** – the mapping between issue/ticket IDs and the commit SHA(s) that resolved them.
3. **`project_repo`** – the full Git history of the benchmark project.
4. **`patches_neg/`** – *negative* git diff patches.

> 🗂️  Rename / copy your dataset file to **`pr_states.csv`** (e.g. `dataset_CF_anonymized.csv → pr_states.csv`).  The scripts look for that exact filename by default.

The directory layout with necessary files should look like this:

```
project_root/
├── pr_states.csv
├── project_repo/         # cloned target project
├── patches_neg/
│   ├── <ticket1>_non_test.diff
│   └── ...
```

---

## Running the Benchmark

`4_run_all_tickets.py` processes *every* row in `pr_states.csv`:

```bash
# Run the script
$ python3 4_run_all_tickets.py --ai --ai-patches-dir /path/to/patches_neg --project_root /path/to/benchmark/project_root
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

| Flag | Purpose | Default |
|------|---------|---------|
| `--ai` | Run only the AI‑patch stage (skips base + merge) | off |
| `--ai-patches-dir PATH` | Directory containing `<ticket>_non_test.diff` files (required with `--ai`) | — |
| `--project-root PATH` | Root of the benchmark project | script’s folder |
| `--java-major N` | Force Java major version (e.g., 8, 17) | highest JDK found |

All parameters are documented via `-h/--help`.

---

## Output & Results

Results are written to `results/` (created automatically) as JSON and CSV summaries which you can post‑process.

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
