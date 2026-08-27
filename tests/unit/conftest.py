"""``tests/unit`` пакетіне ортақ pytest fixture-лары.

Phase 33A-да табылды: LiveGraphWidget графикалық интерактивтілігі
(crosshair, latest-marker, extra toolbar батырмалары) көп ``pg.PlotWidget``
даналарын жиі reconfigure/жою (``deleteLater()``) арқылы жасайды. Бір
файлда ондаған тест бір-бірінен кейін орындалғанда, ``deleteLater()``
арқылы жоспарланған нақты C++ жою ЕШҚАШАН орындалмайды (Qt event loop
тесттер арасында ешқашан pump етілмейді) — деректер жинақталып, session
соңында (interpreter/QApplication teardown) Windows heap corruption
(``0xc0000374``) тудыратыны эмпирикалық түрде табылды. Бұл fixture әр
тесттен кейін ``processEvents()`` шақырып, жоспарланған жоюларды
уақытылы орындатады — Qt/pyqtgraph-негізді GUI тесттерінде кең тараған,
стандартты митигация.
"""

import gc
import os

# QApplication нақты ("windows") платформамен жасалса, top-level widget-тің
# resize()-і host машинаның НАҚТЫ экран өлшемімен клампталады (Qt/Windows
# window manager) — resize(2560, 1440) физикалық экраны 1536×864 болатын
# машинада НЕШЕ РЕТ processEvents() шақырса да ешқашан толық орындалмайды
# (settle/timing мәселесі ЕМЕС, тұрақты клампталу). `setdefault` қолданылады
# — screenshot скрипттері (нақты рендеринг үшін) QT_QPA_PLATFORM=windows-ды
# өздері нақты орнатса, бұл жерде үстінен жазылмайды.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(autouse=True)
def _flush_qt_deferred_deletes():
    yield
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
        app.processEvents()
    gc.collect()
