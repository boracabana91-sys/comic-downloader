"""The one place the version number lives.
The window title, the header, the self-test and the GitHub release (ebz-vNN) all read it,
so changing this line is all an update needs."""
APP_NAME = "EBZ CNVRTR"
VERSION = "01"


def full_name():
    return f"{APP_NAME} {VERSION}"
