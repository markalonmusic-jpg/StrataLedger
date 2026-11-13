"""First-run setup without any screen code (decision S10).

When system_master.db is missing or has no users, the app shows a Welcome screen instead of the login. This module
holds the routing decision, the checks that run BEFORE any file is built, the rule that gates "Continue" on the
recovery-code checkbox, and the plain-language wording of errors. The view in views_first_run.py only draws widgets
and calls these functions, so everything here is testable without Tk.

Routing (stated and tested): missing -> first run, no_users -> first run, ready -> launcher, unreadable -> error.
"""
from dataclasses import dataclass

from modules.database import SchemaUpgradeBlockedError
from modules.services import auth, passwords
from modules.services.errors import PermissionDeniedError, ServiceError, ValidationError

STATE_ROUTES = {"missing": "first_run", "no_users": "first_run", "ready": "launcher", "unreadable": "error"}

WELCOME_TEXT = (
    "Welcome to StrataLedger. Your accounting data stays on this computer. To begin, create the Master account: "
    "the one person who can create companies and decide who may use them. Choose a password of at least "
    f"{passwords.MIN_LENGTH} characters. When you press Create Master, StrataLedger shows a one-time recovery code. "
    "Save it somewhere safe and offline: it is the only way to reset the Master password if you forget it."
)


CODE_NOTICE = (
    "If you ever forget the Master password, this code is the only way to reset it. Write it down or save it in a "
    "password manager, and keep it offline. StrataLedger cannot show it again. If you use Copy, a copy may remain "
    "in the clipboard history on some systems; clear it there if you can."
)

# Step 1c: shown on the code screen, before Continue, when the ledger key's DPAPI copy could not be made.
KEY_LOCKED_NOTICE = (
    "The ledger key could not be saved for this computer. Keep your recovery code: you will need it to restore the "
    "key before you can create a company."
)


@dataclass
class Draft:
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    password: str = ""
    repeat: str = ""


# --- Routing ---------------------------------------------------------------------------------------

def startup_check(master_db_path):
    """(route, error type or None). Reads the master file; never changes it."""
    state, error_type = auth.inspect_master(master_db_path)
    return STATE_ROUTES[state], error_type


def startup_route(master_db_path):
    return startup_check(master_db_path)[0]


# --- The form -----------------------------------------------------------------------------------------

def _sentence(text):
    text = str(text).strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def validate(draft):
    """Plain-language problems with the form; an empty list means it may be submitted.

    Runs before anything is built, so invalid input never creates a file. The password is never stripped or
    changed: spaces at either end are part of it.
    """
    problems = []
    try:
        auth.check_username(draft.username)
    except ValidationError:
        problems.append("The username must be 3 to 64 characters, using letters, digits and the symbols . _ @ and -.")
    if not draft.first_name.strip() or not draft.last_name.strip():
        problems.append("Enter your first and last name.")
    try:
        auth.check_person("x", "y", draft.email)
    except ValidationError:
        problems.append("Enter a valid email address.")
    password = draft.password
    if len(password) < passwords.MIN_LENGTH:
        problems.append(f"The password must be at least {passwords.MIN_LENGTH} characters.")
    elif len(password) > passwords.MAX_LENGTH:
        problems.append(f"The password can be at most {passwords.MAX_LENGTH} characters.")
    elif not password.strip():
        problems.append("The password cannot be only spaces.")
    if password != draft.repeat:
        problems.append("The two passwords do not match.")
    if draft.username.strip() and password.casefold() == draft.username.strip().casefold():
        problems.append("The password cannot be the same as the username.")
    return problems


def sign_in_secret(draft):
    """The password exactly as typed (whitespace is never stripped)."""
    return draft.password


# --- The recovery code -----------------------------------------------------------------------------------

def can_continue(code_shown, acknowledged):
    """Continue is allowed only after the code has been shown and 'I have saved this code' is ticked."""
    return bool(code_shown and acknowledged)


def _normalize_code(text):
    return "".join(ch for ch in str(text or "").upper() if ch.isalnum())


def same_code(held, code):
    """Do two texts hold the same recovery code (ignoring dashes, spaces and case)? Empty never matches."""
    held, code = _normalize_code(held), _normalize_code(code)
    return bool(held) and held == code


# --- Wording ----------------------------------------------------------------------------------------------------

def unreadable_message(path):
    """(title, message) for a master file that cannot be used. The file is left exactly as it was."""
    return ("Cannot open the StrataLedger database",
            f"The file {path} is from an older version or damaged, so StrataLedger cannot use it. Nothing was "
            "changed: the file was left exactly as it was. Restore a backup copy of that file or ask for help. "
            "StrataLedger will now close.")


def explain_error(error):
    """(dialog title, message): what happened and what to do next. Never shows an error's own text unless it is a
    service message written for people."""
    if isinstance(error, SchemaUpgradeBlockedError):
        return ("Cannot use the existing file",
                "The master database file is from an older version or damaged, so setup cannot use it. Nothing was "
                "changed. Restore a backup copy of the file or ask for help.")
    if isinstance(error, PermissionDeniedError):
        return "Not allowed", "You do not have permission to do this. No user was created."
    if isinstance(error, ValidationError):
        return "Please check this", f"{_sentence(error)} Correct it and press Create Master. No user was created."
    if isinstance(error, ServiceError):
        return "Cannot create the Master", f"{_sentence(error)} No user was created."
    return "Something went wrong", ("The Master account was not created. Try again. If this keeps happening, send "
                                    "the log file to support.")
