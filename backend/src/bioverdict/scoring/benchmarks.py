"""Public probability-of-success benchmarks. Every number carries its source.

Values were read from the sources named below on 2026-10-07. They are `extracted` facts,
not model output. Replace a table only together with its `source` string.
"""

from __future__ import annotations

from typing import Final

PHASES: Final = ("phase1", "phase2", "phase3", "nda")

CITELINE_2024_SOURCE: Final = (
    "Citeline Biomedtracker, 'Why Are Clinical Development Success Rates Falling?', "
    "April 2024, Fig. 1 (2014-2023, 10,954 drug-indication programs)"
)
# Phase transition probabilities, all diseases.
ALL_DISEASES: Final = {"phase1": 0.473, "phase2": 0.280, "phase3": 0.550, "nda": 0.918}

# Likelihood of approval from Phase I by therapy area (same report, Fig. 3).
LOA_BY_AREA: Final = {
    "hematology": 0.191,
    "dermatology": 0.170,
    "metabolic": 0.148,
    "ophthalmology": 0.112,
    "allergy": 0.101,
    "autoimmune": 0.093,
    "psychiatry": 0.088,
    "infectious disease": 0.084,
    "all": 0.067,
    "renal": 0.064,
    "cardiovascular": 0.060,
    "gastroenterology": 0.056,
    "endocrine": 0.054,
    "neurology": 0.053,
    "oncology": 0.047,
    "respiratory": 0.045,
}

BIO_2021_ONCOLOGY_SOURCE: Final = (
    "BIO, QLS Advisors, Informa UK Ltd, 'Clinical Development Success Rates and Contributing "
    "Factors 2011-2020', February 2021, Fig. 2 and 5b (oncology, n=4,179 transitions, LOA 5.3%)"
)
# Phase transitions for oncology, checked against the primary report on 2026-10-07.
BIO_2021_ONCOLOGY: Final = {"phase1": 0.488, "phase2": 0.246, "phase3": 0.477, "nda": 0.920}

GENETIC_SUPPORT_SOURCE: Final = (
    "Minikel, Painter, Dong, Nelson, Nature 2024: drug mechanisms with human genetic support "
    "are 2.6x more likely to succeed (varies by therapy area and phase)"
)
GENETIC_SUPPORT_RELATIVE_SUCCESS: Final = 2.6
