# Modified from AuroraWright's OwOCR
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst, Gio
from PIL import Image

from meikipop.utils import hyprland
from meikipop.utils.paths import paths

import mss as real_mss
from mss.exception import ScreenShotError
from mss.screenshot import ScreenShot, Size
from mss.models import Monitor

logger = logging.getLogger(__name__)  # todo add proper info and debug logs

screencast = None
screencast_lock = threading.Lock()

token_file = Path(paths.cache_dir) / '.ocr_screencapture_token'
persist_token = str(uuid.UUID(int=0))

if token_file.exists():
    with open(token_file, "r") as file:
        persist_token = file.read().strip()


def _in_flatpak():
    return os.path.exists('/.flatpak-info')


def _grim_command():
    """Return the argv prefix used to run grim, or None when unavailable."""
    if _in_flatpak():
        if shutil.which('flatpak-spawn') is None:
            return None
        return ['flatpak-spawn', '--host', 'grim']
    if shutil.which('grim') is None:
        return None
    return ['grim']


_grim_available_cache = None


def _grim_available():
    """Return True when grim can be invoked for Wayland screen capture.

    Inside the Flatpak sandbox grim cannot use wlr-screencopy itself, but the
    host copy can through ``flatpak-spawn --host`` (requires the
    ``org.freedesktop.Flatpak`` talk permission). Only the command's
    availability is checked here, so this stays fast while the screen is
    locked; capture failures are handled by the screenshot loop.
    """
    global _grim_available_cache
    if _grim_available_cache is not None:
        return _grim_available_cache

    prefix = _grim_command()
    if not prefix or not hyprland.available():
        _grim_available_cache = False
        return False

    try:
        result = subprocess.run(
            prefix + ['-h'],
            capture_output=True, timeout=5,
            stdin=subprocess.DEVNULL,
        )
        # grim -h exits successfully and prints its usage text.
        available = result.returncode == 0 and b'Usage: grim' in result.stdout
    except Exception:
        logger.debug("grim availability test failed", exc_info=True)
        available = False

    _grim_available_cache = available
    if available:
        logger.info("Using grim (from the host) for Wayland screen capture")
    else:
        logger.info("grim is not usable; falling back to the screen-cast portal")
    return available


def _parse_ppm(data):
    """Parse a binary P6 PPM into RGB bytes."""
    pos = 0

    def next_token():
        nonlocal pos
        while pos < len(data):
            char = data[pos:pos + 1]
            if char.isspace():
                pos += 1
            elif char == b'#':
                newline = data.find(b'\n', pos)
                pos = len(data) if newline < 0 else newline + 1
            else:
                break
        start = pos
        while pos < len(data):
            char = data[pos:pos + 1]
            if char.isspace() or char == b'#':
                break
            pos += 1
        return data[start:pos]

    if next_token() != b'P6':
        raise ScreenShotError('grim did not return a binary PPM image')
    width = int(next_token())
    height = int(next_token())
    maxval = int(next_token())
    if maxval != 255:
        raise ScreenShotError(f'Unsupported PPM max value: {maxval}')

    # Exactly one whitespace character separates the header from the pixels.
    if data[pos:pos + 2] == b'\r\n':
        pos += 2
    elif data[pos:pos + 1] in (b'\n', b'\r', b' ', b'\t'):
        pos += 1

    expected = width * height * 3
    pixels = data[pos:pos + expected]
    if len(pixels) != expected:
        raise ScreenShotError('grim returned truncated pixel data')
    return pixels, width, height


