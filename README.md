<h1 align="center">
  <strong>Optical Coherence Tomography (OCT)</strong>
</h1>
<h3 align="center">Data-driven, auto-validated literature corpus on optical coherence tomography</h3>

### 🔗 Links

- **License**: https://github.com/tobias-weiss-ai-xr/oct-research/blob/main/LICENSE
- **CI**: https://github.com/tobias-weiss-ai-xr/oct-research/actions/workflows/validate.yml
- **GitHub Pages**: https://tobias-weiss-ai-xr.github.io/oct-research/


> ⚕️ **Auto-validated corpus:** a data-driven, agentic literature review of
> optical coherence tomography (OCT). `papers.yaml` is the source of truth;
> the README paper list, corpus statistics, and research reports are generated
> and kept fresh by the pipeline — nothing human-maintained goes stale.
>
> Built on the `*-research` corpus skeleton, so it inherits the same
> guardrailed agentic workflow (see `AGENTS.md`).

## What you get

| Capability | How |
|------------|-----|
| 📄 **Curated corpus** | `papers.yaml` is the source of truth — one structured entry per paper |
| ✅ **Auto-validation** | `scripts/validate_papers.py` checks schema, duplicates, URL normalization, LaTeX artifacts |
| 🧾 **Auto-generated README** | `scripts/generate_readme.py` renders the paper list grouped by your taxonomy |
| 📊 **Statistics & trends** | `scripts/standard_stats.py` → `statistics.json` (momentum, gaps, bursts, venues, authors) |
| 🔍 **Literature review report** | `scripts/analysis/generate_reports.py` → `docs/research/literature_review.md` + `trends.md` |
| 🧭 **Topic planning** | `tools/topic_planner.py`, `tools/trend_scanner.py`, `tools/landscape_analyzer.py`, `tools/brief_generator.py` |
| 🔎 **New paper discovery** | `scripts/fetch/fetch_new_papers.py` (arXiv), `fetch_other_sources.py` (dblp/crossref/europepmc), `fetch_openalex_bulk.py` |
| 🐙 **GitHub repos discovery** | `scripts/fetch/fetch_github_repos.py` (optional, config-driven via `github_queries` in taxonomy.yaml) |
| 🦊 **GitLab projects discovery** | `scripts/fetch/fetch_gitlab_repos.py` (optional, config-driven via `gitlab_queries` in taxonomy.yaml) |
| 🏠 **Codeberg repos discovery** | `scripts/fetch/fetch_codeberg_repos.py` (optional, config-driven via `codeberg_queries` in taxonomy.yaml) |
| 📰 **News / intelligence digest** | `run_pipeline.py` — RSS/Atom + arXiv + GitHub releases + catalogs (e.g. CISA KEV) → scored, de-duplicated daily digest (`data/latest.md`/`.html`/`.json`) |
| 🖥️ **GitHub Pages site** | `docs/index.html` — searchable, filterable paper browser |
| 🤖 **Agentic workflow** | `AGENTS.md` + `config/taxonomy.yaml` make this repo agent-friendly by design |

## 🚀 Day-to-day workflow

```bash
# 1. Add or edit a paper in papers.yaml (see "Adding a paper" in AGENTS.md)

# 2. Validate + regenerate all derived outputs
python3 scripts/validate_papers.py && \
python3 scripts/generate_readme.py && \
python3 scripts/standard_stats.py && \
python3 scripts/analysis/generate_reports.py

# 3. Commit — CI re-validates on push and re-checks freshness weekly
git add -A && git commit -m "add OCT paper: <short title>" && git push

# …or let discovery seed the corpus for you:
python3 scripts/fetch/fetch_new_papers.py --months 12 --dry-run  # preview arXiv hits
python3 scripts/fetch/fetch_new_papers.py --local                # append to papers.yaml
```

Or use the task runner:

```bash
make all       # validate → check freshness → generate → test
make discover  # fetch new arXiv papers & open a PR (needs GH_TOKEN)
make help      # list all targets
```

