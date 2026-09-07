#!/usr/bin/env python3
"""Vercel Ignored Build Step.

exit 0 = 이 배포를 건너뜀
exit 1 = 빌드 진행

공식 프론트는 Vercel 프로젝트 `my-streamlit-app-2` (tillion.io.kr)만 허용한다.
옛 `my-streamlit-app`은 같은 GitHub 저장소에 연결되어 있어도 빌드하지 않는다.
"""

from __future__ import annotations

import os
import sys


OFFICIAL_PROJECT = "my-streamlit-app-2"
OFFICIAL_HOSTS = ("tillion.io.kr", "www.tillion.io.kr")
LEGACY_PROJECT = "my-streamlit-app"


def should_build(
    production_url: str = "",
    project_name: str = "",
    allow_flag: str = "",
) -> bool:
    url = (production_url or "").strip().lower()
    name = (project_name or "").strip()
    allow = (allow_flag or "").strip().lower()

    if allow in {"1", "true", "yes"}:
        return True
    if name == OFFICIAL_PROJECT:
        return True
    if name == LEGACY_PROJECT:
        return False
    if url in OFFICIAL_HOSTS or OFFICIAL_PROJECT in url:
        return True
    if url.startswith(f"{LEGACY_PROJECT}.") or url.startswith(f"{LEGACY_PROJECT}-"):
        return False
    return False


def main() -> int:
    url = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL", "")
    name = os.environ.get("VERCEL_PROJECT_NAME", "")
    allow = os.environ.get("ALLOW_VERCEL_FRONTEND_DEPLOY", "")
    if should_build(url, name, allow):
        print(f"Build official frontend {OFFICIAL_PROJECT} (url={url} name={name})")
        return 1
    print(
        f"Skip: not official Vercel {OFFICIAL_PROJECT}. "
        f"url={url} name={name}. Disconnect Git on legacy {LEGACY_PROJECT}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
