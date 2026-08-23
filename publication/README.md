# Publikasi edisi Hefferon id-ID

`publish_release.py` adalah penggerak publikasi berbasis REST yang tidak
menjalankan Git. Rencana tetap berada di `publication-plan.json`. GitHub dan
Zenodo memakai staging final yang sama, terikat DOI dan berisi tepat sembilan
aset, tetapi setiap kanal dapat dijalankan sendiri.

Akses GitHub telah dipulihkan. Setiap kanal tetap dapat diperiksa dan
dipublikasikan secara terpisah. Untuk preflight Zenodo tanpa satu pun panggilan
GitHub, gunakan:

```powershell
python -B publication/publish_release.py zenodo-preflight
```

Setelah build ganda, QA seluruh halaman, dan validasi backend lulus, transaksi
Zenodo yang sudah diotorisasi dijalankan tanpa jeda konfirmasi percakapan:

```powershell
python -B publication/publish_release.py zenodo-publish
python -B publication/publish_release.py zenodo-verify
```

Gate lokal juga mewajibkan audit PDF otomatis tanpa kegagalan keras serta
resi tinjauan visual yang mengikat seluruh halaman melalui lembar kontak,
menyelesaikan setiap kandidat pemeriksaan, dan menyisakan nol temuan terbuka.
Resi itu hanya dibuat setelah pemeriksaan visual yang sebenarnya selesai.

Urutan Zenodo dapat dilanjutkan: validasi lokal; penemuan konsep karya yang sama
melalui judul, kreator, dan penanda sumber pada deposit terautentikasi serta
indeks publik; pemeriksaan duplikasi judul dan
versi; reservasi atau pemakaian ulang DOI transaksi yang tepat; pembuatan paket
deterministik; verifikasi draf terautentikasi; satu tindakan publikasi
irreversibel; lalu pembacaan ulang byte anonim untuk kesembilan aset dan
resolusi DOI. Jika satu konsep karya yang dimaksud sudah ada tetapi versi
transaksi tepat belum ada, alat hanya memanggil
`/deposit/depositions/{latest-version-id}/actions/newversion`, memverifikasi
bahwa responsnya adalah sumber versi asli, lalu mengikuti `links.latest_draft`.
Alat tidak membuat deposit baru dalam keadaan itu. Deposit baru hanya
diizinkan bila pencarian terautentikasi dan publik sama-sama membuktikan bahwa
konsep tersebut belum ada. Konsep ganda, konsep publik yang tidak dapat
direkonsiliasi dengan akun, atau identitas lineage yang berubah semuanya
gagal-tertutup.

`transaction-state.json` mematok `conceptrecid`, DOI konsep, ID deposit versi
terbaru yang menjadi induk, serta ID dan DOI rekaman publik induk secara
terpisah; perbedaan ID deposit dan ID rekaman tidak diasumsikan sama. Semua
identitas itu dibaca ulang saat proses dilanjutkan. State menyimpan hanya ID dan
hash publik, tidak pernah token. Rencana publik hanya
menyebut nama variabel lingkungan dan `publication/.runtime.json`; lokasi
berkas kredensial berada di konfigurasi lokal privat tersebut, yang
dikecualikan dari staging, ZIP, repositori, dan manifes. Token dibaca hanya saat
proses berjalan, diautentikasi satu per satu, dan tidak dicetak atau disalin.

Sidik jari transaksi mengikat byte penggerak, rencana, dan inventaris lengkap
dari semua input staging yang dibatasi rencana (termasuk saksi build
reproduktif). Staging dasar yang dipakai ulang harus kembali cocok dengan input
langsung dan gate kesiapan saat ini. State juga mengunci SHA-256 seluruh berkas
`inventory.json`, bukan hanya daftar berkas di dalamnya, sehingga metadata QA,
DOI, dan penutupan aset tidak dapat diganti diam-diam saat melanjutkan proses.

Draf Zenodo harus memiliki metadata ternormalisasi lengkap, nama dan MD5 tepat,
serta pembacaan ulang SHA-256 terautentikasi tepat pada batas sebelum
publikasi. Respons tulis yang hilang dipulihkan dengan membaca ulang identitas
transaksi; alat tidak menebak keberhasilan dari ukuran atau status lokal. Jika
permintaan pembuatan deposit, pembuatan versi baru, atau publikasi sudah
tercatat tetapi hasilnya masih ambigu, alat hanya membaca ulang/polling dan
menolak mengirim tindakan irreversibel kedua.

Sembilan aset rilis adalah tiga PDF pembaca, tiga ZIP (sumber dapat diedit,
backend modular, dan bukti provenance/QA), README rilis, manifes JSON, serta
`SHA256SUMS`. README aset, metadata Zenodo, dan halaman pembaca bersifat netral
terhadap repositori: semuanya menunjuk ke DOI dan sumber hulu, bukan mengklaim
rilis GitHub yang belum ada.

Byte yang sudah dipublikasikan di Zenodo dapat dicerminkan ke GitHub tanpa
membangun atau men-stage ulang:

```powershell
python -B publication/publish_release.py github-preflight
python -B publication/publish_release.py github-publish
python -B publication/publish_release.py github-verify
```

Rute GitHub khusus mewajibkan publikasi Zenodo selesai, resi pembacaan ulang
anonim Zenodo cocok byte demi byte, DOI tersimpan, dan inventaris final yang
sama; gate itu hanya membaca berkas lokal dan tidak memanggil Zenodo. Resi
anonim terpisah ditulis ke
`public-readback.zenodo.json` dan `public-readback.github.json`. Hanya perintah
gabungan `verify`—yang memeriksa kedua kanal—boleh menulis
`public-readback.json` dan menandai transaksi keseluruhan `complete`.

Tidak ada operasi dalam alat ini yang menghubungi repositori hulu atau penulis.
