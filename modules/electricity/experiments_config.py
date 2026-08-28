"""experiments_config — "Тұрақты электр тогы" бөлімінің 6 зертхана
жұмысының (1 жоспарланған + 5 іске асырылған: электр тізбегін
құрастыру және ток күшін өлшеу, тізбек бөлігі үшін кернеудің ток
күшіне тәуелділігін зерттеу, тізбектей/параллель қосуды зерттеу,
электр тогының жұмысы мен қуатын анықтау — 8-сынып жаңа оқу
бағдарламасына сай атаулар) ExperimentDefinition конфигурациялары.

Барлық жұмыс бірдей екі негізгі арнаны (voltage, current) қолданады —
Arduino протоколы (``docs/serial_protocol.md``) осыдан артық шама
жібермейді. Жұмыстар бір-бірінен тек derived_channels/formulas/graph_*
баптаулары бойынша ажыратылады. Туынды шамаларды ``CalculationEngine``
есептейді (resistance, power, work), ``formulas`` мәні тек пайдаланушыға
көрсетілетін формула мәтіні — есептеуге қатыспайды.

Нақты hardware құрылымында voltage/current — екі БӨЛЕК физикалық
құрылғыдан (Voltage Sensor, Current Sensor — әрқайсысы жеке Arduino/
COM-порт) келеді, сондықтан барлық 5 жұмыс ``required_sensor_types``
арқылы екі сенсордың бірге қосылуын талап етеді.
``MultiSensorExperimentCoordinator`` + ``ChannelAggregator`` осы екі
портты бір толық Measurement-ке біріктіреді (audit: multi-device
architecture, кодтауға дейінгі растау), сондықтан ``current`` қайтадан
``required=True`` — DataValidator аяқталған (aggregated) жиынтықты
алады, партиалды пакетті ешқашан көрмейді.
"""

from domain.entities.experiment_assessment import (
    ExperimentAssessmentDefinition,
    MultipleChoiceQuestion,
    OpenResponseQuestion,
)
from domain.entities.experiment_definition import (
    ExperimentDefinition,
    ExperimentDiagram,
    ExperimentGuide,
    ExperimentReport,
)
from domain.services.graph_analysis import DERIVED_ANALYSIS_POWER_ENERGY
from modules.electricity.channels import (
    CURRENT_CHANNEL,
    POWER_CHANNEL,
    RESISTANCE_CHANNEL,
    TEMPERATURE_CHANNEL,
    TIME_CHANNEL,
    VOLTAGE_CHANNEL,
    WORK_CHANNEL,
)
from modules.electricity.experiment_assets import (
    BASIC_SAFETY as _BASIC_SAFETY,
    CURRENT_VOLTAGE_WIRING_PATH as _CURRENT_VOLTAGE_WIRING_PATH,
    OHMS_LAW_WIRING_PATH as _OHMS_LAW_WIRING_PATH,
    PARALLEL_CONNECTION_WIRING_PATH as _PARALLEL_CONNECTION_WIRING_PATH,
    REQUIRED_SENSOR_TYPES as _REQUIRED_SENSOR_TYPES,
    SENSOR_EQUIPMENT as _SENSOR_EQUIPMENT,
    SERIES_CONNECTION_WIRING_PATH as _SERIES_CONNECTION_WIRING_PATH,
    WIRING_DIAGRAM_CAPTION as _WIRING_DIAGRAM_CAPTION,
    reflection_questions as _reflection_questions,
)

# Арна/схема/жабдық константалары ``channels.py`` мен ``experiment_assets.py``-де.
# 8-сынып жаңа оқу бағдарламасы (curriculum rename): бұл тәжірибе ЕНДІ
# №3 куррикулум атауын алады — бұрын осы атау/нөмір тек каталогтық
# placeholder-де (CIRCUIT_CURRENT_MEASUREMENT_EXPERIMENT, is_implemented=
# False) резервте тұратын, нақты pipeline осы CURRENT_VOLTAGE_EXPERIMENT-
# те болатын. Placeholder ЕНДІ артық (дубликат атау/нөмір болдырмау
# үшін алынып тасталды) — функционалдық (сенсорлар/график/өлшеу/есеп/
# диаграмма) МҮЛДЕ өзгермеді, тек атауы/дисплей нөмірі/мақсаты.
_CURRENT_VOLTAGE_ASSESSMENT = ExperimentAssessmentDefinition(
    level1_questions=(
        MultipleChoiceQuestion(
            id="cv-l1-1",
            prompt="Ток күші қандай өлшем бірлікпен өлшенеді?",
            options=("Вольт", "Ампер", "Ом", "Ватт"),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="cv-l1-2",
            prompt="Ток өлшегіш құрылғы (амперметр/ток датчигі) тізбекке қалай қосылады?",
            options=("Тізбектей", "Параллель", "Кез келген ретпен", "Тек батареяға тікелей"),
            correct_option_index=0,
        ),
        MultipleChoiceQuestion(
            id="cv-l1-3",
            prompt="Тізбек ашық (үзік) болса, тізбекте не болады?",
            options=("Ток күшейеді", "Ток өтпейді", "Кернеу артады", "Кедергі кемиді"),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="cv-l1-4",
            prompt="Электр тізбегінің негізгі элементтеріне не жатпайды?",
            options=("Қорек көзі", "Өткізгіш сымдар", "Тұтынушы (жүктеме)", "Магнит өрісі"),
            correct_option_index=3,
        ),
        MultipleChoiceQuestion(
            id="cv-l1-5",
            prompt="Тізбекті құрастырудың қауіпсіз тәртібі қандай?",
            options=(
                "Қосылымдарды тексермей іске қосу керек",
                "Барлық қосылымдарды алдын ала мұқият тексеру керек",
                "Датчиктің рұқсат етілген шегінен әдейі асыру керек",
                "Ток жүріп тұрған кезде сымдарды ауыстыру керек",
            ),
            correct_option_index=1,
        ),
    ),
    level2_questions=(
        OpenResponseQuestion(
            id="cv-l2-1", prompt="Ток күші уақыт бойынша қалай өзгерді? Графиктен не байқадыңыз?"
        ),
        OpenResponseQuestion(
            id="cv-l2-2", prompt="Тізбекті құрастыру барысында қандай қиындықтар кездесті?"
        ),
        OpenResponseQuestion(
            id="cv-l2-3",
            prompt="Ток күшінің тұрақты болуы (немесе болмауы) физикалық тұрғыда нені білдіреді?",
        ),
    ),
    level3_questions=_reflection_questions("cv"),
)

