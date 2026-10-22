from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from fpl_lab.api import APIError

APP = str(Path(__file__).resolve().parents[1] / "appfantasy.py")


class AppTests(unittest.TestCase):
    def app(self):
        at = AppTest.from_file(APP, default_timeout=45)
        at.session_state["demo_mode"] = True
        at.run()
        self.assertEqual(len(at.exception), 0)
        return at

    def test_comparison_and_head_to_head(self):
        at = self.app()
        self.assertTrue(any("DEMO MODE" in str(w.value) for w in at.warning))
        self.assertGreater(len(at.dataframe), 0)
        select = next(m for m in at.multiselect if m.label == "Choose up to four players")
        select.set_value([1, 2]).run()
        self.assertEqual(len(at.exception), 0)
        self.assertGreaterEqual(len(at.dataframe), 2)

    def test_build_and_display_squad(self):
        at = self.app()
        next(b for b in at.button if b.label == "Open Build a squad").click().run()
        next(b for b in at.button if b.label == "Generate best projected squad").click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.error), 0)
        self.assertGreaterEqual(len(at.metric), 4)
        self.assertEqual(len(at.session_state["build_result"][1].squad), 15)

    def test_transfer_screen_with_manual_squad(self):
        at = self.app()
        next(b for b in at.button if b.label == "Open Build a squad").click().run()
        next(b for b in at.button if b.label == "Generate best projected squad").click().run()
        ids = at.session_state["build_result"][1].squad.id.tolist()
        next(b for b in at.button if b.label == "Open Improve my team").click().run()
        next(m for m in at.multiselect if m.label == "Your current 15 players").set_value(ids).run()
        self.assertEqual(len(at.exception), 0)
        next(c for c in at.checkbox if c.key == "confirm_prices").check().run()
        next(b for b in at.button if b.label == "Suggest transfers").click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.error), 0)
        self.assertGreaterEqual(len(at.metric), 4)

    def test_methodology_screen(self):
        at = self.app()
        next(b for b in at.button if b.label == "Open Data & methodology").click().run()
        self.assertEqual(len(at.exception), 0)

    def test_home_workspace_cards_replace_sidebar_navigation(self):
        at = self.app()
        self.assertFalse(any(text.label == "Cover picture URL" for text in at.text_input))
        self.assertEqual(len(at.sidebar.radio), 0)
        self.assertTrue(any(button.label == "Open Compare players" for button in at.button))
        next(button for button in at.button if button.label == "Open Build a squad").click().run()
        self.assertEqual(at.session_state["workspace"], "Build a squad")
        self.assertEqual(len(at.exception), 0)

    def test_imported_team_is_visualized(self):
        from fpl_lab.demo import load_demo_data

        demo = load_demo_data()
        live_data = {**demo, "demo": False}
        with patch("fpl_lab.api.load_live_data", return_value=live_data), \
                patch("fpl_lab.api.load_entry") as load_entry:
            at = self.app()
            next(button for button in at.button if button.label == "Open Build a squad").click().run()
            next(button for button in at.button if button.label == "Generate best projected squad").click().run()
            ids = at.session_state["build_result"][1].squad.id.tolist()
            load_entry.return_value = {"picks": [{"element": pid} for pid in ids]}
            next(button for button in at.button if button.label == "Open Improve my team").click().run()
            next(toggle for toggle in at.toggle if toggle.key == "demo_mode").set_value(False).run()
            next(button for button in at.button if button.label == "Import published squad").click().run()
            self.assertEqual(len(at.exception), 0)
            self.assertIn("imported_lineup", at.session_state)
            self.assertEqual(len(at.session_state["imported_lineup"][1].squad), 15)
            self.assertTrue(any("Your imported team" in str(item.value) for item in at.markdown))

    def test_live_failure_has_actionable_error(self):
        import streamlit as st
        st.cache_data.clear()
        with patch("fpl_lab.api.load_live_data", side_effect=APIError("Test network unavailable")):
            at = AppTest.from_file(APP).run()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("Test network unavailable" in e.value for e in at.error))


if __name__ == "__main__":
    unittest.main()
