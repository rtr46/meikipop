# Modified from AuroraWright's OwOCR
import logging
import threading
import base64
import time
import obsws_python as obs
from PIL import Image
import io
from meikipop.config.config import config

import mss as real_mss
from mss.exception import ScreenShotError
from mss.screenshot import ScreenShot, Size
from mss.models import Monitor

logger = logging.getLogger(__name__)

# disable annoying debug output from obsws_python
logging.getLogger("obsws_python").setLevel(logging.WARNING)

screencast = None
screencast_lock = threading.Lock()

class OBSWaylandManager:
    def __init__(self):
        # some frames stuff
        self.frame_lock = threading.Lock()
        self.ready_event = threading.Event()
        self.last_frame = None
        self.running = False
        self.client = None

        # obs is not enabled
        if not config.use_obs:
            logger.info(f"""
            --------------------------------------------------
            Please toggle \"Use OBS as Capturing Backend\" in the Settings to use OBS for capturing.
            You are required to restart the program after switching the toggle.
            --------------------------------------------------
            """)

        # no host or port found?
        if not config.obs_host or not config.obs_port:
            logger.info("no obs_host or obs_port found")
            return

        # obs websocket configurations
        self.host = str(config.obs_host) if config.obs_host else "127.0.0.1"
        self.port = str(config.obs_port) if config.obs_port else "4455"
        self.password = str(config.obs_password) if config.obs_password else ""

        # ok start now
        self.start()
    
    def _capturing_loop(self):
        # connect first
        try:
            # try to initilize a client
            self.client = obs.ReqClient(
                host=self.host,
                port=self.port,
                password=self.password,

                # timeout
                timeout=10
            )
            logger.info("connected to obs websocket server.")

            # get obs version (useless but it prove that obs is connected)
            resp = self.client.get_version()
            logger.info(f"obs version: {resp.obs_version}")
        except Exception as e:
            # log error
            logger.error(f"failed to connect to obs websocket server, error: {e}")

            # the user might make mistakes in the configuration, disable use_obs so they can edit the settings again
            config.use_obs = False
            config.save()

            # raise runtime error
            raise RuntimeError("failed to connect to obs websocket server")
        
        # dimension size
        canvas_width = None
        canvas_height = None
        cached_scene_name = None

        while self.running:
            try:
                if cached_scene_name is None:
                    try:
                        curr_scene_info = self.client.get_current_program_scene()
                        cached_scene_name = curr_scene_info.current_program_scene_name
                    except Exception as e:
                        logger.error(f"cannot get the current scene name, error: {e}")
                        time.sleep(0.5) # wait another half second and hope that the scene name arrive on next loop
                        continue

                # dynamically fetch canvas size from obs
                if canvas_width is None or canvas_height is None:
                    try:
                        video_settings = self.client.get_video_settings()
                        canvas_width = video_settings.base_width
                        canvas_height =video_settings.base_height
                    except Exception as e:
                        logger.warn(f"cannot fetch obs settings, fallbacks to 1920x1080, error: {e}")
                        canvas_width = 1920
                        canvas_height = 1080

                # get image
                try:
                    resp = self.client.get_source_screenshot(
                        name=str(cached_scene_name),
                        img_format="png",
                        width=int(canvas_width),
                        height=int(canvas_height),
                        quality=-1 # -1 is the default quality
                    )
                except Exception as e:
                    logger.debug(f"failed to screenshot. scene might have changed, error: {e}")
                    cached_scene_name = None
                    time.sleep(0.1)
                    continue

                if not resp or not hasattr(resp, 'image_data'):
                    raise ValueError("image_data attribute doesn't exist in the response of self.client.get_source_screenshot(...). OBS might have returned empty response.")
                
                # get raw image bytes
                raw_data = resp.image_data.split(",", 1)[-1]
                png_bytes = base64.b64decode(raw_data)

                # load the encoded png file from bytes
                with Image.open(io.BytesIO(png_bytes)) as img:
                    raw_rgba_img = img.convert("RGBA")

                    # convert RGBA to RGBA bytes
                    r, g, b, a = raw_rgba_img.split()
                    bgra_img = Image.merge("RGBA", (b, g, r, a))
                    img_bytes = bgra_img.tobytes()

                    # get the image size from frame directly
                    frame_width, frame_height = img.size

                # set last_frame
                with self.frame_lock:
                    self.last_frame = (
                        img_bytes,
                        frame_width,
                        frame_height
                    )

                if not self.ready_event.is_set():
                    self.ready_event.set()

                # i don't know, but doing this will make it sleeps for 30 frames per second like the original code
                time.sleep(1 / 30)

            except Exception as e:
                logger.debug(f"error in the capturing loop when capturing frame, error: {e}")
                time.sleep(0.1)

    def request_frame(self):
        if self.ready_event.is_set():
            with self.frame_lock:
                if self.last_frame:
                    return self.last_frame
        return (None, 0, 0)

    def start(self):
        self.last_frame = None
        self.ready_event.clear()
        self.running = True

        self.init_thread = threading.Thread(target=self._capturing_loop, daemon=True)
        self.init_thread.start()


    def __del__(self):
        self.stop()
    
    def stop(self):
        self.running = False
        self.ready_event.clear()
        if self.client:
            try:
                self.client.disconnect()
            except:
                logger.info("cannot disconnect the obs websocket connection")
                pass


class OBSWaylandShim: 
    def __init__(self):
        global screencast
        with screencast_lock:
            if not screencast:
                screencast = OBSWaylandManager()
                if not screencast.ready_event.wait(timeout=3):
                    raise ScreenShotError('Screencast initialization timed out') 
        self._create_monitors()

    @property
    def monitors(self):
        return self._monitors

    def _grab(self, sct_params):
        # client must be present and active before perform any actions
        if not self.client:
            logger.error("cannot perform grab() without a working obs connection")
            raise RuntimeError("self.client might still be None; therefore, grab() cannot be used")
        
        resp = self.client.get_source_screenshot(
            name="Screen Capture",
            img_format="png",
            quality=-1 # -1 is default quality
        )

        # base64 decode the newly retrieved image
        img_data = base64.b64decode(resp.image_data.split(",", 1)[1])
        
        # return just like mss
        return ScreenShot()

    def grab(self, sct_params):
        frame_data = self._grab_screenshot(sct_params)
        bgra_data, crop_width, crop_height = frame_data

        return ScreenShot(bgra_data, self._monitors[0], size=Size(crop_width, crop_height))
    
    def _create_monitors(self):
        self._monitors = []

        frame = screencast.request_frame()
        if frame is None or frame[0] is None:
            raise ScreenShotError("frame or frame[0] is None, which is invalid")
        
        _, width, height = frame

        fake_monitor = Monitor({
            'top': 0,
            'left': 0,
            'width': width,
            'height': height
        })

        # what?
        # let's copy like the old code
        self._monitors.append(fake_monitor)
        self._monitors.append(fake_monitor)


    def _grab_screenshot(self, sct_params):
        frame =  screencast.request_frame()
        if frame is None or frame[0] is None:
            raise ScreenShotError("frame or frame[0] is None, which is invalid")
        
        # copy from the original code
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
        if config.use_obs and config.obs_host and config.obs_port:
            return OBSWaylandShim()
        
        # fallback to default mss if user doesn't use obs
        logger.info(f"""
        --------------------------------------------------
        Please toggle \"Use OBS as Capturing Backend\" in the Settings to use OBS for capturing.
        You are required to restart the program after switching the toggle.
        --------------------------------------------------
        """)
        return real_mss.mss()
    
    def __getattr__(self, name):
        return getattr(real_mss, name)