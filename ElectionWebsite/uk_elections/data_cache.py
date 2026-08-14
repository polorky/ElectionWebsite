import os
import pickle

_app_static_dir = os.path.join(os.path.dirname(__file__), 'static')

_svg_data = None
_hex_data = None


def get_svg_data():
    global _svg_data
    if _svg_data is None:
        try:
            with open(os.path.join(_app_static_dir, 'uk_svg_data_ws'), 'rb') as f:
                _svg_data = pickle.load(f)
        except Exception:
            _svg_data = {}
    return _svg_data


def get_hex_data():
    global _hex_data
    if _hex_data is None:
        with open(os.path.join(_app_static_dir, 'uk_hex_data_ws'), 'rb') as f:
            _hex_data = pickle.load(f)
    return _hex_data
