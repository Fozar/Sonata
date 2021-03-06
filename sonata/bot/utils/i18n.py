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
from glob import glob

from babel.support import Translations, NullTranslations

BASE_DIR = os.getcwd()
GETTEXT_TRANSLATIONS = {}
LOCALES = frozenset()
default_locale = "en_US"
locales_dir = "locales"


def update_translations():
    global GETTEXT_TRANSLATIONS, LOCALES
    LOCALES = frozenset(
        map(
            os.path.basename,
            filter(os.path.isdir, glob(os.path.join(BASE_DIR, locales_dir, "??_??"))),
        )
    )

    GETTEXT_TRANSLATIONS = {
        locale: Translations.load(
            locales=[locale], dirname=os.path.join(BASE_DIR, locales_dir)
        )
        for locale in LOCALES
        if not locale.startswith("_")
    }

    # source code is already in en_US.
    # we don't use default_locale as the key here
    # because the default locale for this installation may not be en_US
    GETTEXT_TRANSLATIONS["en_US"] = NullTranslations()
    LOCALES = LOCALES | {"en_US"}


def use_current_gettext(*args, **kwargs):
    if not GETTEXT_TRANSLATIONS:
        return gettext.gettext(*args, **kwargs)

    locale = current_locale.get(default_locale)
    return GETTEXT_TRANSLATIONS.get(
        locale, GETTEXT_TRANSLATIONS[default_locale]
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


update_translations()
current_locale = contextvars.ContextVar("i18n")
builtins._ = use_current_gettext

current_locale.set(default_locale)
