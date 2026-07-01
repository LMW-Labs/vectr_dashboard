"""Smoke tests for run_scraper_analysis: multi-source dispatch and Firestore dedupe."""
import unittest
from unittest.mock import patch, MagicMock

import scraper_logic


def _gemini_json(insight, category, quote):
    return f'[{{"insight": "{insight}", "category": "{category}", "quote": "{quote}"}}]'


class TestScraperSmoke(unittest.TestCase):
    @patch('scraper_logic.firestore')
    @patch('scraper_logic.fetch_from_x_api')
    @patch('scraper_logic.fetch_from_reddit_api')
    @patch('scraper_logic.extract_info_with_gemini')
    @patch('scraper_logic.scrape_website_text')
    @patch('scraper_logic.genai')
    def test_mixed_sources_and_dedupe_on_rerun(
        self, mock_genai, mock_scrape, mock_extract, mock_reddit, mock_x, mock_firestore
    ):
        mock_scrape.return_value = "web page text"
        mock_reddit.return_value = "reddit post text"
        mock_x.return_value = "tweet text"

        mock_extract.side_effect = [
            _gemini_json("Web pain point", "Usability", "It is confusing"),
            _gemini_json("Reddit pain point", "Pricing", "Too expensive"),
            _gemini_json("X pain point", "Support", "No response"),
        ] * 2  # two full runs

        mock_db = MagicMock()
        mock_firestore.Client.return_value = mock_db
        mock_firestore.SERVER_TIMESTAMP = "SERVER_TIMESTAMP"

        sites_str = "https://example.com/post\nreddit:testsub:keyword1,keyword2\nx:keywordA,keywordB"

        status1, columns1, _ = scraper_logic.run_scraper_analysis("fake-api-key", "pain_points", sites_str)
        self.assertEqual(status1, "success")
        mock_reddit.assert_called_once_with("testsub", ["keyword1", "keyword2"])
        mock_x.assert_called_once_with(["keywordA", "keywordB"])
        mock_scrape.assert_called_once_with("https://example.com/post")

        first_run_hashes = [call.args[0] for call in mock_db.collection.return_value.document.call_args_list]
        self.assertEqual(len(first_run_hashes), 3)
        self.assertEqual(len(set(first_run_hashes)), 3)  # distinct per insight

        for call in mock_db.collection.return_value.document.return_value.set.call_args_list:
            self.assertTrue(call.kwargs.get('merge'))

        mock_db.reset_mock()

        status2, columns2, _ = scraper_logic.run_scraper_analysis("fake-api-key", "pain_points", sites_str)
        self.assertEqual(status2, "success")

        second_run_hashes = [call.args[0] for call in mock_db.collection.return_value.document.call_args_list]
        self.assertEqual(first_run_hashes, second_run_hashes)  # stable content_hash across reruns


if __name__ == '__main__':
    unittest.main()
