"""experiments_config — "Жылу құбылыстары" бөлімінің 2 зертхана жұмысы.

kезeng 39B: ``COMPARE_HEAT_QUANTITY_EXPERIMENT`` толық конфигурацияланды
(арна/график/нұсқаулық/бағалау) — электр модуліндегі
``metal-resistance-temperature``-мен бірдей себеппен, ``is_implemented``
ӘЛІ ДЕ ``False``: температура сенсорының firmware-і
(``firmware/temperature_sensor/``) НАҚТЫ hardware-де тексерілмеген
(Voltage/Current Sensor-дың "ВАЛИДТЕЛГЕН КАЛИБРЛЕУ" статусына ие емес).
Physical сынақтан кейін ғана ``True``-ге ауыстырылуы керек.

``ICE_SPECIFIC_HEAT_OF_FUSION_EXPERIMENT`` әлі толық каталогта ғана —
арна/график конфигурациясы жоқ (``required_channels``/
``required_sensor_types`` бос).

2026-07-29 catalog order correction: бұрынғы "Металдардың меншікті жылу
сыйымдылығын анықтау" (№3) authoritative 12-work каталогынан алынып
тасталды (пайдаланушының нақты сұрауы бойынша) — бірақ болашақта қажет
болуы мүмкін болғандықтан анықтамасы (``METAL_SPECIFIC_HEAT_CAPACITY_
EXPERIMENT``) төменде САҚТАЛҒАН, тек ``HEAT_EXPERIMENTS`` tuple-ынан
(яғни ``HeatModule.get_experiments()``-тен) шығарылды және
``display_number=None`` етіп белгіленді.
"""

from domain.entities.experiment_assessment import (
    ExperimentAssessmentDefinition,
    MultipleChoiceQuestion,
    OpenResponseQuestion,
)
from domain.entities.experiment_definition import ExperimentDefinition, ExperimentGuide
from modules.heat.channels import TEMPERATURE_CHANNEL
from modules.heat.experiment_assets import reflection_questions as _reflection_questions

