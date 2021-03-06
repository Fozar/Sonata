import re
from decimal import Decimal
from typing import Union

from babel import Locale

from . import i18n
from .converters import locale_to_flag


def lang_to_locale(lang: str):
    r = re.compile(lang + r"_\w{2}")
    locale = next(filter(r.match, list(i18n.LOCALES)), None)
    return locale


def make_locale_list(flag=True, display_name=False):
    locales = []
    for locale in i18n.LOCALES:
        string = f"`{locale if not display_name else Locale.parse(locale, sep='_').display_name}`"
        if flag:
            string = f"{locale_to_flag(locale)} {string}"
        locales.append(string)
    return locales


def map_locale():
    return [
        {
            "locale": locale,
            "display_name": Locale.parse(locale, sep="_").display_name,
            "flag": locale_to_flag(locale),
        }
        for locale in i18n.LOCALES
    ]


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def format_e(n: Union[int, float, Decimal]):
    if isinstance(n, int):
        try:
            n = float(n)
        except OverflowError:
            n = Decimal(n)
    a = "{:E}".format(n)
    return a.split("E")[0].rstrip("0").rstrip(".") + "E" + a.split("E")[1]
