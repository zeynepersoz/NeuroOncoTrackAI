import re

with open('neuroConstants.js', 'r', encoding='utf-8') as f:
    text = f.read()

# Update capabilities
text = text.replace(
    "{ icon: FileText, label: 'Klinik rapor', value: 'WHO 2021 uyumlu taslak' }",
    "{ icon: FileText, label: 'Çift-LLM Rapor', value: 'gpt-4o + Claude Sonnet' }"
)

# Update loginMetrics (Macro F1 0.874 -> Doğruluk %95.8 from report)
text = text.replace(
    "{ label: 'Macro F1', value: '0.874' }",
    "{ label: 'Sınıflandırma', value: '%95.8' }"
)

# Update analysisStages (ResUNet -> nnU-Net 3d_fullres)
text = text.replace(
    "'ResUNet hattı olası tümör alanını ve hacim bilgisini hazırlıyor.'",
    "'nnU-Net 3d_fullres hattı olası tümör alanını ve hacim bilgisini hazırlıyor.'"
)

# Also fix encoding issues if any exists from previous powershell reads, but we are reading the raw file so it should be fine.
with open('neuroConstants.js', 'w', encoding='utf-8') as f:
    f.write(text)

print("Updated neuroConstants.js to match Final Report.")
