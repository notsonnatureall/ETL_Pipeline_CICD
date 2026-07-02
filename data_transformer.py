import pandas as pd
import re
from datetime import datetime
from difflib import SequenceMatcher
import traceback

# ==========================================
# 1. HELPER FUNCTIONS
# ==========================================

def build_success_response(data):
    return {
        'status': 'success',
        'message': 'OK',
        'code': 'OK',
        'trace': 'OK',
        'data': data
    }

def build_error_response(message, exception=None, code=None):
    return {
        'status': 'error',
        'message': f"{message}" if exception else message,
        'code': code or getattr(exception, 'pgcode', None),
        'trace': traceback.format_exc() if exception else None,
        'data': None
    }

def format_kabupaten_kota(name):
    name = name.upper().strip()
    if name.startswith('KOTA ') or name.startswith('KABUPATEN '):
        return name
    elif name in ['KEDIRI', 'BLITAR', 'MALANG', 'PROBOLINGGO', 'PASURUAN', 'MOJOKERTO', 'MADIUN', 'SURABAYA', 'BATU']:
        return f'KOTA {name}'
    elif name.startswith('KAB. '):
        return name.replace('KAB. ', 'KABUPATEN ')
    elif name.startswith('0'):
        return name
    return f'KABUPATEN {name}'

def format_kecamatan(name):
    name = name.upper().strip()
    if name.startswith('KECAMATAN '):
        return name.replace('KECAMATAN ', '')
    return name

# ==========================================
# 2. CORE PREPROCESSING & TRANSFORM
# ==========================================

def preprocessing(df):
    try:
        data = df.copy()
        
        if 'kategori' in data.columns and 'jumlah' in data.columns:
            if data.kategori.isnull().values.any() and data.jumlah.isnull().values.any():
                data.drop(columns=['kategori', 'jumlah'], errors='ignore', inplace=True)
        
        if data.isnull().values.any():
            null_row = data[data.isnull().any(axis=1)]
            id_with_null = null_row['id'].tolist()
            return build_error_response(f"Gagal Melakukan Cleansing, Ada Data Kosong di Baris {id_with_null[:3]} dst.", code='NULL_VALUE')
        
        rename_map = {}
        found_kode = found_nama = False

        if 'satuan' not in data.columns:
            return build_error_response(f"Gagal Preprocessing: Kolom 'satuan' tidak ditemukan saat validasi.", code='SATUAN_NOT_FOUND')

        if (df['satuan'].dropna().nunique() == 1 and df['satuan'].isin(['0', '-', 'N/A', 'NA', 'N\\A']).all()) or df['satuan'].isna().all():
            return build_error_response(f"Gagal Preprocessing: Kolom 'satuan' null / tidak memiliki value.", code='SATUAN_IS_NULL')

        for del_kode in ['bps_kode_desa_kelurahan', 'bps_kode_kecamatan', 'kemendagri_kode_desa_kelurahan', 'kode_kabupaten_kota', 'kemendagri_kode_kecamatan', 'kode_kecamatan', 'kode_kabupaten', 'kode_kelurahan']:
            if del_kode in data.columns:
                data.drop(columns=[del_kode], inplace=True)

        for col in data.columns:
            col_data = data[col]

            if col_data.dtype == object:
                col_series = col_data.astype(str).str.strip()
                col_series = (
                    col_series.str.upper()
                              .str.replace('_', ' ', regex=False)
                              .str.replace('\\n', ' ', regex=True)
                              .replace(['N/A', 'NA', 'N\\A', '-', ''], '0')
                )
                data[col] = col_series

                if (data[col] == 'JAWA TIMUR').mean() > 0.5:
                    data[col] = 'JAWA TIMUR'
                    rename_map[col] = 'nama_provinsi'
                    found_nama = True

            elif pd.api.types.is_numeric_dtype(col_data):
                if (col_data == 35).mean() > 0.5:
                    data[col] = 35
                    rename_map[col] = 'kode_provinsi'
                    found_kode = True

        data.rename(columns=rename_map, inplace=True)

        if not found_kode and 'kode_provinsi' not in data.columns:
            data['kode_provinsi'] = 35
        if not found_nama and 'nama_provinsi' not in data.columns:
            data['nama_provinsi'] = 'JAWA TIMUR'

        return build_success_response(data)

    except Exception as e:
        return build_error_response(f"Terjadi kesalahan saat preprocessing.", exception=e, code="PREPROCESSING_ERROR")