def _capture_with_grim(left, top, width, height):
    prefix = _grim_command()
    if not prefix:
        raise ScreenShotError('grim is not available')

    grim_args = [
        '-s', '1',
        '-g', f'{left},{top} {width}x{height}',
        '-t', 'ppm',
        '-',
    ]

    if _in_flatpak():
        # The host grim process is not a child of this sandbox, so a Python
        # timeout cannot reliably kill it. Have the host's timeout(1) do it.
        command = prefix[:2] + ['timeout', '4'] + prefix[2:] + grim_args
    else:
        command = prefix + grim_args

    result = subprocess.run(
        command,
        capture_output=True,
        timeout=8 if _in_flatpak() else 5,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        message = result.stderr.decode('utf-8', errors='replace').strip()
        if result.returncode == 124:
            message = 'grim timed out (is the screen locked?)'
        raise ScreenShotError(message or 'grim failed to capture the screen')

    pixels, width, height = _parse_ppm(result.stdout)
    # ScreenShot expects BGRx raw pixels (the x byte is ignored downstream).
    bgra = Image.frombytes('RGB', (width, height), pixels).tobytes('raw', 'BGRX')
    return bytearray(bgra), width, height


_layout = None
_layout_lock = threading.Lock()


def _full_layout(monitors):
    left = min(int(monitor['x']) for monitor in monitors)
    top = min(int(monitor['y']) for monitor in monitors)
    right = max(int(monitor['x']) + int(monitor['width']) for monitor in monitors)
    bottom = max(int(monitor['y']) + int(monitor['height']) for monitor in monitors)
    return {
        'left': left,
        'top': top,
        'width': right - left,
        'height': bottom - top,
    }


def _shared_layout(monitors):
    """Return the geometry dict shared with ScreenManager and hit scanning.

    It is updated in place in ``GrimWaylandShim.grab`` so the object held by
    ScreenManager always describes the monitor that was actually captured.
    """
    global _layout
    with _layout_lock:
        if _layout is None:
            _layout = _full_layout(monitors)
        return _layout


class GrimWaylandShim:
    """Capture the monitor under the cursor through the host's grim binary."""

    def __init__(self):
        monitors = hyprland.get_monitors()
        if not monitors:
            raise ScreenShotError('Could not read the Hyprland monitor layout')
        _shared_layout(monitors)

    @property
    def monitors(self):
        monitors = hyprland.get_monitors()
        if not monitors:
            return [_layout, _layout]
        layout = _shared_layout(monitors)
        # mss convention: index 0 is the whole/most relevant monitor.
        return [layout, layout]

    def grab(self, sct_params):
        monitors = hyprland.get_monitors()
        if not monitors:
            raise ScreenShotError('Could not read the Hyprland monitor layout')
        layout = _shared_layout(monitors)

        is_layout_request = sct_params is layout or sct_params == layout

        if is_layout_request:
            # Capture the monitor under the cursor. The shared layout dict is
            # updated in place so ScreenManager and hit scanning always use the
            # geometry of the monitor that was actually captured, even after the
            # user moves to another display or the layout changes.
            cursor = hyprland.get_cursor_pos()
            target = None
            if cursor is not None:
                cx, cy = cursor
                for monitor in monitors:
                    mx, my = int(monitor['x']), int(monitor['y'])
                    mw, mh = int(monitor['width']), int(monitor['height'])
                    if mx <= cx < mx + mw and my <= cy < my + mh:
                        target = monitor
                        break

            if target is not None:
                left, top = int(target['x']), int(target['y'])
                width, height = int(target['width']), int(target['height'])
                with _layout_lock:
                    layout.update({
                        'left': left,
                        'top': top,
                        'width': width,
                        'height': height,
                    })
            else:
                full = _full_layout(monitors)
                left, top = full['left'], full['top']
                width, height = full['width'], full['height']
        else:
            left, top = int(sct_params['left']), int(sct_params['top'])
            width, height = int(sct_params['width']), int(sct_params['height'])

        # Clamp the requested region to the current monitor layout.
        full = _full_layout(monitors)
        right = min(left + width, full['left'] + full['width'])
        bottom = min(top + height, full['top'] + full['height'])
        left = max(left, full['left'])
        top = max(top, full['top'])
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            raise ScreenShotError('Requested capture region is outside the monitor layout')

        bgra, width, height = _capture_with_grim(left, top, width, height)
        monitor = {'left': left, 'top': top, 'width': width, 'height': height}
        return ScreenShot(bgra, monitor, size=Size(width, height))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class ScreenCastManager:
    def __init__(self):
        self.screen_cast_iface = 'org.freedesktop.portal.ScreenCast'
        self.frame_lock = threading.Lock()
        self.selected_event = threading.Event()
        self.ready_event = threading.Event()
        self.request_token_counter = 0
        self.session_token_counter = 0
        self.restore_token = None
        self.stream_position = (0, 0)
        self.start()

    def __del__(self):
        self.stop()

    def _new_request_path(self):
        self.request_token_counter += 1
        token = f'u{self.request_token_counter}'
        path = f'/org/freedesktop/portal/desktop/request/{self.sender_name}/{token}'
        return path, token

    def _new_session_path(self):
        self.session_token_counter += 1
        token = f'u{self.session_token_counter}'
        path = f'/org/freedesktop/portal/desktop/session/{self.sender_name}/{token}'
        return path, token

    def _screen_cast_call(self, method: str, request_path: str, callback, variant: GLib.Variant):
        self.bus.signal_subscribe(
            'org.freedesktop.portal.Desktop',
            'org.freedesktop.portal.Request',
            'Response',
            request_path,
            None,
            Gio.DBusSignalFlags.NO_MATCH_RULE,
            callback,
        )

        self.bus.call_sync(
            'org.freedesktop.portal.Desktop',
            '/org/freedesktop/portal/desktop',
            self.screen_cast_iface,
            method,
            variant,
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

    def _on_session_closed(self, *args, **kwargs):
        self.stop()

    def _on_gst_message(self, bus, message):
        t = message.type
        if t in (Gst.MessageType.EOS, Gst.MessageType.ERROR):
            self.stop()

    def _process_sample(self, sample):
        buffer = sample.get_buffer()
        caps = sample.get_caps()
        caps_struct = caps.get_structure(0)
        width = caps_struct.get_value('width')
        height = caps_struct.get_value('height')

        success, map_info = buffer.map(Gst.MapFlags.READ)
        if success:
            try:
                data = bytes(map_info.data)
                return data, width, height
            finally:
                buffer.unmap(map_info)
        return None, width, height

    def _on_new_sample(self, appsink):
        try:
            sample = appsink.emit('pull-sample')
            if sample is None:
                raise ValueError
            frame_data = self._process_sample(sample)
            if frame_data[0] is None:
                raise ValueError
            with self.frame_lock:
                self.last_frame = frame_data
            self.ready_event.set()
        except:  # todo should we "except Exception as e" and add logs?
            self.stop()
            return Gst.FlowReturn.ERROR
        return Gst.FlowReturn.OK

    def _play_pipewire_stream(self, node_id):
        result, out_fd_list = self.bus.call_with_unix_fd_list_sync(
            'org.freedesktop.portal.Desktop',
            '/org/freedesktop/portal/desktop',
            self.screen_cast_iface,
            'OpenPipeWireRemote',
            GLib.Variant('(oa{sv})', (self.session, {})),
            GLib.VariantType.new('(h)'),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
        )
        fd_index = result.unpack()[0]
        fd = out_fd_list.get(fd_index)

        pipeline_str = (
            f'pipewiresrc fd={fd} path={node_id} ! '
            'videoconvert ! '
            'videorate drop-only=true ! '
            'video/x-raw,format={BGRA,BGRx},max-framerate=30/1 ! '
            'appsink name=sink max-buffers=1 drop=true emit-signals=true enable-last-sample=false qos=false sync=false'
        )
        self.pipeline = Gst.parse_launch(pipeline_str)
        bus = self.pipeline.get_bus()
        bus.connect('message', self._on_gst_message)
        appsink = self.pipeline.get_by_name('sink')
        appsink.connect('new-sample', self._on_new_sample)

        self.pipeline.set_state(Gst.State.PLAYING)

    def _on_start_response(self, connection, sender, object_path, interface, signal, parameters):
        response, results = parameters.unpack()
        if response != 0:
            self.stop()
            raise ScreenShotError(f'Failed to start screencast: {response}')

        self.selected_event.set()

        if results.get('restore_token'):
            with open(token_file, "w") as file:
                file.write(results['restore_token'])
        if results.get('streams'):
            node_id, stream_properties = results['streams'][0]

            def _unwrap(value):
                return value.unpack() if hasattr(value, 'unpack') else value

            # xdg-desktop-portal-hyprland always reports position (0, 0), but it
            # does report the captured monitor's name as mapping_id. Look up the
            # real position from Hyprland so hit scanning can translate global
            # mouse coordinates into frame-relative coordinates on multi-monitor
            # setups.
            mapping_id = _unwrap(stream_properties.get('mapping_id'))
            position_x, position_y = (0, 0)
            for monitor in hyprland.get_monitors() or []:
                if monitor.get('name') == str(mapping_id):
                    position_x, position_y = int(monitor['x']), int(monitor['y'])
                    break
            self.stream_position = (position_x, position_y)

            logger.info(
                "Wayland screencast: mapping_id=%s, position=(%d,%d)",
                str(mapping_id), position_x, position_y,
            )
            self._play_pipewire_stream(node_id)
        else:
            self.stop()
            raise ScreenShotError('No streams available')

    def _on_select_sources_response(self, connection, sender, object_path, interface, signal, parameters):
        response, results = parameters.unpack()
        if response != 0:
            self.stop()
            raise ScreenShotError(f'Failed to select sources: {response}')

        request_path, request_token = self._new_request_path()
        variant = GLib.Variant('(osa{sv})', (
            self.session,
            '',
            {
                'handle_token': GLib.Variant('s', request_token),
                'multiple': GLib.Variant('b', False),
                'types': GLib.Variant('u', 1 | 2),
                'framerate': GLib.Variant('u', 30),
            },
        ))
        self._screen_cast_call(
            "Start",
            request_path,
            self._on_start_response,
            variant,
        )

    def _on_create_session_response(self, connection, sender, object_path, interface, signal, parameters):
        response, results = parameters.unpack()
        if response != 0:
            self.stop()
            raise ScreenShotError(f'Failed to create session: {response}')

        self.session = results['session_handle']

        self.bus.signal_subscribe(
            'org.freedesktop.portal.Desktop',
            'org.freedesktop.portal.Session',
            'Closed',
            self.session,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_session_closed,
        )

        request_path, request_token = self._new_request_path()
        variant = GLib.Variant('(oa{sv})', (
            self.session,
            {
                'handle_token': GLib.Variant('s', request_token),
                'multiple': GLib.Variant('b', False),
                'types': GLib.Variant('u', 1),
                'framerate': GLib.Variant('u', 30),
                'persist_mode': GLib.Variant('u', 2),
                'restore_token': GLib.Variant('s', persist_token)
            },
        ))
        self._screen_cast_call(
            "SelectSources",
            request_path,
            self._on_select_sources_response,
            variant
        )

    def _initialize_screencast(self):
        Gst.init(None)
        
        context = GLib.MainContext.new()
        context.push_thread_default()
        
        try:
            self.loop = GLib.MainLoop.new(context)
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self.sender_name = re.sub(r'\.', r'_', self.bus.get_unique_name()[1:])

            session_path, session_token = self._new_session_path()
            request_path, request_token = self._new_request_path()
            variant =  GLib.Variant('(a{sv})', ({
                'handle_token': GLib.Variant('s', request_token),
                'session_handle_token': GLib.Variant('s', session_token),
            },))
            self._screen_cast_call(
                "CreateSession",
                request_path,
                self._on_create_session_response,
                variant
            )

            self.loop.run()
        except Exception as e:
            self.stop()
            raise ScreenShotError(f'Error initializing screencast: {e}')
        finally:
            context.pop_thread_default()
            
    def request_frame(self):
        if self.ready_event.is_set():
            with self.frame_lock:
                if self.last_frame:
                    return self.last_frame
        return (None, 0, 0)

    def start(self):
        self.pipeline = None
        self.loop = None
        self.session = None
        self.last_frame = None
        self.selected_event.clear()

        self.init_thread = threading.Thread(target=self._initialize_screencast, daemon=True)
        self.init_thread.start()

    def stop(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)

        if self.loop:
            self.loop.quit()

        self.selected_event.set()
        self.ready_event.clear()


class MSSWaylandShim:
    def __init__(self):
        global screencast
        with screencast_lock:
            if not screencast:
                screencast = ScreenCastManager()
                if not screencast.selected_event.wait(timeout=60):
                    raise ScreenShotError('Source selection timed out')
                if not screencast.ready_event.wait(timeout=3):
                    raise ScreenShotError('Screencast initialization timed out')
                time.sleep(1)  # todo it seems like we can delete this... needs to be tested
        self._create_monitors()

    @property
    def monitors(self):
        return self._monitors

    def grab(self, sct_params):
        frame_data = self._grab_screenshot(sct_params)
        bgra_data, crop_width, crop_height = frame_data

        if sct_params is self._monitors[0]:
            monitor = self._monitors[0]
        else:
            monitor = {
                'left': int(sct_params['left']),
                'top': int(sct_params['top']),
                'width': crop_width,
                'height': crop_height,
            }

        return ScreenShot(bgra_data, monitor, size=Size(crop_width, crop_height))

    def _create_monitors(self):
        self._monitors = []

        frame = screencast.request_frame()
        if frame[0] is None:
            raise ScreenShotError('Invalid frame received')

        _, width, height = frame

        # The portal reports the stream at (0, 0); use the real compositor
        # position resolved from mapping_id so global coordinates line up.
        origin_x, origin_y = getattr(screencast, 'stream_position', (0, 0))
        fake_monitor = Monitor({
            'top': origin_y,
            'left': origin_x,
            'width': width,
            'height': height
        })

        self._monitors.append(fake_monitor)
        self._monitors.append(fake_monitor)

    def _grab_screenshot(self, sct_params):
        frame = screencast.request_frame()
        if frame[0] is None:
            raise ScreenShotError('Invalid frame received')

        bgra_data, full_width, full_height = frame
        origin_x, origin_y = getattr(screencast, 'stream_position', (0, 0))

        if sct_params != self._monitors[0]:
            crop_top = sct_params['top'] - origin_y
            crop_left = sct_params['left'] - origin_x
            crop_width = sct_params['width']
            crop_height = sct_params['height']

            crop_right = crop_left + crop_width
            crop_bottom = crop_top + crop_height

            crop_left = max(0, min(crop_left, full_width - 1))
            crop_top = max(0, min(crop_top, full_height - 1))
            crop_right = max(crop_left + 1, min(crop_right, full_width))
            crop_bottom = max(crop_top + 1, min(crop_bottom, full_height))

            if crop_right > crop_left and crop_bottom > crop_top:
                final_crop_width = crop_right - crop_left
                final_crop_height = crop_bottom - crop_top
                stride = full_width * 4

                cropped_data = bytearray(final_crop_width * final_crop_height * 4)

                for y in range(final_crop_height):
                    src_y = crop_top + y
                    src_start = src_y * stride + crop_left * 4
                    src_end = src_start + final_crop_width * 4
                    dst_start = y * final_crop_width * 4
                    cropped_data[dst_start:dst_start + (src_end - src_start)] = bgra_data[src_start:src_end]

                return cropped_data, final_crop_width, final_crop_height

        return bgra_data, full_width, full_height

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MSSModuleShim:
    def mss(self):
        if _grim_available():
            return GrimWaylandShim()
        return MSSWaylandShim()

    def __getattr__(self, name):
        return getattr(real_mss, name)
