from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from adblockparser import AdblockRules

from extractors.base import Extractor
from utils import parse_domain

RULES_DIR = Path(__file__).resolve().parent.parent / "resources"
EASYLIST_FILES = ("easylist.txt", "easyprivacy.txt")

_adblock_rules_cache: AdblockRules | None = None
_adblock_rules_cache_key: tuple[str, ...] | None = None


class TrackerExtractor(Extractor):
	rules: AdblockRules | None = None

	def extract_information(self):
		self._load_rules()

		(
			trackers_fqdn,
			trackers_domain,
			num_tracker_requests,
			tracker_request_counts_by_fqdn,
		) = self._tag_tracker_requests()
		num_tracker_cookies, tracker_cookie_domains, tracker_cookie_counts_by_fqdn = self._tag_tracker_cookies(
			trackers_fqdn,
			trackers_domain,
		)

		self.result["trackers"] = {
			"trackers": sorted(trackers_fqdn),
			"num_tracker_requests": num_tracker_requests,
			"tracker_request_counts_by_fqdn": tracker_request_counts_by_fqdn,
			"num_tracker_cookies": num_tracker_cookies,
			"tracker_cookie_domains": sorted(tracker_cookie_domains),
			"tracker_cookie_counts_by_fqdn": tracker_cookie_counts_by_fqdn,
		}

	def _tag_tracker_requests(self) -> tuple[set[str], set[str], int, dict[str, int]]:
		trackers_fqdn: set[str] = set()
		trackers_domain: set[str] = set()
		blacklist: set[str] = set()
		num_tracker_requests = 0
		tracker_request_counts_by_fqdn: dict[str, int] = {}

		for request in self.data.request_log.values():
			request.is_tracker = False
			if not request.is_thirdparty or request.url.startswith("data:"):
				continue

			netloc = request.parsed_url.netloc
			is_tracker = netloc in blacklist

			if not is_tracker:
				# A short prefix is enough for matching and keeps evaluation fast.
				request_url = request.url[:150]
				document_url = request.frame_url or self.result.get("final_url")
				is_tracker = self._matches_tracker_rule(request_url, document_url)

			if not is_tracker:
				continue

			request.is_tracker = True
			extracted = parse_domain(request.url)
			if extracted.fqdn:
				trackers_fqdn.add(extracted.fqdn)
				tracker_request_counts_by_fqdn[extracted.fqdn] = (
					tracker_request_counts_by_fqdn.get(extracted.fqdn, 0) + 1
				)
			if extracted.top_domain_under_public_suffix:
				trackers_domain.add(extracted.top_domain_under_public_suffix)
			num_tracker_requests += 1
			if netloc:
				blacklist.add(netloc)

		return trackers_fqdn, trackers_domain, num_tracker_requests, tracker_request_counts_by_fqdn

	def _tag_tracker_cookies(
		self,
		trackers_fqdn: set[str],
		trackers_domain: set[str],
	) -> tuple[int, set[str], dict[str, int]]:
		num_tracker_cookies = 0
		tracker_cookie_domains: set[str] = set()
		tracker_cookie_counts_by_fqdn: dict[str, int] = {}

		for cookie in self.data.cookies:
			domain = cookie.domain or ""
			normalized_domain = domain[1:] if domain.startswith(".") else domain
			reg_domain = (
				parse_domain(normalized_domain).top_domain_under_public_suffix if normalized_domain else ""
			)

			is_tracker = any(
				candidate
				and (candidate in trackers_fqdn or candidate in trackers_domain)
				for candidate in (domain, normalized_domain, reg_domain)
			)

			cookie.is_tracker = is_tracker
			if is_tracker:
				num_tracker_cookies += 1
				if normalized_domain:
					tracker_cookie_domains.add(normalized_domain)
					cookie_fqdn = parse_domain(normalized_domain).fqdn or normalized_domain
					tracker_cookie_counts_by_fqdn[cookie_fqdn] = (
						tracker_cookie_counts_by_fqdn.get(cookie_fqdn, 0) + 1
					)

		return num_tracker_cookies, tracker_cookie_domains, tracker_cookie_counts_by_fqdn

	def _matches_tracker_rule(self, request_url: str, document_url: str | None) -> bool:
		if self.rules is None:
			return False

		options: dict[str, object] = {"third-party": True}
		if document_url:
			hostname = urlparse(document_url).hostname
			if hostname:
				options["domain"] = hostname

		return bool(self.rules.should_block(request_url, options=options))

	def _load_rules(self) -> None:
		global _adblock_rules_cache
		global _adblock_rules_cache_key

		rule_paths = [RULES_DIR / filename for filename in EASYLIST_FILES]
		existing_rule_paths = [path for path in rule_paths if path.is_file()]

		if not existing_rule_paths:
			self.rules = None
			return

		cache_key = tuple(str(path.resolve()) for path in existing_rule_paths)
		if _adblock_rules_cache is not None and _adblock_rules_cache_key == cache_key:
			self.rules = _adblock_rules_cache
			return

		raw_rules: list[str] = []
		for rule_path in existing_rule_paths:
			raw_rules.extend(
				rule_path.read_text(encoding="utf-8", errors="ignore").splitlines()
			)

		self.rules = AdblockRules(raw_rules)
		_adblock_rules_cache = self.rules
		_adblock_rules_cache_key = cache_key