def periode_update(df):
    try:
        def standardize_periode(periode):
            month_map = {
                'JANUARI': '01', 'FEBRUARI': '02', 'MARET': '03', 'APRIL': '04',
                'MEI': '05', 'JUNI': '06', 'JULI': '07', 'AGUSTUS': '08',
                'SEPTEMBER': '09', 'OKTOBER': '10', 'NOVEMBER': '11', 'DESEMBER': '12'
            }
            tri_map = {'I': 'Q1', 'II': 'Q2', 'III': 'Q3', 'IV': 'Q4'}
            cat_map = {'I': 'C1', 'II': 'C2', 'III': 'C3'}
            sem_map = {'I': 'S1', 'II': 'S2'}

            if pd.isna(periode) or str(periode).strip() in ['', '-']:
                return '0'

            periode = str(periode).upper().strip()

            if re.match(r"\d{2}-\d{2}-\d{4}", periode):
                try:
                    return datetime.strptime(periode, "%d-%m-%Y").strftime("%Y-%m-%d")
                except:
                    return '0'

            match = re.match(r"(\d{1,2})\s+([A-Z]+)\s+(\d{4})", periode)
            if match:
                day, month_name, year = match.groups()
                month = month_map.get(month_name.upper())
                return f"{year}-{month}-{int(day):02d}" if month else '0'

            if re.match(r"\d{4}-\d{2}-\d{2}", periode):
                return periode

            if 'TAHUN' in periode:
                return periode.replace("TAHUN", "").strip()

            for bulan, num in month_map.items():
                if bulan in periode:
                    tahun_match = re.search(r'\d{4}', periode)
                    return f"{tahun_match.group()}-{num}" if tahun_match else '0'

            if 'TRIWULAN' in periode:
                parts = periode.split()
                if len(parts) >= 3:
                    tahun = re.search(r'\d{4}', periode)
                    if tahun:
                        tri = tri_map.get(parts[1], parts[1])
                        return f"{tahun.group()}-{tri}"

            if 'CATURWULAN' in periode:
                parts = periode.split()
                if len(parts) >= 3:
                    tahun = re.search(r'\d{4}', periode)
                    if tahun:
                        cat = cat_map.get(parts[1], parts[1])
                        return f"{tahun.group()}-{cat}"

            if 'SEMESTER' in periode:
                parts = periode.split()
                if len(parts) >= 3:
                    tahun = re.search(r'\d{4}', periode)
                    if tahun:
                        sem = sem_map.get(parts[1], parts[1])
                        return f"{tahun.group()}-{sem}"

            if any(x in periode for x in ['S1', 'S2', 'Q1', 'Q2', 'Q3', 'Q4', 'C1', 'C2', 'C3']):
                tahun_match = re.search(r'\d{4}', periode)
                return periode if tahun_match else '0'

            tahun_match = re.search(r'\d{4}', periode)
            return tahun_match.group() if tahun_match else '0'

        if 'periode_update' in df.columns:
            df['periode_update'] = df['periode_update'].astype(str)
        elif 'periode' in df.columns:
            df['periode_update'] = df['periode'].astype(str)
            df.drop(columns=['periode'], inplace=True)
        elif 'tahun' in df.columns:
            df['periode_update'] = df['tahun'].astype(str)
        else:
            return build_error_response("Kolom 'periode_update', 'periode', atau 'tahun' tidak ditemukan.", code="PERIODE_COLUMN_NOT_FOUND")

        df['periode_update'] = df['periode_update'].apply(standardize_periode)
        df['tahun'] = df['periode_update'].str.extract(r'(\d{4})').fillna(0).astype(int)

        if df['periode_update'].isin(['0']).all():
            return build_error_response("Semua nilai 'periode_update' tidak valid.", code="PERIODE_INVALID_ALL")

        return build_success_response(df)

    except Exception as e:
        return build_error_response(f"Terjadi kesalahan saat memproses periode: {str(e)}", code="PERIODE_EXCEPTION")

