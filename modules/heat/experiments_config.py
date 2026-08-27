"""experiments_config — "Жылу құбылыстары" бөлімінің 2 зертхана жұмысы.

Барлығы каталогта ғана — әлі workspace/sensor pipeline-і жоқ
(``is_implemented=False``). Нақты hardware/арна ойдан шығарылмайды:
``required_channels``/``required_sensor_types`` бос қалады, себебі бұл
тәжірибелер ешқашан нақты ExperimentWorkspacePage-ті ашпайды.

2026-07-29 catalog order correction: бұрынғы "Металдардың меншікті жылу
сыйымдылығын анықтау" (№3) authoritative 12-work каталогынан алынып
тасталды (пайдаланушының нақты сұрауы бойынша) — бірақ болашақта қажет
болуы мүмкін болғандықтан анықтамасы (``METAL_SPECIFIC_HEAT_CAPACITY_
EXPERIMENT``) төменде САҚТАЛҒАН, тек ``HEAT_EXPERIMENTS`` tuple-ынан
(яғни ``HeatModule.get_experiments()``-тен) шығарылды және
``display_number=None`` етіп белгіленді.
"""

from domain.entities.experiment_definition import ExperimentDefinition

COMPARE_HEAT_QUANTITY_EXPERIMENT = ExperimentDefinition(
    id="compare-heat-quantity",
    title="Температураға әртүрлі бөлінетін жылудың мөлшерін салыстыру",
    description="Қыздыру/салқындату процесінде температураны тіркеу.",
    display_number=1,
    is_implemented=False,
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
