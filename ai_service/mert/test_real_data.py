from pathlib import Path

from preprocessing.utils import Patient
from preprocessing.qc import run_pre_pipeline_qc, quarantine_if_critical
from preprocessing.skull_strip import _HD_BET_AVAILABLE
from preprocessing.bias_correction import n4_bias_correction
from preprocessing.registration import register_patient_to_t1
from preprocessing.normalize import resample_and_normalize

RAW_DIR = Path("raw_data/ucsd_ptgbm_sub0002")
OUTPUT_DIR = Path("processed/ucsd_ptgbm_sub0002")

patient = Patient(
    patient_id="ucsd_ptgbm_sub0002",
    modalities={
        "t1": RAW_DIR / "sub-0002_ses-01_run-pre_T1w.nii.gz",
        "t1c": RAW_DIR / "sub-0002_ses-01_run-post_T1w.nii.gz",
        "t2": RAW_DIR / "sub-0002_ses-01_T2w.nii.gz",
        "flair": RAW_DIR / "sub-0002_ses-01_FLAIR.nii.gz",
    },
    output_dir=OUTPUT_DIR,
    source="ucsd_ptgbm",
)

print("=" * 60)
print("HASTA BİLGİSİ")
print("=" * 60)
print(f"ID: {patient.patient_id}")
print(f"Kaynak: {patient.source}")
print(f"Eğitime uygun mu: {patient.is_training_eligible()}")
print(f"Tüm modaliteler var mı: {patient.has_all_modalities()}")

for modality, path in patient.modalities.items():
    exists = path.exists()
    size_mb = path.stat().st_size / (1024 * 1024) if exists else 0
    print(f"  {modality}: {'✅' if exists else '❌'} ({size_mb:.2f} MB)")

print("\n" + "=" * 60)
print("QC KONTROLÜ")
print("=" * 60)
patient = run_pre_pipeline_qc(patient)
print(f"QC uyarıları: {patient.qc_flags if patient.qc_flags else 'Yok'}")

quarantined = quarantine_if_critical(patient, quarantine_root=Path("quarantine"))
if quarantined:
    print("⚠️  Hasta karantinaya alındı, pipeline devam etmiyor.")
    exit()

print("\n" + "=" * 60)
print("HD-BET DURUMU")
print("=" * 60)
print(f"HD-BET kurulu mu: {_HD_BET_AVAILABLE}")

if not _HD_BET_AVAILABLE:
    print("HD-BET kurulu değil, kafatası soyma adımı atlanacak.")
    print("Bunun yerine ham T1 üzerinden N4 + registration + normalize adımlarını deniyoruz.")

    print("\n--- N4 Bias Correction (T1 üzerinde) ---")
    n4_output = patient.stage_output_path("n4", "t1")
    n4_bias_correction(patient.modalities["t1"], n4_output)
    print(f"✅ N4 tamamlandı: {n4_output}")

    print("\n--- Registration (diğer modaliteleri T1'e hizala) ---")
    reg_dir = patient.output_dir / "registered"
    registered = register_patient_to_t1(
        {"t1": n4_output, **{k: v for k, v in patient.modalities.items() if k != "t1"}},
        reg_dir,
        reference_modality="t1",
    )
    for modality, path in registered.items():
        print(f"✅ {modality}: {path}")

    print("\n--- Resample + Z-score Normalizasyon ---")
    for modality, path in registered.items():
        final_output = patient.stage_output_path("final", modality)
        resample_and_normalize(path, final_output)
        print(f"✅ {modality}: {final_output}")

    print("\n" + "=" * 60)
    print("SONUÇ: Kısmi pipeline (kafatası soyma hariç) gerçek veriyle başarıyla çalıştı.")
    print("=" * 60)
else:
    print("HD-BET kurulu, tam pipeline deneniyor...")
    from preprocessing.pipeline import preprocess_patient
    result = preprocess_patient(patient, quarantine_root=Path("quarantine"), device="cpu")
    print("\n" + "=" * 60)
    print("SONUÇ: Tam pipeline gerçek veriyle başarıyla çalıştı.")
    print(f"Çıktılar: {result.processed}")
    print("=" * 60)