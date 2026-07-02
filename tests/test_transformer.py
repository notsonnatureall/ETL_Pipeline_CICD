import pandas as pd
from data_transformer import format_kabupaten_kota, format_kecamatan, build_success_response

def test_format_kabupaten_kota():
    assert format_kabupaten_kota("kediri") == "KOTA KEDIRI"
    assert format_kabupaten_kota("kab. blitar") == "KABUPATEN BLITAR"
    assert format_kabupaten_kota("sidoarjo") == "KABUPATEN SIDOARJO"

def test_format_kecamatan():
    assert format_kecamatan("KECAMATAN WARU") == "WARU"

def test_build_success_response():
    data = {"test": 123}
    res = build_success_response(data)
    assert res['status'] == 'success'
    assert res['message'] == 'OK'
