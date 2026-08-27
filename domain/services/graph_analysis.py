"""graph_analysis — LiveGraphWidget-тің ғылыми анализ қабатына (Phase 33B:
аралық статистика, сызықтық регрессия, трапеция интеграциясы) арналған
таза, Qt-сыз numpy утилиталары.

Бұл модуль ЕШБІР Measurement/ExperimentSession/CalculationEngine
логикасын қайталамайды және ЕШБІР жаңа физикалық формула ойлап
таппайды — тек графикте САҚТАЛҒАН нақты (x, y) үлгілерінің үстінен
СИПАТТАМАЛЫҚ статистика/регрессия есептейді. Интерполяция/фейк нүкте
ЕШҚАШАН жасалмайды — барлық функция тек нақты сақталған мәндермен
жұмыс істейді.

Домен қабатында орналасуының себебі: бұл функциялар таза сандық
(numpy-негізді), UI/pyqtgraph-қа ЕШБІР тәуелділігі жоқ — сондықтан
болашақ Жылу/Магнетизм/Оптика модульдерінде де, тіпті UI-сыз (мыс.
скрипт/notebook) де қайта пайдалануға болады.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

_MIN_REGRESSION_POINTS = 2

# ExperimentDefinition.graph_derived_analysis мәні — "Ток жұмысы мен қуаты"
# секілді тәжірибелерде P(t)-тен W=∫P dt есептеу үшін (§10). Домен
# қабатында орналасуының себебі: ExperimentDefinition (домен) осы мәнді
# validate_configuration()-де тексереді және LiveGraphWidget (UI) осыны
# импорттайды — керісінше (UI константасын домен импорттауы) қабат
# архитектурасын бұзар еді.
DERIVED_ANALYSIS_POWER_ENERGY = "power_energy"


def nearest_index(x_values: Sequence[float], x_target: float) -> int:
    """``x_values``-тегі ``x_target``-ге ЕҢ ЖАҚЫН элементтің индексін
    қайтарады (реттелген/ретсіз тізімге бірдей жұмыс істейді — XY/scatter
    деректер уақыт бойынша монотонды өспеуі мүмкін). Бос тізім үшін -1.

    Phase 33A-да ``ui/widgets/graph_crosshair.py``-де анықталған,
    Phase 33B-де осында көшірілді (§1: "Do not create a second
    independent graph-analysis architecture") — crosshair ДӘЛ ОСЫ
    функцияны қайта импорттайды, дубликат жоқ.
    """
    if len(x_values) == 0:
        return -1
    diffs = np.abs(np.asarray(x_values, dtype=float) - x_target)
    return int(np.argmin(diffs))


def indices_in_range(x_values: Sequence[float], x_min: float, x_max: float) -> np.ndarray:
    """``x_min <= x <= x_max`` шартын қанағаттандыратын индекстердің
    numpy маскасын қайтарады (vectorized — §17 Performance: 5000+
    нүктеде де жылдам).
    """
    if len(x_values) == 0:
        return np.array([], dtype=bool)
    array = np.asarray(x_values, dtype=float)
    lo, hi = (x_min, x_max) if x_min <= x_max else (x_max, x_min)
    return (array >= lo) & (array <= hi)


@dataclass(frozen=True)
class RegionStatistics:
    """Таңдалған аралықтағы ([t1, t2]) БІР арнаның сипаттамалық
    статистикасы — тек НАҚТЫ сақталған үлгілерден (§4).

    ``std_dev`` конвенциясы: POPULATION standard deviation (``ddof=0``,
    numpy әдепкісі) — таңдалған үлгі жиынының ӨЗІН сипаттайды (кеңірек
    популяцияны инференс жасау ЕМЕС, тек осы нақты аралықтағы нақты
    өлшеулердің таралуын көрсетеді). Бұл — физика зертханасы
    бағдарламаларында (Vernier/PASCO) кең тараған, қарапайым конвенция.
    """

    n: int
    minimum: float | None
    maximum: float | None
    average: float | None
    delta: float | None  # maximum - minimum
    std_dev: float | None  # population std (ddof=0)

    @property
    def coefficient_of_variation_percent(self) -> float | None:
        """CV = σ / |AVG| × 100% — тек ТҰРАҚТЫЛЫҚ/вариация көрсеткіші
        (§12: "Do NOT claim that CV is measurement error"). AVG=0 немесе
        деректер жеткіліксіз болса None қайтарады (бөлуге болмайды).
        """
        if self.std_dev is None or self.average is None or self.average == 0:
            return None
        return abs(self.std_dev / self.average) * 100.0

    @property
    def standard_error_of_mean(self) -> float | None:
        """SEM = σ / √N — таза СТАТИСТИКАЛЫҚ стандартты қате (Phase 34 §4).

        Бұл аспаптық/жүйелік (калибрлеу) қателікпен АРАЛАСПАУЫ тиіс —
        тек осы нақты N үлгінің орташа мәнін бағалаудағы статистикалық
        сенімділікті көрсетеді. N < 2 болса анықталмайды (бөлек 1 үлгіде
        "стандартты қате" мағынасыз).
        """
        if self.std_dev is None or self.n < 2:
            return None
        return self.std_dev / math.sqrt(self.n)


def compute_region_statistics(values: Sequence[float]) -> RegionStatistics:
    """Берілген нақты мәндер тізімінен ``RegionStatistics`` есептейді.
    Бос тізім үшін барлық өріс ``None``/``n=0`` (fake 0.0 мән ЕШҚАШАН
    қайтарылмайды — §7-дегі "Prefer returning an explicit unavailable
    result rather than inventing zeroes" принципі статистикаға да
    қолданылады).
    """
    n = len(values)
    if n == 0:
        return RegionStatistics(n=0, minimum=None, maximum=None, average=None, delta=None, std_dev=None)

    array = np.asarray(values, dtype=float)
    minimum = float(np.min(array))
    maximum = float(np.max(array))
    return RegionStatistics(
        n=n,
        minimum=minimum,
        maximum=maximum,
        average=float(np.mean(array)),
        delta=maximum - minimum,
        std_dev=float(np.std(array, ddof=0)),
    )


@dataclass(frozen=True)
class RegressionResult:
    """Сызықтық регрессия нәтижесі (``y = m*x + b``). ``valid=False``
    болса, ``slope``/``intercept``/``r_squared``/``rmse`` барлығы
    ``None`` — деградацияланған деректерде (§7: "fewer than 2 points,
    identical X values, NaN/Inf, zero variance") ЕШҚАШАН жалған 0.0
    мән қайтарылмайды, тек "қолжетімсіз" күй анық белгіленеді.
    """

    valid: bool
    slope: float | None
    intercept: float | None
    r_squared: float | None
    rmse: float | None
    n: int


def compute_linear_regression(
    x_values: Sequence[float], y_values: Sequence[float]
) -> RegressionResult:
    """``y = m*x + b`` сызықтық регрессиясын (numpy.polyfit, дәреже 1)
    есептеп, R²/RMSE-мен бірге қайтарады.

    RMSE = sqrt(mean((y_measured - y_predicted)^2)) — §7-де нақты
    көрсетілген формула.

    Қауіпсіз ажыратылатын жағдайлар (crash/жалған мән ЖОҚ): 2-ден аз
    нүкте, барлық X мәні бірдей (нөлдік дисперсия — сызық анықталмайды),
    NaN/Inf, ``ss_tot<=0`` (барлық Y мәні бірдей — R² анықталмайды).
    """
    n = len(x_values)
    if n < _MIN_REGRESSION_POINTS or len(y_values) != n:
        return RegressionResult(valid=False, slope=None, intercept=None, r_squared=None, rmse=None, n=n)

    x_array = np.asarray(x_values, dtype=float)
    y_array = np.asarray(y_values, dtype=float)

    if not (np.all(np.isfinite(x_array)) and np.all(np.isfinite(y_array))):
        return RegressionResult(valid=False, slope=None, intercept=None, r_squared=None, rmse=None, n=n)

    if len(set(x_values)) < _MIN_REGRESSION_POINTS:
        # Барлық X мәні бірдей — тік сызық, "y = m*x + b" моделі
        # анықталмайды (шексіз slope). Жалған slope=0 қайтармаймыз.
        return RegressionResult(valid=False, slope=None, intercept=None, r_squared=None, rmse=None, n=n)

    try:
        slope, intercept = np.polyfit(x_array, y_array, 1)
    except (np.linalg.LinAlgError, ValueError):
        return RegressionResult(valid=False, slope=None, intercept=None, r_squared=None, rmse=None, n=n)

    if not (math.isfinite(slope) and math.isfinite(intercept)):
        return RegressionResult(valid=False, slope=None, intercept=None, r_squared=None, rmse=None, n=n)

    y_predicted = slope * x_array + intercept
    residuals = y_array - y_predicted
    rmse = float(np.sqrt(np.mean(residuals**2)))

    ss_tot = float(np.sum((y_array - np.mean(y_array)) ** 2))
    if ss_tot <= 0:
        # Барлық Y мәні бірдей — R² анықталмайды (0/0), бірақ slope/
        # intercept/RMSE әлі де мағыналы болуы мүмкін (RMSE=0 бұл жерде).
        r_squared = None
    else:
        ss_res = float(np.sum(residuals**2))
        r_squared = 1.0 - ss_res / ss_tot

    return RegressionResult(
        valid=True,
        slope=float(slope),
        intercept=float(intercept),
        r_squared=r_squared,
        rmse=rmse,
        n=n,
    )


def compute_trapezoidal_integral(x_values: Sequence[float], y_values: Sequence[float]) -> float | None:
    """Нақты сақталған (x, y) жұптарының үстінен трапеция ережесімен
    сандық интеграл есептейді (мыс. P(t)-ден W=∫P dt). Нақты timestamp-
    тарды қолданады — БІРКЕЛКІ аралықты ойдан шығармайды (§10: "Do not
    invent evenly spaced timestamps if actual timestamps exist").

    2-ден аз нүкте үшін ``None`` (интеграл анықталмайды — 0.0 жалған
    мән ЕМЕС, "белгісіз" күй).
    """
    if len(x_values) < 2 or len(x_values) != len(y_values):
        return None

    x_array = np.asarray(x_values, dtype=float)
    y_array = np.asarray(y_values, dtype=float)
    if not (np.all(np.isfinite(x_array)) and np.all(np.isfinite(y_array))):
        return None

    # numpy>=2.0: trapezoid; ескі numpy-де trapz әлі бар (deprecated,
    # бірақ функционалды) — үйлесімділік үшін fallback.
    trapezoid_fn = getattr(np, "trapezoid", None) or np.trapz
    return float(trapezoid_fn(y_array, x_array))


@dataclass(frozen=True)
class DeltaResult:
    """Екі нақты сақталған нүкте (A, B) арасындағы Δ өлшеу нәтижесі
    (Phase 34 §1: two-point/Δ measurement tool). ``ratio`` тек ``dx != 0``
    кезінде анықталады (I-U графигінде ΔU/ΔI секілді) — таңбасы (sign)
    сақталады, ``abs()`` ЕШҚАШАН қолданылмайды, себебі теріс градиент те
    физикалық мағыналы болуы мүмкін (мыс. салқындау кезіндегі dT/dt).
    """

    x1: float
    y1: float
    x2: float
    y2: float
    dx: float
    dy: float
    ratio: float | None


def compute_delta(x1: float, y1: float, x2: float, y2: float) -> DeltaResult:
    """A(``x1``, ``y1``) мен B(``x2``, ``y2``) — екеуі де НАҚТЫ сақталған
    үлгілерден (шақырушы ``nearest_index()`` арқылы таңдайды, бұл функция
    тек арифметика) — Δx/Δy/(Δy/Δx, dx != 0 болса) есептейді.
    """
    dx = x2 - x1
    dy = y2 - y1
    ratio = (dy / dx) if dx != 0 else None
    return DeltaResult(x1=x1, y1=y1, x2=x2, y2=y2, dx=dx, dy=dy, ratio=ratio)


def compute_residuals(
    x_values: Sequence[float], y_values: Sequence[float], slope: float, intercept: float
) -> list[float]:
    """Сызықтық fit-тің (``y = slope*x + intercept``) қалдықтарын
    (residual = measured_y - fitted_y) есептейді — ТЕК fit-ке қолданылған
    НАҚТЫ өлшенген нүктелерден (Phase 34 §6). Ұзындықтары сәйкес келмесе
    бос тізім қайтарады (crash/жалған мән ЕШҚАШАН емес).
    """
    if len(x_values) != len(y_values) or not x_values:
        return []
    x_array = np.asarray(x_values, dtype=float)
    y_array = np.asarray(y_values, dtype=float)
    fitted = slope * x_array + intercept
    return (y_array - fitted).tolist()
