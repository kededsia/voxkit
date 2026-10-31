# STATUS — tanah-air

Proyek ini adalah pindahan dari `D:/VOX-PLUGIN-2` (baseline `v2.0-conscious-vox-director`).
Asetnya dipindah, bukan digambar ulang: 2.072 berkas dari `rebuild/` dipetakan ke bentuk
yang dibaca `voxkit` (`build/mNN/sNN.jpg`, `cards/`, `fills/`, `plates/`, `iso/`, `specs/`),
dan setiap `layout.json` ditulis ulang supaya `src` keping dan `src` puppet menunjuk ke
tempat yang benar-benar dibaca renderer.

```
film/
  vox.toml        22 rencana, 30 fps, 1920×1080, narasi Indonesia
  plans/          m01–m22 (plan_version 2)
  audio/          m01–m22 .wav + .json (transkrip kata)
  assets/         style-key.jpg
  build/          still, keping, fill, plate, iso, specs
  remotion/       aplikasi render (komponen + node_modules)
```

## Keadaan per modul

| modul | shot | kartu | still | keping | plate | puppet | gerbang gagal |
|---|---|---|---|---|---|---|---|
| m01 | 7 | 31 | 7 | 31 | 7 | 6/6 | compose 1, data 3 |
| m02 | 6 | 34 | 6 | 34 | 6 | 2/2 | compose 3 |
| m03 | 8 | 36 | 8 | 36 | 8 | 5/5 | — |
| m04 | 5 | 26 | 5 | 26 | 5 | 4/4 | — |
| m05 | 15 | 64 | 15 | 64 | 15 | 3/3 | compose 1 |
| m06 | 5 | 24 | 5 | 24 | 5 | 2/2 | — |
| m07 | 5 | 25 | 5 | 25 | 5 | 2/2 | compose 1 |
| m08 | 8 | 34 | 8 | 34 | 8 | 2/2 | — |
| m09 | 13 | 61 | 13 | 61 | 13 | 3/3 | — |
| m10 | 12 | 57 | 12 | 57 | 12 | 3/3 | — |
| m11 | 5 | 24 | 5 | 24 | 5 | 2/2 | — |
| m12 | 4 | 24 | 4 | 24 | 4 | 2/2 | — |
| m13 | 7 | 34 | 7 | 34 | 7 | 2/2 | — |
| m14 | 7 | 33 | 7 | 33 | 7 | 0/2 | pose 2 |
| m15 | 5 | 23 | 0 | 0 | 0 | — | belum digambar |
| m16 | 7 | 39 | 0 | 0 | 0 | — | belum digambar |
| m17 | 5 | 30 | 0 | 0 | 0 | — | belum digambar |
| m18 | 5 | 32 | 0 | 0 | 0 | — | belum digambar |
| m19 | 16 | 97 | 0 | 0 | 0 | — | belum digambar |
| m20 | 7 | 43 | 7 | 43 | 7 | 2/2 | — |
| m21 | 6 | 37 | 0 | 0 | 0 | — | belum digambar |
| m22 | 7 | 44 | 0 | 0 | 0 | — | belum digambar |

**Siap render sekarang (10):** m03 m04 m06 m08 m09 m10 m11 m12 m13 m20.
Film yang sudah terpasang di `remotion/src/film/Film.tsx`: 15 modul, 21.941 frame (12:11).

## Sisa pekerjaan

Tiga kelompok, dan hanya satu di antaranya butuh model gambar.

1. **Butuh still baru (9 temuan).** Enam `compose` (satu keping menutupi 55–93 % keping
   lain) dan tiga `data` di m01 (`CIANJUR 60 KM`, `PUNCAK 1.500 M`, `KM 12` — angka yang
   tidak pernah diucapkan narasi). Memperbaikinya berarti menggeser atau mengganti teks di
   still, jadi satu generate per shot yang terkena.
   `m01 s03` · `m02 s02, s05, s06` · `m05 s13` · `m07 s03` · `m01 s01, s02` (teks).
2. **Butuh 6 frame puppet (m14).** `s02/juru_tulis_batu` dan `s03/penulis_kertas`
   mendeklarasikan 3 aksi masing-masing dan belum pernah digambar.
   `vox poses m14`.
3. **Belum ada aset sama sekali (7 modul, 51 shot).** m15 m16 m17 m18 m19 m21 m22 —
   rencananya lolos semua gerbang rencana; yang belum ada hanya gambarnya.

Urutan yang disarankan: `m14` (6 frame, paling murah) → modul baru dari m15 ke atas
(satu modul penuh sebelum pindah ke berikutnya) → kembali ke m01/m02 untuk still yang
bermasalah, karena itu pekerjaan menggeser komposisi yang sudah ada, bukan membuat baru.

## Alat di `../tools/`

| alat | gunanya |
|---|---|
| `migrate_legacy.py` | pindahkan `rebuild/` ke bentuk `build/`; sekali jalan, tidak menimpa |
| `normalise_plan.py` | `cut` untuk keping yang keluar halaman, alasan untuk tiap pengecualian, durasi mark yang berbeda, R6 (kartu cetak di atas) |
| `repair_poses.py` | kembalikan frame puppet ke kanvas kartunya tanpa menggambar ulang |

## Catatan yang jangan hilang

- `layout.json` menyimpan `z` yang **sama** dengan rencana. Kalau keduanya berbeda,
  urutan gambar dan urutan yang diukur tidak lagi satu cerita.
- Jalur `src` puppet bersifat **relatif modul** (`m04/cards/s01/x_pose2.png`), bukan
  `build/...`: renderer membacanya dari `public/`, dan `build/` akan 404 di tengah render
  setelah semua gerbang hijau.
- Plate juga relatif modul (`m04/plates/s01.jpg`). Tanpa awalan itu `PaperStage` diam-diam
  memakai lembar krem bersama, dan satu modul bisa dirender tanpa halamannya.