CURRENT_VOLTAGE_EXPERIMENT = ExperimentDefinition(
    id="current-voltage",
    title="Электр тізбегін құрастыру және ток күшін өлшеу",
    description=(
        "Электр тізбегін дұрыс құрастырып, ондағы ток күші мен кернеуді "
        "бір уақытта өлшеу және олардың уақыт бойынша өзгерісін бақылау."
    ),
    display_number=3,
    required_channels=(VOLTAGE_CHANNEL, CURRENT_CHANNEL),
    derived_channels=(POWER_CHANNEL,),
    # Негізгі шамалар — U, I. Қуат (P=U×I) қосымша, әдепкі бойынша жасырын
    # (readout/table-де toggle арқылы көрсетіледі), resistance/fit/scatter
    # бұл тәжірибеге мүлде қатысы жоқ (ол — Ohm's Law-дың жұмысы).
    display_channels=("voltage", "current"),
    optional_display_channels=("power",),
    optional_display_show_label="Қуатты көрсету",
    optional_display_hide_label="Қуатты жасыру",
    # Time-series: U(t)/I(t) екі бөлек, синхрондалған X (уақыт) осімен
    # stacked график — әртүрлі бірлік/диапазонды бір Y scale-ге қыспау үшін.
    graph_x_channel=None,
    graph_x_label="Уақыт, t",
    graph_y_channels=("voltage", "current"),
    graph_stacked=True,
    graph_stacked_titles={
        "voltage": "Кернеудің уақыт бойынша өзгерісі",
        "current": "Ток күшінің уақыт бойынша өзгерісі",
    },
    graph_stacked_y_labels={"voltage": "Кернеу, U", "current": "Ток күші, I"},
    formulas={"power": "P = U × I"},
    required_sensor_types=_REQUIRED_SENSOR_TYPES,
    # Phase 34 §13: A/B екі нүктелік Δ өлшеу (уақыт бойынша синхрондалған
    # cursor-лар U(t)/I(t) екі subplot-та). rate-of-change (dU/dt, dI/dt)
    # әдейі қосылмаған — спецификацияда тек A/B талап етілген.
    graph_allow_delta_measurement=True,
    guide=ExperimentGuide(
        objective=(
            "электр тізбегін дұрыс құрастыру дағдысын қалыптастыру;",
            "ток күші мен кернеудің уақыт бойынша бір мезгілде өзгерісін бақылау;",
            "екі шаманың арасындағы байланысты тәжірибе жүзінде қадағалау;",
            "қажет болса, тұтынылатын қуатты (P = U × I) есептеу.",
        ),
        equipment=_SENSOR_EQUIPMENT + ("Зерттелетін тізбек (жүктеме)",),
        theory=(
            "Бұл тәжірибеде кернеу U(t) және ток күші I(t) бір мезгілде, "
            "нақты уақыт режимінде екі бөлек графикте (бір-біріне синхрондалған "
            "уақыт осімен) тіркеледі. Мұнда сызықтық аппроксимация/кедергі "
            "есептелмейді — ол «Тізбек бөлігі үшін кернеудің ток күшіне "
            "тәуелділігін зерттеу» жұмысының міндеті. Қажет болса, "
            "қосымша «Қуатты көрсету» батырмасы арқылы лездік қуат P = U × I "
            "мәнін де көруге болады."
        ),
        formulas=("P = U × I",),
        procedure=(
            "Кернеу және ток датчиктерін тиісті COM-порттарда «Анықтау» арқылы қосыңыз.",
            "Екі құрылғының да дайын («2 / 2 құрылғы») екенін тексеріңіз.",
            "«Бастау» батырмасын басыңыз.",
            "U(t) және I(t) графиктерінің нақты уақытта салынуын бақылаңыз.",
            "Қажет болса, «Қуатты көрсету» батырмасымен P(t) мәнін қосыңыз.",
            "Екі уақыт нүктесін салыстыру үшін A⟷B құралын қолданыңыз.",
            "Өлшеуді аяқтағанда «Тоқтату» басып, нәтижені экспорттаңыз.",
        ),
        safety=_BASIC_SAFETY,
        control_questions=(
            "Кернеу мен ток уақыт бойынша қалай өзгереді?",
            "Электр қуаты қалай есептеледі және қандай бірлікпен өлшенеді?",
            "U(t) және I(t) графиктерінің арасында қандай байланыс байқалады?",
        ),
    ),
    # Phase 36: зертханалық есеп — мазмұны (мақсат/жабдық guide-тен
    # қайта пайдаланылады, статистика/график/есептелген шамалар
    # сессиядан ӘР РЕТ жаңадан есептеледі), әдепкі баптау жеткілікті.
    report=ExperimentReport(),
    # Phase 36.1: НАҚТЫ қосылым суреті — осы тәжірибенің физикалық
    # құрылымы (2 сенсор + 1 резистор breadboard-та) диаграммамен дәл
    # сәйкес келеді.
    diagram=ExperimentDiagram(
        image_path=_CURRENT_VOLTAGE_WIRING_PATH, caption=_WIRING_DIAGRAM_CAPTION
    ),
    assessment=_CURRENT_VOLTAGE_ASSESSMENT,
)

