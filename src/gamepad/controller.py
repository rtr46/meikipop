# src/gamepad/controller.py
#
# Reads physical gamepad events via pygame.
#
# In normal (pass-through) mode every button / axis / hat event is
# forwarded to a virtual Xbox 360 controller (vgamepad / ViGEmBus) so
# the game continues to receive all inputs unchanged.
#
# When the user presses the configured toggle button the controller
# enters navigation mode.  In navigation mode:
#   • gamepad events are NOT forwarded to the virtual pad
#   • the virtual pad is reset (prevents stuck buttons in the game)
#   • d-pad events are routed to NavigationState for character stepping
#   • LB / RB are routed to NavigationState for word-level stepping
#   • Y (configurable) toggles the furigana overlay
#   • B (configurable) immediately exits navigation mode
#
# Availability:
#   pip install pygame vgamepad
#   ViGEmBus driver: https://github.com/nefarius/ViGEmBus/releases/latest
#
# All imports are lazy so the rest of the application is unaffected when
# these packages are not installed.

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Human-readable labels used in the settings UI
BUTTON_LABELS = {
    0: "A",
    1: "B",
    2: "X",
    3: "Y",
    4: "LB",
    5: "RB",
    6: "Back",
    7: "Start",
    8: "L3",
    9: "R3",
}


# ---------------------------------------------------------------------------
# Availability helpers
# ---------------------------------------------------------------------------

def is_pygame_available() -> bool:
    try:
        import pygame  # noqa: F401
        return True
    except ImportError:
        return False


def is_vgamepad_available() -> bool:
    """
    Returns True when vgamepad is importable AND ViGEmBus is installed.
    Instantiates a temporary pad to confirm the driver is present.
    """
    try:
        import vgamepad
        pad = vgamepad.VX360Gamepad()
        del pad
        return True
    except Exception:
        return False


VIGEMBUS_DOWNLOAD_URL = "https://github.com/nefarius/ViGEmBus/releases/latest"


# ---------------------------------------------------------------------------
# Controller thread
# ---------------------------------------------------------------------------

