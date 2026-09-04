"""Сайттағы Windows .exe нұсқасы.

Docker контекстінде ``core/`` жоқ (.dockerignore), сондықтан сервер
``core.version``-ді импорттамайды. Жергілікті тест
``DESKTOP_VERSION == core.version.__version__`` екенін тексереді.
"""

DESKTOP_VERSION = "0.10.3"