_OHMS_LAW_ASSESSMENT = ExperimentAssessmentDefinition(
    level1_questions=(
        MultipleChoiceQuestion(
            id="ol-l1-1",
            prompt="Ом заңы бойынша кернеу мен ток күшінің арасындағы байланыс қандай?",
            options=("U = I / R", "U = I × R", "U = R / I", "U ток күшіне тәуелсіз"),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="ol-l1-2",
            prompt="Электр кедергісі қандай өлшем бірлікпен өлшенеді?",
            options=("Ампер", "Вольт", "Ом", "Ватт"),
            correct_option_index=2,
        ),
        MultipleChoiceQuestion(
            id="ol-l1-3",
            prompt="U(I) графигіндегі түзу сызықтың көлбеулігі (slope) нені білдіреді?",
            options=("Қуатты", "Кедергіні", "Уақытты", "Жиілікті"),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="ol-l1-4",
            prompt="U мен I арасындағы тәуелділік СЫЗЫҚТЫҚ болса, бұл нені білдіреді?",
            options=(
                "U мен I бір-біріне тура пропорционал",
                "U мен I бір-біріне кері пропорционал",
                "U тұрақты, I өзгереді",
                "I тұрақты, U өзгереді",
            ),
            correct_option_index=0,
        ),
        MultipleChoiceQuestion(
            id="ol-l1-5",
            prompt="Сызықтық аппроксимацияның R² мәні 1-ге жақын болса, бұл нені көрсетеді?",
            options=(
                "Өлшеу қатесі өте көп",
                "Нүктелер түзу сызыққа жақсы сәйкес келеді",
                "Кедергі тұрақсыз",
                "Тәжірибе сәтсіз аяқталды",
            ),
            correct_option_index=1,
        ),
    ),
    level2_questions=(
        OpenResponseQuestion(id="ol-l2-1", prompt="U(I) графигінен қандай заңдылық байқадыңыз?"),
        OpenResponseQuestion(
            id="ol-l2-2", prompt="Тәжірибелік график неліктен идеал түзу болмауы мүмкін?"
        ),
        OpenResponseQuestion(
            id="ol-l2-3", prompt="Кедергі өлшеу барысында тұрақты болды ма? Түсіндіріңіз."
        ),
        OpenResponseQuestion(
            id="ol-l2-4", prompt="Нәтиже Ом заңымен сәйкес келе ме? Неліктен?"
        ),
    ),
    level3_questions=_reflection_questions("ol"),
)

OHMS_LAW_EXPERIMENT = ExperimentDefinition(
    id="ohms-law",
    title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
    description=(
        "Тізбек бөлігіндегі кернеудің ток күшіне тәуелділігін тәжірибе "
        "арқылы зерттеу және өткізгіш кедергісін анықтау."
    ),
    display_number=4,
    required_channels=(VOLTAGE_CHANNEL, CURRENT_CHANNEL),
    derived_channels=(RESISTANCE_CHANNEL,),
    graph_x_channel="current",
    graph_y_channels=("voltage",),
    formulas={"resistance": "R = U / I"},
    required_sensor_types=_REQUIRED_SENSOR_TYPES,
    # Vernier Graphical Analysis тәрізді scatter+linear fit график: нүктелер
    # қосылмайды (тек scatter), R=slope есептеп fit сызығы көрсетіледі.
    graph_connect_points=False,
    graph_show_fit=True,
    graph_title="Кернеудің ток күшіне тәуелділігі",
    graph_x_label="Ток, I",
    graph_y_label="Кернеу, U",
    # VOLTAGE_CHANNEL/CURRENT_CHANNEL decimals=3-ке сай: least-count-тың жартысы —
    # тек сол дәлдіктегі "бірдей" қайталанған нүктелерді graph-та дублдемеу үшін.
    graph_dedup_x_tolerance=0.0005,
    graph_dedup_y_tolerance=0.0005,
    graph_fit_result_prefix="R",
    graph_fit_unit="Ω",
    # Manual point capture (V2): 10Hz raw ағын графикке автоматты түспейді —
    # пайдаланушы "Нүктені сақтау" басқанда, соңғы 10 үлгінің тұрақты
    # (voltage spread<=0.02V, current spread<=0.002A) орташасынан бір нүкте
    # алынады. Transient/шулы аралық мәндер fit-ке ешқашан кірмейді.
    graph_capture_mode="manual",
    graph_capture_sample_count=10,
    graph_capture_x_tolerance=0.002,
    graph_capture_y_tolerance=0.02,
    graph_fit_x_symbol="I",
    graph_fit_y_symbol="U",
    graph_fit_display_name="Кедергі",
    # Phase 34 §12: A/B Δ өлшеу (мыс. таңдалған екі captured нүкте
    # арасындағы ΔU/ΔI) + residual toggle (graph_show_fit=True болғандықтан
    # автоматты қолжетімді, қосымша конфигурация қажет емес).
    graph_allow_delta_measurement=True,
    guide=ExperimentGuide(
        objective=(
            "ток күші мен кернеу арасындағы тәуелділікті тәжірибе жүзінде зерттеу;",
            "өткізгіш кедергісін анықтау;",
            "тізбек бөлігіндегі кернеу мен ток арасындағы тәуелділікті эксперименттік түрде тексеру.",
        ),
        equipment=_SENSOR_EQUIPMENT + ("Кедергісі анықталатын өткізгіш (резистор)",),
        theory=(
            "Кедергісі тұрақты өткізгіш үшін ток күші кернеуге тура пропорционал: "
            "кернеу қанша есе артса, ток күші де сонша есе артады. Осы "
            "тәуелділікті сипаттайтын коэффициент — өткізгіштің электр "
            "кедергісі R. Бағдарламадағы U(I) графигінде түзу сызықтың "
            "көлбеулігі (slope) дәл осы кедергіге тең: R = ΔU / ΔI."
        ),
        formulas=("U = I × R", "R = U / I", "R = ΔU / ΔI"),
        procedure=(
            "Кернеу және ток датчиктерін тиісті COM-порттарда «Анықтау» арқылы қосыңыз.",
            "Екі құрылғының да дайын («2 / 2 құрылғы») екенін тексеріңіз.",
            "«Бастау» батырмасын басыңыз.",
            "Тізбектегі ток/кернеуді өзгертіп, көрсеткіштің тұрақтануын күтіңіз.",
            "Мән тұрақталған сәтте «+ Нүктені сақтау» батырмасын басыңыз.",
            "Осы қадамды кемінде 5-7 әртүрлі мән үшін қайталаңыз.",
            "U(I) графигіндегі сызықтық аппроксимация (fit) нәтижесін — R мен R² мәнін оқыңыз.",
            "Қажет болса, A⟷B құралымен екі нүкте арасындағы ΔU/ΔI қатынасын тексеріңіз.",
            "Өлшеуді аяқтағанда «Тоқтату» басып, алынған R мәні бойынша қорытынды жасаңыз.",
        ),
        safety=_BASIC_SAFETY,
        control_questions=(
            "Тұрақты кедергілі өткізгіш үшін кернеу мен ток арасындағы тәуелділік қалай тұжырымдалады?",
            "Ток күші кернеуге қалай тәуелді?",
            "Өткізгіштің кедергісі қандай физикалық шамаларға байланысты?",
            "U(I) графигінің көлбеулігі қандай физикалық шаманы сипаттайды?",
        ),
    ),
    report=ExperimentReport(),
    # Phase 36.1 follow-up: осы тәжірибе ӨЗ файлын пайдаланады
    # (``ohms_law_wiring.png``) — пайдаланушы растағандай, мазмұны
    # Электр тізбегін құрастыру және ток күшін өлшеу жұмысының суретімен
    # әдейі БІРДЕЙ (дәл сол физикалық құрылым), бірақ бөлек файл ретінде
    # сақталған.
    diagram=ExperimentDiagram(
        image_path=_OHMS_LAW_WIRING_PATH, caption=_WIRING_DIAGRAM_CAPTION
    ),
    assessment=_OHMS_LAW_ASSESSMENT,
)

