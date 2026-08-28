"""Қолданба бойында қолданылатын тұрақтылар.

Мәндер кодта нақты қолданылатын протокол/жабдық шектерінен алынған
(``docs/serial_protocol.md``, firmware ``Serial.begin(115200)``,
``SerialWorker`` буфері, ``CalculationEngine`` бөлу қорғанысы).
"""

# USB Serial — Arduino эскиздері мен Баптаулар бетіндегі канондық baud.
SERIAL_BAUD_RATE = 115200
SERIAL_BAUD_RATES = (9600, 57600, SERIAL_BAUD_RATE)

# SerialWorker receive буферінің жоғарғы шегі (байт).
SERIAL_RECEIVE_BUFFER_MAX_BYTES = 64 * 1024

# R = U/I: ток осы мәннен кіші болса кедергі есептелмейді.
CURRENT_EPSILON = 1e-9
