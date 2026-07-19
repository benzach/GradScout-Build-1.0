"""
Static scraper for server-rendered sites (charityjob, acca, thirdsector).

Parsing logic is unchanged from the prototype — it was already tested
against real page structure for all three sites. What changed:
  - Field name `organisation` -> `company` (matches the dedup engine and
    schema from Phase 0/1)
  - Returns plain dicts instead of JobListing dataclass objects (storage.py
    expects dicts directly — no intermediate conversion needed)
  - `self.name` now comes from a DB row (sources table) via the registry,
    not a sites.yaml entry — the scraper class itself doesn't care either way
"""
import requests
from bs4 import BeautifulSoup

from app.dedup.parsing import detect_contract_type
from app.scrapers.base import BaseScraper

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    # A real browser never sends ONLY a User-Agent — some bot-detection
    # systems specifically flag requests missing the rest of a normal
    # browser's header set as automated traffic, independent of the
    # User-Agent string's content. This won't defeat IP-based blocking
    # (the likely cause if a site starts 403'ing only once requests come
    # from cloud-hosted infrastructure like Railway, not from a home
    # connection) but it's a genuine, low-cost thing to rule out first.
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
TIMEOUT = 15


class StaticScraper(BaseScraper):
    def scrape(self) -> list[dict]:
        resp = requests.get(self.url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # config['parser'] names which method to use (set in the sources
        # table's config JSONB — see migrations/0002_seed_sources.sql)
        parser_name = self.config.get("parser")
        parser_method = getattr(self, parser_name, None) if parser_name else None
        if parser_method:
            return parser_method(soup)
        return self._generic_scrape(soup)

    def _generic_scrape(self, soup: BeautifulSoup) -> list[dict]:
        """Selector-driven scraping for sites configured with plain CSS selectors."""
        selectors = self.config.get("selectors", {})
        container_sel = selectors.get("job_container")
        if not container_sel:
            raise ValueError(f"No job_container selector configured for {self.name}")

        jobs = []
        for el in soup.select(container_sel):
            title_el = el.select_one(selectors["title"]) if selectors.get("title") else el
            link_el = el.select_one(selectors["link"]) if selectors.get("link") else el
            loc_el = el.select_one(selectors["location"]) if selectors.get("location") else None

            title = title_el.get_text(strip=True) if title_el else ""
            href = link_el.get("href", "") if link_el else ""
            if href and not href.startswith("http"):
                href = requests.compat.urljoin(self.url, href)
            location = loc_el.get_text(strip=True) if loc_el else ""

            if title and href:
                jobs.append({"title": title, "url": href, "location": location})
        return jobs

    def parse_charityjob(self, soup: BeautifulSoup) -> list[dict]:
        """
        CharityJob-specific parsing. Job titles are <h2><a href="/jobs/...">
        which can appear more than once per listing page — dedup by URL.
        Location/salary/contract-type sit in sibling elements after the
        <h2>, scanned rather than selected by exact class (site doesn't
        expose stable class names for these on the listing page).
        """
        jobs = []
        seen_urls = set()

        for link in soup.select("h2 a[href*='/jobs/']"):
            href = link.get("href", "")
            if not href:
                continue
            full_url = requests.compat.urljoin(self.url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            title = link.get_text(strip=True)
            if not title:
                continue

            org_location, salary = "", ""
            extra_text_parts = []
            h2 = link.find_parent("h2") or link.find_parent()
            if h2:
                sibling = h2.find_next_sibling()
                count = 0
                while sibling and count < 3:
                    text = sibling.get_text(strip=True)
                    if text:
                        extra_text_parts.append(text)
                        if count == 0:
                            org_location = text
                        elif "£" in text and not salary:
                            salary = text
                    sibling = sibling.find_next_sibling()
                    count += 1

            jobs.append({
                "title": title,
                "url": full_url,
                "location": org_location,
                "salary": salary,
                "contract_type": detect_contract_type(title, *extra_text_parts),
            })
        return jobs

    def parse_acca(self, soup: BeautifulSoup) -> list[dict]:
        """
        ACCA Careers (Madgex-powered job board). Job title links follow a
        distinctive /job/{id}/ URL pattern, each followed by ~3 bullet
        items (location, salary, company) then a description snippet.
        """
        jobs = []
        seen_urls = set()

        for link in soup.select("h3 a[href*='/job/']"):
            href = link.get("href", "")
            if not href:
                continue
            full_url = requests.compat.urljoin(self.url, href.split("?")[0])
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            title = link.get_text(strip=True)
            if not title:
                continue

            h3 = link.find_parent("h3")
            location, salary, company, description = "", "", "", ""
            if h3:
                bullets = []
                sib = h3.find_next_sibling()
                hops = 0
                while sib and hops < 6:
                    text = sib.get_text(strip=True)
                    if sib.name in ("ul", "div") and text:
                        bullets.extend(
                            li.get_text(strip=True) for li in sib.find_all("li")
                        ) if sib.name == "ul" else bullets.append(text)
                    elif sib.name == "p" and text and not description:
                        description = text
                    sib = sib.find_next_sibling()
                    hops += 1

                if len(bullets) >= 1:
                    location = bullets[0]
                if len(bullets) >= 2:
                    salary = bullets[1]
                if len(bullets) >= 3:
                    company = bullets[2]

            jobs.append({
                "title": title,
                "url": full_url,
                "company": company,
                "location": location,
                "salary": salary,
                "description": description,
                "contract_type": detect_contract_type(title, " ".join([location, salary])),
            })
        return jobs

    def parse_thirdsector(self, soup: BeautifulSoup) -> list[dict]:
        """
        Third Sector Jobs. Job title links follow a /jobdetail/{id}/ URL
        pattern, each followed by a 3-item list (location, salary,
        hours/contract type) then a description snippet.
        """
        jobs = []
        seen_urls = set()

        for link in soup.select("h2 a[href*='/jobdetail/']"):
            href = link.get("href", "")
            if not href:
                continue
            full_url = requests.compat.urljoin(self.url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            title = link.get_text(strip=True)
            if not title:
                continue

            h2 = link.find_parent("h2")
            location, salary, hours, description = "", "", "", ""
            if h2:
                ul = h2.find_next_sibling("ul")
                if ul:
                    items = [li.get_text(strip=True) for li in ul.find_all("li")]
                    if len(items) >= 1:
                        location = items[0]
                    if len(items) >= 2:
                        salary = items[1]
                    if len(items) >= 3:
                        hours = items[2]
                    p = ul.find_next_sibling("p")
                    if p:
                        description = p.get_text(strip=True)

            jobs.append({
                "title": title,
                "url": full_url,
                "location": location,
                "salary": salary,
                "description": description,
                "contract_type": detect_contract_type(title, hours, description),
            })
        return jobs