_SERIES_CONNECTION_ASSESSMENT = ExperimentAssessmentDefinition(
    level1_questions=(
        MultipleChoiceQuestion(
            id="sc-l1-1",
            prompt="Тізбектей қосылған өткізгіштердегі ток күші қандай?",
            options=("Әр өткізгіште әртүрлі", "Барлық жерде бірдей", "Тек біреуінде бар", "Нөлге тең"),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="sc-l1-2",
            prompt="Тізбектей қосылған екі өткізгіштің жалпы кедергісі қалай есептеледі?",
            options=("R = R₁ + R₂", "R = R₁ × R₂", "1/R = 1/R₁ + 1/R₂", "R = R₁ − R₂"),
            correct_option_index=0,
        ),
        MultipleChoiceQuestion(
            id="sc-l1-3",
            prompt="Тізбектей қосылған тізбектің бір жерінен үзілсе, не болады?",
            options=(
                "Тек сол бөлік істемей қалады",
                "Бүкіл тізбектегі ток тоқтайды",
                "Ток күшейеді",
                "Ешнәрсе өзгермейді",
            ),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="sc-l1-4",
            prompt="Тізбектей қосылған өткізгіштердегі жалпы кернеу неге тең?",
            options=(
                "Әр өткізгіштегі кернеулердің қосындысына",
                "Ең үлкен кернеуге",
                "Ең кіші кернеуге",
                "Нөлге",
            ),
            correct_option_index=0,
        ),
        MultipleChoiceQuestion(
            id="sc-l1-5",
            prompt="Тізбектей қосылған өткізгіш санын арттырса, жалпы кедергі қалай өзгереді?",
            options=("Кемиді", "Артады", "Өзгермейді", "Нөлге тең болады"),
            correct_option_index=1,
        ),
    ),
    level2_questions=(
        OpenResponseQuestion(
            id="sc-l2-1", prompt="Тәжірибе нәтижесі бойынша жалпы кедергі қалай өзгерді?"
        ),
        OpenResponseQuestion(
            id="sc-l2-2",
            prompt="Ток күшінің тізбектің әр нүктесінде бірдей болғанын қалай тексердіңіз?",
        ),
        OpenResponseQuestion(
            id="sc-l2-3", prompt="Нәтиже теориямен (R = R₁ + R₂) сәйкес келе ме? Неліктен?"
        ),
    ),
    level3_questions=_reflection_questions("sc"),
)

