"""
The Sonata Discord Bot
Copyright (C) 2020 Fozar

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Almost everything here is copied from
https://github.com/Gelbpunkt/IdleRPG/blob/v4/utils/i18n.py
"""
import ast
import builtins
import contextvars
import gettext
import inspect
import os
import re
from glob import glob

import flag as f
from babel import Locale
from babel.support import Translations, NullTranslations

BASE_DIR = os.getcwd()
default_locale = "en_US"
locales_dir = "locales"

locales = frozenset(
    map(
        os.path.basename,
        filter(os.path.isdir, glob(os.path.join(BASE_DIR, locales_dir, "*"))),
    )
)

gettext_translations = {
    locale: Translations.load(
        locales=[locale], dirname=os.path.join(BASE_DIR, locales_dir)
    )
    for locale in locales
    if not locale.startswith("_")
}

# source code is already in en_US.
# we don't use default_locale as the key here
# because the default locale for this installation may not be en_US
gettext_translations["en_US"] = NullTranslations()
locales = locales | {"en_US"}


def use_current_gettext(*args, **kwargs):
    if not gettext_translations:
        return gettext.gettext(*args, **kwargs)

    locale = current_locale.get()
    return gettext_translations.get(
        locale, gettext_translations[default_locale]
    ).gettext(*args, **kwargs)


def i18n_docstring(func):
    src = inspect.getsource(func)
    try:
        tree = ast.parse(src)
    except IndentationError:
        tree = ast.parse("class Foo:\n" + src)
        tree = tree.body[0].body[0]  # ClassDef -> FunctionDef
    else:
        tree = tree.body[0]  # FunctionDef

    if not isinstance(tree.body[0], ast.Expr):
        return func

    tree = tree.body[0].value
    if not isinstance(tree, ast.Call):
        return func

    if not isinstance(tree.func, ast.Name) or tree.func.id != "_":
        return func

    assert len(tree.args) == 1
    assert isinstance(tree.args[0], ast.Str)

    func.__doc__ = tree.args[0].s
    return func


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


current_locale = contextvars.ContextVar("i18n")
builtins._ = use_current_gettext

# noinspection PyArgumentList
current_locale.set(default_locale)