## 📖 How it works

```
config/taxonomy.yaml ──► papers.yaml ──► validate_papers.py
                          │   ▲              │
                          ▼   └── fetch_* ───┘
                   generate_readme.py ──► README.md paper list (auto)
                          │
                          ▼
                  standard_stats.py ──► statistics.json, docs/papers.json,
                                        README.md corpus statistics (auto)
                          │
                          ▼
              analysis/generate_reports.py ──► docs/research/*.md
```

The generated README sections (paper list + corpus statistics) are
**marker-delimited** (`<!-- BEGIN … -->` … `<!-- END … -->`) and are owned by
the pipeline: `generate_readme.py` and `standard_stats.py` regenerate exactly
their section on every run. Everything else in the README is user-owned prose
and is left untouched. If a repo drops a section entirely (e.g. the paper list
lives on the GitHub Pages site), the owning script skips it gracefully instead
of erroring.

- **Never edit the generated README sections by hand** — run the pipeline.
- The **taxonomy lives in one place** (`config/taxonomy.yaml`); every script reads it via `scripts/research_config.py`, which now validates the config up front so mistakes fail loudly.
- **CI (validate.yml)** runs on every push/PR and weekly to discover new papers. The `validate` job re-checks that all generated outputs are fresh (README, statistics, reports), and a `test` job runs the pytest suite.

## 🧪 Local pipeline (all in one)

```bash
make all          # validate → check freshness → generate → test
# …or run the raw steps:
python3 scripts/validate_papers.py && \
python3 scripts/generate_readme.py && \
python3 scripts/standard_stats.py && \
python3 scripts/analysis/generate_reports.py

# Freshness checks (non-destructive; exit 1 if stale) — used by CI
python3 scripts/generate_readme.py --check
python3 scripts/standard_stats.py --check
python3 scripts/analysis/generate_reports.py --check

# Unit tests
python3 -m pytest
```

## 📰 News / Intelligence Digest (`run_pipeline.py`)

A complementary pipeline that ingests **RSS/Atom feeds**, **arXiv queries**,
**GitHub release feeds**, and **structured catalogs** (e.g. CISA KEV), then
classifies + scores each item, de-duplicates against a seen-history, and renders
a daily digest (`data/latest.md`, `data/latest.html`, `data/raw.json`).

```bash
python3 run_pipeline.py --dry-run   # ingest + score only (no writes)
python3 run_pipeline.py              # full run → writes digest + marks seen
python3 run_pipeline.py --top 30     # smaller digest
```

Sources, weights and keyword classification live in `config/sources.yml`.

### Anti-saturation controls