SERIES_CONNECTION_EXPERIMENT = ExperimentDefinition(
    id="series-connection",
    title="Өткізгіштерді тізбектей қосуды зерттеу",
    description="Тізбектей жалғанған өткізгіштердегі ток пен кернеуді, "
    "жалпы кедергі мен қуатты зерттеу.",
    display_number=5,
    required_channels=(VOLTAGE_CHANNEL, CURRENT_CHANNEL),
    derived_channels=(RESISTANCE_CHANNEL, POWER_CHANNEL),
    graph_x_channel="voltage",
    graph_y_channels=("current",),
    formulas={"resistance": "R = U / I", "power": "P = U × I"},
    required_sensor_types=_REQUIRED_SENSOR_TYPES,
    guide=ExperimentGuide(
        objective=(
            "өткізгіштерді тізбектей жалғау тәсілін тәжірибе жүзінде меңгеру;",
            "тізбектей қосылған бөлікте ток күшінің бірдей болатынын тексеру;",
            "жалпы кедергі мен тұтынылатын қуатты анықтау.",
        ),
        equipment=_SENSOR_EQUIPMENT
        + ("Тізбектей жалғанатын өткізгіштер (кемінде 2 резистор)",),
        theory=(
            "Өткізгіштер тізбектей жалғанғанда, олардың бәрінен БІРДЕЙ ток "
            "күші өтеді (I = I₁ = I₂ = ...), ал жалпы кернеу әр өткізгіштегі "
            "кернеулердің қосындысына тең (U = U₁ + U₂ + ...). Осыдан "
            "тізбектің жалпы кедергісі әр өткізгіш кедергісінің қосындысына "
            "тең болады: R_жалпы = R₁ + R₂ + ... . Бағдарлама датчиктер "
            "арқылы тізбектің ЖАЛПЫ кернеуі мен тогын өлшеп, осы R_жалпы "
            "мен тұтынылатын қуатты (P = U × I) автоматты есептейді."
        ),
        formulas=("R_жалпы = R₁ + R₂ + ...", "R = U / I", "P = U × I"),
        procedure=(
            "Кемінде екі өткізгішті (резисторды) тізбектей жалғап, тізбекті құрастырыңыз.",
            "Кернеу және ток датчиктерін тиісті COM-порттарда «Анықтау» арқылы қосыңыз.",
            "Екі құрылғының да дайын («2 / 2 құрылғы») екенін тексеріңіз.",
            "«Бастау» батырмасын басыңыз.",
            "Тізбектің жалпы кернеуі мен тогының өлшенуін бақылаңыз.",
            "Есептелген жалпы кедергі (R) және қуат (P) мәндерін оқыңыз.",
            "Өлшеуді аяқтағанда «Тоқтату» басып, нәтижені жазып алыңыз.",
        ),
        safety=_BASIC_SAFETY,
        control_questions=(
            "Тізбектей қосылған өткізгіштердегі ток күші неге бірдей болады?",
            "Тізбектей қосылған тізбектің жалпы кедергісі қалай есептеледі?",
            "Өткізгіш санын арттырса, жалпы кедергі қалай өзгереді?",
        ),
    ),
    report=ExperimentReport(),
    # Phase 36.1 follow-up: ӨЗ қосылым суреті (басқа тізбек топологиясы —
    # бірнеше резистор тізбектей жалғанған).
    diagram=ExperimentDiagram(
        image_path=_SERIES_CONNECTION_WIRING_PATH, caption=_WIRING_DIAGRAM_CAPTION
    ),
    assessment=_SERIES_CONNECTION_ASSESSMENT,
)

_PARALLEL_CONNECTION_ASSESSMENT = ExperimentAssessmentDefinition(
    level1_questions=(
        MultipleChoiceQuestion(
            id="pc-l1-1",
            prompt="Параллель қосылған тармақтардағы кернеу қандай?",
            options=("Әртүрлі", "Бірдей", "Нөлге тең", "Тек біреуінде бар"),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="pc-l1-2",
            prompt="Параллель қосылған екі өткізгіштің жалпы (эквивалентті) кедергісі қалай есептеледі?",
            options=("R = R₁ + R₂", "1/R = 1/R₁ + 1/R₂", "R = R₁ × R₂", "R = R₁ − R₂"),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="pc-l1-3",
            prompt="Параллель тізбектегі жалпы ток күші неге тең?",
            options=(
                "Тармақтардағы токтардың қосындысына",
                "Ең үлкен ток тармағына",
                "Ең кіші ток тармағына",
                "Нөлге",
            ),
            correct_option_index=0,
        ),
        MultipleChoiceQuestion(
            id="pc-l1-4",
            prompt="Параллель тармақтардың біреуі үзілсе, басқа тармақтар қалай болады?",
            options=(
                "Олар да жұмысын тоқтатады",
                "Жұмысын жалғастыра алады",
                "Қысқа тұйықталады",
                "Кернеуі нөлге түседі",
            ),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="pc-l1-5",
            prompt="Параллель тармақ санын арттырса, жалпы (эквивалентті) кедергі қалай өзгереді?",
            options=("Артады", "Кемиді", "Өзгермейді", "Шексіздікке ұмтылады"),
            correct_option_index=1,
        ),
    ),
    level2_questions=(
        OpenResponseQuestion(
            id="pc-l2-1", prompt="Тармақтардағы кернеу неге бірдей болды?"
        ),
        OpenResponseQuestion(
            id="pc-l2-2",
            prompt="Жалпы ток пен тармақ токтарының қосындысын салыстырыңыз — қандай қорытынды жасауға болады?",
        ),
        OpenResponseQuestion(
            id="pc-l2-3", prompt="Нәтиже теориямен (1/R = 1/R₁ + 1/R₂) сәйкес келе ме?"
        ),
    ),
    level3_questions=_reflection_questions("pc"),
)

