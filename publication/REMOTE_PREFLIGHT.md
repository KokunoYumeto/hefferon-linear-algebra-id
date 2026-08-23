# Status kanal publikasi — 2026-08-22

Tidak ada keadaan jarak jauh yang diubah saat dokumen ini diperbarui.

## GitHub

- Pengguna melaporkan bahwa akses GitHub telah dipulihkan setelah tiket dukungan.
- Sasaran penggerak dipatok tepat ke
  `KokunoYumeto/hefferon-linear-algebra-id`, cabang `main`, dengan Pages dari
  `/docs`; perubahan rencana ke akun, repositori, atau cabang lain ditolak.
- Preflight, publikasi, dan pembacaan ulang GitHub dapat dilanjutkan dari
  inventaris final yang sama melalui perintah khusus GitHub tanpa panggilan
  Zenodo. Perintah publikasi khusus GitHub gagal-tertutup sampai resi anonim
  Zenodo yang dipatok state membuktikan DOI, ID rekaman, penutupan aset, ukuran,
  dan SHA-256 yang tepat.

## Zenodo

- Preflight yang telah dicatat sebelumnya tidak menemukan draf atau rekaman
  publik Hefferon untuk judul, komit sumber
  `df2262e089a02651c127f1dd12649c4622ee1383`, dan versi sasaran ini.
- Rekaman `21935111` (`10.5281/zenodo.21935111`) adalah edisi Bahasa Indonesia
  *Understanding Linear Algebra* karya David Austin. Sumber, penulis, lisensi,
  dan garis keturunannya berbeda; rekaman itu tidak boleh dipakai ulang atau
  dijadikan versi untuk edisi Hefferon.
- `zenodo-preflight` harus dijalankan lagi tepat sebelum transaksi. Sebelum
  membuat draf, penggerak gagal-tertutup jika menemukan judul dan versi yang
  sama dengan penanda transaksi berbeda atau hilang. Pemeriksaan itu juga
  mencari karya yang sama melalui judul, kreator, dan penanda sumber, lalu
  merekonsiliasikannya ke satu `conceptrecid` pada deposit terautentikasi dan
  indeks publik. Konsep ganda atau konsep publik yang tidak berada dalam akun
  menghentikan transaksi.

## Transaction design

Jika konsep Hefferon yang dimaksud sudah ada dan versi tepat belum ada,
penggerak membuat versi baru hanya dari ID deposit versi terbaru melalui
`actions/newversion`, lalu mengambil draf lewat `links.latest_draft` pada
respons sumber asli. Ia tidak mengirim `POST /deposit/depositions` pada jalur
itu. Jika tidak ada konsep yang terbukti pada kedua kanal pencarian, tepat satu
deposit konsep baru boleh dibuat. `conceptrecid`, DOI konsep, ID deposit induk,
ID rekaman induk, dan DOI rekaman induk dipatok dan divalidasi ulang saat
resume.

Penggerak API mereservasi atau memakai ulang DOI transaksi yang tepat hanya
setelah setiap gate lokal lulus. DOI itu dimasukkan ke README rilis dan halaman
pembaca sebelum inventaris final dibekukan. Sembilan aset bernama kemudian
diunggah ke Zenodo, diverifikasi terautentikasi, dipublikasikan sekali, lalu
diunduh ulang secara anonim dan dicocokkan ukuran serta SHA-256-nya. Resi
Zenodo tidak menyatakan GitHub selesai dan tidak menandai transaksi gabungan
`complete`. Berkas state lokal menyimpan ID dan hash publik agar transaksi yang
terputus dilanjutkan alih-alih menduplikasi rekaman.
