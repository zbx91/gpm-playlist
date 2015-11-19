from playlist.settings import *

SESSION_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 2592000 #30 days
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_FRAME_DENY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_SSL_REDIRECT = True
CSRF_COOKIE_SECURE = True

SECURE_REDIRECT_EXEMPT = [
    # App Engine doesn't use HTTPS internally, so the /_ah/.* URLs need to be exempt.
    # djangosecure compares these to request.path.lstrip("/"), hence the lack of preceding /
    r"^_ah/",
    r'^cron/',  # cron cannot use HTTPS
]

SECURE_CHECKS += ["playlist.checks.check_csp_sources_not_unsafe"]

DEBUG = False
TEMPLATE_DEBUG = False

DGANGAE_ALLOW_USER_PRE_CREATION = True
DGANGAE_FORCE_USER_PRE_CREATION = True