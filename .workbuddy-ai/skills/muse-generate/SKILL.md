---
name: muse-generate
description: Generate aset voxkit (still, keping, pose, fill) lewat Muse / Muse4AI sebagai pengganti gflow — muse_status, muse_generate, muse_get_job, request_id idempoten, kredit, needs_review, download_url 60 menit, dan cara memetakannya ke voxkit/batch.py. Pakai saat menyentuh vox.toml [generation], voxkit/batch.py, perintah "generate still/keping/puppet", kegagalan gflow, atau aset film yang hilang.
---

# Muse sebagai backend aset voxkit

Muse4AI adalah jembatan lokal di Windows yang membuka sesi Muse lewat REST, MCP, dan
OAuth. Server: `http://127.0.0.1:47821`, MCP: `/mcp`, kunci `msk_...` di header
`Authorization: Bearer`, token berlaku 1 jam.

## 0. Batas — baca ini sebelum apa pun

**Skill ini tidak menggantikan pipeline.** Ia menggantikan `gflow` sebagai *backend*,
dan itu berarti satu berkas baru (`voxkit/generate/muse.py`), bukan satu alur kerja baru.

`voxkit/batch.py` memanggil backend lewat `subprocess` dengan `generation.binary`, dan
kontraknya: *batch selesai ketika setiap file ada di disk*, bukan ketika proses exit 0.
`config.py` sudah menyatakan bentuk perubahannya:

> `gflow` is the only backend the batch writer knows how to spell; the batch format
> itself is a list of prompts, so another backend is a different emitter, not a
> different pipeline.

Jadi:

- **Jangan** menjalankan 852 keping dengan memanggil `muse_generate` satu per satu dari
  loop agen. Itu 852 × 30–90 detik, dan tidak ada exit code yang bisa dirantai.
- **Jangan** menganggap `succeeded` berarti aset siap. Aset siap = file ada di
  `build/`, gate membacanya, dan ukurannya masuk akal.
- Emitter memanggil REST, bukan MCP: `POST /v1/jobs`, `GET /v1/jobs/{id}`,
  `GET /v1/status`. MCP hanya untuk agen yang mengerjakan satu-dua aset dengan tangan.
- `GET /v1/openapi.json` bebas kunci. Baca itu, bukan artikel blog, kalau ada yang
  tidak cocok dengan skill ini.

## 1. Urutan satu aset

```
muse_status            → akun siap? kredit? capability?
muse_generate          → job_id          (kind, prompt, request_id, reference_*)
muse_get_job (≤50 s)   → queued → running → succeeded
download_url           → unduh SEKARANG  (berlaku 60 menit)
verifikasi di disk     → ukuran, dimensi, bukan halaman penuh
```

`muse_status` bukan formalitas: kredit itu nyata dan habis. Agen yang memanggil
`muse_generate` tanpa cek status adalah agen yang menghabiskan kuota orang lain.

## 2. Tujuh aturan keras

**1. `request_id` deterministik, bukan acak.**
`vox-{module}-{shot}-{piece}` — mis. `vox-m02-s01-foto_ruang_arsip`. Inilah satu-satunya
hal yang membuat pipeline bisa dijalankan ulang tanpa membakar kredit: request_id sama +
input sama = job yang sama, tidak ada generasi kedua. Timestamp atau UUID membatalkan
seluruh gunanya, dan menggantikan `--resume` gflow yang dulu di-scope ke project.

**2. `needs_review` bukan kegagalan, dan bukan alasan mengulang.**
Status itu berarti Muse ingin manusia melihat hasilnya di aplikasi. Submit ulang akan
membuat job kedua, bukan memperbaiki yang pertama.

**3. `download_url` mati dalam 60 menit.**
Unduh di detik yang sama, simpan file, buang URL. URL yang disimpan di katalog adalah
aset yang hilang enam puluh menit kemudian, dengan pesan yang menyesatkan: "404".

**4. Retry hanya untuk tiga kode.**
`PRE_SUBMIT_TRANSIENT`, `PROXY_FAILED`, `PROVIDER_ERROR` (satu kali, setelah beberapa
menit). Selain itu berhenti dan laporkan. Mencoba ulang `failed` yang deterministik
adalah cara membakar kredit sambil terlihat produktif.

**5. Batas prompt: Muse 4000, voxkit 1950.**
`MAX_PROMPT = 1950` ada karena backend lama memotong di 2000, dan marginnya untuk
wrapper. Muse menerima 4000 — tapi menaikkan angka itu berarti mengubah jaminan yang
dikunci `tests/test_prompt.py`, dan satu backend yang memotong senyap lebih mahal
daripada 450 karakter yang tidak terpakai. Kalau tetap mau dinaikkan, jadikan
per-backend dan buktikan dengan satu batch uji; jangan diganti global. Yang tidak boleh
terulang: satu halaman 2146 karakter membatalkan seluruh batch m17/m18.

**6. Satu job = satu aset.**
`repeat=4` menghasilkan empat varian, bukan satu keping yang lebih baik. Empat varian
berarti empat kandidat yang harus dinilai, dan tidak ada gate yang memilih di antara
mereka.

**7. Jangan pernah menyebut "berhasil" tanpa file.**
`BatchOutcome.ok` salah kalau `missing` tidak kosong. Skill ini tidak boleh melonggarkan
itu hanya karena Muse menjawab `succeeded`.

