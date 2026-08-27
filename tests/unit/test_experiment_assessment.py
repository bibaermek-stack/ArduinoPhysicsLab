"""experiment_assessment (Phase 39A) — сұрақ конфигурациясының domain
модель тесттері: жарамды/жарамсыз жағдайлар, ID қайталану тексерісі.
"""

from domain.entities.experiment_assessment import (
    ExperimentAssessmentDefinition,
    MultipleChoiceQuestion,
    OpenResponseQuestion,
    ReflectionQuestion,
)


def _mcq(id_="q1", options=("A", "B"), correct=0) -> MultipleChoiceQuestion:
    return MultipleChoiceQuestion(id=id_, prompt="Prompt?", options=options, correct_option_index=correct)


# ---- MultipleChoiceQuestion -------------------------------------------------


def test_valid_multiple_choice_question() -> None:
    question = _mcq()
    assert question.validate() == []


def test_multiple_choice_question_empty_id_invalid() -> None:
    question = MultipleChoiceQuestion(id="", prompt="P?", options=("A", "B"), correct_option_index=0)
    assert any("id" in e for e in question.validate())


def test_multiple_choice_question_empty_prompt_invalid() -> None:
    question = MultipleChoiceQuestion(id="q1", prompt="", options=("A", "B"), correct_option_index=0)
    assert any("prompt" in e for e in question.validate())


def test_multiple_choice_question_too_few_options_invalid() -> None:
    question = MultipleChoiceQuestion(id="q1", prompt="P?", options=("A",), correct_option_index=0)
    assert any("options" in e for e in question.validate())


def test_multiple_choice_question_correct_index_out_of_range_invalid() -> None:
    question = MultipleChoiceQuestion(id="q1", prompt="P?", options=("A", "B"), correct_option_index=5)
    assert any("correct_option_index" in e for e in question.validate())


def test_multiple_choice_question_negative_correct_index_invalid() -> None:
    question = MultipleChoiceQuestion(id="q1", prompt="P?", options=("A", "B"), correct_option_index=-1)
    assert any("correct_option_index" in e for e in question.validate())


def test_multiple_choice_question_zero_points_invalid() -> None:
    question = MultipleChoiceQuestion(
        id="q1", prompt="P?", options=("A", "B"), correct_option_index=0, points=0
    )
    assert any("points" in e for e in question.validate())


# ---- OpenResponseQuestion / ReflectionQuestion ------------------------------


def test_open_response_question_empty_prompt_invalid() -> None:
    question = OpenResponseQuestion(id="o1", prompt="")
    assert any("prompt" in e for e in question.validate())


def test_reflection_question_empty_id_invalid() -> None:
    question = ReflectionQuestion(id="", prompt="P?")
    assert any("id" in e for e in question.validate())


def test_open_response_and_reflection_valid() -> None:
    assert OpenResponseQuestion(id="o1", prompt="P?").validate() == []
    assert ReflectionQuestion(id="r1", prompt="P?").validate() == []


# ---- ExperimentAssessmentDefinition -----------------------------------------


def test_valid_assessment_definition() -> None:
    assessment = ExperimentAssessmentDefinition(
        level1_questions=(_mcq("q1"),),
        level2_questions=(OpenResponseQuestion(id="o1", prompt="P?"),),
        level3_questions=(ReflectionQuestion(id="r1", prompt="P?"),),
    )
    assert assessment.validate() == []


def test_assessment_requires_at_least_one_level1_question() -> None:
    assessment = ExperimentAssessmentDefinition()
    assert any("level1_questions" in e for e in assessment.validate())


def test_assessment_rejects_duplicate_question_ids_across_levels() -> None:
    assessment = ExperimentAssessmentDefinition(
        level1_questions=(_mcq("dup"),),
        level2_questions=(OpenResponseQuestion(id="dup", prompt="P?"),),
    )
    errors = assessment.validate()
    assert any("dup" in e and "қайталанды" in e for e in errors)


def test_assessment_propagates_nested_question_errors() -> None:
    assessment = ExperimentAssessmentDefinition(level1_questions=(_mcq("q1", options=("A",)),))
    errors = assessment.validate()
    assert any("options" in e for e in errors)


def test_assessment_self_assessment_bounds_must_be_increasing() -> None:
    assessment = ExperimentAssessmentDefinition(
        level1_questions=(_mcq(),), self_assessment_min=5, self_assessment_max=1
    )
    assert any("self_assessment_min" in e for e in assessment.validate())


def test_assessment_default_self_assessment_range_is_one_to_five() -> None:
    assessment = ExperimentAssessmentDefinition(level1_questions=(_mcq(),))
    assert assessment.self_assessment_min == 1
    assert assessment.self_assessment_max == 5