PARALLEL_CONNECTION_EXPERIMENT = ExperimentDefinition(
    id="parallel-connection",
    title="Өткізгіштерді параллель қосуды зерттеу",
    description="Параллель жалғанған өткізгіштердегі ток пен кернеуді, "
    "жалпы кедергі мен қуатты зерттеу.",
    display_number=6,
    required_channels=(VOLTAGE_CHANNEL, CURRENT_CHANNEL),
    derived_channels=(RESISTANCE_CHANNEL, POWER_CHANNEL),
    graph_x_channel="voltage",
    graph_y_channels=("current",),
    formulas={"resistance": "R = U / I", "power": "P = U × I"},
    required_sensor_types=_REQUIRED_SENSOR_TYPES,
    guide=ExperimentGuide(
        objective=(
            "өткізгіштерді параллель жалғау тәсілін тәжірибе жүзінде меңгеру;",
            "параллель тармақтардағы кернеудің бірдей болатынын тексеру;",
            "жалпы кедергі мен тұтынылатын қуатты анықтау.",
        ),
        equipment=_SENSOR_EQUIPMENT
        + ("Параллель жалғанатын өткізгіштер (кемінде 2 резистор)",),
        theory=(
            "Өткізгіштер параллель жалғанғанда, әр тармақтағы кернеу "
            "БІРДЕЙ болады (U = U₁ = U₂ = ...), ал жалпы ток күші әр "
            "тармақтан өтетін токтардың қосындысына тең (I = I₁ + I₂ + ...). "
            "Осыдан тізбектің жалпы кедергісінің кері шамасы әр өткізгіш "
            "кедергісінің кері шамасының қосындысына тең болады: "
            "1 / R_жалпы = 1 / R₁ + 1 / R₂ + ... . Бағдарлама датчиктер "
            "арқылы тізбектің ЖАЛПЫ кернеуі мен тогын өлшеп, осы R_жалпы "
            "мен тұтынылатын қуатты (P = U × I) автоматты есептейді."
        ),
        formulas=("1 / R_жалпы = 1 / R₁ + 1 / R₂ + ...", "R = U / I", "P = U × I"),
        procedure=(
            "Кемінде екі өткізгішті (резисторды) параллель жалғап, тізбекті құрастырыңыз.",
            "Кернеу және ток датчиктерін тиісті COM-порттарда «Анықтау» арқылы қосыңыз.",
            "Екі құрылғының да дайын («2 / 2 құрылғы») екенін тексеріңіз.",
            "«Бастау» батырмасын басыңыз.",
            "Тізбектің жалпы кернеуі мен тогының өлшенуін бақылаңыз.",
            "Есептелген жалпы кедергі (R) және қуат (P) мәндерін оқыңыз.",
            "Өлшеуді аяқтағанда «Тоқтату» басып, нәтижені жазып алыңыз.",
        ),
        safety=_BASIC_SAFETY,
        control_questions=(
            "Параллель қосылған тармақтардағы кернеу неге бірдей болады?",
            "Параллель қосылған тізбектің жалпы кедергісі қалай есептеледі?",
            "Өткізгіш санын арттырса, жалпы кедергі қалай өзгереді?",
        ),
    ),
    report=ExperimentReport(),
    # Phase 36.1 follow-up: ӨЗ қосылым суреті (басқа тізбек топологиясы —
    # бірнеше резистор параллель жалғанған).
    diagram=ExperimentDiagram(
        image_path=_PARALLEL_CONNECTION_WIRING_PATH, caption=_WIRING_DIAGRAM_CAPTION
    ),
    assessment=_PARALLEL_CONNECTION_ASSESSMENT,
)

_CURRENT_WORK_POWER_ASSESSMENT = ExperimentAssessmentDefinition(
    level1_questions=(
        MultipleChoiceQuestion(
            id="cwp-l1-1",
            prompt="Электр қуатының формуласы қандай?",
            options=("P = U / I", "P = U × I", "P = I / U", "P = U + I"),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="cwp-l1-2",
            prompt="Электр қуаты қандай өлшем бірлікпен өлшенеді?",
            options=("Джоуль", "Ватт", "Ампер", "Кулон"),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="cwp-l1-3",
            prompt="Тұрақты қуатта электр жұмысының (энергиясының) формуласы қандай?",
            options=("A = P / t", "A = P × t", "A = P + t", "A = t / P"),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="cwp-l1-4",
            prompt="P(t) графигінің астындағы аудан нені білдіреді?",
            options=("Орташа ток күшін", "Атқарылған жұмысты (энергияны)", "Кедергіні", "Жиілікті"),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="cwp-l1-5",
            prompt="Электр жұмысы (энергиясы) қандай өлшем бірлікпен өлшенеді?",
            options=("Ватт", "Джоуль", "Ампер", "Вольт"),
            correct_option_index=1,
        ),
    ),
    level2_questions=(
        OpenResponseQuestion(
            id="cwp-l2-1",
            prompt="P(t) графигінен қуаттың уақыт бойынша өзгерісі туралы не айта аласыз?",
        ),
        OpenResponseQuestion(
            id="cwp-l2-2", prompt="Есептелген жұмыс (энергия) мәні не үшін маңызды?"
        ),
        OpenResponseQuestion(
            id="cwp-l2-3",
            prompt="Қуат тұрақты болмаса, атқарылған жұмысты қалай дәл есептеуге болады?",
        ),
    ),
    level3_questions=_reflection_questions("cwp"),
)

CURRENT_WORK_POWER_EXPERIMENT = ExperimentDefinition(
    id="current-work-power",
    title="Электр тогының жұмысы мен қуатын анықтау",
    description="Тұрақты ток тізбегіндегі қуат пен уақыт бойынша "
    "атқарылған жұмысты есептеу.",
    display_number=7,
    required_channels=(VOLTAGE_CHANNEL, CURRENT_CHANNEL, TIME_CHANNEL),
    derived_channels=(POWER_CHANNEL, WORK_CHANNEL),
    graph_x_channel=None,
    graph_y_channels=("power",),
    formulas={"power": "P = U × I", "work": "A = ∫ P dt"},
    # voltage/current есептеу үшін (power=U×I) required_channels-те қалады,
    # бірақ workspace-те тек уақыт/қуат/жұмыс көрсетіледі (2-бөлім спецификациясы).
    display_channels=("time", "power", "work"),
    required_sensor_types=_REQUIRED_SENSOR_TYPES,
    graph_derived_analysis=DERIVED_ANALYSIS_POWER_ENERGY,
    guide=ExperimentGuide(
        objective=(
            "тұрақты ток тізбегіндегі лездік қуаттың уақыт бойынша өзгерісін бақылау;",
            "белгілі уақыт аралығында атқарылған электр жұмысын (энергияны) есептеу.",
        ),
        equipment=_SENSOR_EQUIPMENT + ("Зерттелетін тізбек (жүктеме)",),
        theory=(
            "Қуат P — электр энергиясының бірлік уақытта тасымалдану жылдамдығын "
            "сипаттайды (лездік шама). Ал жұмыс (энергия) A — қуаттың уақыт "
            "бойынша жинақталған қосындысы, яғни P(t) графигінің астындағы "
            "аудан. Бағдарлама аймақ таңдау («↔») құралы арқылы дәл осы "
            "ауданды (жұмысты) және орташа/максимал қуатты автоматты есептейді."
        ),
        formulas=("P = U × I", "A = ∫ P dt", "тұрақты P үшін A = P × t"),
        procedure=(
            "Кернеу және ток датчиктерін тиісті COM-порттарда «Анықтау» арқылы қосыңыз.",
            "Екі құрылғының да дайын («2 / 2 құрылғы») екенін тексеріңіз.",
            "«Бастау» батырмасын басыңыз.",
            "Қуат P(t) графигінің уақыт бойынша салынуын бақылаңыз.",
            "«↔» (аймақты талдау) құралымен қажетті уақыт аралығын таңдаңыз.",
            "Таңдалған аралықтағы орташа қуат (P_орта) және жұмыс (A) мәндерін оқыңыз.",
            "Өлшеуді аяқтағанда «Тоқтату» басып, нәтижелерді жазып алыңыз.",
        ),
        safety=_BASIC_SAFETY,
        control_questions=(
            "Қуат пен жұмыстың (энергияның) айырмашылығы неде?",
            "Жұмыс уақыт бойынша қалай жинақталады?",
            "P(t) графигінің астындағы аудан физикалық тұрғыда нені білдіреді?",
        ),
    ),
    report=ExperimentReport(),
    # Phase 36.1: НАҚТЫ қосылым суреті — жүктеме бір резистор ретінде
    # осы breadboard-та, дәл сол физикалық құрылым.
    diagram=ExperimentDiagram(
        image_path=_CURRENT_VOLTAGE_WIRING_PATH, caption=_WIRING_DIAGRAM_CAPTION
    ),
    assessment=_CURRENT_WORK_POWER_ASSESSMENT,
)

