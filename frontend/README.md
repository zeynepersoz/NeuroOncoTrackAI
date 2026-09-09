# NeuroOncoTrack-AI Frontend

NeuroOncoTrack-AI, beyin tümörü MRG görüntüleri üzerinden klinik karar destek sürecini görselleştiren React tabanlı frontend uygulamasıdır. Arayüz; vaka seçimi, MRG yükleme, görüntü inceleme, segmentasyon/Grad-CAM görüntüleri, sanal biyopsi çıktıları, klinik rapor taslağı ve FHIR kaynak görünümü için tek bir çalışma paneli sunar.

Bu README, frontend uygulamasını kurmak, çalıştırmak ve klasör yapısını anlamak için hazırlanmıştır.

## Teknolojiler

- React
- Vite
- JavaScript
- CSS
- Lucide React ikonları

## Gereksinimler

- Node.js
- npm
- Backend servisinin ayrıca çalışıyor olması

Frontend, analiz ve vaka verileri için varsayılan olarak şu backend adresini kullanır:

```txt
http://127.0.0.1:8000
```

API adresi [src/config/neuroConstants.js](src/config/neuroConstants.js) içinde `API_BASE` sabitiyle tanımlıdır.

## Kurulum

Proje klasörüne girin:

```powershell
cd "C:\Users\hakan\Desktop\TeknoFest Ana(Front)\NeuroOncoTrackAI"
```

Bağımlılıkları yükleyin:

```powershell
npm install
```

## Geliştirme Sunucusu

Frontend geliştirme sunucusunu başlatmak için:

```powershell
npm run dev
```

Vite genellikle uygulamayı aşağıdaki adreste açar:

```txt
http://127.0.0.1:5173
```

## Build

Üretim derlemesi almak için:

```powershell
npm run build
```

Derleme çıktısı `dist/` klasörüne oluşturulur.

## Lint

Kod standardı kontrolü için:

```powershell
npm run lint
```

## Backend Bağlantısı

Frontend şu temel endpointleri kullanır:

| Endpoint | Amaç |
| --- | --- |
| `/api/library` | Demo vaka kütüphanesini alır. |
| `/api/analyze` | Yüklenen veya seçilen MRG için analiz sonucunu döndürür. |
| `/api/report` | Klinik rapor taslağı üretir. |

Backend kapalıysa arayüz açılır, ancak vaka kütüphanesi, analiz ve rapor üretimi çalışmaz.

## Backend Mimari Planına Hazırlık

Frontend içinde API çağrıları `src/services/` altında merkezi hale getirilmiştir. Mevcut demo backend endpointleri çalışmaya devam ederken, planlanan `/api/v1` mimarisi için auth, izin, asenkron AI task takibi, rapor iş akışı ve FHIR senkronizasyon servisleri hazırlandı.

Varsayılan çalışma modu mevcut backend ile uyumlu olacak şekilde `legacy` değerindedir. Yeni backend sözleşmesi uygulandığında Vite ortam değişkeniyle kontrat modu açılabilir:

```powershell
$env:VITE_API_MODE="contract"
npm run dev
```

Bu modda frontend `/api/v1/auth`, `/api/v1/studies`, `/api/v1/ai`, `/api/v1/reports` ve `/api/v1/fhir` servislerini kullanmaya hazırlanır.

## Proje Yapısı

```txt
src/
  App.jsx
  main.jsx
  index.css
  assets/
  components/
    common/
      StatusPill.jsx
      ThemeToggle.jsx
    workspace/
      MetricCard.jsx
      ModuleLoader.jsx
      ProductWorkspace.jsx
  config/
    neuroConstants.js
  services/
    apiClient.js
    authService.js
    fhirService.js
    reportService.js
    studyService.js
    taskStream.js
  utils/
    neuroUtils.js
```

## Klasör Açıklamaları

| Yol | Açıklama |
| --- | --- |
| `src/App.jsx` | Giriş ekranı, oturum durumu ve ana çalışma alanına geçişi yönetir. |
| `src/components/common` | Farklı ekranlarda kullanılabilecek ortak bileşenleri içerir. |
| `src/components/workspace` | Klinik çalışma alanı, metrik kartları ve modül yüklenme bileşenlerini içerir. |
| `src/config/neuroConstants.js` | API adresi, modül tanımları, görünüm modları, FHIR seçenekleri ve demo profilleri içerir. |
| `src/services` | Auth, API istemcisi, çalışma yükleme/analiz, asenkron görev izleme, rapor ve FHIR servislerini içerir. |
| `src/utils/neuroUtils.js` | Formatlama, rapor üretimi, FHIR özetleme, metin düzeltme ve viewer yardımcılarını içerir. |
| `src/assets` | Arayüzde kullanılan görsel varlıkları içerir. |

## Ana Özellikler

- Kurum/proje kodu, e-posta ve şifre alanlarına sahip giriş ekranı
- Demo erişimi
- Açık/koyu tema ve sürüklenebilir tema anahtarı
- Vaka kütüphanesi ve filtreleme
- MRG yükleme
- Overlay, Grad-CAM ve karşılaştırmalı MRG görüntüleme
- Mouse wheel ile zoom
- Sürükleyerek görüntü taşıma
- Tam ekran görüntü inceleme
- Ön işleme, sanal biyopsi, açıklanabilirlik, rapor ve FHIR sekmeleri
- Klinik rapor taslağı, inceleme, onay, imza ve düzeltme sürümü akışı
- İzin listesine göre çizilen modül ve eylem kontrolleri
- Asenkron AI görevleri için WebSocket/polling uyumlu takip altyapısı
- Hekim düzeltmesi için gerekçeli frontend alanı
- FHIR R4 kaynak görünümü

## Karar Özeti Notu

Karar özeti alanındaki sınıflandırma değeri frontend içinde sabitlenmiş değildir. Bu alan backend yanıtındaki `predicted_tumor_type` değerinden okunur. Farklı vakalarda aynı sınıflandırma görünüyorsa backend/model çıktısı, model yükleme durumu veya fallback davranışı kontrol edilmelidir.

## Geliştirme Notları

- Frontend kodu bileşen, konfigürasyon ve yardımcı fonksiyon katmanlarına ayrılmıştır.
- Backend ve AI tarafı ayrı çalışma alanları olarak değerlendirilmelidir.
- API sözleşmesi değişirse frontend tarafında öncelikle `src/config/neuroConstants.js` ve `src/utils/neuroUtils.js` kontrol edilmelidir.
- Görüntüleyici davranışları `ProductWorkspace.jsx` içinde yönetilir.

## Ekip İçin Önerilen Sonraki Adımlar

- Backend analiz yanıtlarında sınıflandırma, güven skoru ve fallback durumu açık alanlarla dönülmeli.
- DICOM/NIfTI ve çok kesitli MRG desteği için entegrasyon planı çıkarılmalı.
- Rapor üretimi ve FHIR kaynakları backend tarafında klinik onay durumuyla senkronize edilmeli.
- Frontend ilerleyen aşamada daha küçük viewer, report ve fhir alt bileşenlerine ayrılabilir.
