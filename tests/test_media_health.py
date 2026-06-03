from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from app.main import main as app_main


class MediaHealthTests(unittest.TestCase):
    def test_no_secrets_printed_in_media_health(self) -> None:
        with patch.dict("os.environ", {"PEXELS_API_KEY": "secret_pexels_value"}, clear=False):
            stream = io.StringIO()
            with redirect_stdout(stream):
                result = app_main(["media-health"])

        output = stream.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("media_health_passed:", output)
        self.assertIn("secrets_printed: false", output)
        self.assertNotIn("secret_pexels_value", output)


if __name__ == "__main__":
    unittest.main()
