"""Compiled from languages/mizo.yaml by reference/compile_spec.py.

Do not edit by hand. Regenerate with `python compile_spec.py` from
reference/ and commit the result.
"""

LANGUAGE = 'Mizo'
CODE = 'lus'
SPEC_VERSION = '0.3.0'
SUPPORTS = (0, 199)

LEXICON = {
    'scales': {
        10: {'multiplied': 'sawm', 'standalone': 'sâwm'},
        100: {'multiplied': 'za', 'standalone': 'zâ'},
    },
    'units': {
        0: {'bound': 'bial', 'standalone': 'bial'},
        1: {'bound': 'khat', 'standalone': 'pakhat'},
        2: {'bound': 'hnih', 'standalone': 'pahnih'},
        3: {'bound': 'thum', 'standalone': 'pathum'},
        4: {'bound': 'li', 'standalone': 'pali'},
        5: {'bound': 'nga', 'standalone': 'panga'},
        6: {'bound': 'ruk', 'standalone': 'paruk'},
        7: {'bound': 'sarih', 'standalone': 'pasarih'},
        8: {'bound': 'riat', 'standalone': 'pariat'},
        9: {'bound': 'kua', 'standalone': 'pakua'},
    },
}

RULES = (
    {
        'name': 'units',
        'range': (0, 9),
        'condition': None,
        'output': (('units', 'ones_digit', 'standalone'),),
        'parse_aliases': (),
    },
    {
        'name': 'ten',
        'range': (10, 10),
        'condition': None,
        'output': (('scales', 10, 'standalone'),),
        'parse_aliases': (),
    },
    {
        'name': 'teens',
        'range': (11, 19),
        'condition': None,
        'output': (('scales', 10, 'standalone'), ' ', ('units', 'ones_digit', 'standalone')),
        'parse_aliases': (),
    },
    {
        'name': 'exact_tens',
        'range': (20, 99),
        'condition': lambda variables: variables['ones_digit'] == 0,
        'output': (('scales', 10, 'multiplied'), ' ', ('units', 'tens_digit', 'bound')),
        'parse_aliases': (),
    },
    {
        'name': 'compound_tens',
        'range': (21, 99),
        'condition': lambda variables: variables['ones_digit'] > 0,
        'output': (('scales', 10, 'multiplied'), ' ', ('units', 'tens_digit', 'bound'), ' ', ('units', 'ones_digit', 'standalone')),
        'parse_aliases': ((('units', 'tens_digit', 'bound'), ' ', ('units', 'ones_digit', 'bound')),),
    },
    {
        'name': 'hundred',
        'range': (100, 100),
        'condition': None,
        'output': (('scales', 100, 'standalone'),),
        'parse_aliases': (),
    },
    {
        'name': 'hundred_units',
        'range': (101, 109),
        'condition': None,
        'output': (('scales', 100, 'standalone'), ' leh ', ('units', 'ones_digit', 'standalone')),
        'parse_aliases': (),
    },
    {
        'name': 'hundred_ten',
        'range': (110, 110),
        'condition': None,
        'output': (('scales', 100, 'standalone'), ' leh ', ('scales', 10, 'standalone')),
        'parse_aliases': (),
    },
    {
        'name': 'hundred_teens',
        'range': (111, 119),
        'condition': None,
        'output': (('scales', 100, 'standalone'), ' ', ('scales', 10, 'standalone'), ' leh ', ('units', 'ones_digit', 'standalone')),
        'parse_aliases': (),
    },
    {
        'name': 'hundred_exact_tens',
        'range': (120, 199),
        'condition': lambda variables: variables['ones_digit'] == 0,
        'output': (('scales', 100, 'standalone'), ' leh ', ('scales', 10, 'multiplied'), ' ', ('units', 'tens_digit', 'bound')),
        'parse_aliases': (),
    },
    {
        'name': 'hundred_compound_tens',
        'range': (121, 199),
        'condition': lambda variables: variables['ones_digit'] > 0,
        'output': (('scales', 100, 'standalone'), ' ', ('scales', 10, 'multiplied'), ' ', ('units', 'tens_digit', 'bound'), ' leh ', ('units', 'ones_digit', 'standalone')),
        'parse_aliases': (),
    },
)

PARSE = {
    'case_insensitive': True,
    'strip_diacritics': True,
    'word_separators': (' ', '-'),
    'accepted_forms': {'units': ('bound',)},
    'connectors': ('leh',),
    'aliases': {},
}
