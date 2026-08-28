"""Электр тәжірибелерінің ортақ схема/жабдық/қауіпсіздік мәтіндері.

``experiments_config`` осы константаларды ``_`` префиксімен қайта
атап қолданады — тәжірибе анықтамаларының мәтіні өзгермейді.
"""

from core.resource_paths import resource_path
from domain.entities.experiment_assessment import ReflectionQuestion

# Phase 36.1 / 36.1 follow-up: пайдаланушы дайындаған, Fritzing-тәрізді
# қосылым суреттері — ЕШҚАШАН кодта қайта салынбайды, тек дайын файл
# жолдары. ``resource_path`` пакеттелген .exe ішінде де каталогты табады.
#
# "Электр тізбегін құрастыру және ток күшін өлшеу" МЕН "Электр тогының
# жұмысы мен қуатын анықтау" — дәл СОЛ бір файлды пайдаланады (нақты
# бірдей физикалық құрылым: 2 сенсор + 1 резистор breadboard-та).
# "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу" — ӨЗ
# файлы (``ohms_law_wiring.png``), бірақ пайдаланушы растағандай, сурет
# мазмұны әдейі СОЛ бір тізбекті бейнелейді (сол физикалық құрылым).
# Тізбектей/параллель қосуды зерттеу — екеуі де ӨЗ, БАСҚА тізбек
# топологиясын (бірнеше резистор) көрсететін суреттер.
_ASSETS_DIR = resource_path("ui", "resources", "images")
CURRENT_VOLTAGE_WIRING_PATH = str(_ASSETS_DIR / "current_voltage_wiring.png")
OHMS_LAW_WIRING_PATH = str(_ASSETS_DIR / "ohms_law_wiring.png")
SERIES_CONNECTION_WIRING_PATH = str(_ASSETS_DIR / "series_connection_wiring.png")
PARALLEL_CONNECTION_WIRING_PATH = str(_ASSETS_DIR / "parallel_connection_wiring.png")
WIRING_DIAGRAM_CAPTION = (
    "Суреттегі сымдарды көрсетілген ретпен жалғаңыз. Қызыл сым — оң полюс, "
    "қара сым — теріс полюс."
)

# Phase 35: барлық электр тәжірибесі бірдей 2 физикалық сенсормен (Voltage
# Sensor, Current Sensor — әрқайсысы жеке Arduino Nano/Uno + INA226 I2C
# breakout, 0x40 мекенжай) жұмыс істейді (docs/hardware_test_guide.md §1) —
# нұсқаулықтардағы жабдық тізімі осы НАҚТЫ конфигурацияға сай, ойдан
# шығарылған сенсор/аспап ЖОҚ (мыс. Омметр әлі іске асырылмаған).
SENSOR_EQUIPMENT = (
    "Кернеу датчигі (Arduino Nano/Uno + INA226 модулі)",
    "Ток датчигі (Arduino Nano/Uno + INA226 модулі)",
    "2× USB кабелі (әр Arduino — жеке компьютерге)",
    "Дербес компьютер (Arduino Physics Lab бағдарламасы орнатылған)",
    "Қосылым сымдары",
)
BASIC_SAFETY = (
    "Тізбекті жинамас бұрын барлық қосылымдарды мұқият тексеріңіз.",
    "Датчиктердің рұқсат етілген шегінен (кернеу/ток) асырмаңыз.",
    "Қосылған тізбекке ылғал қолмен тимеңіз.",
    "Тәжірибе аяқталғаннан кейін қоректендіруді өшіріп, құрылғыларды ретімен ажыратыңыз.",
)

REQUIRED_SENSOR_TYPES = ("VOLTAGE", "CURRENT")


def reflection_questions(id_prefix: str) -> tuple[ReflectionQuestion, ...]:
    """3-деңгей (Рефлексия) сұрақтары барлық тәжірибеде мағыналық түрде бірдей."""
    return (
        ReflectionQuestion(id=f"{id_prefix}-l3-1", prompt="Бүгінгі тәжірибеде не үйрендіңіз?"),
        ReflectionQuestion(id=f"{id_prefix}-l3-2", prompt="Қандай қиындық кездесті?"),
        ReflectionQuestion(id=f"{id_prefix}-l3-3", prompt="Тәжірибенің қай бөлімі ең қызықты болды?"),
    )
