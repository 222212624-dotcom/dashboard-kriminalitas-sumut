import html
import json
import os

import folium
import geopandas as gpd
import numpy as np
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(page_title="Peta Kerawanan Kriminalitas Sumut", layout="wide")

# Rapatkan jarak bawaan Streamlit supaya isi halaman muat dalam satu layar
st.markdown(
    "<style>"
    ".block-container{padding-top:3rem;padding-bottom:0.5rem}"
    "[data-testid='stHeader']{height:2.5rem}"
    "[data-testid='stTabs'] [role='tablist']{margin-bottom:0.25rem}"
    "[data-testid='stVerticalBlock']{gap:0.5rem}"
    "</style>",
    unsafe_allow_html=True,
)

WARNA = {"Berisiko": "#c0392b", "Aman": "#2e86c1"}

# Kelompok ketepatan prediksi: urutan = urutan di filter dan legenda
KET_URUT = [
    "Benar Berisiko",
    "Benar Aman",
    "Aman tapi diprediksi Berisiko",
    "Berisiko tapi diprediksi Aman",
]
WARNA_KET = {
    "Benar Berisiko": "#922b21",                  # merah tua
    "Benar Aman": "#1b4f72",                      # biru tua
    "Aman tapi diprediksi Berisiko": "#e67e22",   # oranye
    "Berisiko tapi diprediksi Aman": "#8e44ad",   # ungu
}

MODE_PREDIKSI = "Kelas prediksi"
MODE_AKTUAL = "Kelas aktual (PODES)"
MODE_KET = "Ketepatan prediksi"

CARTO_ESRI = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/"
    "World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
)


# ---------------- Fungsi bantu ----------------
def rb(n):
    """Angka dengan titik pemisah ribuan, gaya Indonesia."""
    return f"{int(n):,}".replace(",", ".")


def pers(x):
    return f"{x:.1f}%".replace(".", ",")


def esc(teks):
    return html.escape(str(teks))


def ke_geojson(gdf):
    """GeoDataFrame jadi dict GeoJSON. Folium menerima dict apa adanya,
    jadi tidak memanggil to_crs (yang butuh pyproj)."""
    return json.loads(gdf.to_json())


def banner(jumlah_desa):
    return (
        "<div style='border-radius:12px;padding:10px 18px;margin-bottom:8px;color:#fff;"
        "display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:4px 16px;"
        "background:linear-gradient(120deg,#922b21 0%,#c0392b 38%,#2e86c1 100%)'>"
        "<div style='font-size:1.2rem;font-weight:700;line-height:1.3'>"
        "Peta Kerawanan Kriminalitas Desa/Kelurahan, Sumatera Utara</div>"
        f"<div style='font-size:.8rem;opacity:.92'>{rb(jumlah_desa)} desa/kelurahan, "
        "klasifikasi Aman atau Berisiko dari citra satelit dan data POI</div></div>"
    )


def lencana(teks, warna):
    return (
        f"<span style='display:inline-block;padding:3px 10px;border-radius:999px;"
        f"background:{warna};color:#fff;font-size:.8rem;font-weight:600;"
        f"margin:2px 4px 2px 0'>{esc(teks)}</span>"
    )


def kartu_desa(r):
    warna = WARNA_KET[r["KETEPATAN"]]
    return (
        f"<div style='border-radius:14px;padding:14px 16px;margin-bottom:14px;"
        f"background:rgba(128,128,128,.10);border:1px solid rgba(128,128,128,.22);"
        f"border-left:6px solid {warna}'>"
        "<div style='font-size:.72rem;opacity:.7;text-transform:uppercase;letter-spacing:.1em'>"
        "Desa/kelurahan terpilih</div>"
        f"<div style='font-size:1.3rem;font-weight:700;line-height:1.25'>{esc(r['NAMA_DESA'])}</div>"
        f"<div style='font-size:.85rem;opacity:.75;margin-bottom:8px'>"
        f"Kec. {esc(r['NAMA_KEC'])}, {esc(r['NAMA_KAB'])}</div>"
        + lencana(f"Aktual: {r['KELAS_AKTUAL']}", WARNA[r["KELAS_AKTUAL"]])
        + lencana(f"Prediksi: {r['KELAS_PREDIKSI']}", WARNA[r["KELAS_PREDIKSI"]])
        + f"<div style='margin-top:8px;font-size:.92rem;font-weight:600'>"
        f"<span style='color:{warna};font-size:1.15em'>■</span> {esc(r['KETEPATAN'])}</div></div>"
    )


