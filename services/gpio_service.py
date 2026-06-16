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

    Supports pull-up or pull-down input wiring.
    For pull-up wiring (pin to GND when closed), active state is LOW.
    For pull-down wiring (pin to 3.3V when closed), active state is HIGH.
    """

    _POLL_INTERVAL = 0.05  # seconds between pin reads
    _DEBOUNCE_SECONDS = 0.2

    def __init__(
        self,
        pin: int = 26,
        callback_on=None,
        callback_off=None,
        debounce_seconds: float = _DEBOUNCE_SECONDS,
        pull_up: bool = True,
        active_low: bool = True,
    ):
        self._pin = pin
        self._callback_on = callback_on
        self._callback_off = callback_off
        self._debounce_seconds = debounce_seconds
        self._pull_up = pull_up
        self._active_low = active_low
        self._running = False
        self._thread: threading.Thread | None = None
        self._stable_state: int | None = None
        self._candidate_state: int | None = None
        self._candidate_since = 0.0

    # -- lifecycle --------------------------------------------------------------

    def start(self) -> None:
        """Start monitoring the GPIO pin in a background daemon thread."""
        if not _GPIO_AVAILABLE:
            logger.warning("RPi.GPIO unavailable; switch monitoring skipped.")
            return

        GPIO.setmode(GPIO.BCM)
        pull_mode = GPIO.PUD_UP if self._pull_up else GPIO.PUD_DOWN
        GPIO.setup(self._pin, GPIO.IN, pull_up_down=pull_mode)
        initial_state = GPIO.input(self._pin)
        self._stable_state = initial_state
        self._candidate_state = initial_state
        self._candidate_since = time.monotonic()

        self._running = True
        self._thread = threading.Thread(
            target=self._monitor,
            daemon=True,
            name="gpio-monitor",
        )
        self._thread.start()
        state_name = "HIGH" if initial_state == GPIO.HIGH else "LOW"
        pull_name = "PULL_UP" if self._pull_up else "PULL_DOWN"
        activity_name = "LOW" if self._active_low else "HIGH"
        logger.info(
            "GPIO monitoring started on BCM pin %d (mode=%s, active=%s, initial=%s)",
            self._pin,
            pull_name,
            activity_name,
            state_name,
        )

    def stop(self) -> None:
        """Stop the monitoring thread and release the GPIO pin."""
        self._running = False
        if _GPIO_AVAILABLE:
            try:
                GPIO.cleanup(self._pin)
            except Exception:
                logger.exception("Failed to cleanup GPIO pin %d", self._pin)
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

            now = time.monotonic()
            if state != self._candidate_state:
                self._candidate_state = state
                self._candidate_since = now
            elif (
                state != self._stable_state
                and (now - self._candidate_since) >= self._debounce_seconds
            ):
                self._stable_state = state
                if self._is_active_state(state):
                    logger.info("Latching switch ON (GPIO %d active)", self._pin)
                    if self._callback_on:
                        self._callback_on()
                else:
                    logger.info("Latching switch OFF (GPIO %d inactive)", self._pin)
                    if self._callback_off:
                        self._callback_off()

            time.sleep(self._POLL_INTERVAL)

    def _is_active_state(self, state: int) -> bool:
        return state == GPIO.LOW if self._active_low else state == GPIO.HIGH
