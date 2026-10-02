"""Compiled from languages/mizo.yaml by reference/compile_spec.py.

Do not edit by hand. Regenerate with `python compile_spec.py` from
reference/ and commit the result.
"""

LANGUAGE = 'Mizo'
CODE = 'lus'
SPEC_VERSION = '0.8.0'
SUPPORTS = (0, 9999999999)

LEXICON = {
    'scales': {
        10: {'multiplied': 'sawm', 'standalone': 'sâwm'},
        100: {'multiplied': 'za', 'standalone': 'zâ'},
        1000: {'multiplied': 'sâng', 'standalone': 'sâng'},
        10000: {'multiplied': 'sîng', 'standalone': 'sîng'},
        100000: {'multiplied': 'nuai', 'standalone': 'nuai'},
        1000000: {'multiplied': 'maktaduai', 'standalone': 'maktaduai'},
        10000000: {'multiplied': 'vaibêlchhe', 'standalone': 'vaibêlchhe'},
        100000000: {'multiplied': 'vaibêlchhetak', 'standalone': 'vaibêlchhetak'},
        1000000000: {'multiplied': 'tlûklehdingâwn', 'standalone': 'tlûklehdingâwn'},
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
        'scale': 1,
        'multiplier': None,
        'condition': None,
        'output': (('lex', 'units', 'multiplier', 'standalone'),),
        'emit': True,
        'whole_only': False,
        'stacks': False,
    },
    {
        'name': 'ten',
        'scale': 10,
        'multiplier': 1,
        'condition': None,
        'output': (('lex', 'scales', 10, 'standalone'), ('optional', (' ', ('remainder',)))),
        'emit': True,
        'whole_only': False,
        'stacks': False,
    },
    {
        'name': 'tens',
        'scale': 10,
        'multiplier': None,
        'condition': lambda variables: variables['multiplier'] > 1,
        'output': (('lex', 'scales', 10, 'multiplied'), ' ', ('lex', 'units', 'multiplier', 'bound'), ('optional', (' ', ('remainder',)))),
        'emit': True,
        'whole_only': False,
        'stacks': False,
    },
    {
        'name': 'hundred',
        'scale': 100,
        'multiplier': 1,
        'condition': None,
        'output': (('lex', 'scales', 100, 'standalone'), ('optional', (' ', ('remainder',)))),
        'emit': True,
        'whole_only': False,
        'stacks': False,
    },
    {
        'name': 'hundreds',
        'scale': 100,
        'multiplier': None,
        'condition': lambda variables: variables['multiplier'] > 1,
        'output': (('lex', 'scales', 100, 'multiplied'), ' ', ('lex', 'units', 'multiplier', 'bound'), ('optional', (' ', ('remainder',)))),
        'emit': True,
        'whole_only': False,
        'stacks': False,
    },
    {
        'name': 'thousands',
        'scale': 1000,
        'multiplier': None,
        'condition': lambda variables: variables['multiplier'] > 0,
        'output': (('lex', 'scales', 1000, 'multiplied'), ' ', ('lex', 'units', 'multiplier', 'bound'), ('optional', (' ', ('remainder',)))),
        'emit': True,
        'whole_only': False,
        'stacks': False,
    },
    {
        'name': 'ten_thousands',
        'scale': 10000,
        'multiplier': None,
        'condition': lambda variables: variables['multiplier'] > 0,
        'output': (('lex', 'scales', 10000, 'multiplied'), ' ', ('lex', 'units', 'multiplier', 'bound'), ('optional', (' ', ('remainder',)))),
        'emit': True,
        'whole_only': False,
        'stacks': False,
    },
    {
        'name': 'hundred_thousands',
        'scale': 100000,
        'multiplier': None,
        'condition': lambda variables: variables['multiplier'] > 0,
        'output': (('lex', 'scales', 100000, 'multiplied'), ' ', ('lex', 'units', 'multiplier', 'bound'), ('optional', (' ', ('remainder',)))),
        'emit': True,
        'whole_only': False,
        'stacks': True,
    },
    {
        'name': 'millions',
        'scale': 1000000,
        'multiplier': None,
        'condition': lambda variables: variables['multiplier'] > 0,
        'output': (('lex', 'scales', 1000000, 'multiplied'), ' ', ('lex', 'units', 'multiplier', 'bound'), ('optional', (' ', ('remainder',)))),
        'emit': True,
        'whole_only': False,
        'stacks': True,
    },
    {
        'name': 'ten_millions',
        'scale': 10000000,
        'multiplier': None,
        'condition': lambda variables: variables['multiplier'] > 0,
        'output': (('lex', 'scales', 10000000, 'multiplied'), ' ', ('lex', 'units', 'multiplier', 'bound'), ('optional', (' ', ('remainder',)))),
        'emit': True,
        'whole_only': False,
        'stacks': True,
    },
    {
        'name': 'hundred_millions',
        'scale': 100000000,
        'multiplier': None,
        'condition': lambda variables: variables['multiplier'] > 0,
        'output': (('lex', 'scales', 100000000, 'multiplied'), ' ', ('lex', 'units', 'multiplier', 'bound'), ('optional', (' ', ('remainder',)))),
        'emit': True,
        'whole_only': False,
        'stacks': True,
    },
    {
        'name': 'billions',
        'scale': 1000000000,
        'multiplier': None,
        'condition': lambda variables: variables['multiplier'] > 0,
        'output': (('lex', 'scales', 1000000000, 'multiplied'), ' ', ('lex', 'units', 'multiplier', 'bound'), ('optional', (' ', ('remainder',)))),
        'emit': True,
        'whole_only': False,
        'stacks': True,
    },
    {
        'name': 'tens_shorthand',
        'scale': 10,
        'multiplier': None,
        'condition': lambda variables: variables['multiplier'] > 1 and variables['remainder'] > 0,
        'output': (('lex', 'units', 'multiplier', 'bound'), ' ', ('lex', 'units', 'remainder', 'bound')),
        'emit': False,
        'whole_only': True,
        'stacks': False,
    },
)

CONNECTOR = {'word': 'leh', 'min': 100}

PARSE = {
    'case_insensitive': True,
    'strip_diacritics': True,
    'word_separators': ('-',),
    'accepted_forms': {'units': ('bound',)},
    'connectors': ('leh',),
    'aliases': {'maktaduaih': 'maktaduai', 'nuaih': 'nuai'},
}