class GamepadController(threading.Thread):
    """
    Daemon thread that owns the pygame event loop and the virtual pad.

    Constructor arguments
    ─────────────────────
    shared_state   – the application's SharedState (for .running flag)
    input_loop     – InputLoop instance (reads .gamepad_navigation_active)
    navigation     – NavigationState instance (receives nav commands)
    """

    def __init__(self, shared_state, input_loop, navigation):
        super().__init__(daemon=True, name="GamepadController")
        self.shared_state = shared_state
        self.input_loop = input_loop
        self.navigation = navigation

        self._virtual_pad = None
        self._joystick = None

        # Cache last axis values so we can call left_joystick(x, y) atomically
        self._left_stick = [0, 0]  # [x, y]  in vgamepad range −32768…32767
        self._right_stick = [0, 0]
        self._left_trigger = 0  # 0…255
        self._right_trigger = 0

    # ------------------------------------------------------------------
    # Thread entry point
    # ------------------------------------------------------------------

    def run(self):
        from src.config.config import config

        if not config.gamepad_enabled:
            logger.debug("Gamepad support disabled in config – controller thread exiting.")
            return

        if not is_pygame_available():
            logger.error("pygame is not installed. Gamepad support unavailable.")
            return

        import pygame

        pygame.init()
        pygame.joystick.init()

        self._try_init_virtual_pad()

        logger.info("GamepadController thread started.")

        while self.shared_state.running:
            # ---- Joystick (re-)connection --------------------------------
            if pygame.joystick.get_count() == 0:
                if self._joystick is not None:
                    logger.info("Gamepad disconnected.")
                    self._joystick = None
                time.sleep(1.0)
                pygame.joystick.quit()
                pygame.joystick.init()
                continue

            if self._joystick is None:
                idx = min(config.gamepad_joystick_index,
                          pygame.joystick.get_count() - 1)
                self._joystick = pygame.joystick.Joystick(idx)
                self._joystick.init()
                logger.info("Gamepad connected: %s (index %d)",
                            self._joystick.get_name(), idx)

            # ---- Event pump ---------------------------------------------
            for event in pygame.event.get():
                if not self.shared_state.running:
                    break
                self._handle_event(event, config)

            time.sleep(0.005)  # ~200 Hz polling

        pygame.quit()
        logger.debug("GamepadController thread stopped.")

    # ------------------------------------------------------------------
    # Event routing
    # ------------------------------------------------------------------

    def _handle_event(self, event, config):
        import pygame

        nav = self.input_loop.gamepad_navigation_active

        # ---- Button down -----------------------------------------------
        if event.type == pygame.JOYBUTTONDOWN:
            btn = event.button

            # Toggle / enter navigation mode
            if btn == config.gamepad_toggle_button:
                self._toggle_nav_mode()
                return

            if nav:
                # Quick-exit
                if btn == config.gamepad_exit_button:
                    self._exit_nav_mode()
                    return
                # Furigana overlay toggle
                if btn == config.gamepad_furigana_button:
                    self.navigation.toggle_furigana()
                    return
                # Word-level navigation via configured buttons (default LB/RB)
                if btn == config.gamepad_word_prev_button:
                    self.navigation.step_word(-1)
                    return
                if btn == config.gamepad_word_next_button:
                    self.navigation.step_word(1)
                    return
                # All other buttons are consumed (not forwarded) in nav mode
                return

            self._vpad_button_down(btn)

        # ---- Button up -------------------------------------------------
        elif event.type == pygame.JOYBUTTONUP:
            btn = event.button
            if nav:
                return  # consume silently
            self._vpad_button_up(btn)

        # ---- D-pad (hat) -----------------------------------------------
        elif event.type == pygame.JOYHATMOTION:
            hat_x, hat_y = event.value

            if nav:
                # Horizontal d-pad → character navigation
                if hat_x == -1:
                    self.navigation.step_char(-1)
                elif hat_x == 1:
                    self.navigation.step_char(1)
                # Vertical d-pad also navigates characters
                # (useful for vertical text laid out top-to-bottom)
                if hat_y == 1:
                    self.navigation.step_char(-1)  # up = previous
                elif hat_y == -1:
                    self.navigation.step_char(1)  # down = next
                return

            self._vpad_hat(hat_x, hat_y)

        # ---- Analog axes -----------------------------------------------
        elif event.type == pygame.JOYAXISMOTION:
            if nav:
                return  # consume; stick/trigger inputs suppressed in nav mode
            self._vpad_axis(event.axis, event.value)

        # ---- Other events (ball, etc.) ---------------------------------
        # ignored

    # ------------------------------------------------------------------
    # Navigation mode transitions
    # ------------------------------------------------------------------

    def _toggle_nav_mode(self):
        if self.input_loop.gamepad_navigation_active:
            self._exit_nav_mode()
        else:
            self._enter_nav_mode()

    def _enter_nav_mode(self):
        logger.debug("Entering gamepad navigation mode.")
        # Reset virtual pad first to prevent any stuck inputs in the game
        if self._virtual_pad:
            try:
                self._virtual_pad.reset()
                self._virtual_pad.update()
            except Exception:
                pass
        self.input_loop.gamepad_navigation_active = True
        self.navigation.on_enter()

    def _exit_nav_mode(self):
        logger.debug("Exiting gamepad navigation mode.")
        # Set flag FIRST to prevent race condition with popup timer
        # Popup's timer checks this flag every 10ms - must be False
        # BEFORE we call on_exit() which emits queued signals
        self.input_loop.gamepad_navigation_active = False
        # Then hide popup and overlays
        self.navigation.on_exit()
        # Trigger a fresh screenshot to restart OCR loop
        self.input_loop.trigger_screenshot()
        # Clean slate for the virtual pad when returning to the game
        if self._virtual_pad:
            try:
                self._virtual_pad.reset()
                self._virtual_pad.update()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Virtual pad initialisation
    # ------------------------------------------------------------------

    def _try_init_virtual_pad(self):
        try:
            import vgamepad
            self._virtual_pad = vgamepad.VX360Gamepad()
            logger.info("Virtual gamepad (ViGEmBus) initialised successfully.")
        except Exception as exc:
            logger.warning(
                "Could not initialise virtual gamepad: %s  "
                "Pass-through disabled – the game will NOT receive inputs "
                "while meikipop navigation mode is inactive.  "
                "Install ViGEmBus from %s and restart.",
                exc, VIGEMBUS_DOWNLOAD_URL
            )
            self._virtual_pad = None

    # ------------------------------------------------------------------
    # vgamepad forwarding helpers
    # ------------------------------------------------------------------

    # Xbox 360 button map: pygame button index → vgamepad constant
    @staticmethod
    def _vpad_button_constant(btn: int):
        try:
            import vgamepad
            _MAP = {
                0: vgamepad.XUSB_BUTTON.XUSB_GAMEPAD_A,
                1: vgamepad.XUSB_BUTTON.XUSB_GAMEPAD_B,
                2: vgamepad.XUSB_BUTTON.XUSB_GAMEPAD_X,
                3: vgamepad.XUSB_BUTTON.XUSB_GAMEPAD_Y,
                4: vgamepad.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
                5: vgamepad.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
                6: vgamepad.XUSB_BUTTON.XUSB_GAMEPAD_BACK,
                7: vgamepad.XUSB_BUTTON.XUSB_GAMEPAD_START,
                8: vgamepad.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,
                9: vgamepad.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
            }
            return _MAP.get(btn)
        except Exception:
            return None

    def _vpad_button_down(self, btn: int):
        if not self._virtual_pad:
            return
        const = self._vpad_button_constant(btn)
        if const is None:
            return
        try:
            self._virtual_pad.press_button(button=const)
            self._virtual_pad.update()
        except Exception as exc:
            logger.debug("vpad button_down %d: %s", btn, exc)

    def _vpad_button_up(self, btn: int):
        if not self._virtual_pad:
            return
        const = self._vpad_button_constant(btn)
        if const is None:
            return
        try:
            self._virtual_pad.release_button(button=const)
            self._virtual_pad.update()
        except Exception as exc:
            logger.debug("vpad button_up %d: %s", btn, exc)

    def _vpad_hat(self, hat_x: int, hat_y: int):
        """Forward a d-pad hat event to the virtual pad."""
        if not self._virtual_pad:
            return
        try:
            import vgamepad
            B = vgamepad.XUSB_BUTTON
            # Release all four d-pad directions, then press the active ones
            for d in (B.XUSB_GAMEPAD_DPAD_LEFT, B.XUSB_GAMEPAD_DPAD_RIGHT,
                      B.XUSB_GAMEPAD_DPAD_UP, B.XUSB_GAMEPAD_DPAD_DOWN):
                self._virtual_pad.release_button(button=d)
            if hat_x == -1:
                self._virtual_pad.press_button(button=B.XUSB_GAMEPAD_DPAD_LEFT)
            elif hat_x == 1:
                self._virtual_pad.press_button(button=B.XUSB_GAMEPAD_DPAD_RIGHT)
            if hat_y == 1:
                self._virtual_pad.press_button(button=B.XUSB_GAMEPAD_DPAD_UP)
            elif hat_y == -1:
                self._virtual_pad.press_button(button=B.XUSB_GAMEPAD_DPAD_DOWN)
            self._virtual_pad.update()
        except Exception as exc:
            logger.debug("vpad hat (%d,%d): %s", hat_x, hat_y, exc)

    def _vpad_axis(self, axis: int, value: float):
        """
        Forward an analog axis event to the virtual pad.

        Axis mapping (standard Xbox controller via SDL/pygame on Windows):
          0 = Left stick X   1 = Left stick Y   (pygame ±1.0)
          2 = Left trigger   3 = Right trigger  (pygame −1.0 released → +1.0 full)
          4 = Right stick X  5 = Right stick Y  (pygame ±1.0)
        """
        if not self._virtual_pad:
            return
        try:
            stick_val = int(value * 32767)
            # Triggers: pygame −1.0…+1.0 → vgamepad 0…255
            trig_val = int((value + 1.0) / 2.0 * 255)

            if axis == 0:
                self._left_stick[0] = stick_val
                self._virtual_pad.left_joystick(
                    x_value=self._left_stick[0], y_value=self._left_stick[1])
            elif axis == 1:
                # pygame Y is inverted vs XInput
                self._left_stick[1] = -stick_val
                self._virtual_pad.left_joystick(
                    x_value=self._left_stick[0], y_value=self._left_stick[1])
            elif axis == 2:
                self._left_trigger = trig_val
                self._virtual_pad.left_trigger(value=self._left_trigger)
            elif axis == 3:
                self._right_trigger = trig_val
                self._virtual_pad.right_trigger(value=self._right_trigger)
            elif axis == 4:
                self._right_stick[0] = stick_val
                self._virtual_pad.right_joystick(
                    x_value=self._right_stick[0], y_value=self._right_stick[1])
            elif axis == 5:
                self._right_stick[1] = -stick_val
                self._virtual_pad.right_joystick(
                    x_value=self._right_stick[0], y_value=self._right_stick[1])

            self._virtual_pad.update()
        except Exception as exc:
            logger.debug("vpad axis %d=%.3f: %s", axis, value, exc)

    # ------------------------------------------------------------------
    # Settings hot-reload
    # ------------------------------------------------------------------

    def reapply_settings(self):
        """Called from the main thread after settings are saved."""
        from src.config.config import config
        # If gamepad was just disabled, exit nav mode cleanly
        if not config.gamepad_enabled and self.input_loop.gamepad_navigation_active:
            self._exit_nav_mode()
        # Joystick index change takes effect on next reconnect
        self._joystick = None
