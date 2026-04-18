"""
test_6a_detect_doctype.py — Unit tests for document type classification (6A).

Tests that detect_document_type() correctly classifies:
- Nanocomposite TDS → "tds"  (key improvement in 6A)
- Research papers → "paper"
- Classic polymer TDS → "tds"
- Ambiguous short text → reasonable default

Run:  pytest tests/test_6a_detect_doctype.py -v
"""
import pytest
from extractor import detect_document_type


# ── Nanocomposite TDS texts (6A critical cases) ────────────────────────────────

NANOCOMPOSITE_TDS = """
Product Name: MXene-Epoxy Nanocomposite TDS-MX400
Technical Data Sheet

Typical Properties (Test Method: ASTM D638)
Tensile Strength: 85 MPa
Electrical Conductivity: 1200 S/m
EMI Shielding Effectiveness (SE): 42 dB at 1 GHz
Thermal Conductivity: 3.2 W/mK
Glass Transition Temperature (Tg): 148 °C
Filler Loading: 3 wt%
Aspect Ratio: 2000 (dimensionless)
ILSS: 38 MPa

Processing Conditions:
Resin:Hardener ratio 100:30 by weight
Cure Temperature: 120°C for 2h, Post-cure: 180°C for 1h
Drying Conditions: 80°C for 4h

Meets IEC 61000-4-3 shielding requirements.
"""

CLASSIC_POLYMER_TDS = """
PRODUCT DATA SHEET
Grade: PA66-GF30

Typical Properties                Test Method    Value
Density                           ISO 1183       1.36 g/cm³
Tensile Strength                  ISO 527        185 MPa
Flexural Modulus                  ISO 178        9200 MPa
Notched Izod Impact               ISO 180        60 kJ/m²
Heat Deflection Temperature       ISO 75         240 °C
Melt Flow Index                   ISO 1133       11 g/10min

Processing:
Mold Temperature: 80-90°C
Injection Molding conditions per standard guidelines.
Conforms to UL94 V-0 at 0.8mm.
"""

RESEARCH_PAPER = """
Abstract
In this study, we report the fabrication of MXene/epoxy nanocomposites with
enhanced EMI shielding effectiveness. Ti₃C₂Tₓ MXene nanosheets were prepared
via selective etching and incorporated into an epoxy matrix at filler loadings
of 1–5 wt%.

Introduction
Electromagnetic interference (EMI) shielding is critical for modern electronics.
Nanocomposites offer a route to high shielding effectiveness at low filler loading
by exploiting the percolation threshold.

Experimental
Sample preparation: MXene dispersions were mixed with resin using a planetary
centrifugal mixer. Scanning electron microscopy (SEM) confirmed homogeneous dispersion.
FTIR and XRD confirmed intercalation.

Results
We investigated the effect of filler loading on electrical conductivity. Results show
that a 3 wt% MXene loading achieves ~1100 S/m and EMI SE of 40 dB at X-band.

Conclusion
In this work we demonstrate that MXene/epoxy composites achieve EMI SE > 40 dB.

References
[1] Smith et al., European Polymer Journal, doi:10.1016/j.eurpolymj.2024.01.001
[2] Kumar et al., 2023.
"""

MOSTLY_PAPER_WITH_TDS_WORDS = """
Abstract
We investigated a nanocomposite that meets ASTM D638 tensile requirements.
In this study we report the synthesis and characterization of CNT/polymer blends.
Figure 1 shows results. Table 2 shows properties. et al. have reported similar values.
Acknowledgement: funded by NSF.

References: [1] doi:10.1002/...
"""


def test_nanocomposite_tds_classified_as_tds():
    """A nanocomposite TDS with EMI SE, conductivity, wt% must → 'tds' (key 6A improvement)."""
    assert detect_document_type(NANOCOMPOSITE_TDS) == "tds"


def test_classic_polymer_tds_classified_as_tds():
    """A classic PA66 polymer TDS → 'tds'."""
    assert detect_document_type(CLASSIC_POLYMER_TDS) == "tds"


def test_research_paper_classified_as_paper():
    """A full research paper with abstract/intro/references → 'paper'."""
    assert detect_document_type(RESEARCH_PAPER) == "paper"


def test_paper_with_some_tds_words_still_paper():
    """A paper that references ASTM but has abstract/references/et al. → 'paper'."""
    assert detect_document_type(MOSTLY_PAPER_WITH_TDS_WORDS) == "paper"


def test_empty_text_returns_default():
    """Empty string should not crash, returns either 'tds' or 'paper'."""
    result = detect_document_type("")
    assert result in ("tds", "paper")


def test_returns_string_not_none():
    """Result is always a string."""
    assert isinstance(detect_document_type("some material text"), str)


def test_cure_conditions_tds():
    """Text with resin:hardener ratio and cure temperature → 'tds'."""
    text = "Resin:Hardener mix ratio 100:28. Cure temperature 80°C. Post-cure 150°C 1h. Pot life: 45 min."
    assert detect_document_type(text) == "tds"


def test_paper_markers_dominate():
    """Text with 'Abstract', 'et al.', 'doi:', 'In this study' → 'paper'."""
    text = (
        "Abstract. In this study we report graphene synthesis. "
        "et al. 2024. doi:10.1002/xyz. Acknowledgement: funded. "
        "References: [1]... Experimental section follows."
    )
    assert detect_document_type(text) == "paper"
