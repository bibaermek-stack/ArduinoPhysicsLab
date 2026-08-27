"""SyncStatus — жалпы қосылым/синхрондау күйі (Offline-First + Cloud
Sync Foundation фазасы, §13 "Connectivity Service").

§ ``SyncState``-пен (жеке жазбаның күйі) ШАТАСТЫРМАУ КЕРЕК — бұл
БҮКІЛ қолданбаның ағымдағы sync/желі күйі, Sidebar индикаторында
көрсетіледі (§14).
"""

from enum import Enum


class SyncStatus(Enum):
    OFFLINE = "offline"
    ONLINE = "online"
    SYNCING = "syncing"
    SYNCED = "synced"
    SYNC_ERROR = "sync_error"
    # § Phase 3 (Production Authentication + Authorization): сервер
    # қолжетімді, БІРАҚ жергілікті сақталған credential (PIN/оқушы коды)
    # серверде қабылданбады НЕМЕСЕ ешкім жергілікті логин жасамаған —
    # ``SYNC_ERROR``-дан ӘДЕЙІ бөлек (§8 "mark sync as requiring login/
    # authentication" — UI-ге "серверде қате" емес, "қайта кіру керек"
    # деп нақты хабарлау үшін).
    AUTH_REQUIRED = "auth_required"
