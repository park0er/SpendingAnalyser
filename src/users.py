"""
Multi-user profile configuration.

Maps file metadata (names, account numbers) to user IDs.
"""

USER_PROFILES = {
    "parko": {
        "display_name": "Parko",
        "aliases": ["Parko", "PARKO", "赵锡盛"],
        "alipay_account": "18211094248",
    },
    # Future: add more users
    # "wife": {
    #     "display_name": "...",
    #     "aliases": ["..."],
    #     "alipay_account": "...",
    # },
}


def identify_user(name: str = None, account: str = None) -> str:
    """
    Identify user_id from file metadata.

    Args:
        name: Name or nickname found in file header (e.g. "Parko", "赵锡盛")
        account: Account number found in file header (e.g. "18211094248")

    Returns:
        user_id string, or "unknown" if no match
    """
    for uid, profile in USER_PROFILES.items():
        if account and account == profile.get("alipay_account"):
            return uid
        if name:
            for alias in profile.get("aliases", []):
                if alias.lower() in name.lower() or name.lower() in alias.lower():
                    return uid
    return "unknown"