def panel_peringkat(d, mode, kolom_kelas, kolom_grup, objek):
    """10 wilayah teratas (kab/kota atau kecamatan), ditampilkan sebagai daftar berbar."""
    if mode == MODE_KET:
        flag = d["KETEPATAN"].isin(KET_URUT[2:])
        judul, warna = "Salah prediksi tertinggi", "#e67e22"
        ket = "% desa/kelurahan salah prediksi"
    else:
        flag = d[kolom_kelas] == "Berisiko"
        judul, warna = "Persentase Berisiko tertinggi", WARNA["Berisiko"]
        ket = "% desa/kelurahan Berisiko"

    g = flag.groupby(d[kolom_grup]).agg(["mean", "size"])
    g["mean"] = g["mean"] * 100
    g = g.sort_values(["mean", "size"], ascending=False).head(10)

    baris = ""
    for nama, r in g.iterrows():
        baris += (
            "<div style='margin:5px 0'>"
            "<div style='display:flex;justify-content:space-between;font-size:.85rem'>"
            f"<span>{esc(str(nama).title())} <span style='opacity:.55'>({rb(r['size'])})</span></span>"
            f"<b>{pers(r['mean'])}</b></div>"
            "<div style='height:8px;border-radius:4px;background:rgba(128,128,128,.2)'>"
            f"<div style='width:{r['mean']:.1f}%;height:100%;border-radius:4px;background:{warna}'></div>"
            "</div></div>"
        )
    return (
        "<div style='border-radius:14px;padding:14px 16px;"
        "background:rgba(128,128,128,.10);border:1px solid rgba(128,128,128,.22)'>"
        f"<div style='font-size:.72rem;opacity:.7;text-transform:uppercase;letter-spacing:.1em'>"
        f"Top 10 {objek}</div>"
        f"<div style='font-size:1.05rem;font-weight:700;margin-bottom:2px'>{judul}</div>"
        f"<div style='font-size:.75rem;opacity:.6'>{ket}, jumlah desa/kelurahan dalam kurung</div>"
        f"{baris}</div>"
    )


def panel_daftar_desa(d, mode, kolom_kelas, nama_kec):
    """Daftar desa/kelurahan dalam satu kecamatan, dengan penanda warna status."""
    baris = ""
    for _, r in d.sort_values("NAMA_DESA").iterrows():
        if mode == MODE_PREDIKSI:
            warna, status = WARNA[r["KELAS_PREDIKSI"]], r["KELAS_PREDIKSI"]
        elif mode == MODE_AKTUAL:
            warna, status = WARNA[r["KELAS_AKTUAL"]], r["KELAS_AKTUAL"]
        else:
            warna, status = WARNA_KET[r["KETEPATAN"]], r["KETEPATAN"]
        baris += (
            "<div style='display:flex;justify-content:space-between;gap:8px;"
            "padding:5px 0;border-bottom:1px solid rgba(128,128,128,.15);font-size:.85rem'>"
            f"<span>{esc(r['NAMA_DESA'])}</span>"
            f"<span style='white-space:nowrap'><span style='color:{warna}'>■</span> "
            f"<span style='opacity:.75'>{esc(status)}</span></span></div>"
        )
    return (
        "<div style='border-radius:14px;padding:14px 16px;"
        "background:rgba(128,128,128,.10);border:1px solid rgba(128,128,128,.22)'>"
        "<div style='font-size:.72rem;opacity:.7;text-transform:uppercase;letter-spacing:.1em'>"
        "Desa/kelurahan</div>"
        f"<div style='font-size:1.05rem;font-weight:700;margin-bottom:6px'>"
        f"Kec. {esc(str(nama_kec).title())} ({rb(len(d))})</div>"
        f"<div style='max-height:340px;overflow-y:auto'>{baris}</div></div>"
    )


