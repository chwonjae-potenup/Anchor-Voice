import httpx
import cv2
import numpy as np
from app_config import app_config

API_BASE = app_config.api_base_url

# Generate a blank image to simulate valid jpeg frame
img = np.zeros((480, 640, 3), dtype=np.uint8)
success, buffer = cv2.imencode('.jpg', img)
jpeg_bytes = buffer.tobytes()

files = []
for i in range(10): # passing 10 blank frames
    files.append(("files", (f"frame_{i}.jpg", jpeg_bytes, "image/jpeg")))

data = {
    "action1_id": "head_right",
    "action2_id": "blink_right"
}

print("POSTing to sequence-frames...")
try:
    resp = httpx.post(
        f"{API_BASE}/api/auth/face/sequence-frames",
        data=data,
        files=files,
        timeout=10
    )
    print("STATUS CODE:", resp.status_code)
    print("RESPONSE:", resp.json())
except Exception as e:
    print("FAILED:", e)
