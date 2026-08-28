"""Қолданбаға тән exception иерархиясы."""


class AppException(Exception):
    """Arduino Physics Lab қателерінің базалық класы."""


class SerialError(AppException):
    """USB Serial байланысы/пакет қабылдау қатесі."""


class ExportError(AppException):
    """CSV/Excel/PDF экспорт қатесі (белгісіз формат, жазу сәтсіз)."""


class ValidationError(AppException):
    """Өлшем мәнін SensorChannel ережелері бойынша тексеру қатесі."""