@st.cache_data
def muat_data():
    g = gpd.read_file("data_dashboard.geojson")
    g["KETEPATAN"] = np.select(
        [
            (g["KELAS_AKTUAL"] == "Berisiko") & (g["KELAS_PREDIKSI"] == "Berisiko"),
            (g["KELAS_AKTUAL"] == "Aman") & (g["KELAS_PREDIKSI"] == "Aman"),
            (g["KELAS_AKTUAL"] == "Aman") & (g["KELAS_PREDIKSI"] == "Berisiko"),
        ],
        KET_URUT[:3],
        default=KET_URUT[3],
    )
    return g


@st.cache_data
def muat_batas_kab():
    if os.path.exists("batas_kab.geojson"):
        return gpd.read_file("batas_kab.geojson")
    return None


data = muat_data()
batas_kab = muat_batas_kab()

# ---------------- Sidebar ----------------
st.sidebar.header("Filter")
mode = st.sidebar.radio(
    "Warnai peta berdasarkan", [MODE_PREDIKSI, MODE_AKTUAL, MODE_KET]
)

# Kolom dan pilihan filter kelas mengikuti mode yang dipilih
if mode == MODE_PREDIKSI:
    kolom_kelas, pilihan, label_filter = "KELAS_PREDIKSI", ["Aman", "Berisiko"], "Kelas prediksi"
elif mode == MODE_AKTUAL:
    kolom_kelas, pilihan, label_filter = "KELAS_AKTUAL", ["Aman", "Berisiko"], "Kelas aktual"
else:
    kolom_kelas, pilihan, label_filter = "KETEPATAN", KET_URUT, "Kelompok ketepatan"

# Level 1: kabupaten/kota
kab = st.sidebar.multiselect(
    "Kabupaten/Kota", sorted(data["NAMA_KAB"].unique()), placeholder="Semua kabupaten/kota"
)

# Level 2: kecamatan, hanya berisi kecamatan dari kab/kota yang dipilih
if kab:
    pasangan = (
        data.loc[data["NAMA_KAB"].isin(kab), ["NAMA_KAB", "NAMA_KEC"]]
        .drop_duplicates()
        .sort_values(["NAMA_KAB", "NAMA_KEC"])
    )
    opsi_kec = list(zip(pasangan["NAMA_KAB"], pasangan["NAMA_KEC"]))
else:
    opsi_kec = []


def label_kec(p):
    return p[1] if len(kab) == 1 else f"{p[1]} ({p[0].title()})"


kec = st.sidebar.multiselect(
    "Kecamatan",
    opsi_kec,
    format_func=label_kec,
    disabled=not kab,
    placeholder="Pilih kab/kota dulu" if not kab else "Semua kecamatan",
)

kelas = st.sidebar.multiselect(
    label_filter, pilihan, default=pilihan, key=f"filter_{mode}"
)

d = data[data[kolom_kelas].isin(kelas)]
if kab:
    d = d[d["NAMA_KAB"].isin(kab)]
if kec:
    dipilih = set(kec)
    d = d[np.array([p in dipilih for p in zip(d["NAMA_KAB"], d["NAMA_KEC"])], dtype=bool)]

# Tingkat tampilan panel kanan mengikuti kedalaman filter
if len(kec) == 1:
    tingkat = "desa"
elif len(kab) == 1:
    tingkat = "kecamatan"
else:
    tingkat = "kabupaten"

# Level 3: desa/kelurahan, pilihan mengikuti filter di atasnya
if tingkat == "desa":
    def label_desa(n, kc, kb):
        return n
elif tingkat == "kecamatan":
    def label_desa(n, kc, kb):
        return f"{n} (Kec. {kc})"
else:
    def label_desa(n, kc, kb):
        return f"{n} (Kec. {kc}, {kb})"