Without guards, static catalogs (CISA KEV's 1,600+ entry list) and full-archive
feeds (Snyk's 1,600+ post history) recycle old items every run, and one
high-volume feed (e.g. a project blog) can crowd out everything else. Three
config knobs in `config/sources.yml` prevent this:

| Knob | Effect |
|------|--------|
| `recent_days` (per source) / `default_recent_days` | Drop items published/added older than N days. Applied to RSS + catalog sources; **opt in only on archive/catalog feeds** — normal blogs already return recent items, so leave the default at `0` to avoid starving low-frequency, high-signal feeds. |
| `max_items` (per source) | Hard cap on raw items kept from one source (e.g. 15 for an archive feed). |
| `max_source_share` (global) | Hard ceiling on how many digest slots a single source may occupy (default `0.40` → no source takes >40% of the digest). |

> Why `default_recent_days: 0`? Only archive/catalog feeds recycle. A blanket
> window would silently drop infrequent but high-signal feeds (e.g. Project
> Zero, which posts monthly). Set `recent_days` explicitly on the feeds that
> need it.

## 🔎 Discovery & utility scripts

Beyond the core pipeline, several scripts remain available for manual / scheduled use:

| Script | What it does |
|---|---|
| `scripts/fetch/fetch_new_papers.py` | arXiv discovery; `--create-pr` opens a weekly PR (used by CI) |
| `scripts/fetch/fetch_openalex_bulk.py` | OpenAlex bulk discovery per category (`--months`, `--local`) |
| `scripts/fetch/fetch_other_sources.py` | dblp / crossref / Europe PMC / Semantic Scholar discovery |
| `scripts/fetch/fetch_metadata.py` | backfill authors/abstracts/venues for existing arXiv papers |
| `scripts/fetch/saturate_papers.py` | expand queries & loop arXiv until corpus saturates |
| `scripts/fetch/fetch_github_repos.py` / `fetch_gitlab_repos.py` / `fetch_codeberg_repos.py` | discover topic-relevant code repos → `repos.yaml` |
| `scripts/fetch/search_arxiv_html.py` / `search_arxiv_offline.py` | alternate/ad-hoc arXiv search helpers |
| `scripts/export_bibtex.py` | write `paper/references.bib` from `papers.yaml` |
| `scripts/visualize_statistics.py` | visualise `statistics.json` |

The repo-discovery fetchers share rate-limit/backoff + relevance logic in `scripts/fetch/repos_common.py`.

## 🤖 Agentic workflow (AGENTS.md)

This repo is designed to be driven by coding agents (OpenCode, Claude Code, …):

- **Spec-style guardrails** in `AGENTS.md` — agents know the pipeline, never edit README, always re-validate.
- **One config file** to change → one re-run to verify (low context cost for agents).
- **Auto-validation** gives agents an objective pass/fail signal.
- **Weekly discovery** keeps the corpus fresh without human babysitting.

<!-- BEGIN PAPER LIST -->

## 📚 Paper list

- [📚 Methoden & Technikvarianten](#methoden-&-technikvarianten)
  - [Grundlagen & Interferometrie](#grundlagen-&-interferometrie)
  - [Spektraldomänen-OCT (SD-OCT)](#spektraldomänen-oct-(sd-oct))
  - [Swept-Source-OCT (SS-OCT)](#swept-source-oct-(ss-oct))
  - [OCT-Angiographie (OCTA)](#oct-angiographie-(octa))
  - [Polarisations-sensitive OCT (PS-OCT)](#polarisations-sensitive-oct-(ps-oct))
  - [Deep Learning & KI-Bildanalyse](#deep-learning-&-ki-bildanalyse)
- [📚 Klinische & technische Anwendungen](#klinische-&-technische-anwendungen)
  - [Ophthalmologie](#ophthalmologie)
  - [Kardiologie](#kardiologie)
  - [Dermatologie](#dermatologie)
  - [Neuro & HNO](#neuro-&-hno)
  - [Weitere Anwendungen](#weitere-anwendungen)
- [📚 Evaluation, Datensätze & Benchmarks](#evaluation,-datensätze-&-benchmarks)
  - [Datensätze & Benchmarks](#datensätze-&-benchmarks)
- [📚 Surveys & Übersichtsarbeiten](#surveys-&-übersichtsarbeiten)
  - [Übersichtsarbeiten](#übersichtsarbeiten)

### Methoden & Technikvarianten

#### Grundlagen & Interferometrie

##### 2026

- [2026] **Seeded SU(1,1) interferometry for Fourier-domain optical coherence tomography** [[paper](https://arxiv.org/abs/2608.18750)]

##### 1991

- [1991] **Optical Coherence Tomography** *Science* [[paper](https://doi.org/10.1126/science.1957169)]

[⬆ Back to top](#paper-list)

#### Spektraldomänen-OCT (SD-OCT)

##### 2026

- [2026] **Bridging the gap: Using deep learning to reconstruct noise-reduced super-resolved OCT images from gapped spectra** [[paper](https://arxiv.org/abs/2608.11989)]

##### 2003

- [2003] **Sensitivity advantage of swept source and Fourier domain optical coherence tomography** *Optics Express* [[paper](https://doi.org/10.1364/OE.11.002183)]

[⬆ Back to top](#paper-list)

#### Swept-Source-OCT (SS-OCT)

##### 2022

- [2022] **Multi-scale reconstruction of undersampled spectral-spatial OCT data for coronary imaging using deep learning** [[paper](https://arxiv.org/abs/2204.11769)]

##### 2021

- [2021] **Neural network-based image reconstruction in swept - source optical coherence tomography using undersampled spectral data** [[paper](https://arxiv.org/abs/2103.03877)]

[⬆ Back to top](#paper-list)

#### OCT-Angiographie (OCTA)

##### 2026

- [2026] **In Defense of OCTA: The Reconstruction-Utility Gap in OCT-to-OCTA Synthesis** [[paper](https://arxiv.org/abs/2608.15626)]

##### 2023

- [2023] **Retinal blood flow speed quantification at the capillary level using temporal autocorrelation fitting OCTA** [[paper](https://arxiv.org/abs/2302.11612)]

##### 2022

- [2022] **OMSN and FAROS: OCTA Microstructure Segmentation Network and Fully Annotated Retinal OCTA Segmentation Dataset** [[paper](https://arxiv.org/abs/2212.13059)]

##### 2020

- [2020] **ROSE: A Retinal OCT - Angiography Vessel Segmentation Dataset and New Model** [[paper](https://arxiv.org/abs/2007.05201)]

[⬆ Back to top](#paper-list)

#### Polarisations-sensitive OCT (PS-OCT)

##### 2025

- [2025] **Polarization-Sensitive Module for Optical Coherence Tomography Instruments** [[paper](https://arxiv.org/abs/2511.11274)]

[⬆ Back to top](#paper-list)

#### Deep Learning & KI-Bildanalyse

##### 2026

- [2026] **Full end-to-end diagnostic workflow automation of 3D OCT via foundation model-driven AI for retinal diseases** [[paper](https://arxiv.org/abs/2602.03302)]

##### 2025

- [2025] **MIRAGE: Multimodal foundation model and benchmark for comprehensive retinal OCT image analysis** [[paper](https://arxiv.org/abs/2506.08900)]

##### 2024

- [2024] **OCTolyzer: Fully automatic toolkit for segmentation and feature extracting in optical coherence tomography and scanning laser ophthalmoscopy data** [[paper](https://arxiv.org/abs/2407.14128)]
- [2024] **Memory-efficient High-resolution OCT Volume Synthesis with Cascaded Amortized Latent Diffusion Models** [[paper](https://arxiv.org/abs/2405.16516)]
- [2024] **Less is more: Ensemble Learning for Retinal Disease Recognition Under Limited Resources** [[paper](https://arxiv.org/abs/2402.09747)]

##### 2023

- [2023] **Retinal OCT Synthesis with Denoising Diffusion Probabilistic Models for Layer Segmentation** [[paper](https://arxiv.org/abs/2311.05479)]
- [2023] **Deep learning network to correct axial and coronal eye motion in 3D OCT retinal imaging** [[paper](https://arxiv.org/abs/2305.18361)]
- [2023] **nnUNet RASPP for Retinal OCT Fluid Detection, Segmentation and Generalisation over Variations of Data Sources** [[paper](https://arxiv.org/abs/2302.13195)]

##### 2022

- [2022] **ADC-Net: An Open-Source Deep Learning Network for Automated Dispersion Compensation in Optical Coherence Tomography** [[paper](https://arxiv.org/abs/2201.12625)]

##### 2021

- [2021] **Demystifying Deep Learning Models for Retinal OCT Disease Classification using Explainable AI** [[paper](https://arxiv.org/abs/2111.03890)]

[⬆ Back to top](#paper-list)

### Klinische & technische Anwendungen

#### Ophthalmologie

##### 2024

- [2024] **Nonperfused Retinal Capillaries -- A New Method Developed on OCT and OCTA** [[paper](https://arxiv.org/abs/2411.05244)]
- [2024] **Multiscale Color Guided Attention Ensemble Classifier for Age-Related Macular Degeneration using Concurrent Fundus and Optical Coherence Tomography Images** [[paper](https://arxiv.org/abs/2409.00718)]
- [2024] **Deep Learning to Predict Glaucoma Progression using Structural Changes in the Eye** [[paper](https://arxiv.org/abs/2406.05605)]

##### 2018

- [2018] **Clinically applicable deep learning for diagnosis and referral in retinal disease** *Nature Medicine* [[paper](https://doi.org/10.1038/s41591-018-0107-6)]
- [2018] **Pivotal trial of an autonomous AI-based diagnostic system for detection of diabetic retinopathy in primary care offices** *npj Digital Medicine* [[paper](https://doi.org/10.1038/s41746-018-0040-6)]
- [2018] **Identifying Medical Diagnoses and Treatable Diseases by Image-Based Deep Learning** *Cell* [[paper](https://doi.org/10.1016/j.cell.2018.02.010)]

[⬆ Back to top](#paper-list)

#### Kardiologie

##### 2026

- [2026] **Intracoronary Optical Coherence Tomography Image Processing and Vessel Classification Using Machine Learning** [[paper](https://arxiv.org/abs/2602.15579)]

##### 2025

- [2025] **Attenuation artifact detection and severity classification in intracoronary OCT using mixed image representations** [[paper](https://arxiv.org/abs/2503.05322)]

##### 2023

- [2023] **Deep learning segmentation of fibrous cap in intravascular optical coherence tomography images** [[paper](https://arxiv.org/abs/2311.06202)]

##### 2022

- [2022] **Structural constrained virtual histology staining for human coronary imaging using deep learning** [[paper](https://arxiv.org/abs/2211.06737)]

[⬆ Back to top](#paper-list)

#### Dermatologie

##### 2025

- [2025] **3D Deep-learning-based Segmentation of Human Skin Sweat Glands and Their 3D Morphological Response to Temperature Variations** [[paper](https://arxiv.org/abs/2504.17255)]

##### 2023

- [2023] **Deep Learning based Skin-layer Segmentation for Characterizing Cutaneous Wounds from Optical Coherence Tomography Images** [[paper](https://arxiv.org/abs/2306.01252)]

[⬆ Back to top](#paper-list)

#### Neuro & HNO

##### 2025

- [2025] **Bayesian Deep Learning Approaches for Uncertainty-Aware Retinal OCT Image Segmentation for Multiple Sclerosis** [[paper](https://arxiv.org/abs/2505.12061)]

[⬆ Back to top](#paper-list)

#### Weitere Anwendungen

##### 2026

- [2026] **Time-resolved sedimentation of dense potato-starch suspensions measured by optical coherence tomography** [[paper](https://arxiv.org/abs/2608.15067)]

##### 2025

- [2025] **Defect Segmentation in OCT scans of ceramic parts for non-destructive inspection using deep learning** [[paper](https://arxiv.org/abs/2510.00745)]

##### 2021

- [2021] **Cervical Optical Coherence Tomography Image Classification Based on Contrastive Self-Supervised Texture Learning** [[paper](https://arxiv.org/abs/2108.05081)]

[⬆ Back to top](#paper-list)

### Evaluation, Datensätze & Benchmarks

#### Datensätze & Benchmarks

##### 2023

- [2023] **OCTDL: Optical Coherence Tomography Dataset for Image-Based Deep Learning Methods** [[paper](https://arxiv.org/abs/2312.08255)]

##### 2022

- [2022] **Inflation of test accuracy due to data leakage in deep learning -based classification of OCT images** [[paper](https://arxiv.org/abs/2202.12267)]

[⬆ Back to top](#paper-list)

### Surveys & Übersichtsarbeiten

#### Übersichtsarbeiten

##### 2023

- [2023] **Deep Learning and Computer Vision for Glaucoma Detection: A Review** [[paper](https://arxiv.org/abs/2307.16528)]

##### 2021

- [2021] **Automatic Segmentation of the Optic Nerve Head Region in Optical Coherence Tomography : A Methodological Review** [[paper](https://arxiv.org/abs/2109.02322)]

##### 2017

- [2017] **Optical coherence tomography angiography** *Progress in Retinal and Eye Research* [[paper](https://doi.org/10.1016/j.preteyeres.2017.11.003)]

##### 2003

- [2003] **Optical coherence tomography - principles and applications** *Reports on Progress in Physics* [[paper](https://doi.org/10.1088/0034-4885/66/2/204)]

[⬆ Back to top](#paper-list)

<!-- END PAPER LIST -->

<!-- BEGIN CORPUS STATISTICS -->

## 📊 Corpus Statistics

**43 papers** across **4 categories**.  
Sources: **arXiv** 36 (84%).  

### Top categories

| Category | Papers | Recent | |
|----------|--------|--------|-|
| method | **21** | 5 | ████████████ |
| application | **16** | 3 | █████████░░░ |
| survey | **4** | 0 | ██░░░░░░░░░░ |
| evaluation | **2** | 0 | █░░░░░░░░░░░ |

### By year

| Year | Papers | |
|------|--------|-|
| 1991 | 1 | ██░░░░░░░░░░ |
| 2003 | 2 | ███░░░░░░░░░ |
| 2017 | 1 | ██░░░░░░░░░░ |
| 2018 | 3 | ████░░░░░░░░ |
| 2020 | 1 | ██░░░░░░░░░░ |
| 2021 | 4 | ██████░░░░░░ |
| 2022 | 5 | ████████░░░░ |
| 2023 | 8 | ████████████ |
| 2024 | 6 | █████████░░░ |
| 2025 | 6 | █████████░░░ |
| 2026 | 6 | █████████░░░ |

### Momentum (hottest categories)

| Category | Total | Rate | Recent | Score |
|----------|-------|------|--------|-------|
| Method | 21 | 0.4/mo | 24% | 424 |
| Evaluation | 2 | 0.0/mo | 0% | 0 |
| Survey | 4 | 0.0/mo | 0% | 0 |
| Application | 16 | 0.2/mo | 19% | -21 |

### Trending keywords

| Keyword | Papers | Burst |
|---------|--------|-------|
| polarization | 1 | 5.38 |
| foundation model | 1 | 2.69 |
| classification | 1 | 1.07 |
| coronary | 1 | 1.07 |
| deep learning | 2 | 0.67 |
| segmentation | 1 | 0.49 |
| retina | 1 | 0.36 |

### Top venues

| Venue | Papers |
|-------|--------|
| Science | 1 |
| Optics Express | 1 |
| Nature Medicine | 1 |
| Cell | 1 |
| npj Digital Medicine | 1 |
| Reports on Progress in Physics | 1 |
| Progress in Retinal and Eye Research | 1 |

### Research gaps (thinnest cells)

| Cell | Papers |
|------|--------|
| `method/ps-oct` | 1 |
| `application/neuro` | 1 |
| `method/fundamentals` | 2 |
| `method/sd-oct` | 2 |
| `method/ss-oct` | 2 |

*Generated 2026-09 by `scripts/standard_stats.py`.*

<!-- END CORPUS STATISTICS -->

## 📖 Citation

If you use this skeleton for a project, please cite:

```bibtex
@misc{oct-research,
  author = {Weiß, Tobias},
  title = {OCT Research Corpus: Data-Driven Agentic Literature Review on Optical Coherence Tomography},
  year = {2026},
  publisher = {GitHub},
  url = {https://github.com/tobias-weiss-ai-xr/oct-research}
}
```

## 📄 License

MIT — see [LICENSE](LICENSE).
