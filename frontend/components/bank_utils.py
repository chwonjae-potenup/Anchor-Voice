BANKS = {
    "KB국민은행": {"len": 14, "fmt": [6, 2, 6]},
    "신한은행": {"len": 12, "fmt": [3, 3, 6]},
    "우리은행": {"len": 13, "fmt": [4, 3, 6]},
    "하나은행": {"len": 14, "fmt": [3, 6, 5]},
    "NH농협은행": {"len": 13, "fmt": [3, 4, 4, 2]},
    "IBK기업은행": {"len": 14, "fmt": [3, 6, 2, 3]},
    "카카오뱅크": {"len": 13, "fmt": [4, 2, 7]},
    "토스뱅크": {"len": 12, "fmt": [4, 4, 4]},
}

def validate_and_format_account(bank_name, account_str):
    """
    숫자만 추출하여 길이를 검증하고 지정된 포맷으로 변환하여 반환.
    Returns:
        (formatted_str, is_valid: bool)
    """
    raw_num = ''.join(filter(str.isdigit, account_str))
    
    if bank_name not in BANKS:
        return account_str, True
        
    info = BANKS[bank_name]
    if len(raw_num) != info["len"]:
        return raw_num, False
        
    formatted = ""
    idx = 0
    for i, size in enumerate(info["fmt"]):
        formatted += raw_num[idx:idx+size]
        idx += size
        if i < len(info["fmt"]) - 1:
             formatted += "-"
             
    return formatted, True
