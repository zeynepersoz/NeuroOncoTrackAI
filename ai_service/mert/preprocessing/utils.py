from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

REQUIRED_MODALITIES = ("t1", "t1c", "t2", "flair")
REFERENCE_MODALITY = "t1"
TARGET_SPACING = (1.0, 1.0, 1.0)

VALID_SOURCES = (
    "brats",
    "upenn_gbm",
    "tcga_gbm",
    "tcga_lgg",
    "ucsf_pdgm",
    "brats_africa",
    "hospital_external",
)

TRAINING_SOURCES = (
    "brats",
    "upenn_gbm",
    "tcga_gbm",
    "tcga_lgg",
    "ucsf_pdgm",
    "brats_africa",
)


def setup_logger(name: str = "neurooncotrack.preprocessing") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


logger = setup_logger()


class PreprocessingError(RuntimeError):
    pass


@dataclass
class Patient:
    patient_id: str
    modalities: Dict[str, Path]
    output_dir: Path
    source: str = "brats"
    processed: Dict[str, Path] = field(default_factory=dict)
    qc_flags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.modalities = {k: Path(v) for k, v in self.modalities.items()}

        if self.source not in VALID_SOURCES:
            raise PreprocessingError(
                f"Geçersiz kaynak: '{self.source}'. Geçerli kaynaklar: {VALID_SOURCES}"
            )

    def has_all_modalities(self) -> bool:
        return all(mod in self.modalities for mod in REQUIRED_MODALITIES)

    def missing_modalities(self) -> list[str]:
        return [m for m in REQUIRED_MODALITIES if m not in self.modalities]

    def is_training_eligible(self) -> bool:
        return self.source in TRAINING_SOURCES

    def stage_output_path(self, stage: str, modality: str) -> Path:
        stage_dir = self.output_dir / stage
        stage_dir.mkdir(parents=True, exist_ok=True)
        return stage_dir / f"{modality}.nii.gz"

    def latest(self, modality: str) -> Path:
        return self.processed.get(modality, self.modalities[modality])