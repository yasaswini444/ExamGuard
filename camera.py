import cv2
import numpy as np
import os
from datetime import datetime


UPLOAD_FOLDER = "static/uploads"


def save_captured_photo(image_data):
    """
    Convert uploaded image bytes into an OpenCV image
    and save it inside static/uploads.
    """

    # Create upload folder if it does not exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Convert image bytes into NumPy array
    image_array = np.frombuffer(
        image_data,
        dtype=np.uint8
    )

    # Decode image
    frame = cv2.imdecode(
        image_array,
        cv2.IMREAD_COLOR
    )

    # Check whether image was decoded successfully
    if frame is None:
        return None

    # Create unique filename
    filename = (
        "candidate_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    )

    # Complete file path
    photo_path = os.path.join(
        UPLOAD_FOLDER,
        filename
    )

    # Save image
    success = cv2.imwrite(
        photo_path,
        frame
    )

    # Check whether saving succeeded
    if not success:
        return None

    return photo_path