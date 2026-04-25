import time
import threading
import logging

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
    _GPIO_AVAILABLE = True
except ImportError:
    logger.warning("RPi.GPIO not available — GPIO monitoring disabled")
    _GPIO_AVAILABLE = False


class GPIOService:
    """Monitors a latching switch on a GPIO pin and fires callbacks on state change.

    The switch is expected to be wired between the GPIO pin and 3.3 V.
    An internal pull-down resistor is enabled so the pin reads LOW when the
    switch is open and HIGH when it is closed (latched on).
    """

    _POLL_INTERVAL = 0.1  # seconds between pin reads

    def __init__(self, pin: int = 17, callback_on=None, callback_off=None):
        self._pin = pin
        self._callback_on = callback_on
        self._callback_off = callback_off
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_state: int | None = None

    # -- lifecycle --------------------------------------------------------------

    def start(self) -> None:
        """Start monitoring the GPIO pin in a background daemon thread."""
        if not _GPIO_AVAILABLE:
            logger.warning("RPi.GPIO unavailable; switch monitoring skipped.")
            return

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self._pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

        self._running = True
        self._thread = threading.Thread(
            target=self._monitor,
            daemon=True,
            name="gpio-monitor",
        )
        self._thread.start()
        logger.info("GPIO monitoring started on BCM pin %d", self._pin)

    def stop(self) -> None:
        """Stop the monitoring thread and release the GPIO pin."""
        self._running = False
        if _GPIO_AVAILABLE:
            try:
                GPIO.cleanup(self._pin)
            except Exception:
                pass
        logger.info("GPIO monitoring stopped.")

    # -- internal loop ----------------------------------------------------------

    def _monitor(self) -> None:
        while self._running:
            try:
                state = GPIO.input(self._pin)
            except Exception:
                logger.exception("Error reading GPIO pin %d", self._pin)
                time.sleep(1)
                continue

            if state != self._last_state:
                self._last_state = state
                if state == GPIO.HIGH:
                    logger.info("Latching switch ON (GPIO %d HIGH)", self._pin)
                    if self._callback_on:
                        self._callback_on()
                else:
                    logger.info("Latching switch OFF (GPIO %d LOW)", self._pin)
                    if self._callback_off:
                        self._callback_off()

            time.sleep(self._POLL_INTERVAL)
