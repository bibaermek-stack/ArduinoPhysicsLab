"""experiment_conclusion — тәжірибе есебіндегі "Автоматты талдау"
секциясының жалғыз дерек көзі (Phase 38B).

Бұл модуль ЕШБІР жаңа физикалық/статистикалық шама есептемейді — тек
``build_experiment_report_data()`` (Phase 36) арқылы АЛДЫН АЛА есептелген
``ExperimentReportData``-ны оқып, қысқа фактілік қазақша сөйлем(дер)
құрастырады. Барлық электр тәжірибесіне БІР ҒАНА жалпы функция қызмет
етеді (эксперимент ID бойынша ешбір special-case ЖОҚ) — fit/қуат/жұмыс/
арна статистикасының қайсысы бар болуына қарай генерик түрде таңдайды.
Студенттің өз қолмен жазатын "Қорытынды" өрісін ЕШҚАШАН алмастырмайды —
тек соның үстінде қосымша, тек оқуға арналған анықтама секциясы ретінде
көрсетіледі (``ExperimentReportDialog``).
"""

from __future__ import annotations

from domain.services.experiment_report_data import ExperimentReportData

_EMPTY_SESSION_TEXT = (
    "Өлшеу деректері әлі жоқ — автоматты талдау үшін алдымен өлшеу жүргізіңіз."
)
_NO_DATA_FOR_CONCLUSION_TEXT = "Есептелген қорытынды үшін жеткілікті дерек жоқ."
_LAW_AGREEMENT_R_SQUARED_THRESHOLD = 0.8


def build_automatic_conclusion(report_data: ExperimentReportData) -> str:
    """``report_data``-дан (кез келген тәжірибеге бірдей, толығымен
    генерик түрде — эксперимент ID бойынша ешбір special-case ЖОҚ) қысқа
    автоматты талдау мәтінін құрастырады. ``report_data``-ның өз ішінде
    (``build_experiment_report_data()`` арқылы) тәжірибенің
    ``graph_fit_*`` презентациялық конфигурациясы (символ/бірлік/атау)
    ЕНДІ ҚОСЫЛҒАН болатын, сондықтан бұл функцияға ``ExperimentDefinition``
    мүлде қажет емес.
    """
    if report_data.sample_count == 0:
        return _EMPTY_SESSION_TEXT

    sentences: list[str] = []

    fit_sentence = _build_fit_sentence(report_data)
    if fit_sentence:
        # Fit нәтижесі (мыс. R=U/I-дің slope-і) шамамен АРНА-ОРТАША
        # мәнмен БІРДЕЙ физикалық шаманы сипаттайды — екеуін де қатар
        # көрсету қайталауға әкеледі, сондықтан fit болса, генерик арна
        # қорытындысы ЖАСАЛМАЙДЫ.
        sentences.append(fit_sentence)
    else:
        excluded_keys: set[str] = set()
        if report_data.power_average is not None:
            sentences.append(f"Орташа қуат ≈ {report_data.power_average:.3f} Вт.")
            excluded_keys.add("power")

        if report_data.work_energy is not None:
            sentences.append(f"Жұмыс/энергия ≈ {report_data.work_energy:.3f} Дж.")
            excluded_keys.add("work")

        # Қалған (қуат/жұмыс сөйлемдерімен ҚАЙТАЛАНБАЙТЫН) арналардың
        # орташа мәні — мыс. Тізбектей/Параллель қосудағы кедергі.
        channel_sentence = _build_channel_summary_sentence(report_data, excluded_keys)
        if channel_sentence:
            sentences.append(channel_sentence)

    if not sentences:
        return _NO_DATA_FOR_CONCLUSION_TEXT

    return " ".join(sentences)


def _build_fit_sentence(report_data: ExperimentReportData) -> str | None:
    result = report_data.fit_result
    if result is None or result.slope is None or result.intercept is None:
        return None

    prefix = report_data.fit_display_name or report_data.fit_result_prefix
    unit_suffix = f" {report_data.fit_unit}" if report_data.fit_unit else ""
    parts = [f"Сызықтық тәуелділік анықталды: {prefix} ≈ {result.slope:.3f}{unit_suffix}"]

    if result.r_squared is not None:
        parts.append(f" (R²={result.r_squared:.3f})")

    sentence = "".join(parts) + "."

    if result.r_squared is not None:
        if result.r_squared >= _LAW_AGREEMENT_R_SQUARED_THRESHOLD:
            sentence += " Нәтиже күтілетін сызықтық модельге сәйкес келеді."
        else:
            sentence += (
                " Нәтиже күтілетін сызықтық модельге толық сәйкес келмейді — "
                "қосымша өлшеу немесе қайталау қажет болуы мүмкін."
            )

    return sentence


def _build_channel_summary_sentence(
    report_data: ExperimentReportData, excluded_keys: set[str]
) -> str | None:
    parts: list[str] = []
    for stats in report_data.channel_statistics:
        if stats.n == 0 or stats.average is None or stats.channel_key in excluded_keys:
            continue
        parts.append(f"{stats.display_name} ≈ {stats.average:.{stats.decimals}f} {stats.unit}")

    if not parts:
        return None

    return "Өлшенген орташа мәндер: " + "; ".join(parts) + "."
