"""ChannelAggregator — бірнеше физикалық құрылғыдан (портан) келген
ішінара (partial) channel мәндерін бір толық snapshot-қа біріктіретін
таза domain сервисі.

Strict timestamp synchronization жасамайды — "соңғы белгілі мән +
monotonic timestamp" үлгісін қолданады: әр арнаның ең соңғы мәні мен
осы мән қашан келгені сақталады, барлық күтілетін (expected) арна
белгіленген staleness терезесі ішінде "жаңа" болған сәтте ғана толық
sөздік қайтарылады.

Бұл сервис тек completeness/freshness үшін жауап береді — NaN/Infinity
секілді физикалық валидацияны қайталамайды (ол ``DataValidator``-дің
жауапкершілігі, өзгеріссіз қалады).
"""

import time


class ChannelAggregator:
    """Күтілетін (``expected_channels``) арналардың соңғы мәндерін
    ұстап, барлығы staleness терезесі ішінде жаңа болғанда толық
    snapshot қайтаратын сервис.
    """

    def __init__(
        self,
        expected_channels: frozenset[str],
        staleness_seconds: float = 0.5,
    ) -> None:
        self._expected_channels = frozenset(expected_channels)
        self._staleness_seconds = staleness_seconds
        self._latest: dict[str, tuple[float, float]] = {}

    def update(
        self, channel_key: str, value: float, timestamp: float | None = None
    ) -> dict[str, float] | None:
        """``channel_key``-дің жаңа мәнін тіркейді (уақыт мөрімен бірге).

        ``channel_key`` ``expected_channels`` ішінде болмаса, тіркелмейді
        және ``None`` қайтарылады. ``timestamp`` берілмесе, ``time.monotonic()``
        қолданылады.

        Осы жаңартудан кейін барлық ``expected_channels`` staleness
        терезесі ішінде жаңа болса, әр арнаның соңғы мәнінен тұратын
        толық ``dict``-ті қайтарады; әйтпесе ``None``.
        """
        if channel_key not in self._expected_channels:
            return None

        now = timestamp if timestamp is not None else time.monotonic()
        self._latest[channel_key] = (value, now)

        return self._snapshot_if_fresh(now)

    def missing_channels(self) -> frozenset[str]:
        """Осы сәтте жоқ немесе stale (ескірген) арналардың жиынын қайтарады."""
        now = time.monotonic()
        return frozenset(
            key
            for key in self._expected_channels
            if key not in self._latest or now - self._latest[key][1] > self._staleness_seconds
        )

    def reset(self) -> None:
        """Барлық сақталған мәндерді тазалайды (Stop/Clear/тәжірибе ауысу кезінде)."""
        self._latest.clear()

    def _snapshot_if_fresh(self, now: float) -> dict[str, float] | None:
        if not self._expected_channels:
            return None

        for key in self._expected_channels:
            cached = self._latest.get(key)
            if cached is None or now - cached[1] > self._staleness_seconds:
                return None

        return {key: self._latest[key][0] for key in self._expected_channels}
