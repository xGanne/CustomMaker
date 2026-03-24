# Dark Editorial Clean - base tokens
SURFACE_BG = "#141821"
SURFACE_PANEL = "#1B202B"
SURFACE_ELEVATED = "#222938"
SURFACE_MUTED = "#2A3244"

ACCENT = "#2F8CFF"
ACCENT_HOVER = "#1F6DCC"
SUCCESS = "#1FA971"
SUCCESS_HOVER = "#177F56"
WARNING = "#E7A83D"
ERROR = "#D94B5E"

TEXT_PRIMARY = "#E9EEF8"
TEXT_SECONDARY = "#A8B3C7"
TEXT_MUTED = "#7B879D"

BORDER_SOFT = "#334056"
BORDER_STRONG = "#4A5A75"

RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16

SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_5 = 20
SPACE_6 = 24

FONT_TITLE = ("Segoe UI", 24, "bold")
FONT_SECTION = ("Segoe UI", 16, "bold")
FONT_BODY = ("Segoe UI", 13)
FONT_CAPTION = ("Segoe UI", 11)


def button_style(kind="secondary"):
    if kind == "primary":
        return {
            "fg_color": ACCENT,
            "hover_color": ACCENT_HOVER,
            "text_color": TEXT_PRIMARY,
            "corner_radius": RADIUS_SM,
            "height": 38,
            "font": FONT_BODY,
        }
    if kind == "success":
        return {
            "fg_color": SUCCESS,
            "hover_color": SUCCESS_HOVER,
            "text_color": TEXT_PRIMARY,
            "corner_radius": RADIUS_SM,
            "height": 38,
            "font": FONT_BODY,
        }
    if kind == "danger":
        return {
            "fg_color": ERROR,
            "hover_color": "#B13B4A",
            "text_color": TEXT_PRIMARY,
            "corner_radius": RADIUS_SM,
            "height": 38,
            "font": FONT_BODY,
        }
    return {
        "fg_color": SURFACE_MUTED,
        "hover_color": "#353E52",
        "text_color": TEXT_PRIMARY,
        "corner_radius": RADIUS_SM,
        "height": 36,
        "font": FONT_BODY,
    }


def card_style(kind="default"):
    if kind == "root":
        return {
            "fg_color": SURFACE_PANEL,
            "corner_radius": RADIUS_LG,
            "border_width": 1,
            "border_color": BORDER_SOFT,
        }
    return {
        "fg_color": SURFACE_ELEVATED,
        "corner_radius": RADIUS_MD,
        "border_width": 1,
        "border_color": BORDER_SOFT,
    }


def input_style():
    return {
        "fg_color": SURFACE_MUTED,
        "border_color": BORDER_SOFT,
        "text_color": TEXT_PRIMARY,
        "corner_radius": RADIUS_SM,
        "height": 34,
        "font": FONT_BODY,
    }


def section_spacing():
    return {"padx": SPACE_4, "pady": SPACE_3}
