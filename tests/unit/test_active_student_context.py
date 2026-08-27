"""ActiveStudentContext — жеңіл frozen dataclass контрактісі."""

from domain.entities.active_student_context import ActiveStudentContext


def test_context_holds_classroom_and_student_ids() -> None:
    context = ActiveStudentContext(classroom_id="c1", student_id="s1")
    assert context.classroom_id == "c1"
    assert context.student_id == "s1"


def test_context_equality_by_value() -> None:
    a = ActiveStudentContext(classroom_id="c1", student_id="s1")
    b = ActiveStudentContext(classroom_id="c1", student_id="s1")
    assert a == b