nama_lengkap = {
    int(i): label_desa(n, kc, kb)
    for i, n, kc, kb in zip(d["ID_DESA"], d["NAMA_DESA"], d["NAMA_KEC"], d["NAMA_KAB"])
}
pilih_id = st.sidebar.selectbox(
    "Desa/Kelurahan",
    options=list(nama_lengkap.keys()),
    index=None,
    placeholder="Ketik nama desa/kelurahan",
    format_func=lambda i: nama_lengkap[i],
)

st.sidebar.markdown("---")
tinggi_peta = st.sidebar.slider(
    "Tinggi peta (piksel)", 360, 800, 580, 20,
    help="Kecilkan kalau halaman masih perlu di-scroll di layarmu.",
)

# ---------------- Judul dan ringkasan ----------------
st.markdown(banner(len(data)), unsafe_allow_html=True)



tab_peta, tab_kab, tab_data = st.tabs(["Peta", "Per wilayah", "Tabel data"])

# ---------------- Tab peta ----------------
with tab_peta:
    if d.empty:
        st.warning("Tidak ada desa/kelurahan yang cocok dengan filter.")
    else:
        kol_peta, kol_info = st.columns([3, 1])

        with kol_peta:
            peta_d = d[[
                "NAMA_DESA", "NAMA_KEC", "NAMA_KAB", "KELAS_AKTUAL",
                "KELAS_PREDIKSI", "KETEPATAN", "geometry",
            ]]

            def gaya(fitur):
                p = fitur["properties"]
                if mode == MODE_PREDIKSI:
                    warna = WARNA[p["KELAS_PREDIKSI"]]
                elif mode == MODE_AKTUAL:
                    warna = WARNA[p["KELAS_AKTUAL"]]
                else:
                    warna = WARNA_KET[p["KETEPATAN"]]
                return {"fillColor": warna, "color": "white", "weight": 0.2, "fillOpacity": 0.8}

            def sorot(fitur):
                return {"color": "#111111", "weight": 2.2, "fillOpacity": 0.95}

            # Area yang di-zoom: desa terpilih, atau semua desa yang lolos filter
            if pilih_id is not None:
                x1, y1, x2, y2 = data.loc[data["ID_DESA"] == pilih_id].total_bounds
            else:
                x1, y1, x2, y2 = peta_d.total_bounds

            m = folium.Map(tiles=CARTO_ESRI, attr="Tiles &copy; Esri")
            m.fit_bounds([[y1, x1], [y2, x2]], max_zoom=13)

            folium.GeoJson(
                ke_geojson(peta_d),
                style_function=gaya,
                highlight_function=sorot,
                tooltip=folium.GeoJsonTooltip(
                    fields=["NAMA_DESA", "NAMA_KEC", "NAMA_KAB", "KELAS_AKTUAL",
                            "KELAS_PREDIKSI", "KETEPATAN"],
                    aliases=["Desa/Kel", "Kecamatan", "Kab/Kota", "Aktual",
                             "Prediksi", "Ketepatan"],
                ),
            ).add_to(m)

            # Garis batas kab/kota di atas poligon desa
            if batas_kab is not None:
                bk = batas_kab[batas_kab["NAMA_KAB"].isin(kab)] if kab else batas_kab
                folium.GeoJson(
                    ke_geojson(bk),
                    style_function=lambda f: {
                        "fill": False, "color": "#1f2d3d", "weight": 1.6, "opacity": 0.9,
                    },
                ).add_to(m)

            # Bingkai tebal untuk desa/kelurahan yang dipilih
            if pilih_id is not None:
                folium.GeoJson(
                    ke_geojson(data.loc[data["ID_DESA"] == pilih_id, ["geometry"]]),
                    style_function=lambda f: {
                        "fill": False, "color": "#000000", "weight": 4, "opacity": 1,
                    },
                ).add_to(m)

            st_folium(m, height=tinggi_peta, use_container_width=True, returned_objects=[])

            # Legenda
            peta_warna = WARNA_KET if mode == MODE_KET else WARNA
            legenda = " &nbsp; ".join(
                f"<span style='color:{w}; font-size:1.2em'>■</span> {n}"
                for n, w in peta_warna.items()
            )
            st.markdown(legenda, unsafe_allow_html=True)

        with kol_info.container(height=tinggi_peta):
            if pilih_id is not None:
                st.markdown(
                    kartu_desa(data.loc[data["ID_DESA"] == pilih_id].iloc[0]),
                    unsafe_allow_html=True,
                )
            if tingkat == "desa":
                st.markdown(
                    panel_daftar_desa(d, mode, kolom_kelas, kec[0][1]),
                    unsafe_allow_html=True,
                )
            elif tingkat == "kecamatan":
                st.markdown(
                    panel_peringkat(d, mode, kolom_kelas, "NAMA_KEC", "kecamatan"),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    panel_peringkat(d, mode, kolom_kelas, "NAMA_KAB", "kab/kota"),
                    unsafe_allow_html=True,
                )

