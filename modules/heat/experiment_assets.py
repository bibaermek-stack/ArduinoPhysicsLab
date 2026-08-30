"""Жылу модулінің ортақ (тәжірибелер арасында қайталанатын) көмекші
деректері.

Electricity/experiment_assets.py-дегі ``reflection_questions()``-пен
мағыналық тұрғыда бірдей (3-деңгей сұрақтары барлық тәжірибеде бірдей) —
модульдер арасында тәуелділік құрмау үшін осында жеке сақталады (әр
физика модулі өз assets-ін иеленеді, ``modules/electricity/channels.py``
vs ``modules/heat/channels.py``-мен бірдей конвенция).
"""

from domain.entities.experiment_assessment import ReflectionQuestion


def reflection_questions(id_prefix: str) -> tuple[ReflectionQuestion, ...]:
    """3-деңгей (Рефлексия) сұрақтары барлық тәжірибеде мағыналық түрде бірдей."""
    return (
        ReflectionQuestion(id=f"{id_prefix}-l3-1", prompt="Бүгінгі тәжірибеде не үйрендіңіз?"),
        ReflectionQuestion(id=f"{id_prefix}-l3-2", prompt="Қандай қиындық кездесті?"),
        ReflectionQuestion(id=f"{id_prefix}-l3-3", prompt="Тәжірибенің қай бөлімі ең қызықты болды?"),
    )