def deteksi_wilayah(df):
    try:
        if df is None or df.empty:
            raise ValueError("DataFrame kosong atau tidak valid.")

        def best_match(target):
            return max(df.columns, key=lambda col: SequenceMatcher(None, target, col).ratio())

        expected = ['nama_provinsi', 'kabupaten_kota', 'nama_kecamatan', 'desa_kelurahan']
        matched = {key: best_match(key) for key in expected}

        kolom = [col.lower() for col in df.columns]
        kelurahan = any(k in kolom for k in ['bps_nama_desa_kelurahan', 'kemendagri_nama_desa_kelurahan', 'nama_kelurahan/desa', 'nama_kelurahan', 'nama_desa', 'kelurahan', 'desa'])
        kecamatan = any(k in kolom for k in ['kemendagri_nama_kecamatan', 'bps_nama_kecamatan', 'nama_kecamatan', 'kecamatan'])
        kabupaten = any(k in kolom for k in ['nama_kabupaten', 'kabupaten', 'kabupaten_kota', 'nama_kabupaten_kota'])
        provinsi  = any(k in kolom for k in ['nama_provinsi', 'provinsi', 'prov'])

        if provinsi and not (kabupaten or kecamatan or kelurahan):
            return build_success_response(('data_provinsi', {'nama_provinsi': matched['nama_provinsi']}))

        elif kabupaten and not (kecamatan or kelurahan):
            return build_success_response((
                'data_kabupaten', {
                    'nama_provinsi': matched['nama_provinsi'],
                    'nama_kabupaten_kota': matched['kabupaten_kota']
                }
            ))

        elif kecamatan:
            return build_success_response((
                'data_kecamatan', {
                    'nama_provinsi': matched['nama_provinsi'],
                    'nama_kabupaten_kota': matched['kabupaten_kota'],
                    'bps_nama_kecamatan': matched['nama_kecamatan'],
                    'kemendagri_nama_kecamatan': matched['nama_kecamatan']
                }
            ))

        elif kelurahan:
            return build_success_response((
                'data_kelurahan', {
                    'nama_provinsi': matched['nama_provinsi'],
                    'nama_kabupaten_kota': matched['kabupaten_kota'],
                    'bps_nama_kecamatan': matched['nama_kecamatan'],
                    'kemendagri_nama_kecamatan': matched['nama_kecamatan'],
                    'bps_desa_kelurahan': matched['desa_kelurahan'],
                    'kemendagri_desa_kelurahan': matched['desa_kelurahan']
                }
            ))

        else:
            return build_error_response("Tidak dapat mendeteksi wilayah dari struktur data yang diberikan.", code = "DETECT_LOC_FAILED")

    except Exception as e:
        return build_error_response("Gagal mendeteksi wilayah.", exception=e, code = "DETECT_LOC_ERROR")

def merge_df(df, masterdata, left_on_col, right_on):
    try:
        if df is None or masterdata is None:
            return build_error_response("Dataframe utama atau masterdata tidak boleh None.", code ='DATA_NULL')

        if isinstance(left_on_col, str):
            left_on_col = [left_on_col]
        if isinstance(right_on, str):
            right_on = [right_on]

        merged = df.merge(
            masterdata,
            left_on=left_on_col,
            right_on=right_on,
            how='left',
            suffixes=('_x', '_y')
        )

        cols_to_drop = [col for col in left_on_col if col not in right_on]
        merged.drop(columns=cols_to_drop, errors='ignore', inplace=True)

        dup_bases = {c[:-2] for c in merged.columns if c.endswith(('_x', '_y'))}
        for base in dup_bases:
            col_x, col_y = f"{base}_x", f"{base}_y"

            if col_x in merged.columns and col_y in merged.columns:
                merged[base] = merged[col_y].combine_first(merged[col_x])
                merged.drop([col_x, col_y], axis=1, inplace=True)
            elif col_x in merged.columns:
                merged.rename(columns={col_x: base}, inplace=True)
            elif col_y in merged.columns:
                merged.rename(columns={col_y: base}, inplace=True)

        return build_success_response(merged)

    except Exception as e:
        return build_error_response(message="Gagal melakukan merge ke masterdata pada dataframe.", exception=e, code="MERGE_ERROR")

