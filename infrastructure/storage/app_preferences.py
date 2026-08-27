"""AppPreferences — Settings бетінде өзгертілетін, қолданба
рестарттарынан аман қалатын шағын UI баптауларын сақтау сервисі
(Phase 22).

``QSettings`` қолданады (§ "core/config.py"/"infrastructure/storage/
paths.py" бос TODO stub-тар — нақты баптау сақтау механизмі бұрын
мүлде болмаған). ``app.py``-де ``QCoreApplication.setOrganizationName/
setApplicationName("ArduinoPhysicsLab")`` әлдеқашан орнатылған,
сондықтан әдепкі ``QSettings()`` конструкторы дұрыс, тұрақты
орналасуды (Windows тізілімі) автоматты түрде қолданады.

Бұл сервис ТЕК шын мәнінде қолданбаның бір жерінде НАҚТЫ әсер ететін
баптауларды сақтайды (§ "Do not create fake/non-functional settings")
— тіл/тема/baud rate/экспорт пішімі сияқты ҚАЗІР жалғыз мүмкін мәні бар
"баптаулар" мұнда ЕШҚАШАН сақталмайды (олар SettingsPage-те тек
ақпараттық түрде көрсетіледі, § ``settings_page.py`` докстрингі).
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSettings

from core.deployment_config import load_deployment_config

_KEY_AUTO_SCALE_DEFAULT = "measurement/auto_scale_default"

# § ``ui/widgets/live_graph.py``-дегі ``self._auto_scale_checkbox.
# setChecked(True)`` бұрыннан бар НАҚТЫ әдепкі мәні — осы жерде ЕШҚАШАН
# өзбетінше өзгертілмейді (§ "Do NOT silently change the existing
# default").
_DEFAULT_AUTO_SCALE = True

# § Offline-First + Cloud Sync Foundation §25 "Configuration" — "do not
# hardcode localhost only", бірақ жергілікті әзірлеу әдепкісі
# ``http://127.0.0.1:<port>`` (§ нақты мән). Production мәні ӘРҚАШАН
# Баптаулар арқылы (немесе ортаға тәуелді deployment config арқылы)
# ауыстырылады, бұл файлда ЕШБІР нақты құпия/production URL ЖОҚ.
_KEY_SYNC_API_BASE_URL = "sync/api_base_url"
_KEY_SYNC_ENABLED = "sync/enabled"
_KEY_SYNC_REQUEST_TIMEOUT = "sync/request_timeout_seconds"
_KEY_SYNC_PULL_CURSOR_PREFIX = "sync/pull_cursor/"
# § Phase 3 (Production Authentication + Authorization): қысқа мерзімді
# JWT access token, жергілікті QSettings-те сақталады — Teacher PIN
# хэшімен/сынхрондау API кілтімен БІРДЕЙ "at-rest шифрлау ЖОҚ" деңгейі
# (§ established конвенция, жобада БАСҚА ЕШБІР жерде at-rest шифрлау
# ЖОҚ). ЕШҚАШАН логталмайды (§8/§27 — ``sync_engine.py``/``sync_
# worker.py`` бұл мәнді ешқашан ``print``/``logging``-ке шығармайды).
_KEY_SYNC_AUTH_TOKEN = "sync/auth_token"
_KEY_SYNC_AUTH_TOKEN_EXPIRES_AT = "sync/auth_token_expires_at"
# § Токен ҚАЙ пайдаланушыға шығарылғанын да сақтайды — Мұғалім А
# шыққаннан кейін Оқушы Б кірсе, ЕСКІ (А-ға шығарылған) токен ЕШҚАШАН
# Б атынан қате қолданылмауы керек (§ ``sync_engine.py::_ensure_
# authenticated()`` ағымдағы белсенді сәйкестікпен салыстырады).
_KEY_SYNC_AUTH_TOKEN_ROLE = "sync/auth_token_role"
_KEY_SYNC_AUTH_TOKEN_SYNC_ID = "sync/auth_token_sync_id"
# § Phase 4 (Raw Arduino Measurement Cloud Sync) — "chunk size must be
# configurable, not hardcoded". 250 таңдалды: НАҚТЫ Ohm's Law/RC
# тәжірибелерінің типтік ұзақтығында (§ audit) секундына бірнеше ондаған
# өлшеу кезінде де БІР batch payload-ы бірнеше ондаған КБ шамасында
# қалады (§ "conservative default from real inspection", HTTP payload
# ретінде ыңғайлы, БІРАҚ ЭКСПЕРИМЕНТ АЯҚТАЛҒАНША да занятость сақтайды).
_KEY_MEASUREMENT_BATCH_CHUNK_SIZE = "sync/measurement_batch_chunk_size"
_DEFAULT_MEASUREMENT_BATCH_CHUNK_SIZE = 250

# § Phase 5 (Connectivity-Aware Automatic Sync + Near-Real-Time
# Classroom Monitoring). Үш БӨЛЕК, тәуелсіз реттелетін интервал —
# әрқайсысы ӨЗ мақсатына сай ӘРТҮРЛІ жиілік талап етеді:
#   - connectivity check: ЖЕҢІЛ (тек ``GET /health``), жиі жүруі
#     мүмкін — 12с әдепкі (§ "conservative default, e.g. 10-15
#     seconds").
#   - teacher auto-refresh: ТОЛЫҚ sync циклі (push+pull), тек
#     мұғалім рөлі белсенді болғанда ғана осы қысқа интервалмен
#     жүреді (§ "5-15s teacher polling interval is acceptable") —
#     оқушы рөлінде ЕСКІ 15-минуттық интервал өзгеріссіз қалады
#     (§ "avoid excessive server requests when idle").
#   - active-experiment sync: тәжірибе ЖҮРІП ЖАТҚАНДА ғана белсенді,
#     Phase 4-тегі жергілікті persist таймерімен БІРДЕЙ әдепкі (10с)
#     — "5-15s" мақсатты latency терезесінің ортасы.
_KEY_CONNECTIVITY_CHECK_INTERVAL_SECONDS = "sync/connectivity_check_interval_seconds"
_KEY_TEACHER_AUTO_REFRESH_INTERVAL_SECONDS = "sync/teacher_auto_refresh_interval_seconds"
_KEY_ACTIVE_EXPERIMENT_SYNC_INTERVAL_SECONDS = "sync/active_experiment_sync_interval_seconds"
_DEFAULT_CONNECTIVITY_CHECK_INTERVAL_SECONDS = 12
_DEFAULT_TEACHER_AUTO_REFRESH_INTERVAL_SECONDS = 10
_DEFAULT_ACTIVE_EXPERIMENT_SYNC_INTERVAL_SECONDS = 10

_DEFAULT_SYNC_API_BASE_URL = "http://127.0.0.1:8000"
_DEFAULT_SYNC_ENABLED = False
_DEFAULT_SYNC_REQUEST_TIMEOUT = 5.0

_KEY_ACCOUNT_TOKEN = "account/access_token"
_KEY_ACCOUNT_ID = "account/id"
_KEY_ACCOUNT_EMAIL = "account/email"
_KEY_ACCOUNT_NAME = "account/display_name"
_KEY_ACCOUNT_ROLE = "account/role"
_KEY_ACCOUNT_PUBLIC_ID = "account/public_id"


class AppPreferences:
    """``QSettings``-ті ораған, типтелген getter/setter интерфейсі —
    беттер (``SettingsPage``/``ExperimentWorkspacePage``) ``QSettings``
    кілттерімен ЕШҚАШАН тікелей жұмыс істемейді.
    """

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings()

    def get_auto_scale_default(self) -> bool:
        """Жаңа ``LiveGraphWidget`` данасының "Автоауқым" checkbox-ының
        бастапқы күйі (§ Phase 22 ӨЛШЕУ бөлімі). Белсенді (жұмыс істеп
        тұрған) графикке ЕШҚАШАН кері әсер етпейді — тек ЖАҢА
        экземпляр құрылғанда оқылады."""
        value = self._settings.value(_KEY_AUTO_SCALE_DEFAULT, _DEFAULT_AUTO_SCALE)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1")

    def set_auto_scale_default(self, value: bool) -> None:
        self._settings.setValue(_KEY_AUTO_SCALE_DEFAULT, bool(value))

    def reset_to_defaults(self) -> None:
        """§11 "Reset" — тек осы сервис иеленетін баптау кілттерін
        әдепкіге қайтарады. Домен/дерекқор деректеріне (студенттер,
        сыныптар, нәтижелер) ЕШБІР қатысы жоқ (§ "must NOT delete
        students/classrooms/experiments/results/measurement data")."""
        self._settings.remove(_KEY_AUTO_SCALE_DEFAULT)
        self._settings.remove(_KEY_SYNC_API_BASE_URL)
        self._settings.remove(_KEY_SYNC_ENABLED)

    # ---- Cloud Sync §25 "Configuration" ----------------------------------

    def get_sync_api_base_url(self) -> str:
        if self._settings.contains(_KEY_SYNC_API_BASE_URL):
            return str(self._settings.value(_KEY_SYNC_API_BASE_URL))
        deployed = load_deployment_config().sync_api_base_url
        return deployed or _DEFAULT_SYNC_API_BASE_URL

    def set_sync_api_base_url(self, value: str) -> None:
        """§ Phase 9 (Production Deployment) Part K "HTTPS / Network
        Model" — production таратуда сервер URL ЕШҚАШАН ``localhost``-қа
        мәжбүрленбейді, БІРАҚ ``http://``/``https://`` СХЕМАСЫ міндетті
        (§ "server URL validation" талабы) — жарамсыз мән ЕШҚАШАН
        үнсіз сақталмайды, ``ValueError`` шығарады. ``httpx``-тің ӨЗ
        әдепкі TLS сертификат тексеруі ``https://`` үшін автоматты
        қолданылады (§ "Do NOT disable certificate verification" —
        бұл функция ешбір жаңа TLS кодын қоспайды, тек схеманы
        тексереді)."""
        normalized = value.strip()
        if not (normalized.startswith("http://") or normalized.startswith("https://")):
            raise ValueError(
                f"Sync server URL мәні http:// немесе https:// схемасымен басталуы керек: {value!r}"
            )
        self._settings.setValue(_KEY_SYNC_API_BASE_URL, normalized)

    def get_sync_enabled(self) -> bool:
        if self._settings.contains(_KEY_SYNC_ENABLED):
            value = self._settings.value(_KEY_SYNC_ENABLED)
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("true", "1")
        deployed = load_deployment_config().sync_enabled
        if deployed is not None:
            return deployed
        return _DEFAULT_SYNC_ENABLED

    def set_sync_enabled(self, value: bool) -> None:
        self._settings.setValue(_KEY_SYNC_ENABLED, bool(value))

    def get_sync_request_timeout(self) -> float:
        value = self._settings.value(_KEY_SYNC_REQUEST_TIMEOUT, _DEFAULT_SYNC_REQUEST_TIMEOUT)
        return float(value)

    def set_sync_request_timeout(self, value: float) -> None:
        self._settings.setValue(_KEY_SYNC_REQUEST_TIMEOUT, float(value))

    def get_sync_pull_cursor(self, entity_type: str) -> datetime | None:
        """§18 "Pull Sync": incremental pull-дың соңғы cursor-ы (сервер
        уақыты, § "prefer server-controlled revisions/timestamps")."""
        value = self._settings.value(_KEY_SYNC_PULL_CURSOR_PREFIX + entity_type, None)
        if not value:
            return None
        return datetime.fromisoformat(str(value))

    def set_sync_pull_cursor(self, entity_type: str, value: datetime) -> None:
        self._settings.setValue(_KEY_SYNC_PULL_CURSOR_PREFIX + entity_type, value.isoformat())

    def get_measurement_batch_chunk_size(self) -> int:
        """§ Phase 4 "Chunk size must be configurable" — architecture-ты
        өзгертпей-ақ кейін реттеуге болатын жалғыз орын."""
        value = self._settings.value(
            _KEY_MEASUREMENT_BATCH_CHUNK_SIZE, _DEFAULT_MEASUREMENT_BATCH_CHUNK_SIZE
        )
        return int(value)

    def set_measurement_batch_chunk_size(self, value: int) -> None:
        self._settings.setValue(_KEY_MEASUREMENT_BATCH_CHUNK_SIZE, int(value))

    # ---- Phase 5: Connectivity-Aware Automatic Sync -----------------------

    def get_connectivity_check_interval_seconds(self) -> int:
        value = self._settings.value(
            _KEY_CONNECTIVITY_CHECK_INTERVAL_SECONDS, _DEFAULT_CONNECTIVITY_CHECK_INTERVAL_SECONDS
        )
        return int(value)

    def set_connectivity_check_interval_seconds(self, value: int) -> None:
        self._settings.setValue(_KEY_CONNECTIVITY_CHECK_INTERVAL_SECONDS, int(value))

    def get_teacher_auto_refresh_interval_seconds(self) -> int:
        value = self._settings.value(
            _KEY_TEACHER_AUTO_REFRESH_INTERVAL_SECONDS, _DEFAULT_TEACHER_AUTO_REFRESH_INTERVAL_SECONDS
        )
        return int(value)

    def set_teacher_auto_refresh_interval_seconds(self, value: int) -> None:
        self._settings.setValue(_KEY_TEACHER_AUTO_REFRESH_INTERVAL_SECONDS, int(value))

    def get_active_experiment_sync_interval_seconds(self) -> int:
        value = self._settings.value(
            _KEY_ACTIVE_EXPERIMENT_SYNC_INTERVAL_SECONDS, _DEFAULT_ACTIVE_EXPERIMENT_SYNC_INTERVAL_SECONDS
        )
        return int(value)

    def set_active_experiment_sync_interval_seconds(self, value: int) -> None:
        self._settings.setValue(_KEY_ACTIVE_EXPERIMENT_SYNC_INTERVAL_SECONDS, int(value))

    # ---- Phase 3: cached auth token ---------------------------------------

    def get_sync_auth_token(self) -> tuple[str, datetime, str, str] | None:
        """``(token, expires_at, role, sync_id)`` қайтарады — §7
        "Multiple Devices"/§2 "refresh strategy": әр құрылғы ӨЗ токенін
        жергілікті кэштейді. ``role``/``sync_id`` кэштелген токен ҚАЙ
        пайдаланушыға шығарылғанын білдіреді (§ ``set_sync_auth_
        token()`` докстрингі)."""
        token = self._settings.value(_KEY_SYNC_AUTH_TOKEN, None)
        expires_at_raw = self._settings.value(_KEY_SYNC_AUTH_TOKEN_EXPIRES_AT, None)
        role = self._settings.value(_KEY_SYNC_AUTH_TOKEN_ROLE, None)
        sync_id = self._settings.value(_KEY_SYNC_AUTH_TOKEN_SYNC_ID, None)
        if not token or not expires_at_raw or not role or not sync_id:
            return None
        return str(token), datetime.fromisoformat(str(expires_at_raw)), str(role), str(sync_id)

    def set_sync_auth_token(self, token: str, expires_at: datetime, role: str, sync_id: str) -> None:
        self._settings.setValue(_KEY_SYNC_AUTH_TOKEN, token)
        self._settings.setValue(_KEY_SYNC_AUTH_TOKEN_EXPIRES_AT, expires_at.isoformat())
        self._settings.setValue(_KEY_SYNC_AUTH_TOKEN_ROLE, role)
        self._settings.setValue(_KEY_SYNC_AUTH_TOKEN_SYNC_ID, sync_id)

    def clear_sync_auth_token(self) -> None:
        """§2 "logout/token clearing behavior"."""
        self._settings.remove(_KEY_SYNC_AUTH_TOKEN)
        self._settings.remove(_KEY_SYNC_AUTH_TOKEN_EXPIRES_AT)
        self._settings.remove(_KEY_SYNC_AUTH_TOKEN_ROLE)
        self._settings.remove(_KEY_SYNC_AUTH_TOKEN_SYNC_ID)

    def get_account_token(self) -> str:
        return str(self._settings.value(_KEY_ACCOUNT_TOKEN, "") or "")

    def get_account_role(self) -> str:
        return str(self._settings.value(_KEY_ACCOUNT_ROLE, "") or "")

    def get_account_public_id(self) -> str:
        return str(self._settings.value(_KEY_ACCOUNT_PUBLIC_ID, "") or "")

    def get_account_display_name(self) -> str:
        return str(self._settings.value(_KEY_ACCOUNT_NAME, "") or "")

    def set_account_session(
        self,
        *,
        token: str,
        account_id: str,
        email: str,
        display_name: str,
        role: str,
        public_id: str,
    ) -> None:
        self._settings.setValue(_KEY_ACCOUNT_TOKEN, token)
        self._settings.setValue(_KEY_ACCOUNT_ID, account_id)
        self._settings.setValue(_KEY_ACCOUNT_EMAIL, email)
        self._settings.setValue(_KEY_ACCOUNT_NAME, display_name)
        self._settings.setValue(_KEY_ACCOUNT_ROLE, role)
        self._settings.setValue(_KEY_ACCOUNT_PUBLIC_ID, public_id)

    def clear_account_session(self) -> None:
        self._settings.remove(_KEY_ACCOUNT_TOKEN)
        self._settings.remove(_KEY_ACCOUNT_ID)
        self._settings.remove(_KEY_ACCOUNT_EMAIL)
        self._settings.remove(_KEY_ACCOUNT_NAME)
        self._settings.remove(_KEY_ACCOUNT_ROLE)
        self._settings.remove(_KEY_ACCOUNT_PUBLIC_ID)