COMPARE_HEAT_QUANTITY_EXPERIMENT = ExperimentDefinition(
    id="compare-heat-quantity",
    title="Температураға әртүрлі бөлінетін жылудың мөлшерін салыстыру",
    description="Қыздыру/салқындату процесінде температураны тіркеу.",
    display_number=1,
    # kезeng 39B: TEMP= парсинг/арна/UI толық дайын, бірақ температура
    # firmware-і (firmware/temperature_sensor/) НАҚТЫ hardware-де әлі
    # тексерілмеген (electricity/metal-resistance-temperature-мен бірдей
    # себеп/статус). Physical сынақтан ӨТКЕНГЕ дейін False қалуы керек.
    is_implemented=False,
    # kезeng 39B: температура сенсоры — Arduino протоколы (docs/serial_
    # protocol.md §4/§10) "TEMP=" кілтін жібереді, PacketParser оны
    # тұрақты "temperature" арнасына сәйкестендіреді (§ TEMPERATURE_
    # CHANNEL электр модуліндегі бірдей аттас арнамен ОРТАҚ протокол
    # кілтін қолданады, бірақ бөлек SensorChannel данасы — модульдер
    # арасында тәуелділік құрмау конвенциясы).
    required_channels=(TEMPERATURE_CHANNEL,),
    # Q = mcΔT есептеу үшін қажет масса (m) мен меншікті жылу сыйымдылығы
    # (c) сенсормен ӨЛШЕНБЕЙДІ (оқушы/мұғалім өзі біледі/өлшейді) —
    # сондықтан derived_channels/formulas ӘДЕЙІ бос: бағдарлама тек
    # T(t) графигін тіркейді, Q-ны оқушы графиктен алынған ΔT-мен өзі
    # есептейді (§ report.conclusion_prompt осыны нақты сұрайды).
    display_channels=("temperature",),
    graph_x_channel=None,  # уақыттық режим — T(t)
    graph_x_label="Уақыт, t",
    graph_y_channels=("temperature",),
    graph_title="Температураның уақыт бойынша өзгерісі",
    graph_y_label="Температура, T",
    required_sensor_types=("TEMPERATURE",),
    guide=ExperimentGuide(
        objective=(
            "қыздыру/салқындату процесінде дене температурасының уақыт "
            "бойынша өзгерісін бақылау;",
            "температура-уақыт графигінің көлбеуін (қызу/салқындау "
            "жылдамдығын) әртүрлі жағдайлар үшін салыстыру;",
            "бөлінетін/сіңірілетін жылу мөлшерін (Q = mcΔT) есептеу үшін "
            "қажетті ΔT мәнін графиктен анықтау.",
        ),
        equipment=(
            "Arduino Nano/Uno + DS18B20 температура сенсоры",
            "Ыдыс (су/зерттелетін дене үшін)",
            "Қыздырғыш немесе жылу көзі (мыс., ыстық су, спирт шамы — "
            "мектеп қауіпсіздік ережесіне сай)",
            "Секундомер (Arduino-дың өзі уақытты автоматты тіркейді)",
        ),
        theory=(
            "Дене температурасы оған берілген/одан алынған жылу мөлшеріне "
            "тәуелді өзгереді: Q = mcΔT, мұндағы m — масса, c — меншікті "
            "жылу сыйымдылығы, ΔT — температура өзгерісі. Бірдей жылу "
            "көзінде әртүрлі масса/зат үшін температура әртүрлі "
            "жылдамдықпен өзгереді — температура-уақыт графигінің "
            "көлбеуі осы айырмашылықты көрнекі көрсетеді. Бағдарлама "
            "температураны нақты уақытта өлшеп графикке салады, ал m/c "
            "белгілі болса, оқушы Q-ны графиктен алынған ΔT арқылы "
            "қолмен есептейді."
        ),
        formulas=("Q = m·c·ΔT",),
        procedure=(
            "Температура сенсорын (DS18B20) зерттелетін ортаға (су/дене "
            "ішіне) орналастырыңыз.",
            "Температура датчигін тиісті COM-портта «Анықтау» арқылы "
            "қосыңыз.",
            "«Бастау» батырмасын басып, бастапқы температураны жазып "
            "алыңыз.",
            "Қыздыру/салқындату процесін бастаңыз, температураның уақыт "
            "бойынша өзгерісін графиктен бақылаңыз.",
            "Процесс аяқталғанда (немесе жеткілікті деректер жиналғанда) "
            "«Тоқтату» басыңыз.",
            "Графиктен бастапқы/соңғы температураны (ΔT) анықтап, белгілі "
            "m мен c арқылы Q = mcΔT есептеңіз.",
        ),
        safety=(
            "Ыстық су/жылу көзімен жұмыс істегенде абайлаңыз, тікелей "
            "қолмен ұстамаңыз.",
            "Электр қыздырғыш қолдансаңыз, суға түсіп кетпеуін қадағалаңыз.",
        ),
        control_questions=(
            "Температура-уақыт графигінің көлбеуі неге байланысты?",
            "Бірдей жылу мөлшерінде үлкен масса неге баяу қызады?",
        ),
    ),
    assessment=ExperimentAssessmentDefinition(
        level1_questions=(
            MultipleChoiceQuestion(
                id="chq-l1-1",
                prompt="Бұл тәжірибеде негізгі қандай физикалық шама тікелей өлшенеді?",
                options=("Масса", "Температура", "Қысым", "Кернеу"),
                correct_option_index=1,
            ),
            MultipleChoiceQuestion(
                id="chq-l1-2",
                prompt="Температура сенсоры (DS18B20) Arduino-мен қандай интерфейс арқылы жалғанады?",
                options=("I2C (екі сым)", "1-Wire (бір сым)", "SPI", "Bluetooth"),
                correct_option_index=1,
            ),
            MultipleChoiceQuestion(
                id="chq-l1-3",
                prompt="Бөлінген/сіңірілген жылу мөлшерін есептейтін формула қайсы?",
                options=("Q = mcΔT", "P = UI", "R = U/I", "F = ma"),
                correct_option_index=0,
            ),
        ),
        level2_questions=(
            OpenResponseQuestion(
                id="chq-l2-1",
                prompt="Температура-уақыт графигінің көлбеуі (наклоны) не туралы айтады?",
            ),
            OpenResponseQuestion(
                id="chq-l2-2",
                prompt=(
                    "Бірдей қуат көзімен әртүрлі массадағы суды қыздырғанда "
                    "неге температура әртүрлі жылдамдықпен өседі?"
                ),
            ),
            OpenResponseQuestion(
                id="chq-l2-3",
                prompt="Q = mcΔT есептеу үшін график деректерінен қандай шаманы (ΔT) қалай анықтайсыз?",
            ),
        ),
        level3_questions=_reflection_questions("chq"),
    ),
)

ICE_SPECIFIC_HEAT_OF_FUSION_EXPERIMENT = ExperimentDefinition(
    id="ice-specific-heat-of-fusion",
    title="Мұздың меншікті балқу жылуын анықтау",
    description="Балқу процесіндегі температура өзгерісін бақылау.",
    display_number=2,
    is_implemented=False,
)

# ЕСКЕРТУ: authoritative 12-work каталогта ЖОҚ (жоғарыдағы docstring-ті
# қараңыз) — ``HEAT_EXPERIMENTS``-те қасақана жоқ, ``display_number=None``.
METAL_SPECIFIC_HEAT_CAPACITY_EXPERIMENT = ExperimentDefinition(
    id="metal-specific-heat-capacity",
    title="Металдардың меншікті жылу сыйымдылығын анықтау",
    description=(
        "Металл үлгінің жылу алмасуын зерттеу және оның меншікті жылу "
        "сыйымдылығын анықтау."
    ),
    display_number=None,
    is_implemented=False,
)

HEAT_EXPERIMENTS: tuple[ExperimentDefinition, ...] = (
    COMPARE_HEAT_QUANTITY_EXPERIMENT,
    ICE_SPECIFIC_HEAT_OF_FUSION_EXPERIMENT,
)