## 3. Peta jenis aset → parameter

| aset | kind | reference | prompt wajib menyebut | gate |
|---|---|---|---|---|
| still (halaman) | `image` | — | seluruh halaman, kertas krem, bukan digital | `still`, `plate` |
| keping (piece) | `image` | still-nya | latar `#FF00FF` **dan di mana keping berada** | `slot`, `double` |
| pose (puppet) | `image` | kartu yang digantikan | pose menggantikan kartu itu, skala sama | `pose` |
| fill | `image` | — | menutup lubang di belakang keping | `compose` |

Dua yang paling sering salah:

- **Keping tanpa lokasi kembali sebagai seluruh halaman.** 19 keping di 6 modul pernah
  begitu. Prompt harus menyebut tempatnya ("upper left, about 24% across and 33% down"),
  bukan hanya isinya.
- **Keping membawa lembar tetangganya.** Kalau ada keping lain melintang di atasnya,
  model menghapus huruf dan menyisakan kertas kosong. Prompt harus mengatakan *apa yang
  digambar di situ* — lanjutkan permukaan keping itu sendiri — bukan hanya "jadikan
  magenta". Gate `double` menilai dua sisi: kertas kosong **dan** ada cetakan di
  sekelilingnya.

Rasio: pakai `Project.ratio` (16:9 · 9:16 · 1:1 · 4:3 · 3:4). Mengirim `1920:1080`
adalah kesalahan konfigurasi yang membuang seluruh batch sebelum satu gambar pun digambar.

## 4. Yang wajib diukur, bukan diasumsikan

Tulis angkanya ke laporan, jangan ke asumsi:

1. **Resolusi balasan Muse.** gflow mengembalikan 1376×768 di setiap rasio; stage
   menggambar 2976 px, jadi semua aset sudah 2,16× upscale. Kalau Muse mengembalikan
   lebih kecil, rasionya memburuk dan `resolution.py` harus tahu sebelum `upscale`
   dihidupkan.
2. **Kesetiaan kroma.** `#FF00FF` harus rata sampai tepi. Ukur dengan
   `image.keep_largest(near, reach)` yang sudah ada, jangan dengan mata.
3. **Rasio yang benar-benar diterima.** Server bisa menerima daftar yang lebih sempit
   dari `BACKEND_RATIOS`; uji satu job per rasio sebelum batch.
4. **Biaya waktu per aset.** 30–90 detik untuk gambar adalah angka artikel, bukan
   angka mesin ini. Emitter butuh timeout dari pengukuran, bukan dari harapan.

## 5. Perangkap

**Video bukan pose.** Muse menghasilkan 1280×720, 8–10 detik. Puppet voxkit menuntut
frame yang *sejajar piksel* dengan kartu yang digantikannya (§5.11), dan `settle`
mendaratkan kartu tepat di slot — kartu meleset 40 px meninggalkan slip di bawahnya
terbuka. Video gerak bebas tidak bisa memenuhi itu. Video berguna untuk insert,
transisi, dan latar; memakainya untuk pose akan menggagalkan gate `pose` dan merusak
komposisi.

**`succeeded` tanpa file adalah kegagalan.** Unduhan yang gagal setelah URL kedaluwarsa
tidak memunculkan error di Muse — job-nya sudah selesai dari sisi mereka.

**Kredit habis di tengah batch.** Batch 6 prompt (bukan 40) supaya kegagalan kuota
kehilangan enam aset, bukan seluruh modul. `batch_size` di `Generation` sudah 6; jangan
menaikkannya untuk "menghemat waktu".

**Referensi >8 MB ditolak.** PNG/JPEG/WEBP. Gambar yang sama tidak diunggah dua kali
(server memakai SHA-256), jadi referensi berulang murah — tapi hanya kalau byte-nya
identik.

**Cloud agent tidak bisa menghubungi `127.0.0.1`.** Itu alamat mesin pemanggil. Kalau
pekerjaan dijalankan dari agen cloud, butuh Remote access; dari mesin ini, tidak.

## 6. Verifikasi

```bash
# server hidup, akun siap, sisa kredit
curl -s -H "Authorization: Bearer $MSK_KEY" http://127.0.0.1:47821/v1/status

# kontrak openapi, tanpa kunci
curl -s http://127.0.0.1:47821/v1/openapi.json | head -c 2000

# aset benar-benar ada dan gate membacanya
vox plan m01            # gate gratis, tanpa biaya
vox still m01           # satu stage, satu modul
python -m pytest        # 189 tes, di bawah satu detik
```

Kalau gate `still`/`slot`/`double` melaporkan PASS sementara asetnya tidak ada, itu
bug gate, bukan keberhasilan — P5: *cek yang membaca nol item melaporkan PASS*.

## 7. Berhenti dan tanya

- kredit < jumlah aset yang diminta;
- ada job `needs_review`;
- resolusi balasan di bawah 1:1 terhadap stage, dan `upscale` belum diputuskan;
- satu rasio ditolak server;
- video diminta untuk menggantikan pose.

Empat yang pertama adalah keputusan pemilik akun dan pemilik film. Yang kelima adalah
kesalahan desain, dan jawabannya "tidak" — bukan "coba dulu".
