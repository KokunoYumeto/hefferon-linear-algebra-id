# Aljabar Linear — edisi Bahasa Indonesia

Ini adalah edisi Bahasa Indonesia (`id-ID`) dari *Linear Algebra* karya Jim
Hefferon. Edisi ini mencakup tiga keluaran yang saling terhubung:

1. buku teks lengkap;
2. buku jawaban dengan solusi lengkap untuk latihan-latihan buku teks; dan
3. laboratorium komputasi berbasis Sage.

Tautan pada nomor soal dan jawaban dipertahankan agar pembaca dapat berpindah
langsung antara buku teks dan penyelesaian. Berkas PDF siap baca tersedia pada
[rilis terbaru](../../releases/latest); sumber LaTeX yang dapat disunting,
backend modular, manifes, dan alat reproduksi tersedia di repositori ini.

## Isi repositori

- `source/linear-algebra/` — sumber edisi Indonesia dan aset sumber yang
  diperlukan oleh buku, buku jawaban, dan laboratorium;
- `backend/` — indeks modular bebas-lokal yang memetakan unit, segmen, konsep,
  prasyarat, istilah, latihan, jawaban, aset, kode, hak, koreksi, dan peristiwa
  QA;
- `tools/` — alat ekstraksi aset laboratorium dan pembangunan bersih;
- `00_control/` — keputusan edisi, istilah, temuan sumber, status, dan batas
  reproduksi; dan
- `qa/` serta `publication/` — bukti QA dan berkas publikasi setelah rilis.

Backend menggunakan pengenal yang tidak bergantung pada judul terjemahan atau
nomor halaman. Karena itu unit yang sama dapat dipetakan ke Bahasa Indonesia,
Bahasa Mandarin, atau bahasa lain tanpa mengubah identitas sumbernya.

## Otoritas sumber

- Penulis: Jim Hefferon
- Karya: *Linear Algebra*, edisi keempat
- Repositori resmi: <https://gitlab.com/jim.hefferon/linear-algebra>
- Beranda resmi: <https://hefferon.net/linearalgebra>
- Komit sumber: `df2262e089a02651c127f1dd12649c4622ee1383`
- Pohon `src`: `30340725aa2641b3c617b1584c59f6df83e1fdf3`

Repositori sumber menawarkan GNU Free Documentation License atau Creative
Commons Attribution-ShareAlike 2.5. Edisi turunan ini memilih jalur CC BY-SA
2.5 untuk teks dan sumber yang dicakup oleh lisensi tersebut. Lisensi komponen
seperti fon dan kode pihak ketiga tetap mengikuti pemberitahuan masing-masing.
Lihat [NOTICE.id-ID.md](NOTICE.id-ID.md) dan [LICENSE](LICENSE).

## Batas edisi

Edisi ini menerjemahkan buku teks lengkap, jawaban lengkap yang dikompilasi
sebagai buku jawaban, laboratorium Sage lengkap, dan sumber Sage/Python yang
didistribusikan kepada pembaca laboratorium. Arsip pekerjaan rumah, ujian lama,
bank soal, slide kuliah, sumber vendor fon, dan salinan uji pengembang dalam
repositori hulu bukan bagian dari korpus pembaca yang diklaim telah
diterjemahkan.

## Reproduksi

Jalankan alat pembangunan dari akar repositori. Pembangunan dilakukan dalam
pohon staging dan tidak menulis aset hasil kompilasi ke sumber terjemahan.
Karena Sage tidak tersedia secara asli pada host Windows rilis ini, alat
pembangunan menjalankan SageMath 9.5 dan SageTeX 3.6.1 melalui Ubuntu 22.04 di
WSL. Semua 148 blok perintah dieksekusi; perubahan pada 63 sasaran gambar
diaudit; lalu seluruh 64 gambar vektor dipulihkan byte demi byte dari PDF
laboratorium resmi yang dipin agar lapisan gambar akhir tetap menjadi saksi
visual otoritatif. Alat ekstraksi memverifikasi hash PDF, urutan 64 rujukan
sumber, penutupan XObject, validitas satu halaman, dan manifes byte.

Perintah, versi dependensi, hash alat, keluaran runtime, dan sidik jari dua
pembangunan bersih dicatat dalam laporan pembangunan serta manifes rilis.
Enam peta fon PDFTeX beserta pengodean dan program Type 1 yang dirujuknya
disertakan tanpa perubahan di `tools/pdftex-font-closure/`; manifes hash dan
pemberitahuan pihak ketiga di direktori itu mengikat tepat 51 dependensi yang
dipakai oleh pembangunan buku dan buku jawaban. Peta baku milik repositori
dimuat lebih dahulu, pencarian peta/pengodean/program Type 1 dibuat privat,
dan berkas perekam PDFTeX diperiksa sehingga `pdftex.map` global atau program
fon eksternal yang dapat berubah tidak dapat masuk tanpa terdeteksi.
Backend dapat dibuat ulang dengan generator dan diperiksa secara independen
dengan validator di dalam `backend/`.

## Status dan hubungan dengan edisi asli

Ini bukan terbitan resmi Jim Hefferon dan tidak menyiratkan dukungan beliau.
Terjemahan, pengindeksan modular, perbaikan sumber tertentu, dan kompatibilitas
pembangunan dikerjakan oleh Codex atas permintaan pengguna. OpenAI Codex gpt-5.6-sol, Ultra. Semua perubahan yang
memengaruhi isi dicatat secara terpisah dalam
`00_control/ADVERSE_LEDGER.csv`.