def transpose_data(df, data_type):
    try:
        data = df.copy()

        wilayah_cols = {
            'provinsi': ['kode_provinsi', 'nama_provinsi'],
            'kabupaten_kota': ['kode_kabupaten_kota', 'nama_kabupaten_kota'],
            'kecamatan': ['bps_kode_kecamatan', 'bps_nama_kecamatan', 'kemendagri_kode_kecamatan', 'kemendagri_nama_kecamatan'],
            'desa': ['bps_kode_desa_kelurahan', 'bps_desa_kelurahan', 'kemendagri_kode_desa_kelurahan', 'kemendagri_desa_kelurahan']
        }

        identitas_wilayah = [col for group in wilayah_cols.values() for col in group if col in data.columns]
        exclude_cols = ['id_index', 'id', 'kategori', 'jumlah', 'periode_update', 'satuan', 'periode', 'tahun'] + identitas_wilayah
        other_cols = [col for col in data.columns if col not in exclude_cols]

        data[other_cols] = data[other_cols].replace(['N/A', 'NA', 'N\\A'], '0')

        if data_type == 'agregat':
            try:
                num_cols = [
                    col for col in other_cols
                    if pd.api.types.is_numeric_dtype(data[col]) or pd.to_numeric(data[col], errors='coerce').notna().all()
                ]

                num_text = [
                    col for col in other_cols
                    if pd.to_numeric(data[col], errors='coerce').notna().mean() >= 0.5
                ]
                
                error_cols = [
                    col for col in num_text
                    if data[col].astype(str).str.contains(",").any()
                ]

                if error_cols:
                    return build_error_response(
                        f"Data pada kolom numerik {error_cols} memiliki simbol koma(,) sehingga kolom terindikasi tipe text. Simbol koma yang benar adalah titik(.)",
                        code="ERROR_COMMA_VALUE"
                    )
                    
                data[num_cols] = data[num_cols].apply(lambda col: col.apply(lambda x: int(x) if isinstance(x, (int, float)) and x == int(x) else x))
                
                cat_cols = [col for col in other_cols if col not in num_cols]

                if 'kategori' in data.columns or 'jumlah' in data.columns:
                    kategori_kosong = data['kategori'].astype(str).str.strip().isin(['0', '-', '']).all() if 'kategori' in data.columns else True
                    jumlah_kosong   = data['jumlah'].astype(str).str.strip().isin(['0', '-', '']).all() if 'jumlah' in data.columns else True

                    if kategori_kosong and jumlah_kosong:
                        data.drop(columns=['kategori', 'jumlah'], errors='ignore', inplace=True)
                    elif not kategori_kosong and jumlah_kosong:
                        data.rename(columns={'kategori': 'kategorikal'}, inplace=True)
                        cat_cols.append('kategorikal')
                    elif not jumlah_kosong and kategori_kosong:
                        data.rename(columns={'jumlah': 'total'}, inplace=True)
                        num_cols.append('total')
                    else:
                        df_melt = data.copy()

                    if 'df_melt' not in locals():
                        id_vars = [col for col in data.columns if col not in num_cols + ['kategori', 'jumlah']]
                        df_melt = data.melt(
                            id_vars=id_vars,
                            value_vars=num_cols,
                            var_name='kategori',
                            value_name='jumlah'
                        )
                else:
                    id_vars = [col for col in data.columns if col not in num_cols + ['kategori', 'jumlah']]
                    df_melt = data.melt(
                        id_vars=id_vars,
                        value_vars=num_cols,
                        var_name='kategori',
                        value_name='jumlah'
                    )

                if df_melt.empty:
                  return build_error_response(f"Hasil tranpose kosong. Pastikan memiliki kolom numerik yang tepat. Kolom {num_text} Terindikasi Text", code="MELT_AGGREGATE_FAILED")

                df_melt['kategori'] = df_melt['kategori'].str.replace('_', ' ')

                for col in df_melt.select_dtypes(include='object').columns:
                    df_melt[col] = df_melt[col].fillna('0').str.strip().str.upper()

                df_melt.fillna(0, inplace=True)

                df_melt = (
                      df_melt.assign(
                          _order = df_melt['kategori'].rank(method='dense').astype(int)
                      )
                      .sort_values(['id', '_order'])
                      .drop(columns=['_order'])
                      .reset_index(drop=True))

                df_melt['id_index'] = ((df_melt.index + 1).astype(str) + df_melt['id'].astype(str)).astype(int)
                agregat_cols = ['periode_update'] + cat_cols + ['kategori', 'jumlah', 'satuan', 'tahun']
                ordered_cols = ['id_index', 'id'] + identitas_wilayah + agregat_cols

                return build_success_response(df_melt[ordered_cols])

            except Exception as e:
                return build_error_response("Gagal melakukan transposisi data agregat.", exception=e, code="AGGREGATE_TRANSPOSE_ERROR")

        elif data_type == 'transaksi':
            try:
                for col in data.select_dtypes(include='object').columns:
                    data[col] = data[col].fillna('0').str.strip().str.upper().str.replace('_', ' ')

                if 'kategori' in data.columns and not data['kategori'].isin(['0', '-', 'N/A', 'NA', 'N\\A']).all():
                    other_cols.append('kategori')

                if 'jumlah' in data.columns and not data['jumlah'].isin(['0', '-', 'N/A', 'NA', 'N\\A']).all():
                    other_cols.append('jumlah')

                transaksi_cols = other_cols + ['periode_update', 'satuan', 'tahun']

                data['id_index'] = ((data.index + 1).astype(str) + data['id'].astype(str)).astype(int)
                ordered_cols = ['id_index', 'id'] + identitas_wilayah + transaksi_cols
                data.fillna(0, inplace=True)

                return build_success_response(data[ordered_cols])

            except Exception as e:
                return build_error_response("Gagal melakukan transposisi data transaksi.", exception=e, code="TRANSACTION_TRANSPOSE_ERROR")

        else:
            return build_error_response("Jenis data_type tidak valid. Harus 'agregat' atau 'transaksi'.", code="INVALID_DATATYPE")

    except Exception as e:
        return build_error_response("Terjadi kesalahan umum dalam fungsi transpose_data.", exception=e, code="TRANSPOSE_DATA_ERROR")
