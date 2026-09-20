from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ActRef:
    """One row of the laws index."""
    act_id: int
    title: str
    url: str


@dataclass
class SectionRef:
    """One entry in an act's table of contents."""
    section_id: int
    number: str          # as printed, e.g. '২' or '25A'
    number_ascii: str    # normalized, e.g. '2' or '25A'
    title: str
    chapter: str | None  # e.g. 'দ্বিতীয় অধ্যায় - বীমাকারীর জন্য প্রযোজ্য বিধানাবলী'
    url: str


@dataclass
class Act:
    act_id: int
    title: str
    act_number: str | None   # e.g. '২০১০ সনের ১৩ নং আইন' / 'ACT NO. XLV OF 1860'
    date: str | None
    preamble: str | None
    year: int | None
    language: str
    repealed: bool
    url: str
    sections: list[SectionRef] = field(default_factory=list)


@dataclass
class Section:
    act_id: int
    section_id: int
    number: str
    number_ascii: str
    title: str
    chapter: str | None
    text: str
    footnotes: list[str]
    url: str


@dataclass
class Chunk:
    chunk_id: str
    text: str            # what gets embedded (includes a context header)
    body: str            # the raw legal text only (what you show / cite)
    metadata: dict

    def to_dict(self) -> dict:
        return asdict(self)