# Phase 38B: Voltage/Current сенсорлары арқылы кедергіні (R=U/I, БҰРЫННАН
# БАР генерик калькулятор) есептеп, оны Temperature арнасына қарсы
# (X=температура, Y=кедергі) сызу арқылы толық жұмыс істейтін тәжірибе.
# ЖАЛҒЫЗ жетіспейтін бөлік — нақты температура сенсорының firmware-і
# (ENERGY/OHMMETER-мен БІРДЕЙ "hardware adapter белсенді емес" күйі):
# құрылғы қадамы нақты сенсор қосылғанша "!" болып қала береді, бірақ
# бұл ешбір өтірік дерек шығармайды — тек сол сенсор ешқашан "дайын"
# болмайды. MultiSensorExperimentCoordinator/ChannelAggregator/
# DataValidator ҮШЕУІ ДЕ N сенсор түріне толық генерик (кодтан расталды),
# сондықтан 3-сенсорлы бұл тәжірибеге олардың өзінде ЕШБІР өзгеріс қажет
# болмады.
_METAL_RESISTANCE_TEMPERATURE_DIAGRAM_CAPTION = (
    _WIRING_DIAGRAM_CAPTION
    + " Температура сенсоры бағдарлама роудмэпінде жоспарланған — әлі "
    "қосылмаған, сондықтан суретте көрсетілмеген."
)
_METAL_RESISTANCE_TEMPERATURE_ASSESSMENT = ExperimentAssessmentDefinition(
    level1_questions=(
        MultipleChoiceQuestion(
            id="mrt-l1-1",
            prompt="Металдардың электр кедергісі температура өскенде әдетте қалай өзгереді?",
            options=("Кемиді", "Артады", "Өзгермейді", "Кездейсоқ өзгереді"),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="mrt-l1-2",
            prompt="R(T) тәуелділігінің графигіндегі көлбеулігі нені білдіреді?",
            options=("Бастапқы кедергіні", "Температуралық коэффициентті", "Ток күшін", "Кернеуді"),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="mrt-l1-3",
            prompt="Температуралық коэффициент физикалық тұрғыда нені сипаттайды?",
            options=(
                "Кедергінің температураға тәуелділік дәрежесін",
                "Тізбектегі ток күшін",
                "Тұтынылатын қуатты",
                "Тоқтың жиілігін",
            ),
            correct_option_index=0,
        ),
        MultipleChoiceQuestion(
            id="mrt-l1-4",
            prompt="Температура сенсоры әлі қосылмаса, бұл нені білдіреді?",
            options=(
                "Тәжірибе дұрыс орындалмады",
                "Аппараттық жабдық әлі толық қосылмаған — бұл студенттің қатесі емес",
                "Металл қызбайды",
                "Кедергі мүлде есептелмейді",
            ),
            correct_option_index=1,
        ),
        MultipleChoiceQuestion(
            id="mrt-l1-5",
            prompt="Кедергіні (R = U / I) есептеу үшін қандай негізгі шамалар қажет?",
            options=("Тек уақыт", "Кернеу мен ток күші", "Тек температура", "Жиілік пен фаза"),
            correct_option_index=1,
        ),
    ),
    level2_questions=(
        OpenResponseQuestion(
            id="mrt-l2-1",
            prompt="R(T) графигінен (немесе жоспарланған өлшеуден) қандай заңдылық күтесіз/байқадыңыз?",
        ),
        OpenResponseQuestion(
            id="mrt-l2-2",
            prompt="Температураны өлшеу кезінде қандай қателіктер (белгісіздіктер) туындауы мүмкін?",
        ),
        OpenResponseQuestion(
            id="mrt-l2-3",
            prompt="Температура сенсоры әлі қосылмағаны тәжірибенің нәтижесіне қалай әсер етеді?",
        ),
        OpenResponseQuestion(
            id="mrt-l2-4", prompt="Металдың кедергісі температураға неге тәуелді деп ойлайсыз?"
        ),
    ),
    level3_questions=_reflection_questions("mrt"),
)

