"""Smoke tests for run_scraper_analysis: raw_content, prompt versioning, embeddings, pluggable source dispatch."""
import unittest
from unittest.mock import patch, MagicMock

import scraper_logic


def _gemini_json(insight, category, quote):
    return f'[{{"insight": "{insight}", "category": "{category}", "quote": "{quote}"}}]'


class TestScraperSmoke(unittest.TestCase):
    @patch('scraper_logic.firestore')
    @patch('scraper_logic.generate_embedding')
    @patch('sources.x.fetch_from_x_api')
    @patch('sources.reddit.fetch_from_reddit_api')
    @patch('sources.web.scrape_website_text')
    @patch('scraper_logic.extract_info_with_gemini')
    @patch('scraper_logic.genai')
    def test_mixed_sources_raw_content_versioning_embeddings_and_dedupe(
        self, mock_genai, mock_extract, mock_scrape, mock_reddit, mock_x, mock_embed, mock_firestore
    ):
        mock_scrape.return_value = "web page text"
        mock_reddit.return_value = "reddit post text"
        mock_x.return_value = "tweet text"
        mock_embed.return_value = [0.1, 0.2, 0.3]

        mock_extract.side_effect = [
            _gemini_json("Web pain point", "Usability", "It is confusing"),
            _gemini_json("Reddit pain point", "Pricing", "Too expensive"),
            _gemini_json("X pain point", "Support", "No response"),
        ] * 2  # two full runs

        mock_db = MagicMock()
        mock_firestore.Client.return_value = mock_db
        mock_firestore.SERVER_TIMESTAMP = "SERVER_TIMESTAMP"

        # Fakes a real raw_content collection: set() stores by doc id, get()
        # reads it back, so analyze_raw_content genuinely depends on
        # write_raw_content having run first (proving the fetch -> write
        # raw_content -> analyze sequencing, not just that both were called).
        raw_content_store = {}
        collection_mocks = {}

        def raw_content_document_side_effect(doc_id):
            doc_ref = MagicMock()

            def set_side_effect(data, merge=True):
                raw_content_store[doc_id] = data
            doc_ref.set.side_effect = set_side_effect

            def get_side_effect():
                snap = MagicMock()
                stored = raw_content_store.get(doc_id)
                snap.exists = stored is not None
                snap.to_dict.return_value = stored
                return snap
            doc_ref.get.side_effect = get_side_effect
            return doc_ref

        def collection_side_effect(name):
            if name not in collection_mocks:
                collection_mocks[name] = MagicMock()
                if name == 'raw_content':
                    collection_mocks[name].document.side_effect = raw_content_document_side_effect
            return collection_mocks[name]

        mock_db.collection.side_effect = collection_side_effect

        sites_str = "https://example.com/post\nreddit:testsub:keyword1,keyword2\nx:keywordA,keywordB"

        status1, columns1, _ = scraper_logic.run_scraper_analysis("fake-api-key", "pain_points", sites_str)
        self.assertEqual(status1, "success")

        # Pluggable SOURCES dispatch reached all three underlying fetchers.
        mock_scrape.assert_called_once_with("https://example.com/post")
        mock_reddit.assert_called_once_with("testsub", ["keyword1", "keyword2"])
        mock_x.assert_called_once_with(["keywordA", "keywordB"])

        # raw_content was actually written (one doc per source) before analysis
        # could succeed, since analyze_raw_content reads it back by id.
        self.assertEqual(len(raw_content_store), 3)

        insight_writes_run1 = [
            call.args[0] for call in collection_mocks['insights'].document.return_value.set.call_args_list
        ]
        self.assertEqual(len(insight_writes_run1), 3)
        for insight in insight_writes_run1:
            self.assertEqual(insight['prompt_version'], 1)
            self.assertEqual(insight['embedding'], [0.1, 0.2, 0.3])
            self.assertIn('raw_content_id', insight)
            self.assertIn('source_type', insight)
            self.assertTrue(insight['raw_content_id'] in raw_content_store)

        first_run_hashes = [call.args[0] for call in collection_mocks['insights'].document.call_args_list]
        self.assertEqual(len(set(first_run_hashes)), 3)  # distinct per insight

        status2, columns2, _ = scraper_logic.run_scraper_analysis("fake-api-key", "pain_points", sites_str)
        self.assertEqual(status2, "success")

        second_run_hashes = [call.args[0] for call in collection_mocks['insights'].document.call_args_list]
        # First 3 calls from run 1 are still in the list; the new 3 should match them exactly.
        self.assertEqual(second_run_hashes[3:], first_run_hashes)  # stable content_hash across reruns
        self.assertEqual(len(raw_content_store), 3)  # raw_content stayed deduped, not doubled

    def test_new_prompt_goals_registered_with_extra_schema_fields(self):
        for goal in ('willingness_to_pay_signals', 'tool_switching_signals'):
            self.assertIn(goal, scraper_logic.PROMPT_LIBRARY)
            self.assertEqual(scraper_logic.PROMPT_LIBRARY[goal]['version'], 1)

        wtp_columns = scraper_logic.PROMPT_LIBRARY['willingness_to_pay_signals']['columns']
        schema = scraper_logic._build_response_schema(wtp_columns)
        self.assertIn('estimated_wtp_tier', schema['items']['properties'])
        self.assertIn('estimated_wtp_tier', schema['items']['required'])
        self.assertNotIn('source_url', schema['items']['properties'])

        switching_columns = scraper_logic.PROMPT_LIBRARY['tool_switching_signals']['columns']
        schema = scraper_logic._build_response_schema(switching_columns)
        for field in ('from_tool', 'to_tool', 'reason'):
            self.assertIn(field, schema['items']['properties'])
            self.assertIn(field, schema['items']['required'])

    @patch('scraper_logic.firestore')
    @patch('scraper_logic.generate_embedding')
    @patch('sources.web.scrape_website_text')
    @patch('scraper_logic.extract_info_with_gemini')
    @patch('scraper_logic.genai')
    def test_willingness_to_pay_signals_end_to_end(
        self, mock_genai, mock_extract, mock_scrape, mock_embed, mock_firestore
    ):
        mock_scrape.return_value = "someone should build a route inventory tool, I'd pay $100/mo for it"
        mock_embed.return_value = [0.1, 0.2, 0.3]
        mock_extract.return_value = (
            '[{"insight": "wants a route inventory tool", "category": "Inventory", '
            '"quote": "someone should build a route inventory tool", '
            '"estimated_wtp_tier": "mid_50_to_500"}]'
        )

        mock_db = MagicMock()
        mock_firestore.Client.return_value = mock_db
        mock_firestore.SERVER_TIMESTAMP = "SERVER_TIMESTAMP"

        raw_content_store = {}
        collection_mocks = {}

        def raw_content_document_side_effect(doc_id):
            doc_ref = MagicMock()
            doc_ref.set.side_effect = lambda data, merge=True: raw_content_store.__setitem__(doc_id, data)

            def get_side_effect():
                snap = MagicMock()
                stored = raw_content_store.get(doc_id)
                snap.exists = stored is not None
                snap.to_dict.return_value = stored
                return snap
            doc_ref.get.side_effect = get_side_effect
            return doc_ref

        def collection_side_effect(name):
            if name not in collection_mocks:
                collection_mocks[name] = MagicMock()
                if name == 'raw_content':
                    collection_mocks[name].document.side_effect = raw_content_document_side_effect
            return collection_mocks[name]

        mock_db.collection.side_effect = collection_side_effect

        status, columns, _ = scraper_logic.run_scraper_analysis(
            "fake-api-key", "willingness_to_pay_signals", "https://example.com/post"
        )

        self.assertEqual(status, "success")
        column_ids = {c['id'] for c in columns}
        self.assertIn('estimated_wtp_tier', column_ids)

        written = collection_mocks['insights'].document.return_value.set.call_args[0][0]
        self.assertEqual(written['estimated_wtp_tier'], 'mid_50_to_500')

        # The schema passed to Gemini for this goal must include the extra field,
        # not just the generic insight/category/quote triple.
        schema_arg = mock_extract.call_args[0][2]
        self.assertIn('estimated_wtp_tier', schema_arg['items']['properties'])


if __name__ == '__main__':
    unittest.main()
