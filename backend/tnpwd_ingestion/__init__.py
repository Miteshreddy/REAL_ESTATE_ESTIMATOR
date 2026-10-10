"""Tamil Nadu PWD document ingestion: discover → download → verify → classify → extract → validate → store → index.

Only publicly accessible documents are fetched (robots.txt honoured, no CAPTCHA / login / anti-bot circumvention).
Nothing extracted here affects an estimate until it is validated and explicitly activated (version_manager.activate).
"""
PARSER_VERSION = "tnpwd-1.0.1"
