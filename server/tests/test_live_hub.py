from server.app.services.live_hub import LiveHub


def test_samples_reach_only_watchers() -> None:
    hub = LiveHub()
    mine: list[dict] = []
    other: list[dict] = []
    hub.add_viewer("v1", frozenset({"stu-1"}), mine.append)
    hub.add_viewer("v2", frozenset({"stu-2"}), other.append)
    accepted = hub.publish_samples(
        "stu-1",
        experiment_id="ohms-law",
        session_id="s1",
        points=[{"t": "2026-09-04T12:00:00Z", "values": {"voltage": 1.2}}],
    )
    assert accepted == 1
    assert len(mine) == 1
    assert mine[0]["type"] == "samples"
    assert mine[0]["account_id"] == "stu-1"
    assert other == []


def test_teacher_does_not_see_unwatched_student() -> None:
    hub = LiveHub()
    seen: list[dict] = []
    hub.add_viewer("teacher", frozenset({"linked-stu"}), seen.append)
    hub.publish_samples(
        "independent-stu",
        experiment_id="ohms-law",
        session_id="s1",
        points=[{"t": "2026-09-04T12:00:00Z", "values": {"voltage": 3.0}}],
    )
    assert seen == []


def test_late_viewer_gets_buffer() -> None:
    hub = LiveHub(max_buffer_seconds=120)
    hub.publish_samples(
        "stu-1",
        experiment_id="ohms-law",
        session_id="s1",
        points=[{"t": "2026-09-04T12:00:00Z", "values": {"voltage": 1.0}}],
    )
    replayed: list[dict] = []
    hub.add_viewer("late", frozenset({"stu-1"}), replayed.append)
    for frame in hub.buffer_for("stu-1"):
        replayed.append(frame)
    assert any(item.get("type") == "samples" for item in replayed)


def test_rate_limit_drops_excess_points() -> None:
    hub = LiveHub(max_points_per_sec=2)
    hub.publish_samples(
        "stu-1",
        experiment_id="ohms-law",
        session_id="s1",
        points=[{"t": f"2026-09-04T12:00:00.{i:03d}Z", "values": {"voltage": i}} for i in range(10)],
    )
    # First call may accept up to 2; the rest of this burst is dropped.
    accepted = hub.publish_samples(
        "stu-1",
        experiment_id="ohms-law",
        session_id="s1",
        points=[{"t": "2026-09-04T12:00:01Z", "values": {"voltage": 9}}],
    )
    assert accepted == 0


def test_new_publisher_replaces_old_send() -> None:
    hub = LiveHub()
    old: list[dict] = []
    new: list[dict] = []
    # Bound methods are recreated on each attribute access; keep refs for identity.
    old_send = old.append
    new_send = new.append
    previous = hub.set_publisher("stu-1", old_send)
    assert previous is None
    previous = hub.set_publisher("stu-1", new_send)
    assert previous is old_send
