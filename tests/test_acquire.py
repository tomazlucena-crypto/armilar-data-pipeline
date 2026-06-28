import unittest

from armilar_pipeline.acquire import add_query


class AcquireTests(unittest.TestCase):
    def test_add_query_preserves_existing_parameters(self):
        url = add_query("https://example.test/data?format=json", page=2, per_page=5000)
        self.assertIn("format=json", url)
        self.assertIn("page=2", url)
        self.assertIn("per_page=5000", url)


if __name__ == "__main__":
    unittest.main()
