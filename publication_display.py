"""Hardware-free display implementation that publishes rendered PNG frames."""

from __future__ import annotations

import logging
import os

from PIL import Image

from display_protocol import FRAME_HEIGHT, FRAME_WIDTH, FramePublisher

logger = logging.getLogger(__name__)


class PublicationDisplay:
    """Implements the renderer-facing EPD interface without GPIO access."""

    height = FRAME_WIDTH
    width = FRAME_HEIGHT
    BLACK = (0, 0, 0)
    WHITE = (255, 255, 255)

    class _Config:
        @staticmethod
        def module_exit(cleanup=True):
            return None

    epdconfig = _Config()

    def __init__(self, publisher: FramePublisher) -> None:
        self.publisher = publisher
        self.is_bw_display = os.getenv("mock_display_type", "bw").lower() == "bw"
        if not self.is_bw_display:
            self.RED = (255, 0, 0)
            self.YELLOW = (255, 255, 0)
        self.rotation = int(os.getenv("screen_rotation", "90"))

    def init(self):
        return None

    def init_Fast(self):
        return None

    def Clear(self):
        # Keep the last valid frame during renderer startup and shutdown.
        return None

    def sleep(self):
        return None

    def getbuffer(self, image):
        if not isinstance(image, Image.Image):
            raise TypeError("server display buffers must be PIL images")
        return image

    def _publish_render_buffer(self, image):
        if not isinstance(image, Image.Image):
            raise TypeError("server display buffers must be PIL images")
        frame = image.rotate(-self.rotation, expand=True)
        if frame.size != (FRAME_WIDTH, FRAME_HEIGHT):
            raise ValueError(
                f"renderer produced {frame.size}, expected {(FRAME_WIDTH, FRAME_HEIGHT)}"
            )
        snapshot = self.publisher.publish(frame)
        logger.info(
            "Published display frame sequence=%s sha256=%s",
            snapshot.metadata.sequence,
            snapshot.metadata.sha256[:12],
        )

    def display(self, image):
        self._publish_render_buffer(image)

    def displayPartial(self, image):
        self._publish_render_buffer(image)

    def displayPartBaseImage(self, image):
        self._publish_render_buffer(image)
