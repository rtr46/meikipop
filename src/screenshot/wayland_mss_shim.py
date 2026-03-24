# Modified from AuroraWright's OwOCR

import re
import threading
import queue
import time
import uuid
from pathlib import Path

import gi

gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst, Gio

import mss as real_mss
from mss.exception import ScreenShotError
from mss.screenshot import ScreenShot, Size
from mss.models import Monitor

screencast = None
screencast_lock = threading.Lock()

token_file = Path('~/.cache/.ocr_screencapture_token').expanduser()
persist_token = str(uuid.UUID(int=0))

if token_file.exists():
    with open(token_file, "r") as file:
        persist_token = file.read().strip()


class ScreenCastManager:
    def __init__(self):
        self.screen_cast_iface = 'org.freedesktop.portal.ScreenCast'
        self.frame_lock = threading.Lock()
        self.selected_event = threading.Event()
        self.ready_event = threading.Event()
        self.request_token_counter = 0
        self.session_token_counter = 0
        self.restore_token = None
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
        except:
            self.stop()
            return Gst.FlowReturn.Error
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

        if results['restore_token']:
            with open(token_file, "w") as file:
                file.write(results['restore_token'])
        if results['streams']:
            node_id, stream_properties = results['streams'][0]
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
            variant = GLib.Variant('(a{sv})', ({
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
                time.sleep(1)
        self._create_monitors()

    @property
    def monitors(self):
        return self._monitors

    def grab(self, sct_params):
        frame_data = self._grab_screenshot(sct_params)
        bgra_data, crop_width, crop_height = frame_data

        return ScreenShot(bgra_data, self._monitors[0], size=Size(crop_width, crop_height))

    def _create_monitors(self):
        self._monitors = []

        frame = screencast.request_frame()
        if frame[0] is None:
            raise ScreenShotError('Invalid frame received')

        _, width, height = frame

        fake_monitor = Monitor({
            'top': 0,
            'left': 0,
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

        if sct_params != self._monitors[0]:
            crop_top = sct_params['top']
            crop_left = sct_params['left']
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
        return MSSWaylandShim()

    def __getattr__(self, name):
        return getattr(real_mss, name)
