"""experiments_config — "Жарық құбылыстары" бөлімінің 1 зертхана жұмысы.

Каталогта ғана — әлі workspace/sensor pipeline-і жоқ
(``is_implemented=False``). Нақты hardware/арна ойдан шығарылмайды.
"""

from domain.entities.experiment_definition import ExperimentDefinition

# 8-сынып жаңа оқу бағдарламасы: Electricity бөлімі 7-ден 6 тәжірибеге
# қысқарғандықтан, каталогтың ЖАЛПЫ 1..N сандық реті үзіліссіз қалу
# үшін бұл 12-ден 11-ге жылжытылды (тек нөмір — атау/логика өзгермеді).
THIN_LENS_FOCAL_LENGTH_EXPERIMENT = ExperimentDefinition(
    id="thin-lens-focal-length",
    title="Жұқа линзаның фокус арақашықтығын анықтау",
    description="Жұқа линзаның фокус арақашықтығын тәжірибелік жолмен анықтау.",
    display_number=11,
    is_implemented=False,
)

LIGHT_EXPERIMENTS: tuple[ExperimentDefinition, ...] = (THIN_LENS_FOCAL_LENGTH_EXPERIMENT,)
