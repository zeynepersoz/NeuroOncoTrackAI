# NeuroOncoTrack-AI · Ön İşleme Pipeline'ı

MR görüntülerini kafatası soyma, bias correction, registration ve
normalizasyon adımlarından geçirip model için hazır hale getiren modül.

## Kurulum

```bash
pip install -r requirements.txt
apt install dcm2niix
```

## Kullanım

```python
from preprocessing.utils import Patient
from preprocessing.pipeline import preprocess_patient

patient = Patient(
    patient_id="BRATS_00123",
    modalities={
        "t1": "raw/t1.nii.gz",
        "t1c": "raw/t1c.nii.gz",
        "t2": "raw/t2.nii.gz",
        "flair": "raw/flair.nii.gz",
    },
    output_dir="processed/BRATS_00123",
)

preprocess_patient(patient, quarantine_root="quarantine")
```

## Test

```bash
pytest tests/ -v
```