# ---------------- Tab per wilayah ----------------
# Satu kab/kota dipilih: rincian per kecamatan. Selain itu: rincian per kab/kota.
with tab_kab:
    if d.empty:
        st.warning("Tidak ada desa/kelurahan yang cocok dengan filter.")
    else:
        kolom_wilayah = "NAMA_KEC" if len(kab) == 1 else "NAMA_KAB"
        nama_wilayah = "Kecamatan" if len(kab) == 1 else "Kab/Kota"

        if mode == MODE_KET:
            rekap = d.groupby([kolom_wilayah, "KETEPATAN"]).size().reset_index(name="jumlah")
            urut = rekap.groupby(kolom_wilayah)["jumlah"].sum().sort_values().index.tolist()
            fig = px.bar(
                rekap, x="jumlah", y=kolom_wilayah, color="KETEPATAN", orientation="h",
                category_orders={kolom_wilayah: urut, "KETEPATAN": KET_URUT},
                color_discrete_map=WARNA_KET,
                labels={"jumlah": "Jumlah desa/kelurahan", kolom_wilayah: "", "KETEPATAN": "Kelompok"},
            )
            fig.update_layout(height=max(400, 22 * len(urut)), margin=dict(l=0, r=0, t=10, b=0),
                              legend=dict(orientation="h", y=1.02, x=0))
            st.plotly_chart(fig, width="stretch")
        else:
            rekap = (
                d.assign(risiko=(d[kolom_kelas] == "Berisiko"))
                .groupby(kolom_wilayah)
                .agg(jumlah_desa=("risiko", "size"), desa_berisiko=("risiko", "sum"))
                .reset_index()
            )
            rekap["persen_berisiko"] = (rekap["desa_berisiko"] / rekap["jumlah_desa"] * 100).round(1)
            rekap = rekap.sort_values("persen_berisiko")
            fig = px.bar(
                rekap, x="persen_berisiko", y=kolom_wilayah, orientation="h",
                labels={"persen_berisiko": "% desa/kelurahan Berisiko", kolom_wilayah: ""},
                color_discrete_sequence=[WARNA["Berisiko"]],
            )
            fig.update_layout(height=max(400, 22 * len(rekap)), margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, width="stretch")
        st.caption(f"Rincian per {nama_wilayah.lower()}.")

# ---------------- Tab tabel ----------------
with tab_data:
    tabel = d.drop(columns="geometry").rename(columns={
        "ID_DESA": "ID Desa", "NAMA_KAB": "Kab/Kota", "NAMA_KEC": "Kecamatan",
        "NAMA_DESA": "Desa/Kelurahan", "KELAS_AKTUAL": "Aktual", "KELAS_PREDIKSI": "Prediksi",
        "KETEPATAN": "Ketepatan",
    })[["ID Desa", "Kab/Kota", "Kecamatan", "Desa/Kelurahan", "Aktual", "Prediksi", "Ketepatan"]]
    st.dataframe(tabel, width="stretch", hide_index=True)
    st.download_button(
        "Unduh tabel (CSV)",
        tabel.to_csv(index=False).encode("utf-8-sig"),
        file_name="hasil_klasifikasi_terfilter.csv",
        mime="text/csv",
    )
