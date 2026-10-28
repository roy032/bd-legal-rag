"""Where to get help: free legal aid and the hotlines that fit a situation.

An answer says what the law provides. Someone who asked "my husband beats me,
what can I do?" also needs a number to call today, and that number is not in
any Act, so it is not left to the model: it lives here, written once, and the
service attaches the entries that fit the question (by the topics in topics.py).

Every number is a nationwide short code run by the government. District legal
aid offices sit at each district judge's court; their direct numbers change, so
this file names the office and sends people to 16430 or nlaso.gov.bd for the
number rather than printing one that may be stale. Add a `phone` to a district
only after checking it on nlaso.gov.bd, and update CHECKED when you re-check.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ingest.textutils import detect_lang

from .topics import match_topics

# When the numbers below were last checked against the official sources.
# None until a person has done that before launch (docs/legal-aid.md).
CHECKED: str | None = None

NLASO_URL = "https://nlaso.gov.bd/"


@dataclass(frozen=True)
class Contact:
    id: str
    phone: str
    name_en: str
    name_bn: str
    when_en: str
    when_bn: str

    def localized(self, lang: str) -> dict:
        bn = lang == "bn"
        return {"id": self.id, "phone": self.phone,
                "name": self.name_bn if bn else self.name_en,
                "when": self.when_bn if bn else self.when_en}


CONTACTS: dict[str, Contact] = {c.id: c for c in (
    Contact("legal_aid", "16430",
            "National Legal Aid hotline (NLASO)", "জাতীয় আইনগত সহায়তা হটলাইন",
            "Free legal advice, and a free lawyer if you cannot afford one. Toll-free.",
            "বিনামূল্যে আইনি পরামর্শ, আর খরচ বহন করতে না পারলে বিনামূল্যে আইনজীবী। টোল-ফ্রি।"),
    Contact("emergency", "999",
            "National Emergency Service", "জাতীয় জরুরি সেবা",
            "Police, fire or ambulance when someone is in danger right now.",
            "কেউ এখনই বিপদে থাকলে পুলিশ, ফায়ার সার্ভিস বা অ্যাম্বুলেন্স।"),
    Contact("women_children", "109",
            "Helpline for violence against women and children", "নারী ও শিশু নির্যাতন প্রতিরোধ হেল্পলাইন",
            "Violence, dowry demands, harassment or child marriage. Toll-free, day and night.",
            "নির্যাতন, যৌতুকের দাবি, হয়রানি বা বাল্যবিবাহ। টোল-ফ্রি, দিনরাত।"),
    Contact("child", "1098",
            "Child Helpline", "শিশু সহায়তা হেল্পলাইন",
            "A child at risk of abuse, child labour or child marriage.",
            "নির্যাতন, শিশুশ্রম বা বাল্যবিবাহের ঝুঁকিতে থাকা শিশু।"),
    Contact("govt_info", "333",
            "National information and service line", "জাতীয় তথ্য ও সেবা বাতায়ন",
            "Report a planned child marriage to the local administration; ask which office handles a matter.",
            "পরিকল্পিত বাল্যবিবাহের খবর স্থানীয় প্রশাসনকে জানাতে; কোন অফিস কোন কাজ করে জানতে।"),
    Contact("consumer", "16121",
            "Consumer rights directorate (DNCRP)", "জাতীয় ভোক্তা-অধিকার সংরক্ষণ অধিদপ্তর",
            "Complaints about overcharging, adulterated food or faulty goods.",
            "বেশি দাম, ভেজাল খাবার বা ত্রুটিপূর্ণ পণ্যের অভিযোগ।"),
    Contact("labour", "16357",
            "Labour inspection helpline (DIFE)", "কলকারখানা ও প্রতিষ্ঠান পরিদর্শন অধিদপ্তর হেল্পলাইন",
            "Unpaid wages, unfair dismissal, leave or workplace safety.",
            "বকেয়া মজুরি, অন্যায় চাকরিচ্যুতি, ছুটি বা কর্মস্থলের নিরাপত্তা।"),
)}

# topics.py topic name -> the contacts that fit it, most useful first.
DANGER = ("emergency",)
TOPIC_CONTACTS: dict[str, tuple[str, ...]] = {
    "dowry": ("women_children", *DANGER),
    "rape": (*DANGER, "women_children"),
    "sexual harassment": ("women_children",),
    "domestic violence": ("women_children", *DANGER),
    "child marriage": ("women_children", "child", "govt_info"),
    "trafficking": (*DANGER, "women_children"),
    "murder": DANGER,
    "hurt": DANGER,
    "threat": DANGER,
    "consumer": ("consumer",),
    "defective goods": ("consumer",),
    "wages": ("labour",),
    "dismissal": ("labour",),
    "maternity": ("labour",),
}

# The 64 districts, by division. Each has a District Legal Aid Office at the
# district judge's court, run by a District Legal Aid Officer.
DISTRICTS: tuple[tuple[str, str, str], ...] = tuple(
    (division, en, bn) for division, rows in (
        ("Dhaka", (("Dhaka", "ঢাকা"), ("Faridpur", "ফরিদপুর"), ("Gazipur", "গাজীপুর"),
                   ("Gopalganj", "গোপালগঞ্জ"), ("Kishoreganj", "কিশোরগঞ্জ"),
                   ("Madaripur", "মাদারীপুর"), ("Manikganj", "মানিকগঞ্জ"),
                   ("Munshiganj", "মুন্সীগঞ্জ"), ("Narayanganj", "নারায়ণগঞ্জ"),
                   ("Narsingdi", "নরসিংদী"), ("Rajbari", "রাজবাড়ী"), ("Shariatpur", "শরীয়তপুর"),
                   ("Tangail", "টাঙ্গাইল"))),
        ("Chattogram", (("Bandarban", "বান্দরবান"), ("Brahmanbaria", "ব্রাহ্মণবাড়িয়া"),
                        ("Chandpur", "চাঁদপুর"), ("Chattogram", "চট্টগ্রাম"), ("Cumilla", "কুমিল্লা"),
                        ("Cox's Bazar", "কক্সবাজার"), ("Feni", "ফেনী"),
                        ("Khagrachhari", "খাগড়াছড়ি"), ("Lakshmipur", "লক্ষ্মীপুর"),
                        ("Noakhali", "নোয়াখালী"), ("Rangamati", "রাঙ্গামাটি"))),
        ("Rajshahi", (("Bogura", "বগুড়া"), ("Chapainawabganj", "চাঁপাইনবাবগঞ্জ"),
                      ("Joypurhat", "জয়পুরহাট"), ("Naogaon", "নওগাঁ"), ("Natore", "নাটোর"),
                      ("Pabna", "পাবনা"), ("Rajshahi", "রাজশাহী"), ("Sirajganj", "সিরাজগঞ্জ"))),
        ("Khulna", (("Bagerhat", "বাগেরহাট"), ("Chuadanga", "চুয়াডাঙ্গা"), ("Jashore", "যশোর"),
                    ("Jhenaidah", "ঝিনাইদহ"), ("Khulna", "খুলনা"), ("Kushtia", "কুষ্টিয়া"),
                    ("Magura", "মাগুরা"), ("Meherpur", "মেহেরপুর"), ("Narail", "নড়াইল"),
                    ("Satkhira", "সাতক্ষীরা"))),
        ("Barishal", (("Barguna", "বরগুনা"), ("Barishal", "বরিশাল"), ("Bhola", "ভোলা"),
                      ("Jhalokati", "ঝালকাঠি"), ("Patuakhali", "পটুয়াখালী"),
                      ("Pirojpur", "পিরোজপুর"))),
        ("Sylhet", (("Habiganj", "হবিগঞ্জ"), ("Moulvibazar", "মৌলভীবাজার"),
                    ("Sunamganj", "সুনামগঞ্জ"), ("Sylhet", "সিলেট"))),
        ("Rangpur", (("Dinajpur", "দিনাজপুর"), ("Gaibandha", "গাইবান্ধা"), ("Kurigram", "কুড়িগ্রাম"),
                     ("Lalmonirhat", "লালমনিরহাট"), ("Nilphamari", "নীলফামারী"),
                     ("Panchagarh", "পঞ্চগড়"), ("Rangpur", "রংপুর"), ("Thakurgaon", "ঠাকুরগাঁও"))),
        ("Mymensingh", (("Jamalpur", "জামালপুর"), ("Mymensingh", "ময়মনসিংহ"),
                        ("Netrokona", "নেত্রকোণা"), ("Sherpur", "শেরপুর"))),
    ) for en, bn in rows)

# Checked numbers for single offices, keyed by English district name. Empty on
# purpose: see the module docstring.
DISTRICT_PHONES: dict[str, str] = {}

OFFICE = {
    "en": "District Legal Aid Office, District Judge's Court, {district}",
    "bn": "জেলা লিগ্যাল এইড অফিস, জেলা জজ আদালত, {district}",
}
OFFICE_HOW = {
    "en": ("Go in person with any papers you have; the District Legal Aid Officer can give "
           "advice, try mediation, or appoint a free lawyer. Call 16430 for the office's number "
           "and hours."),
    "bn": ("হাতে থাকা কাগজপত্র নিয়ে সরাসরি যান; জেলা লিগ্যাল এইড অফিসার পরামর্শ দিতে, আপস-মীমাংসার "
           "ব্যবস্থা করতে বা বিনামূল্যে আইনজীবী নিয়োগ দিতে পারেন। অফিসের নম্বর ও সময় জানতে ১৬৪৩০-এ কল করুন।"),
}
SUPREME_COURT = {
    "en": "Supreme Court Legal Aid Office, Dhaka: for an appeal or a case in the High Court Division.",
    "bn": "সুপ্রিম কোর্ট লিগ্যাল এইড অফিস, ঢাকা: আপিল বা হাইকোর্ট বিভাগের মামলার জন্য।",
}


def lang_of(question: str) -> str:
    return "bn" if detect_lang(question) == "bn" else "en"


def contacts_for(question: str, lang: str | None = None) -> list[dict]:
    """The legal aid hotline, then whatever fits the situation in the question."""
    lang = lang or lang_of(question)
    ids = ["legal_aid"]
    for topic in match_topics(question):
        ids += [i for i in TOPIC_CONTACTS.get(topic.name, ()) if i not in ids]
    # Someone in danger needs 999 first, before advice.
    if "emergency" in ids and any(t.name in ("rape", "murder", "hurt", "trafficking")
                                  for t in match_topics(question)):
        ids.remove("emergency")
        ids.insert(0, "emergency")
    return [CONTACTS[i].localized(lang) for i in ids]


def directory() -> dict:
    """Everything the page needs for the help box: hotlines and the district offices."""
    return {
        "checked": CHECKED,
        "website": NLASO_URL,
        "contacts": [asdict(c) for c in CONTACTS.values()],
        "districts": [{"division": div, "en": en, "bn": bn, "phone": DISTRICT_PHONES.get(en)}
                      for div, en, bn in DISTRICTS],
        "office": OFFICE, "office_how": OFFICE_HOW, "supreme_court": SUPREME_COURT,
    }
