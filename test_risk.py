import httpx
from app_config import app_config

API_BASE = app_config.api_base_url
try:
    resp = httpx.post(f'{API_BASE}/api/transfer/risk-check', 
                      json={'account_number':'1234-5678-912345', 
                            'amount': 10000000, 
                            'hour': 12, 
                            'is_new_account': True, 
                            'is_blacklisted': False, 
                            'repeat_attempt_count': 0},
                      timeout=5)
    print("STATUS", resp.status_code)
    print("JSON", resp.json())
except Exception as e:
    import traceback
    traceback.print_exc()
