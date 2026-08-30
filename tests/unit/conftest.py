"""``tests/unit`` пакетіне ортақ pytest fixture-лары.

Phase 33A-да табылды: LiveGraphWidget графикалық интерактивтілігі
(crosshair, latest-marker, extra toolbar батырмалары) көп ``pg.PlotWidget``
даналарын жиі reconfigure/жою (``deleteLater()``) арқылы жасайды. Бір
файлда ондаған тест бір-бірінен кейін орындалғанда, ``deleteLater()``
арқылы жоспарланған нақты C++ жою ЕШҚАШАН орындалмайды (Qt event loop
тесттер арасында ешқашан pump етілмейді) — деректер жинақталып, session
соңында (interpreter/QApplication teardown) Windows heap corruption
(``0xc0000374``) тудыратыны эмпирикалық түрде табылды.

Бұл fixture әр тесттен кейін ``QApplication.topLevelWidgets()``
тізіміндегі әр parentless виджетті (мыс. ``page = SomePage(...)`` парентсіз
жасалатын тест паттерні — ``test_experiment_workspace_page.py`` секілді
файлдарда әр тест жеке ``ExperimentWorkspacePage``→``MeasurementWorkspace``→
``LiveGraphWidget``→ ``pg.PlotWidget`` тізбегін парентсіз жасайды) айқын
``close()`` + ``deleteLater()`` арқылы белгілейді, содан соң
``processEvents()`` екі рет шақырылады.

ЭМПИРИКАЛЫҚ ТАБЫЛҒАН, МАҢЫЗДЫ ЕСКЕРТУ: ``sendPostedEvents(None,
QEvent.DeferredDelete)`` арқылы C++ жойылуды МӘЖБҮРЛЕП дереу орындату
(processEvents()-ті жай бірнеше рет шақырудың орнына) — КӨМЕКТЕСПЕЙДІ,
керісінше ``test_experiment_workspace_page.py``-ды 202-нің 1-ші тестінде-ақ
құлатты (``Fatal Python error: Aborted``, бұрын ~96-шы тестте шыққан
``0xc0000374``-тің орнына). Демек, deferred-delete кезегін мәжбүрлеп
"тездету" pyqtgraph/GL виджеттерінің жойылу тәртібін бұзып, use-after-free
тудырады — сондықтан бұл жерде ЕШҚАШАН қолданылмайды. ``close()`` +
``deleteLater()`` + қарапайым ``processEvents()`` (Qt-тің өз event loop
кезегімен, мәжбүрлеусіз) ғана — 202/202 тест тұрақты өтеді (қайталап
тексерілді).
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
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication


@pytest.fixture(autouse=True)
def _flush_qt_deferred_deletes():
    yield
    app = QCoreApplication.instance()
    if app is not None:
        # topLevelWidgets() тек QApplication-да бар (QCoreApplication-да
        # жоқ) — кейбір таза QObject/Signal тесттері (мыс.
        # test_device_identifier.py) виджетсіз QCoreApplication қана
        # жасайды, сол сессияда QApplication ешқашан құрылмауы мүмкін.
        if isinstance(app, QApplication):
            # QApplication-ды өзін емес, parentless QWidget-терді
            # қайтарады. close() closeEvent-терді шақырады (жоба ішінде
            # модалды диалог ашатын closeEvent жоқ — тексерілді),
            # deleteLater() C++ жойылуды Qt-тің ӨЗ кезегімен жоспарлайды.
            for widget in list(app.topLevelWidgets()):
                widget.close()
                widget.deleteLater()
        app.processEvents()
        app.processEvents()
    gc.collect()
