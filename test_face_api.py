import httpx
from app_config import app_config

API_BASE = app_config.api_base_url
try:
    with open('registered_face.jpg', 'rb') as f:
        img_bytes = f.read()

    resp = httpx.post(f'{API_BASE}/api/auth/face', 
                      files={"file": ("face.jpg", img_bytes, "image/jpeg")},
                      timeout=20)
    print("STATUS", resp.status_code)
    print("RESPONSE", resp.text)
except Exception as e:
    import traceback
    traceback.print_exc()
