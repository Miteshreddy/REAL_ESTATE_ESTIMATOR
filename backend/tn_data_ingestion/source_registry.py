"""Tamil Nadu drawing / BOQ sources and their access status (checked against robots.txt by license_check)."""
SOURCES = [
    dict(id="tnrd", name="Tamil Nadu Rural Development — type designs", url="https://www.tnrd.tn.gov.in/", kind="government",
         purposes=["01_DRAWING_TRAINING", "06_VALIDATION", "07_UNSEEN_TEST"],
         note="Public Government type-design drawings (anganwadi, VAO office, ration shop …). Government publication: usable for "
              "internal model development pending client confirmation of licence."),
    dict(id="tnrera", name="Tamil Nadu RERA project documents", url="https://rera.tn.gov.in/", kind="government",
         purposes=["01_DRAWING_TRAINING"],
         note="robots.txt disallows /uploads/ and *.pdf — NOT crawled. Builder drawings are copyrighted; use only with permission."),
    dict(id="tntenders", name="Tamil Nadu e-procurement (tender BOQs)", url="https://tntenders.gov.in/", kind="government",
         purposes=["05_BOQ_GROUND_TRUTH"], note="Per-document CAPTCHA — NOT crawled. BOQs must be downloaded by a person and uploaded."),
    dict(id="tnpwdea", name="TN PWD Engineers' Association downloads", url="https://tnpwdea.org/downloads.php?category_id=4", kind="secondary",
         purposes=["04_PWD_KNOWLEDGE"], note="SOR / Standard Data — handled by backend/tnpwd_ingestion."),
    dict(id="scribd_arch", name="Architecture presentation sites (Scribd / Architizer / SlideShare) — TN complex test set",
         url=None, kind="third_party_copyright", purposes=["SMOKE_TEST"],
         note="Copyrighted third-party uploads supplied by the user as a PDF of five images. Smoke tests only; never training; "
              "not a statistical evaluation set; no ground truth."),
    dict(id="non_tn_reference", name="Non-Tamil Nadu reference drawings (Aparna Hyderabad, Uttarakhand, Nalanda)", url=None,
         kind="non_tn", purposes=["REFERENCE"], note="Not Tamil Nadu — never TN training or TN evaluation; reported as reference only."),
    dict(id="user", name="Drawings uploaded by users / the client", url=None, kind="client",
         purposes=["01_DRAWING_TRAINING", "05_BOQ_GROUND_TRUTH", "07_UNSEEN_TEST"],
         note="Client-provided with permission. Uploaded estimates are NOT added to training automatically."),
]
LOCAL_SEEDS = [
    dict(source="tnrd", path=r"G:\velo\real-estate\drawings\tamilnadu", district=None,
         note="Previously collected TNRD type-design sheets (public Government drawings)"),
]
