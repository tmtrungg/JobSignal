from dataclasses import dataclass


@dataclass
class Job:
    job_id: str
    title: str
    company: str
    location: str
    url: str
    date_posted: str


@dataclass
class SearchQuery:
    name: str
    keywords: str
    location: str
    time_filter: str = "r86400"
    geo_id: int | None = None
    work_type: int | None = None
    results_per_page: int = 25
    max_pages: int = 3

    @classmethod
    def from_signal(cls, signal) -> "SearchQuery":
        return cls(
            name=signal.name,
            keywords=signal.keywords,
            location=signal.location,
            time_filter=signal.time_filter,
            geo_id=signal.geo_id,
            work_type=signal.work_type,
            max_pages=signal.max_pages,
        )
