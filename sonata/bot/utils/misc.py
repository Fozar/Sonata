import re

import flag as f
from babel import Locale

from .i18n import gettext_translations


def to_lower(arg: str) -> str:  # Converter
    return arg.lower()


def locale_to_language(locale: str) -> str:
    return locale[:2]


def locale_to_flag(locale: str) -> str:
    return f.flag(locale[-2:])


def flag_to_locale(flag: str) -> str:
    locale = f.dflagize(flag)
    r = re.compile(r".{2}_" + locale.strip(":"))
    return list(filter(r.match, gettext_translations.keys()))[0]


def make_locale_list(flag=True, display_name=False):
    locales = []
    for locale in gettext_translations.keys():
        string = f"`{locale if not display_name else Locale.parse(locale, sep='_').display_name}`"
        if flag:
            string = f"{locale_to_flag(locale)} {string}"
        locales.append(string)
    return locales
