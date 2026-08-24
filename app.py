import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium
from pathlib import Path
from branca.element import MacroElement, Template, Element
import plotly.express as px
import plotly.graph_objects as go
import base64

# ============================================================
# KONFIGURASI HALAMAN
# ============================================================
# Icon: gunakan logo Pemkot jika tersedia
_logo_path = Path(__file__).parent / "assets" / "logo_surakarta.png"
_page_icon = str(_logo_path) if _logo_path.exists() else "🗺️"

st.set_page_config(
    page_title="Persebaran Penanganan Perkim",
    page_icon=_page_icon,
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .block-container {padding-top: 3rem; padding-bottom: 1rem;}
    section[data-testid="stSidebar"] {width: 300px !important;}
    .stButton>button {width: 100%;}
    [data-testid="stMarkdownContainer"],
    [data-testid="column"],
    [data-testid="stHorizontalBlock"] {
        overflow: visible !important;
    }
    .app-header {
        display: flex;
        align-items: center;
        min-height: 60px;
        overflow: visible;
        margin-bottom: 0.2rem;
    }
    .app-header h1 {
        margin: 0;
        font-size: 1.55rem;
        font-weight: 700;
        line-height: 1.25;
        padding: 0;
        white-space: normal;
        overflow: visible;
    }
    .app-header p {
        margin: 3px 0 0;
        opacity: 0.72;
        font-size: 0.85rem;
        overflow: visible;
        white-space: normal;
    }
    .sidebar-logo-wrap {
        display: flex;
        justify-content: center;
        padding: 4px 0 16px;
    }
    .sidebar-logo-wrap img {
        width: 88px;
        height: auto;
        object-fit: contain;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# PATH & KONSTANTA
# ============================================================
DATA_DIR = Path(__file__).parent / "data"

EXCEL_FILES = {
    "Jaling": DATA_DIR / "jaling.xlsx",
    "Draling": DATA_DIR / "draling.xlsx",
    "Kawasan": DATA_DIR / "kawasan.xlsx",
    "RTLH": DATA_DIR / "rtlh.xlsx",
}

GEOJSON_FILES = {
    "Jaling": DATA_DIR / "jaling.geojson",
    "Draling": DATA_DIR / "draling.geojson",
    "Kawasan": DATA_DIR / "kaw.geojson",
    "RTLH": DATA_DIR / "rtlh.geojson",
}

ADMIN_FILES = {
    "Kecamatan": DATA_DIR / "batas_kecamatan.geojson",
    "Kelurahan": DATA_DIR / "batas_kelurahan.geojson",
}

LAYER_COLORS = {
    "Jaling": "#dc2626",
    "Draling": "#1d4ed8",
    "Kawasan": "#d97706",
    "RTLH": "#A0522D",
}

LAYER_LABELS = {
    "Jaling": "Jalan Lingkungan",
    "Draling": "Drainase Lingkungan",
    "Kawasan": "Penataan Kawasan",
    "RTLH": "RTLH",
}

# ============================================================
# FUNGSI LOAD DATA (CACHE)
# ============================================================
@st.cache_data(show_spinner="Memuat data...")
def load_all_data():
    """Membaca Excel + GeoJSON, join berdasarkan kolom ID."""
    result = {}
    for layer_name in ["Jaling", "Draling", "Kawasan", "RTLH"]:
        excel_path = EXCEL_FILES[layer_name]
        if not excel_path.exists():
            result[layer_name] = gpd.GeoDataFrame()
            continue
        df = pd.read_excel(excel_path)
        df.columns = [str(c).strip() for c in df.columns]
        if "ID" not in df.columns:
            result[layer_name] = gpd.GeoDataFrame()
            continue
        df["ID"] = df["ID"].astype(str).str.strip()
        geo_path = GEOJSON_FILES[layer_name]
        if not geo_path.exists():
            result[layer_name] = gpd.GeoDataFrame(df, geometry=None, crs="EPSG:4326")
            continue
        gdf_geo = gpd.read_file(geo_path)
        if gdf_geo.crs is None:
            gdf_geo = gdf_geo.set_crs("EPSG:4326")
        else:
            gdf_geo = gdf_geo.to_crs("EPSG:4326")
        if "ID" in gdf_geo.columns:
            gdf_geo["ID"] = gdf_geo["ID"].astype(str).str.strip()
        elif "id" in gdf_geo.columns:
            gdf_geo = gdf_geo.rename(columns={"id": "ID"})
            gdf_geo["ID"] = gdf_geo["ID"].astype(str).str.strip()
        else:
            gdf_geo["ID"] = None
        gdf_geo = gdf_geo.drop_duplicates(subset=["ID"], keep="first")
        merged = gdf_geo[["ID", "geometry"]].merge(df, on="ID", how="right")
        result[layer_name] = gpd.GeoDataFrame(merged, geometry="geometry", crs="EPSG:4326")
    return result


@st.cache_data(show_spinner="Memuat batas administrasi...")
def load_admin_boundaries():
    """Membaca GeoJSON batas kecamatan & kelurahan."""
    admin = {}
    for name, path in ADMIN_FILES.items():
        if path.exists():
            gdf = gpd.read_file(path)
            if gdf.crs is None:
                gdf = gdf.set_crs("EPSG:4326")
            else:
                gdf = gdf.to_crs("EPSG:4326")
            admin[name] = gdf
        else:
            admin[name] = gpd.GeoDataFrame()
    return admin


def clear_cache_and_rerun():
    """Hapus cache lalu reload halaman (dipakai tombol Update Data)."""
    st.cache_data.clear()
    st.rerun()


# ============================================================
# FUNGSI FILTER
# ============================================================
def apply_wilayah_filter(gdf, kel_to_kec, selected_kecamatan, selected_kelurahan):
    """Terapkan filter wilayah: Kecamatan (via peta kelurahan->kecamatan) dan/atau Kelurahan."""
    if gdf is None or len(gdf) == 0:
        return gdf
    filtered = gdf.copy()
    kel_col = get_kelurahan_col(filtered)
    if not kel_col:
        return filtered
    if selected_kecamatan and selected_kecamatan != "Semua Kecamatan":
        filtered = filtered[
            filtered[kel_col].astype(str).str.strip().map(lambda k: kel_to_kec.get(k) == selected_kecamatan)
        ]
    if selected_kelurahan:
        filtered = filtered[filtered[kel_col].astype(str).str.strip().isin(selected_kelurahan)]
    return filtered


def apply_kegiatan_filter(gdf, sel_kelurahan, sel_pekerjaan, sel_tahun, sel_penyedia):
    """Terapkan filter kegiatan dinamis: Kelurahan, Nama Pekerjaan, Tahun Anggaran, Penyedia."""
    if gdf is None or len(gdf) == 0:
        return gdf
    filtered = gdf.copy()
    kel_col = get_kelurahan_col(filtered)
    if sel_kelurahan and kel_col:
        filtered = filtered[filtered[kel_col].astype(str).str.strip().isin(sel_kelurahan)]
    if sel_pekerjaan and "Nama Pekerjaan" in filtered.columns:
        filtered = filtered[filtered["Nama Pekerjaan"].astype(str).str.strip().isin(sel_pekerjaan)]
    if sel_tahun and sel_tahun != "Semua Tahun" and "Tahun Anggaran" in filtered.columns:
        filtered = filtered[filtered["Tahun Anggaran"].astype(str) == sel_tahun]
    if sel_penyedia and "Penyedia" in filtered.columns:
        filtered = filtered[filtered["Penyedia"].astype(str).str.strip().isin(sel_penyedia)]
    return filtered


def get_kelurahan_col(gdf):
    """Ambil nama kolom kelurahan yang tersedia."""
    for c in ["Kelurahan", "KELURAHAN"]:
        if c in gdf.columns:
            return c
    return None


def excel_display_columns(gdf):
    """Semua kolom Excel untuk popup, tanpa ID dan geometry."""
    skip = {"geometry", "ID", "id"}
    cols = []
    for c in gdf.columns:
        if c in skip:
            continue
        cols.append(c)
    return cols


def hover_label_column(gdf):
    """Kolom singkat untuk tooltip hover (bukan ID)."""
    for c in ["Nama Jalan", "NAMA LENGKAP", "Nama Pekerjaan", "Lokasi", "Kelurahan", "KELURAHAN"]:
        if c in gdf.columns:
            return c
    cols = excel_display_columns(gdf)
    return cols[0] if cols else None


def gdf_for_map(gdf):
    """Salin GeoDataFrame dan ubah nilai jadi teks agar popup aman."""
    out = gdf.copy()
    for c in out.columns:
        if c == "geometry":
            continue
        if c == "Harga":
            out[c] = out[c].apply(lambda v: format_rp(v) if pd.notna(v) else "-")
        else:
            out[c] = out[c].apply(lambda v: "-" if pd.isna(v) else str(v).strip() or "-")
    return out


# ============================================================
# FUNGSI BANTU RINGKASAN / GRAFIK
# ============================================================
def safe_sum(series):
    """Jumlahkan kolom numerik dengan aman."""
    try:
        return pd.to_numeric(series, errors="coerce").fillna(0).sum()
    except Exception:
        return 0


def build_overall_summary(filtered_data):
    """Hitung metric keseluruhan dari semua layer yang aktif."""
    total_kegiatan = 0
    total_panjang = 0
    total_anggaran = 0
    kelurahan_set = set()
    total_rtlh = 0
    counts = {}

    for name, gdf in filtered_data.items():
        if gdf is None or len(gdf) == 0:
            counts[name] = 0
            continue
        n = len(gdf)
        counts[name] = n
        total_kegiatan += n
        if name in ["Jaling", "Draling"] and "Panjang" in gdf.columns:
            total_panjang += safe_sum(gdf["Panjang"])
        if name in ["Jaling", "Draling"] and "Harga" in gdf.columns:
            total_anggaran += safe_sum(gdf["Harga"])
        if name == "RTLH":
            total_rtlh = n
        kel_col = get_kelurahan_col(gdf)
        if kel_col:
            kelurahan_set.update(gdf[kel_col].dropna().astype(str).str.strip().unique())

    return {
        "total_kegiatan": total_kegiatan,
        "total_panjang": total_panjang,
        "total_anggaran": total_anggaran,
        "jumlah_kelurahan": len([k for k in kelurahan_set if k and k.lower() != "nan"]),
        "total_rtlh": total_rtlh,
        "counts": counts,
    }


def chart_komposisi(counts):
    """Pie chart komposisi jenis kegiatan."""
    df = pd.DataFrame({
        "Jenis": list(counts.keys()),
        "Jumlah": list(counts.values()),
    })
    df = df[df["Jumlah"] > 0]
    if df.empty:
        return None
    fig = px.pie(df, names="Jenis", values="Jumlah", color="Jenis",
                 color_discrete_map=LAYER_COLORS, hole=0.35)
    fig.update_layout(margin=dict(t=30, b=10, l=10, r=10), height=320,
                      legend=dict(orientation="h", y=-0.1))
    return fig


def chart_per_kelurahan(filtered_data):
    """Bar chart jumlah kegiatan per kelurahan (semua layer digabung)."""
    rows = []
    for name, gdf in filtered_data.items():
        if gdf is None or len(gdf) == 0:
            continue
        kel_col = get_kelurahan_col(gdf)
        if not kel_col:
            continue
        for kel, cnt in gdf[kel_col].astype(str).str.strip().value_counts().items():
            if kel and kel.lower() != "nan":
                rows.append({"Kelurahan": kel, "Jumlah": cnt, "Jenis": name})
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df_sum = df.groupby("Kelurahan", as_index=False)["Jumlah"].sum().sort_values("Jumlah", ascending=True)
    fig = px.bar(df_sum, x="Jumlah", y="Kelurahan", orientation="h",
                 color_discrete_sequence=["#1d4ed8"])
    fig.update_layout(margin=dict(t=30, b=10, l=10, r=10), height=max(320, len(df_sum) * 22),
                      yaxis_title="", xaxis_title="Jumlah Kegiatan")
    return fig


def chart_panjang_per_kelurahan(gdf, title):
    """Bar chart total panjang per kelurahan (Jaling / Draling)."""
    if gdf is None or len(gdf) == 0 or "Panjang" not in gdf.columns:
        return None
    kel_col = get_kelurahan_col(gdf)
    if not kel_col:
        return None
    tmp = gdf.copy()
    tmp["Panjang"] = pd.to_numeric(tmp["Panjang"], errors="coerce").fillna(0)
    tmp[kel_col] = tmp[kel_col].astype(str).str.strip()
    df = tmp.groupby(kel_col, as_index=False)["Panjang"].sum()
    df = df[df[kel_col].str.lower() != "nan"].sort_values("Panjang", ascending=True)
    if df.empty:
        return None
    fig = px.bar(df, x="Panjang", y=kel_col, orientation="h",
                 color_discrete_sequence=["#059669"])
    fig.update_layout(margin=dict(t=30, b=10, l=10, r=10), height=max(280, len(df) * 22),
                      yaxis_title="", xaxis_title="Panjang (m)", title=title)
    return fig


def chart_anggaran_per_kelurahan(gdf, title):
    """Bar chart total anggaran (Harga) per kelurahan."""
    if gdf is None or len(gdf) == 0 or "Harga" not in gdf.columns:
        return None
    kel_col = get_kelurahan_col(gdf)
    if not kel_col:
        return None
    tmp = gdf.copy()
    tmp["Harga"] = pd.to_numeric(tmp["Harga"], errors="coerce").fillna(0)
    tmp[kel_col] = tmp[kel_col].astype(str).str.strip()
    df = tmp.groupby(kel_col, as_index=False)["Harga"].sum()
    df = df[df[kel_col].str.lower() != "nan"].sort_values("Harga", ascending=True)
    if df.empty:
        return None
    fig = px.bar(df, x="Harga", y=kel_col, orientation="h",
                 color_discrete_sequence=["#d97706"])
    fig.update_layout(margin=dict(t=30, b=10, l=10, r=10), height=max(280, len(df) * 22),
                      yaxis_title="", xaxis_title="Anggaran (Rp)", title=title)
    return fig


def chart_rtlh_per_kelurahan(gdf):
    """Bar chart jumlah RTLH per kelurahan."""
    if gdf is None or len(gdf) == 0:
        return None
    kel_col = get_kelurahan_col(gdf)
    if not kel_col:
        return None
    tmp = gdf.copy()
    tmp[kel_col] = tmp[kel_col].astype(str).str.strip()
    df = tmp[kel_col].value_counts().reset_index()
    df.columns = ["Kelurahan", "Jumlah"]
    df = df[df["Kelurahan"].str.lower() != "nan"].sort_values("Jumlah", ascending=True)
    if df.empty:
        return None
    fig = px.bar(df, x="Jumlah", y="Kelurahan", orientation="h",
                 color_discrete_sequence=["#dc2626"])
    fig.update_layout(margin=dict(t=30, b=10, l=10, r=10), height=max(280, len(df) * 28),
                      yaxis_title="", xaxis_title="Jumlah Penerima RTLH")
    return fig


def format_rp(nilai):
    """Format angka ke Rupiah penuh, contoh: Rp 1.250.000."""
    try:
        n = float(nilai)
        return "Rp " + f"{n:,.0f}".replace(",", ".")
    except Exception:
        return "-"


# ============================================================
# KONTROL TRANSPARANSI DI DALAM PETA (pojok kanan bawah)
# ============================================================
class OpacityControl(MacroElement):
    """Ikon di pojok kanan bawah peta; klik untuk slider transparansi."""

    _template = Template("""
        {% macro script(this, kwargs) %}
        var _map = {{ this._parent.get_name() }};

        var OpacityCtl = L.Control.extend({
            options: { position: 'bottomright' },
            onAdd: function(map) {
                var wrap = L.DomUtil.create('div', 'opacity-ctl');
                wrap.innerHTML = ''
                    + '<button class="opacity-btn" type="button" title="Tampilan peta">◐</button>'
                    + '<div class="opacity-box">'
                    +   '<div class="opacity-title">Tampilan Peta</div>'
                    +   '<label>Layer Data <span class="v-data">85%</span></label>'
                    +   '<input type="range" min="15" max="100" value="85" class="s-data">'
                    +   '<label>Basemap <span class="v-base">100%</span></label>'
                    +   '<input type="range" min="20" max="100" value="100" class="s-base">'
                    + '</div>';

                L.DomEvent.disableClickPropagation(wrap);
                L.DomEvent.disableScrollPropagation(wrap);

                var btn = wrap.querySelector('.opacity-btn');
                var box = wrap.querySelector('.opacity-box');
                btn.onclick = function(e) {
                    L.DomEvent.stop(e);
                    box.classList.toggle('open');
                };

                function applyData(v) {
                    var op = v / 100.0;
                    map.eachLayer(function(layer) {
                        if (layer instanceof L.TileLayer) return;
                        function styleOne(l) {
                            if (!l || !l.setStyle) return;
                            try {
                                var isFill = (l instanceof L.CircleMarker) || (l instanceof L.Circle) || (l instanceof L.Polygon);
                                l.setStyle({
                                    opacity: op,
                                    fillOpacity: isFill ? op * 0.55 : op * 0.30
                                });
                            } catch (err) {}
                        }
                        styleOne(layer);
                        if (layer.eachLayer) {
                            layer.eachLayer(function(l) {
                                styleOne(l);
                                if (l.eachLayer) l.eachLayer(styleOne);
                            });
                        }
                    });
                }

                function applyBase(v) {
                    var op = v / 100.0;
                    map.eachLayer(function(layer) {
                        if (layer instanceof L.TileLayer && layer.setOpacity) {
                            layer.setOpacity(op);
                        }
                    });
                }

                wrap.querySelector('.s-data').addEventListener('input', function() {
                    wrap.querySelector('.v-data').textContent = this.value + '%';
                    applyData(parseInt(this.value, 10));
                });
                wrap.querySelector('.s-base').addEventListener('input', function() {
                    wrap.querySelector('.v-base').textContent = this.value + '%';
                    applyBase(parseInt(this.value, 10));
                });

                return wrap;
            }
        });

        _map.addControl(new OpacityCtl());
        {% endmacro %}
    """)


# ============================================================
# LEGENDA (pojok kiri bawah peta)
# ============================================================
class LegendControl(MacroElement):
    """Legenda simbol layer kegiatan; pojok kiri bawah peta."""

    def __init__(self, items):
        super().__init__()
        self._name = "LegendControl"
        rows_html = "".join(
            f'<div class="legend-row">'
            f'<span class="legend-dot" style="background:{color}"></span>'
            f'<span class="legend-label">{label}</span>'
            f'</div>'
            for label, color in items
        )
        self._template = Template(
            """
            {% macro script(this, kwargs) %}
            var _map = """ + "{{ this._parent.get_name() }}" + """;

            var LegendCtl = L.Control.extend({
                options: { position: 'bottomleft' },
                onAdd: function(map) {
                    var wrap = L.DomUtil.create('div', 'legend-ctl');
                    wrap.innerHTML = '<div class="legend-title">Keterangan</div>"""
            + rows_html.replace("'", "\\'")
            + """';
                    L.DomEvent.disableClickPropagation(wrap);
                    return wrap;
                }
            });
            _map.addControl(new LegendCtl());
            {% endmacro %}
            """
        )


# ============================================================
# SKALA PETA DI TENGAH BAWAH (dengan scale bar)
# ============================================================
class ScaleCenterControl(MacroElement):
    """Kontrol skala Leaflet dipindah & diposisikan di tengah-bawah peta."""

    _template = Template("""
        {% macro script(this, kwargs) %}
        var _map = {{ this._parent.get_name() }};
        var scaleCtl = L.control.scale({
            position: 'bottomleft',
            metric: true,
            imperial: false,
            maxWidth: 130
        }).addTo(_map);
        var scaleEl = scaleCtl.getContainer();
        scaleEl.classList.add('scale-center');
        _map.getContainer().appendChild(scaleEl);
        {% endmacro %}
    """)


# ============================================================
# HEADER
# ============================================================
col_head, col_btn = st.columns([5, 1.4])
with col_head:
    st.markdown(
        """
        <div class="app-header">
            <div>
                <h1>Persebaran Penanganan Perkim</h1>
                <p>Bidang Perumahan, Kawasan Permukiman &amp; Pertanahan — Kota Surakarta</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_btn:
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    if st.button("🔄 Update Data", help="Muat ulang Excel + GeoJSON", use_container_width=True):
        clear_cache_and_rerun()

# ============================================================
# LOAD DATA
# ============================================================
data = load_all_data()
admin = load_admin_boundaries()

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    _logo = Path(__file__).parent / "assets" / "logo_surakarta.png"
    if _logo.exists():
        _b64 = base64.b64encode(_logo.read_bytes()).decode("utf-8")
        st.markdown(
            f"""
            <div class="sidebar-logo-wrap">
                <img src="data:image/png;base64,{_b64}" alt="Logo Kota Surakarta" />
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### 📍 Filter Wilayah")

    # --- Peta Kelurahan -> Kecamatan (dari batas administrasi) ---
    kel_to_kec = {}
    gdf_kel_admin = admin.get("Kelurahan")
    if gdf_kel_admin is not None and len(gdf_kel_admin) > 0 and "Kecamatan" in gdf_kel_admin.columns:
        for _, r in gdf_kel_admin.iterrows():
            k = str(r.get("Kelurahan", "")).strip()
            kc = str(r.get("Kecamatan", "")).strip()
            if k:
                kel_to_kec[k] = kc

    kecamatan_options = ["Semua Kecamatan"] + sorted({v for v in kel_to_kec.values() if v})
    selected_kecamatan = st.selectbox("Kecamatan", options=kecamatan_options, label_visibility="collapsed")

    if selected_kecamatan != "Semua Kecamatan":
        kelurahan_wilayah_options = sorted([k for k, v in kel_to_kec.items() if v == selected_kecamatan])
    else:
        kelurahan_wilayah_options = sorted(kel_to_kec.keys())
    selected_kelurahan_wilayah = st.multiselect(
        "Kelurahan", options=kelurahan_wilayah_options, default=[],
        placeholder="Semua Kelurahan", label_visibility="collapsed",
    )

    st.markdown("**Layer**")
    show_jaling = st.checkbox("Jalan Lingkungan", value=True)
    show_draling = st.checkbox("Drainase Lingkungan", value=True)
    show_kawasan = st.checkbox("Penataan Kawasan", value=True)
    show_rtlh = st.checkbox("RTLH", value=True)

    st.markdown("---")
    st.markdown("### 🗂️ Filter Kegiatan")

    layer_kegiatan_label = st.selectbox("Layer Kegiatan", options=list(LAYER_LABELS.values()), label_visibility="collapsed")
    label_to_key = {v: k for k, v in LAYER_LABELS.items()}
    target_key = label_to_key[layer_kegiatan_label]

    _base = apply_wilayah_filter(data.get(target_key), kel_to_kec, selected_kecamatan, selected_kelurahan_wilayah)
    _kel_col = get_kelurahan_col(_base) if _base is not None else None

    # --- Kelurahan (dinamis, dari data layer terpilih) ---
    if _base is not None and _kel_col:
        kelurahan_kegiatan_options = sorted([
            k for k in _base[_kel_col].dropna().astype(str).str.strip().unique() if k and k.lower() != "nan"
        ])
    else:
        kelurahan_kegiatan_options = []
    sel_kelurahan_kegiatan = st.multiselect("Kelurahan (kegiatan)", options=kelurahan_kegiatan_options, default=[],
                                             placeholder="Semua Kelurahan")
    _step1 = _base
    if _step1 is not None and _kel_col and sel_kelurahan_kegiatan:
        _step1 = _step1[_step1[_kel_col].astype(str).str.strip().isin(sel_kelurahan_kegiatan)]

    # --- Nama Pekerjaan (dinamis) ---
    if _step1 is not None and "Nama Pekerjaan" in _step1.columns:
        pekerjaan_options = sorted([
            p for p in _step1["Nama Pekerjaan"].dropna().astype(str).str.strip().unique() if p and p.lower() != "nan"
        ])
        sel_pekerjaan = st.multiselect("Nama Pekerjaan", options=pekerjaan_options, default=[], placeholder="Semua Pekerjaan")
    else:
        sel_pekerjaan = []
    _step2 = _step1
    if _step2 is not None and sel_pekerjaan and "Nama Pekerjaan" in _step2.columns:
        _step2 = _step2[_step2["Nama Pekerjaan"].astype(str).str.strip().isin(sel_pekerjaan)]

    # --- Tahun Anggaran (dinamis) ---
    if _step2 is not None and "Tahun Anggaran" in _step2.columns:
        tahun_options = ["Semua Tahun"] + sorted(
            _step2["Tahun Anggaran"].dropna().astype(str).unique(), reverse=True
        )
        sel_tahun_kegiatan = st.selectbox("Tahun Anggaran", options=tahun_options)
    else:
        sel_tahun_kegiatan = "Semua Tahun"
    _step3 = _step2
    if _step3 is not None and sel_tahun_kegiatan != "Semua Tahun" and "Tahun Anggaran" in _step3.columns:
        _step3 = _step3[_step3["Tahun Anggaran"].astype(str) == sel_tahun_kegiatan]

    # --- Penyedia (dinamis) ---
    if _step3 is not None and "Penyedia" in _step3.columns:
        penyedia_options = sorted([
            p for p in _step3["Penyedia"].dropna().astype(str).str.strip().unique() if p and p.lower() != "nan"
        ])
        sel_penyedia = st.multiselect("Penyedia", options=penyedia_options, default=[], placeholder="Semua Penyedia")
    else:
        sel_penyedia = []

    st.markdown("---")
    if st.button("↺ Reset Filter"):
        st.rerun()

# ============================================================
# TERAPKAN FILTER
# ============================================================
layer_visibility = {
    "Jaling": show_jaling,
    "Draling": show_draling,
    "Kawasan": show_kawasan,
    "RTLH": show_rtlh,
}

filtered_data = {}
for name, gdf in data.items():
    if not layer_visibility.get(name, False):
        filtered_data[name] = gpd.GeoDataFrame()
        continue
    wilayah_g = apply_wilayah_filter(gdf, kel_to_kec, selected_kecamatan, selected_kelurahan_wilayah)
    if name == target_key:
        filtered_data[name] = apply_kegiatan_filter(
            wilayah_g, sel_kelurahan_kegiatan, sel_pekerjaan, sel_tahun_kegiatan, sel_penyedia
        )
    else:
        filtered_data[name] = wilayah_g

# ============================================================
# TAB
# ============================================================
tab_peta, tab_ringkasan = st.tabs(["🗺️ Peta", "📊 Ringkasan"])

# ------------------------------------------------------------
# TAB PETA
# ------------------------------------------------------------
with tab_peta:
    all_geoms = []
    for gdf in filtered_data.values():
        if gdf is not None and len(gdf) > 0 and "geometry" in gdf.columns and gdf.geometry.notna().any():
            valid = gdf[gdf.geometry.notna()]
            if len(valid) > 0:
                all_geoms.append(valid)

    center_lat, center_lon = -7.5755, 110.8243
    zoom_start = 13
    fit_bounds = None

    if all_geoms:
        combined = pd.concat(all_geoms, ignore_index=True)
        bounds = combined.total_bounds
        fit_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
        center_lat = (bounds[1] + bounds[3]) / 2
        center_lon = (bounds[0] + bounds[2]) / 2
        zoom_start = 16 if len(combined) <= 3 else 13
    elif len(admin.get("Kecamatan", [])) > 0:
        bounds = admin["Kecamatan"].total_bounds
        center_lat = (bounds[1] + bounds[3]) / 2
        center_lon = (bounds[0] + bounds[2]) / 2
        zoom_start = 12

    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start, tiles=None, control_scale=False)
    if fit_bounds is not None:
        m.fit_bounds(fit_bounds, padding=(40, 40))

    # Basemap
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", overlay=False, control=True).add_to(m)
    folium.TileLayer("CartoDB positron", name="CartoDB Positron", overlay=False, control=True).add_to(m)
    folium.TileLayer(tiles="https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", attr="Google", name="Google Streets", overlay=False, control=True).add_to(m)
    folium.TileLayer(tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", attr="Google", name="Google Satellite", overlay=False, control=True).add_to(m)
    folium.TileLayer(tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", attr="Google", name="Google Hybrid", overlay=False, control=True).add_to(m)

    # Batas Kecamatan
    if len(admin.get("Kecamatan", [])) > 0:
        gdf_kec = admin["Kecamatan"]
        label_field = "Kecamatan" if "Kecamatan" in gdf_kec.columns else gdf_kec.columns[0]
        def style_kec(feature):
            return {"color": "#111827", "weight": 5, "opacity": 0.8, "fillOpacity": 0, "dashArray": "12, 6, 2, 6"}
        fg_kec = folium.FeatureGroup(name="Batas Kecamatan", show=True)
        folium.GeoJson(gdf_kec.__geo_interface__, style_function=style_kec,
                       tooltip=folium.GeoJsonTooltip(fields=[label_field], aliases=["Kecamatan:"], sticky=True)).add_to(fg_kec)
        for _, row in gdf_kec.iterrows():
            try:
                c = row.geometry.centroid
                folium.Marker(location=[c.y, c.x], icon=folium.DivIcon(html=f'<div style="font-size:11px;font-weight:700;color:#111827;text-shadow:0 0 3px #fff,0 0 3px #fff;white-space:nowrap;text-align:center;">{row.get(label_field,"")}</div>')).add_to(fg_kec)
            except Exception:
                pass
        fg_kec.add_to(m)

    # Batas Kelurahan
    if len(admin.get("Kelurahan", [])) > 0:
        gdf_kel = admin["Kelurahan"]
        label_field = "Kelurahan" if "Kelurahan" in gdf_kel.columns else gdf_kel.columns[0]
        def style_kel(feature):
            return {"color": "#4b5563", "weight": 3, "opacity": 0.6, "fillOpacity": 0, "dashArray": "10, 4, 2, 4, 2, 4, 2, 4"}
        fg_kel = folium.FeatureGroup(name="Batas Kelurahan", show=False)
        folium.GeoJson(gdf_kel.__geo_interface__, style_function=style_kel,
                       tooltip=folium.GeoJsonTooltip(fields=[label_field], aliases=["Kelurahan:"], sticky=True)).add_to(fg_kel)
        for _, row in gdf_kel.iterrows():
            try:
                c = row.geometry.centroid
                folium.Marker(location=[c.y, c.x], icon=folium.DivIcon(html=f'<div style="font-size:9px;font-weight:600;color:#374151;text-shadow:0 0 2px #fff,0 0 2px #fff;white-space:nowrap;text-align:center;">{row.get(label_field,"")}</div>')).add_to(fg_kel)
            except Exception:
                pass
        fg_kel.add_to(m)

    # Layer kegiatan
    for layer_name, gdf in filtered_data.items():
        if gdf is None or len(gdf) == 0:
            continue
        valid = gdf[gdf.geometry.notna()].copy() if "geometry" in gdf.columns else gpd.GeoDataFrame()
        if len(valid) == 0:
            continue
        valid = gdf_for_map(valid)
        color = LAYER_COLORS.get(layer_name, "#333333")
        opacity = 0.85
        popup_cols = excel_display_columns(valid)
        hover_col = hover_label_column(valid)
        popup_aliases = [f"{c}:" for c in popup_cols]

        if valid.geometry.iloc[0].geom_type == "Point":
            fg = folium.FeatureGroup(name=layer_name)
            for _, row in valid.iterrows():
                rows_html = "".join(
                    f"<tr><td style='padding:2px 8px 2px 0;font-weight:600;vertical-align:top'>{c}</td>"
                    f"<td style='padding:2px 0'>{row.get(c, '-')}</td></tr>"
                    for c in popup_cols
                )
                popup_html = f"<table style='font-size:12px;border-collapse:collapse'>{rows_html}</table>"
                hover_text = str(row.get(hover_col, layer_name)) if hover_col else layer_name
                folium.CircleMarker(
                    location=[row.geometry.y, row.geometry.x],
                    radius=7,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=opacity,
                    weight=2,
                    popup=folium.Popup(popup_html, max_width=360),
                    tooltip=hover_text,
                ).add_to(fg)
            fg.add_to(m)
        else:
            def style_function(feature, col=color, op=opacity):
                return {"color": col, "weight": 4, "opacity": op, "fillColor": col, "fillOpacity": op * 0.3}

            def highlight_function(feature):
                return {"color": "#000000", "weight": 6, "opacity": 1, "fillOpacity": 0.4}

            folium.GeoJson(
                valid.__geo_interface__,
                style_function=style_function,
                highlight_function=highlight_function,
                tooltip=folium.GeoJsonTooltip(
                    fields=[hover_col],
                    aliases=[""],
                    sticky=True,
                    labels=False,
                ) if hover_col else None,
                popup=folium.GeoJsonPopup(
                    fields=popup_cols,
                    aliases=popup_aliases,
                    max_width=360,
                    labels=True,
                ) if popup_cols else None,
                name=layer_name,
            ).add_to(m)

    folium.LayerControl(collapsed=True, position="topright").add_to(m)
    m.get_root().header.add_child(Element("""
    <style>
    .opacity-ctl { position: relative; }

    /* Perkecil font panel kontrol Basemap & Layer (pojok kanan atas peta) */
    .leaflet-control-layers {
        font-size: 11px !important;
    }
    .leaflet-control-layers-list label {
        font-size: 11px !important;
        margin-bottom: 2px !important;
    }
    .leaflet-control-layers-selector {
        margin-right: 4px !important;
    }
    .leaflet-control-layers-separator {
        margin: 4px 0 !important;
    }

    .opacity-btn {
        width: 34px; height: 34px;
        border: none; border-radius: 4px;
        background: #fff; color: #111;
        font-size: 18px; line-height: 34px;
        cursor: pointer; box-shadow: 0 1px 5px rgba(0,0,0,.35);
        display: block;
    }
    .opacity-btn:hover { background: #f3f4f6; }
    .opacity-box {
        display: none;
        position: absolute;
        right: 0; bottom: 42px;
        width: 190px;
        background: #fff;
        color: #111;
        padding: 10px 12px;
        border-radius: 8px;
        box-shadow: 0 2px 10px rgba(0,0,0,.25);
        font-size: 12px;
        z-index: 1000;
    }
    .opacity-box.open { display: block; }
    .opacity-title { font-weight: 700; margin-bottom: 8px; }
    .opacity-box label {
        display: flex; justify-content: space-between;
        margin: 6px 0 2px; font-size: 12px;
    }
    .opacity-box input[type=range] { width: 100%; margin: 0; }

    /* Legenda pojok kiri bawah */
    .legend-ctl {
        background: #fff;
        padding: 8px 12px;
        border-radius: 8px;
        box-shadow: 0 1px 5px rgba(0,0,0,.35);
        font-size: 11px;
        line-height: 1.5;
        color: #111;
    }
    .legend-title { font-weight: 700; font-size: 11px; margin-bottom: 4px; }
    .legend-row { display: flex; align-items: center; gap: 6px; margin: 2px 0; }
    .legend-dot {
        width: 10px; height: 10px;
        border-radius: 3px;
        flex-shrink: 0;
        display: inline-block;
    }
    .legend-label { white-space: nowrap; }

    /* Skala peta di tengah bawah, dengan bar */
    .scale-center {
        position: absolute !important;
        left: 50% !important;
        transform: translateX(-50%);
        bottom: 10px !important;
        z-index: 1000;
        background: rgba(255,255,255,0.9);
        padding: 2px 10px;
        border-radius: 6px;
        box-shadow: 0 1px 5px rgba(0,0,0,.3);
    }
    .scale-center .leaflet-control-scale-line {
        border: 2px solid #111827;
        border-top: none;
        font-size: 11px;
        font-weight: 600;
        color: #111827;
        background: transparent;
        padding: 0 4px 1px;
    }
    </style>
    """))
    m.add_child(OpacityControl())

    legend_items = [
        (LAYER_LABELS[key], LAYER_COLORS[key]) for key in ["Jaling", "Draling", "Kawasan", "RTLH"]
    ]
    m.add_child(LegendControl(legend_items))
    m.add_child(ScaleCenterControl())

    st_folium(m, width=None, height=620, returned_objects=[])

# ------------------------------------------------------------
# TAB RINGKASAN (menggantikan Tab Data)
# ------------------------------------------------------------
with tab_ringkasan:
    summary = build_overall_summary(filtered_data)

    # --- Metric keseluruhan ---
    st.markdown("### Ringkasan Keseluruhan")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Kegiatan", summary["total_kegiatan"])
    m2.metric("Total Panjang", f"{summary['total_panjang']:,.0f} m")
    m3.metric("Total Anggaran", format_rp(summary["total_anggaran"]))
    m4.metric("Kelurahan Terintervensi", summary["jumlah_kelurahan"])
    m5.metric("Penerima RTLH", summary["total_rtlh"])

    st.markdown("---")

    # --- Grafik keseluruhan ---
    col_a, col_b = st.columns(2)
    with col_a:
        fig_pie = chart_komposisi(summary["counts"])
        if fig_pie:
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Tidak ada data untuk komposisi kegiatan.")
    with col_b:
        fig_kel = chart_per_kelurahan(filtered_data)
        if fig_kel:
            st.plotly_chart(fig_kel, use_container_width=True)
        else:
            st.info("Tidak ada data per kelurahan.")

    # --- Bagian per layer (scroll ke bawah) ---
    # Jaling
    if show_jaling and len(filtered_data.get("Jaling", [])) > 0:
        st.markdown("---")
        st.markdown("### 🛣️ Jalan Lingkungan (Jaling)")
        g = filtered_data["Jaling"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Jumlah Ruas", len(g))
        c2.metric("Total Panjang", f"{safe_sum(g['Panjang']) if 'Panjang' in g.columns else 0:,.0f} m")
        c3.metric("Total Anggaran", format_rp(safe_sum(g["Harga"]) if "Harga" in g.columns else 0))
        ca, cb = st.columns(2)
        with ca:
            fig = chart_panjang_per_kelurahan(g, "Panjang per Kelurahan")
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        with cb:
            fig = chart_anggaran_per_kelurahan(g, "Anggaran per Kelurahan")
            if fig:
                st.plotly_chart(fig, use_container_width=True)

    # Draling
    if show_draling and len(filtered_data.get("Draling", [])) > 0:
        st.markdown("---")
        st.markdown("### 💧 Drainase Lingkungan (Draling)")
        g = filtered_data["Draling"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Jumlah Ruas", len(g))
        c2.metric("Total Panjang", f"{safe_sum(g['Panjang']) if 'Panjang' in g.columns else 0:,.0f} m")
        c3.metric("Total Anggaran", format_rp(safe_sum(g["Harga"]) if "Harga" in g.columns else 0))
        ca, cb = st.columns(2)
        with ca:
            fig = chart_panjang_per_kelurahan(g, "Panjang per Kelurahan")
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        with cb:
            fig = chart_anggaran_per_kelurahan(g, "Anggaran per Kelurahan")
            if fig:
                st.plotly_chart(fig, use_container_width=True)

    # Kawasan
    if show_kawasan and len(filtered_data.get("Kawasan", [])) > 0:
        st.markdown("---")
        st.markdown("### 🏘️ Penataan Kawasan")
        g = filtered_data["Kawasan"]
        st.metric("Jumlah Lokasi", len(g))
        # jumlah per kelurahan
        kel_col = get_kelurahan_col(g)
        if kel_col:
            tmp = g.copy()
            tmp[kel_col] = tmp[kel_col].astype(str).str.strip()
            df = tmp[kel_col].value_counts().reset_index()
            df.columns = ["Kelurahan", "Jumlah"]
            df = df[df["Kelurahan"].str.lower() != "nan"].sort_values("Jumlah", ascending=True)
            if not df.empty:
                fig = px.bar(df, x="Jumlah", y="Kelurahan", orientation="h",
                             color_discrete_sequence=["#d97706"])
                fig.update_layout(margin=dict(t=20, b=10, l=10, r=10), height=max(260, len(df) * 28),
                                  yaxis_title="", xaxis_title="Jumlah Lokasi")
                st.plotly_chart(fig, use_container_width=True)

    # RTLH
    if show_rtlh and len(filtered_data.get("RTLH", [])) > 0:
        st.markdown("---")
        st.markdown("### 🏠 RTLH")
        g = filtered_data["RTLH"]
        st.metric("Jumlah Penerima", len(g))
        fig = chart_rtlh_per_kelurahan(g)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    if summary["total_kegiatan"] == 0:
        st.warning("Tidak ada data yang sesuai filter. Ubah filter di sidebar.")
