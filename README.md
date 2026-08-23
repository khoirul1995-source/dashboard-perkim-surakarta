# Dashboard Persebaran Penanganan Perkim

Dashboard sederhana berbasis **Streamlit + Folium** untuk menampilkan persebaran data (dari GeoJSON) dengan fitur filter.

## Fitur
- Peta interaktif (MultiLineString / garis)
- Filter: pencarian nama ruas, Tim, rentang panjang
- Tabel data terfilter
- Metric ringkasan

## Cara Menjalankan

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Jalankan aplikasi:
```bash
streamlit run app.py
```

3. Buka browser di alamat yang muncul (biasanya http://localhost:8501)

## Struktur Data
File GeoJSON diletakkan di folder `data/ruas_jalan.geojson`.

Anda bisa mengganti file tersebut dengan data penanganan (RTLH, jaling, drainase, kumuh) asalkan masih dalam format GeoJSON FeatureCollection.

## Catatan untuk Aktualisasi
- Data saat ini menggunakan contoh ruas jalan.
- Untuk data penanganan, cukup ganti file GeoJSON dan sesuaikan nama kolom di `app.py` (bagian filter & tabel).