METAL_RESISTANCE_TEMPERATURE_EXPERIMENT = ExperimentDefinition(
    id="metal-resistance-temperature",
    title="Металдар кедергісінің температураға тәуелділігі",
    description=(
        "Металл өткізгіштің температурасы өзгерген кезде оның электр "
        "кедергісінің өзгерісін бақылау."
    ),
    display_number=8,
    # TEMP= парсинг дайын, бірақ температура firmware жоқ — 3/3 дайын
    # болмайды. Каталогта «Жоспарланған» болып қалады.
    is_implemented=False,
    required_channels=(TEMPERATURE_CHANNEL, VOLTAGE_CHANNEL, CURRENT_CHANNEL),
    derived_channels=(RESISTANCE_CHANNEL,),
    display_channels=("temperature", "voltage", "current", "resistance"),
    graph_x_channel="temperature",
    graph_y_channels=("resistance",),
    formulas={"resistance": "R = U / I"},
    required_sensor_types=("VOLTAGE", "CURRENT", "TEMPERATURE"),
    # Ohm's Law-мен БІРДЕЙ Vernier тәрізді scatter+fit+manual capture
    # механизмі (тек X/Y арнасы басқа) — температура тұрақталғанша күтіп,
    # содан кейін нүктені сақтау дәл осы тәжірибеге физикалық тұрғыда сай
    # келеді (Ohm's Law-дағы "мән тұрақталған сәтте сақтау" себебімен БІРДЕЙ).
    graph_connect_points=False,
    graph_show_fit=True,
    graph_title="Кедергінің температураға тәуелділігі",
    graph_x_label="Температура, T",
    graph_y_label="Кедергі, R",
    graph_dedup_x_tolerance=0.05,
    graph_dedup_y_tolerance=0.005,
    graph_fit_result_prefix="k",
    graph_fit_unit="Ω/°C",
    graph_fit_display_name="Температуралық коэффициент",
    graph_capture_mode="manual",
    graph_capture_sample_count=10,
    graph_capture_x_tolerance=0.5,
    graph_capture_y_tolerance=0.5,
    graph_fit_x_symbol="T",
    graph_fit_y_symbol="R",
    graph_allow_delta_measurement=True,
    guide=ExperimentGuide(
        objective=(
            "металл өткізгіштің электр кедергісінің температураға тәуелділігін зерттеу;",
            "R(T) тәуелділігінің көлбеулігінен температуралық коэффициентті анықтау.",
        ),
        equipment=_SENSOR_EQUIPMENT
        + (
            "Температура сенсоры (Arduino Nano/Uno негізінде — бағдарлама "
            "роудмэпінде жоспарланған, әлі қосылмаған)",
            "Қыздыратын/суытатын құрал (мыс. ыстық су ыдысы)",
            "Зерттелетін металл өткізгіш (сынама)",
        ),
        theory=(
            "Көптеген металдар үшін электр кедергісі температура өскен "
            "сайын шамамен сызықтық түрде артады: R(T) ≈ R₀[1 + α(T − T₀)], "
            "мұндағы R₀ — бастапқы температурадағы кедергі, α — "
            "температуралық коэффициент. Бағдарлама әр тұрақталған "
            "температурада кернеу мен ток арқылы кедергіні (R = U / I) "
            "есептеп, R(T) графигін тұрғызады — сызықтық аппроксимацияның "
            "көлбеулігі (k = dR/dT) дәл осы тәуелділікті сипаттайды."
        ),
        formulas=("R = U / I", "R(T) ≈ R₀(1 + α·ΔT)", "k = dR/dT"),
        procedure=(
            "Кернеу, ток және температура датчиктерін тиісті "
            "COM-порттарда «Анықтау» арқылы қосыңыз.",
            "Барлық құрылғының дайын («3 / 3 құрылғы») екенін тексеріңіз.",
            "«Бастау» батырмасын басыңыз.",
            "Өткізгішті бірте-бірте қыздырыңыз/суытыңыз, әр жаңа "
            "температурада мән тұрақталғанша күтіңіз.",
            "Мән тұрақталған сәтте «+ Нүктені сақтау» батырмасын басыңыз.",
            "Осы қадамды кемінде 5-7 әртүрлі температура үшін қайталаңыз.",
            "R(T) графигіндегі сызықтық аппроксимация нәтижесін (k мәнін) оқыңыз.",
            "Өлшеуді аяқтағанда «Тоқтату» басып, нәтиже бойынша қорытынды жасаңыз.",
        ),
        safety=_BASIC_SAFETY
        + (
            "Ыстық су/қыздыратын құралмен жұмыс істегенде күйіп қалудан сақтаныңыз.",
        ),
        control_questions=(
            "Металдың кедергісі температура өскенде қалай өзгереді?",
            "Температуралық коэффициент физикалық тұрғыда нені білдіреді?",
            "R(T) графигінің көлбеулігі қандай физикалық шаманы сипаттайды?",
        ),
    ),
    report=ExperimentReport(),
    diagram=ExperimentDiagram(
        image_path=_CURRENT_VOLTAGE_WIRING_PATH,
        caption=_METAL_RESISTANCE_TEMPERATURE_DIAGRAM_CAPTION,
    ),
    assessment=_METAL_RESISTANCE_TEMPERATURE_ASSESSMENT,
)

# 8-сынып жаңа оқу бағдарламасы: дисплей реті ЕНДІ display_number-мен
# (3..8) сәйкес — ескі "ohms-law бөлімнің ЕҢ СОҢЫНДА" ерекшелігі
# (спецификацияның ескі талабы) енді қолданылмайды.
ELECTRICITY_EXPERIMENTS: tuple[ExperimentDefinition, ...] = (
    CURRENT_VOLTAGE_EXPERIMENT,
    OHMS_LAW_EXPERIMENT,
    SERIES_CONNECTION_EXPERIMENT,
    PARALLEL_CONNECTION_EXPERIMENT,
    CURRENT_WORK_POWER_EXPERIMENT,
    METAL_RESISTANCE_TEMPERATURE_EXPERIMENT,
)
