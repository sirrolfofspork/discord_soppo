import unittest
from pathlib import Path


class SystemPromptTests(unittest.TestCase):
    def test_system_prompt_contains_compact_soppo_runtime_anchors(self):
        from prompts import build_system_prompt

        prompt = build_system_prompt()

        expected_phrases = [
            "M4 SOPMOD II",
            "not a generic assistant",
            "tactically competent",
            "technically curious",
            "high-energy, mischievous",
            "short Discord-friendly replies",
            "do not become",
            "technical help",
            "safe, legal",
        ]
        for phrase in expected_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, prompt)

    def test_system_prompt_keeps_skk_specific_romance_out_of_global_prompt(self):
        from prompts import build_system_prompt

        prompt = build_system_prompt().lower()

        forbidden_global_terms = [
            "wife",
            "husband",
            "spouse",
            "soulmate",
            "chosen partner",
            "mo chroí",
            "mo ghrá",
            "mo chéadsearc",
        ]
        for term in forbidden_global_terms:
            with self.subTest(term=term):
                self.assertNotIn(term, prompt)

    def test_system_prompt_stays_discord_compact(self):
        from prompts import build_system_prompt

        prompt = build_system_prompt()

        self.assertLess(len(prompt), 5000)
        self.assertIn("usually 1 to 3 sentences", prompt)


class UserProfilePromptSeparationTests(unittest.TestCase):
    def test_skk_specific_affection_lives_in_user_profile(self):
        from user_profiles import load_user_profiles

        profiles = load_user_profiles(Path(__file__).resolve().parents[1] / "user_profiles.json")
        skk = profiles["717449407573786655"]
        notes_text = "\n".join(str(note) for note in skk.get("notes", []))
        combined = f"{skk.get('relationship', '')}\n{notes_text}".lower()

        self.assertIn("spouse", combined)
        self.assertIn("guardian", combined)
        self.assertIn("emotional anchor", combined)
        self.assertIn("gaelic", combined)


if __name__ == "__main__":
    unittest.main()
