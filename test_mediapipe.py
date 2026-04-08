import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import cv2
import numpy as np

# Create a blank test image
img = np.zeros((480, 640, 3), dtype=np.uint8)
img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

base_options = python.BaseOptions(model_asset_path='face_landmarker.task')
options = vision.FaceLandmarkerOptions(base_options=base_options,
                                       output_face_blendshapes=False,
                                       output_facial_transformation_matrixes=False,
                                       num_faces=1)
try:
    with vision.FaceLandmarker.create_from_options(options) as landmarker:
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
        detection_result = landmarker.detect(mp_image)
        print("FaceLandmarker process ok, found faces:", bool(detection_result.face_landmarks))
        if detection_result.face_landmarks:
            lm = detection_result.face_landmarks[0]
            print("First landmark x, y:", lm[0].x, lm[0].y)
except Exception as e:
    import traceback
    traceback.print_exc()
