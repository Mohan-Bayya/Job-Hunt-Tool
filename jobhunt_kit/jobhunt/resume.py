"""Loads your resume content from build_resume_codes/build_resume_final.py, so the tool never keeps
a second copy. Tailoring, skill matching and the tracker all start from that one file."""
import sys

from . import config

for folder in (config.ROOT / "build_resume_codes", config.ROOT):
    if folder.is_dir() and str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import build_resume_final as base  # noqa: E402

# Extra bullets the tailoring step may swap in for a weaker one when a posting calls for them.
# Empty by default. To offer one, paste it here in the same **bold** format as your other bullets.
EXTRA_BULLETS = []

PLACEHOLDER_NAMES = {"", "your name"}


def is_placeholder():
    """True while build_resume_final.py still has the template text, so no resume is built from it."""
    return base.NAME.strip().lower() in PLACEHOLDER_NAMES


def skills_text():
    """Headline and skills section, used to decide which skills you have.

    Bullets are left out so a passing mention doesn't count as a skill.
    """
    rows = [f"{category}: {items}" for category, items in base.SKILLS]
    return "\n".join([base.HEADLINE] + rows)
