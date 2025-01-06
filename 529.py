# -*- coding: utf-8 -*-

import re

from .. import ValidationError

_regexes = {
    'word_notword_spaces': re.compile(r'[\w\W\s]*', re.IGNORECASE),
    'notword': re.compile(r'\W', re.IGNORECASE),
    'punctuation': re.compile(r'[^\s\w-]+', re.IGNORECASE),
    'alphanumeric': re.compile(r'[a-z\s\-_0-9]*', re.IGNORECASE),
    'alpha': re.compile(r'[a-z\s\-_]*', re.IGNORECASE),
    'numeric': re.compile(r'\d*', re.IGNORECASE),
    'dash_under_space': re.compile(r'[\-_\s]+', re.IGNORECASE)
}


def _prehook(_strip=True, _value=None, *args, **kwargs):
    if _value is None:
        return u''

    if type(_value) not in (unicode, str):
        raise ValidationError('This _value must be a str or unicode type.')

    if _strip:
        _value = strip(_value=_value)

    return _value if type(_value) is unicode else unicode(_value)


def text(min_len=None, max_len=None, _value=None, *args, **kwargs):
    if min_len is not None and len(_value) <= min_len:
        raise ValidationError('Text length must be greater than %s' % min_len)

    if max_len is not None and len(_value) >= max_len:
        raise ValidationError('Text length must be less than %s' % max_len)

    return _value


def alphanumeric(_value=None, *args, **kwargs):
    if not _regexes['alphanumeric'].match(_value):
        raise ValidationError(
            'This _value must contain alphanumeric characters only.')

    return _value

alnum = alphanumeric


def alpha(_value=None, *args, **kwargs):
    if not _regexes['alpha'].match(_value):
        raise ValidationError(
            'This _value must contain alphabetical characters only.')

    return _value


def numeric_string(_value=None, *args, **kwargs):
    if not _regexes['numeric'].match(_value):
        raise ValidationError(
            'This _value must contain numeric characters only.')

    return _value


def nonblank(_value=None, *args, **kwargs):
    if len(_value) <= 0:
        raise ValidationError('This _value must not be empty.')

    return _value


def removespaces(_value=None, *args, **kwargs):
    return _value.replace(u' ', u'')


def strip(_value=None, *args, **kwargs):
    return _value.strip()


def lower(_value=None, *args, **kwargs):
    return _value.lower()


def upper(_value=None, *args, **kwargs):
    return _value.upper()


def regex(regex, case=False, _value=None, *args, **kwargs):
    if kwargs.get('case'):
        regex = re.compile(regex)
    else:
        regex = re.compile(regex, re.IGNORECASE)

    if not regex.match(_value):
        raise ValidationError('The _value must match the regex %s' % regex)

    return _value


def canonize(_value=None, *args, **kwargs):
    return _regexes['dash_under_space'].sub('_', _value.strip().lower())


def slugify(_value=None, *args, **kwargs):
    _value = _regexes['punctuation'].sub('', _value)
    _value = ' '.join(_value.split('-'))
    _value = ' '.join(_value.split())
    _value = _regexes['notword'].sub('-', _value)
    return _value.lower()


def key_lookup(ref, nomatch='pass', _value=None, *args, **kwargs):
    try:
        return ref[_value]
    except KeyError:
        if nomatch == 'pass':
            return _value
        else:
            raise ValidationError(
                'Could not find a matching entry for key %s' % _value)
