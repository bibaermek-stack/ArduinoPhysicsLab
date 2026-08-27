"""analytics_csv_exporter — Phase 8 (Advanced Analytics & Learning
Progress): оқушылардың топтық үлгерім кестесін CSV файлына экспорттайтын
domain сервисі.

``csv_exporter.py``-мен ДӘЛ БІРДЕЙ пішін/қорғаныс конвенциясы (§ ``export()``
-> ``bool``, ешбір exception сыртқа шықпайды), БІРАҚ мүлде БӨЛЕК дерек
көзі: raw ``Measurement`` тарихы ЕМЕС, ``domain/services/learning_
analytics.py::compute_students_learning_progress()``-тен алынған
жинақталған (aggregated) "гроссбух" (gradebook) жолдары.
"""

import csv

from domain.entities.learning_analytics import StudentLearningProgress

_HEADER = (
    "Оқушы", "Сынып", "Орташа балл (0-10)", "Орындалу деңгейі (%)",
    "Әлсіз тақырып", "Күшті тақырып",
)
_SCORE_DECIMALS = 1


def _format_score(score: float | None) -> str:
    return "" if score is None else f"{score:.{_SCORE_DECIMALS}f}"


def _format_percentage(rate: float | None) -> str:
    return "" if rate is None else f"{round(rate * 100)}"


def _format_topic(topic) -> str:
    return "" if topic is None else topic.experiment_title


class AnalyticsCsvExporter:
    """Оқушылардың сынып бойынша оқу үлгерімін (§ ``StudentLearningProgress``
    жолдары) стандартты, Excel аша алатын CSV файлына жазатын сервис."""

    def export(self, rows: tuple[StudentLearningProgress, ...], output_path: str) -> bool:
        """``rows``-ты ``output_path`` файлына CSV түрінде жазады.

        Тізім бос болса, файл жасалмайды және ``False`` қайтарылады.
        Жазу кезінде кез келген қате (``IOError``, ``PermissionError``,
        т.б.) ұсталады, ешбір exception сыртқа шықпайды — сәтсіз
        болғанда да ``False`` қайтарылады (§ ``csv_exporter.py``-мен
        БІРДЕЙ қорғаныс).
        """
        if not rows:
            return False

        try:
            with open(output_path, mode="w", encoding="utf-8", newline="") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(_HEADER)
                for row in rows:
                    writer.writerow(
                        [
                            row.student_name,
                            row.classroom_name,
                            _format_score(row.overall_average_score),
                            _format_percentage(row.overall_completion_rate),
                            _format_topic(row.weakest_topic),
                            _format_topic(row.strongest_topic),
                        ]
                    )
            return True
        except Exception:  # қорғаныс: IOError/PermissionError/т.б. сыртқа шықпайды
            return False
