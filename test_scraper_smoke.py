# test_scraper_smoke.py
import json
import unittest
from unittest import mock

import scraper_logic


def _fake_insight(insight, category, quote):
    return {"insight": insight, "category": category, "quote": quote}


class ParseTargetsTests(unittest.TestCase):
    def test_mixed_sources_one_per_line(self):
        sites_str = "https://example.com/post\nreddit:vending:route,inventory\nx:pallet,liquidation"
        targets = scraper_logic.parse_targets(sites_str)
        self.assertEqual(
            targets,
            [
                ('web', {'url': 'https://example.com/post'}),
                ('reddit', {'subreddit': 'vending', 'keywords': ['route', 'inventory']}),
                ('x', {'keywords': ['pallet', 'liquidation']}),
            ],
        )

    def test_comma_separated_urls(self):
        targets = scraper_logic.parse_targets("https://a.com, https://b.com")
        self.assertEqual(
            targets,
            [('web', {'url': 'https://a.com'}), ('web', {'url': 'https://b.com'})],
        )

    def test_skips_invalid_url(self):
        warnings = []
        targets = scraper_logic.parse_targets("not-a-url", log=warnings.append)
        self.assertEqual(targets, [])
        self.assertTrue(any('Skipping invalid URL' in w for w in warnings))


class ParseMultipleJsonTests(unittest.TestCase):
    def test_single_object(self):
        self.assertEqual(
            scraper_logic.parse_multiple_json('{"insight": "a", "category": "b", "quote": "c"}'),
            [{"insight": "a", "category": "b", "quote": "c"}],
        )

    def test_array_of_objects(self):
        data = json.dumps([_fake_insight("a", "b", "c"), _fake_insight("d", "e", "f")])
        self.assertEqual(scraper_logic.parse_multiple_json(data), [
            _fake_insight("a", "b", "c"), _fake_insight("d", "e", "f"),
        ])

    def test_concatenated_objects(self):
        data = json.dumps(_fake_insight("a", "b", "c")) + json.dumps(_fake_insight("d", "e", "f"))
        self.assertEqual(scraper_logic.parse_multiple_json(data), [
            _fake_insight("a", "b", "c"), _fake_insight("d", "e", "f"),
        ])

    def test_nested_dicts_and_lists(self):
        nested = {"insight": "a", "category": "b", "quote": "c", "extra": {"tags": ["x", "y"]}}
        self.assertEqual(scraper_logic.parse_multiple_json(json.dumps(nested)), [nested])


class RunScraperAnalysisSmokeTest(unittest.TestCase):
    def setUp(self):
        self.sites_str = "\n".join([
            "https://example.com/post",
            "reddit:vending:route,inventory",
            "x:pallet,liquidation",
        ])
        self.stored_docs = {}

    def _fake_firestore_client(self):
        client = mock.MagicMock()

        def fake_collection(name):
            self.assertEqual(name, 'insights')
            collection = mock.MagicMock()

            def fake_document(doc_id):
                doc_ref = mock.MagicMock()

                def fake_set(data, merge=False):
                    self.stored_docs[doc_id] = data

                doc_ref.set.side_effect = fake_set
                return doc_ref

            collection.document.side_effect = fake_document
            return collection

        client.collection.side_effect = fake_collection
        return client

    @mock.patch('scraper_logic.firestore.Client')
    @mock.patch('scraper_logic.extract_info_with_gemini')
    @mock.patch('scraper_logic.fetch_from_x_api')
    @mock.patch('scraper_logic.fetch_from_reddit_api')
    @mock.patch('scraper_logic.scrape_website_text')
    @mock.patch('scraper_logic.genai.configure')
    def test_mixed_sources_persist_and_dedupe(
        self, mock_configure, mock_scrape, mock_reddit, mock_x, mock_extract, mock_firestore_client
    ):
        mock_scrape.return_value = "web page text"
        mock_reddit.return_value = "reddit post text"
        mock_x.return_value = "tweet text"
        mock_extract.side_effect = [
            json.dumps([_fake_insight("web insight", "Usability", "web quote")]),
            json.dumps([_fake_insight("reddit insight", "Inventory", "reddit quote")]),
            json.dumps([_fake_insight("x insight", "Inventory", "x quote")]),
        ]
        mock_firestore_client.return_value = self._fake_firestore_client()

        status, columns, logs = scraper_logic.run_scraper_analysis("fake-api-key", "pain_points", self.sites_str)

        self.assertEqual(status, "success")
        self.assertEqual(len(self.stored_docs), 3)
        self.assertEqual(mock_scrape.call_count, 1)
        self.assertEqual(mock_reddit.call_count, 1)
        self.assertEqual(mock_x.call_count, 1)

        first_run_hashes = set(self.stored_docs.keys())
        for insight in self.stored_docs.values():
            self.assertIn(insight['source_url'], (
                'https://example.com/post',
                'reddit://r/vending?q=route,inventory',
                'x://search?q=pallet,liquidation',
            ))

        # Re-run with the same inputs: dedupe means the same three content hashes
        # get overwritten (merge=True), not duplicated.
        mock_extract.side_effect = [
            json.dumps([_fake_insight("web insight", "Usability", "web quote")]),
            json.dumps([_fake_insight("reddit insight", "Inventory", "reddit quote")]),
            json.dumps([_fake_insight("x insight", "Inventory", "x quote")]),
        ]
        status2, _, _ = scraper_logic.run_scraper_analysis("fake-api-key", "pain_points", self.sites_str)

        self.assertEqual(status2, "success")
        self.assertEqual(len(self.stored_docs), 3)
        self.assertEqual(set(self.stored_docs.keys()), first_run_hashes)

    @mock.patch('scraper_logic.firestore.Client')
    @mock.patch('scraper_logic.extract_info_with_gemini')
    @mock.patch('scraper_logic.scrape_website_text')
    @mock.patch('scraper_logic.genai.configure')
    def test_new_prompt_goals_work(self, mock_configure, mock_scrape, mock_extract, mock_firestore_client):
        mock_scrape.return_value = "someone should build a route inventory tool, I'd pay $100/mo for it"
        mock_extract.return_value = json.dumps([{
            "insight": "wants a route inventory tool",
            "category": "Inventory",
            "quote": "someone should build a route inventory tool",
            "estimated_wtp_tier": "mid_50_to_500",
        }])
        mock_firestore_client.return_value = self._fake_firestore_client()

        status, columns, logs = scraper_logic.run_scraper_analysis(
            "fake-api-key", "willingness_to_pay_signals", "https://example.com/post"
        )

        self.assertEqual(status, "success")
        self.assertEqual(len(self.stored_docs), 1)
        stored = next(iter(self.stored_docs.values()))
        self.assertEqual(stored["estimated_wtp_tier"], "mid_50_to_500")

        column_ids = {c['id'] for c in columns}
        self.assertIn('estimated_wtp_tier', column_ids)
        self.assertIn('tool_switching_signals', scraper_logic.PROMPT_LIBRARY)
        self.assertEqual(scraper_logic.PROMPT_LIBRARY['tool_switching_signals']['version'], 1)
        self.assertEqual(scraper_logic.PROMPT_LIBRARY['willingness_to_pay_signals']['version'], 1)


if __name__ == '__main__':
    unittest.main()
